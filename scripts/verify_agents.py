"""Focused checks for agent permissions, evidence and purchase safety; isolated SQLite."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, AsyncMock
import sys
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import db
from backend.services import agent_data as data, agents, suppliers

class AgentChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.original=db.DB
        agents._next_provider_call=0.0
        db.DB=Path(self.tmp.name)/'agents.db'
        db.init_db(); data.init()
        with db.transaction() as c:
            for uid,role in [(1,'admin'),(2,'empleado'),(3,'cliente')]:
                c.execute('INSERT INTO users(id,name,email,password_hash,role,consent_at,created_at) VALUES(?,?,?,?,?,?,?)',
                          (uid,'Prueba',f'{role}@test.invalid','unused',role,db.now(),db.now()))
            c.execute("INSERT INTO categories(id,name,slug) VALUES(1,'Frenos','frenos')")
            c.execute("INSERT INTO brands(id,name) VALUES(1,'Prueba')")
            for sid in [1,2]:
                c.execute('INSERT INTO suppliers(id,name,ruc,email,phone) VALUES(?,?,?,?,?)',(sid,f'Proveedor {sid}','', '', ''))
            for pid in [1,2]:
                c.execute('''INSERT INTO products(id,sku,name,brand_id,category_id,price_cents,cost_cents,stock,minimum,created_at)
                    VALUES(?,?,?,1,1,2000,1000,0,5,?)''',(pid,f'CHECK-{pid}',f'Producto de prueba {pid}',db.now()))
                c.execute("INSERT INTO product_images(product_id,url,thumb) VALUES(?,'/media/test.webp','/media/test.webp')",(pid,))
                c.execute('INSERT INTO inventory_policy(product_id,location,maximum,lead_days,pack_size,supplier_id,updated_at) VALUES(?,?,20,3,1,?,?)',
                          (pid,'A1',pid,db.now()))
        data.import_references(1)

    def tearDown(self):
        db.DB=self.original
        # SQLite context managers commit but do not close; temporary files are GC'd before cleanup on Windows.
        import gc
        gc.collect()
        self.tmp.cleanup()

    def proposal(self,budget=50000):
        rid=data.create_run(data.RunInput(kind='reposicion',budget_cents=budget,request_key='test-proposal-key'),1,'test')
        stock=data.candidates(12)
        plan=data.purchase_plan(stock,'costo',budget,True)
        result={'inventory':stock,'plan':plan,'audit':{'passed':True}}
        with db.transaction() as c:
            c.execute("UPDATE agent_runs SET status='revision',result=?,finished_at=? WHERE id=?",(data.dump(result),db.now(),rid))
        return rid

    def test_purchase_approval_is_atomic_and_idempotent(self):
        rid=self.proposal()
        ids=data.approve(rid,1,True)
        self.assertEqual(len(ids),2)
        self.assertEqual(data.approve(rid,1,True),ids)
        with db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],2)
            self.assertEqual(c.execute('SELECT SUM(stock) FROM products').fetchone()[0],0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM purchase_orders WHERE actor='agente'").fetchone()[0],2)

    def test_changed_stock_blocks_entire_approval(self):
        rid=self.proposal()
        with db.transaction() as c: c.execute('UPDATE products SET stock=1 WHERE id=2')
        with self.assertRaisesRegex(ValueError,'cambiaron'): data.approve(rid,1,True)
        with db.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)

    def test_second_supplier_failure_rolls_back_every_purchase(self):
        rid=self.proposal(); original=suppliers.crear_orden_compra
        def fail_second(sid,*a,**kw):
            if sid==2: raise ValueError('Proveedor de prueba no disponible')
            return original(sid,*a,**kw)
        with patch.object(suppliers,'crear_orden_compra',side_effect=fail_second):
            with self.assertRaises(ValueError):data.approve(rid,1,True)
        with db.connect() as c: self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)
        self.assertEqual(data.get_run(rid)['status'],'revision')

    def test_references_require_explicit_acknowledgement(self):
        with self.assertRaisesRegex(ValueError,'académico'):data.approve(self.proposal(),1)

    def test_employees_cannot_approve_or_change_offers(self):
        rid=self.proposal()
        for uid in [2,3]:
            with self.assertRaisesRegex(ValueError,'administradora'):data.approve(rid,uid,True)
            with self.assertRaises(ValueError):data.import_references(uid)

    def test_budget_and_existing_incoming(self):
        suppliers.crear_orden_compra(1,[{'product_id':1,'quantity':20,'cost_cents':1000}],1)
        stock=data.candidates(12)
        self.assertEqual([p['id'] for p in stock['items']],[2])
        plan=data.purchase_plan(stock,'costo',5000,True)
        self.assertEqual(plan['total_cents'],5000)
        self.assertEqual(plan['lines'][0]['quantity'],5)

    def test_mid_analysis_changes_are_rejected(self):
        stock=data.candidates(12)
        with db.transaction() as c: c.execute('UPDATE products SET reserved=0,stock=3 WHERE id=1')
        with self.assertRaisesRegex(ValueError,'inventario cambió'):data.purchase_plan(stock,'costo',50000)

    def test_expired_offer_blocks_purchase(self):
        rid=self.proposal()
        with db.transaction() as c: c.execute("UPDATE supplier_offers SET valid_until='2000-01-01'")
        with self.assertRaises(ValueError):data.approve(rid,1,True)

    def test_manual_offer_survives_reference_import(self):
        data.save_offer(data.OfferInput(product_id=1,supplier_id=1,cost_cents=900,lead_days=2,pack_size=2,minimum_quantity=4,valid_until='2099-12-31'),1)
        data.import_references(1)
        with db.connect() as c:
            offer=db.one(c,'SELECT * FROM supplier_offers WHERE product_id=1 AND supplier_id=1')
        self.assertEqual((offer['source'],offer['cost_cents']),('manual',900))

    def test_queue_claim_is_exclusive(self):
        for n in range(2):data.create_run(data.RunInput(kind='pedidos',request_key=f'queue-unique-key-{n}'),1,'test')
        self.assertIsNotNone(agents.claim())
        self.assertIsNone(agents.claim())

    def test_no_forecast_does_not_invent_ml(self):
        stock=data.candidates(12)
        self.assertFalse(stock['demand']['usable'])
        self.assertTrue(all(p['basis']=='politica' and p['forecast_units'] is None for p in stock['items']))

    def test_cancelled_proposal_cannot_be_approved(self):
        rid=self.proposal(); data.cancel(rid,1)
        with self.assertRaises(ValueError):data.approve(rid,1,True)

    def test_end_to_end_agents_request_budget_revision(self):
        async def fake_ask(role,run,messages,evidence,forced_strategy=None):
            tool=agents.TOOLS[role][0]
            if tool not in evidence:return agents.Decision(action='tool',tool=tool)
            decision='revisar' if role=='finanzas' and evidence[tool].get('over_budget') else 'continuar'
            return agents.Decision(action='finish',message=f'{role}: evidencia revisada.',decision=decision)
        rid=data.create_run(data.RunInput(kind='reposicion',budget_cents=5000,request_key='workflow-test-key'),1,'test')
        run=agents.claim()
        with patch.object(agents,'ask',side_effect=fake_ask):asyncio.run(agents.execute(run))
        result=data.get_run(rid)
        self.assertEqual(result['status'],'revision')
        self.assertLessEqual(result['result']['plan']['total_cents'],5000)
        self.assertTrue(any(s['kind']=='revision' and s['target']=='compras' for s in result['steps']))
        self.assertEqual({s['agent'] for s in result['steps']},{'orquestador','calidad','inventario','compras','finanzas','auditor'})
        with db.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)

    def test_auditor_block_is_binding(self):
        async def fake_ask(role,run,messages,evidence,forced_strategy=None):
            tool=agents.TOOLS[role][0]
            if tool not in evidence:return agents.Decision(action='tool',tool=tool)
            return agents.Decision(action='finish',message='Revisión de prueba.',decision='bloquear' if role=='auditor' else 'continuar')
        rid=data.create_run(data.RunInput(kind='reposicion',request_key='auditor-block-key'),1,'test')
        with patch.object(agents,'ask',side_effect=fake_ask):asyncio.run(agents.execute(agents.claim()))
        self.assertEqual(data.get_run(rid)['status'],'bloqueada')
        with self.assertRaises(ValueError):data.approve(rid,1,True)

    def test_provider_fallback_after_temporary_failure_without_writes(self):
        rid=data.create_run(data.RunInput(kind='pedidos',request_key='provider-retry-key'),1,'test')
        run=agents.claim()
        req=httpx.Request('POST','https://generativelanguage.googleapis.com')
        message={'action':'tool','tool':'contexto','message':'Consultar contexto','decision':'continuar','strategy':'costo','agents':[]}
        response={'choices':[{'message':{'content':json.dumps(message)}}], 'usage':{'total_tokens':42}}
        fake=AsyncMock()
        fake.__aenter__.return_value=fake
        fake.post.side_effect=[httpx.Response(503,request=req),httpx.Response(200,json=response,request=req)]
        with patch.object(agents.httpx,'AsyncClient',return_value=fake), \
             patch.object(agents.llm_provider,'provider_config',return_value=('gemini','gemini-3.1-flash-lite','test-only-key')), \
             patch.object(agents.llm_provider,'env_value',side_effect=lambda key: {'LLM_FALLBACK_PROVIDER':'thehive','THEHIVE_API_KEY':'fallback-key'}.get(key,'')):
            result=asyncio.run(agents.ask('orquestador',run,[],{}))
        self.assertEqual(result.tool,'contexto')
        self.assertEqual(fake.post.call_count,2)
        self.assertEqual(data.get_run(rid)['calls'],1)
        with db.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)

    def test_auditor_schema_requires_conclusion_after_evidence(self):
        data.create_run(data.RunInput(kind='pedidos',request_key='auditor-schema-key'),1,'test')
        run=agents.claim()
        decision=agents.Decision(action='finish',tool='ninguna',message='Controles superados.')
        response={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':decision.model_dump_json()}]}}]}
        fake=AsyncMock();fake.__aenter__.return_value=fake
        fake.post.return_value=httpx.Response(200,json=response,request=httpx.Request('POST','https://generativelanguage.googleapis.com'))
        with patch.object(agents.httpx,'AsyncClient',return_value=fake), \
             patch.object(agents.llm_provider,'provider_config',return_value=('gemini','gemini-3.1-flash-lite','test-only-key')), \
             patch.object(agents.llm_provider,'env_value',return_value=''):
            result=asyncio.run(agents.ask('auditor',run,[],{'auditoria':{'passed':True}}))
        properties=fake.post.call_args.kwargs['json']['generationConfig']['responseSchema']['properties']
        self.assertEqual(properties['action']['enum'],['finish'])
        self.assertEqual(properties['tool']['enum'],['ninguna'])
        self.assertEqual(result.action,'finish')

    def test_resume_keeps_completed_agents_and_audits_current_stock(self):
        seen=[]
        fail=True
        async def fake_ask(role,run,messages,evidence,forced_strategy=None):
            nonlocal fail
            seen.append(role)
            if role=='auditor' and fail:
                fail=False
                raise agents.ProviderUnavailable('Proveedor de prueba interrumpido')
            tool=agents.TOOLS[role][0]
            if tool not in evidence:return agents.Decision(action='tool',tool=tool)
            return agents.Decision(action='finish',message='Evidencia revisada.',decision='continuar')
        rid=data.create_run(data.RunInput(kind='reposicion',request_key='resume-checkpoint-key'),1,'test')
        with patch.object(agents,'ask',side_effect=fake_ask):
            with self.assertRaises(agents.ProviderUnavailable):asyncio.run(agents.execute(agents.claim()))
            with db.transaction() as c:
                c.execute("UPDATE agent_runs SET status='error' WHERE id=?",(rid,))
                c.execute('UPDATE products SET stock=1 WHERE id=1')
            self.assertTrue(data.get_run(rid)['can_resume'])
            calls_before=seen.count('compras')
            data.resume(rid,1)
            asyncio.run(agents.execute(agents.claim()))
        self.assertEqual(seen.count('compras'),calls_before)
        self.assertEqual(data.get_run(rid)['status'],'bloqueada')
        with self.assertRaises(ValueError):data.approve(rid,1,True)

    def test_daily_review_catches_up_once_and_respects_owner(self):
        from backend.services import agent_schedule as schedule
        self.assertFalse(schedule.get()['enabled'])
        with patch.object(schedule,'now',return_value='2026-10-21T18:00:00-05:00'),patch('backend.services.assistant._env_value',return_value='test-key'):
            schedule.save(schedule.ScheduleInput(enabled=True,at_time='09:00'),1)
            rid=schedule.tick('test')
            self.assertIsNotNone(rid)
            self.assertIsNone(schedule.tick('test'))
            self.assertEqual(schedule.get()['next_at'][:10],'2026-10-22')
        with db.transaction() as c:c.execute("UPDATE users SET role='empleado' WHERE id=1")
        with patch.object(schedule,'now',return_value='2026-10-22T18:00:00-05:00'):
            self.assertIsNone(schedule.tick('test'))
            self.assertFalse(schedule.get()['enabled'])

    def test_controls_are_isolated_and_all_pass(self):
        from backend.services import agent_controls
        with db.connect() as c:before=tuple(c.execute('SELECT SUM(stock),SUM(reserved) FROM products').fetchone())
        result=agent_controls.run(1)['result']
        self.assertFalse(result['uses_llm'])
        self.assertEqual(len(result['cases']),3)
        self.assertTrue(all(case['passed'] for case in result['cases']),result)
        with db.connect() as c:
            self.assertEqual(tuple(c.execute('SELECT SUM(stock),SUM(reserved) FROM products').fetchone()),before)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)

    def test_offer_choice_cannot_escape_available_candidates(self):
        stock=data.candidates(12)
        with self.assertRaises(ValueError):data.purchase_plan(stock,'costo',50000,selections={999:1})
        with self.assertRaises(ValueError):data.purchase_plan(stock,'costo',50000,selections={1:999999})

    def test_offer_comparison_and_uncovered_needs(self):
        for sid,cost,lead in [(1,1000,5),(2,1100,2)]:
            data.save_offer(data.OfferInput(product_id=1,supplier_id=sid,cost_cents=cost,lead_days=lead,pack_size=1,minimum_quantity=1,valid_until='2099-01-01'),1)
        stock=data.candidates(12)
        cost=data.purchase_plan(stock,'costo',50000)
        fast=data.purchase_plan(stock,'rapidez',50000)
        self.assertEqual(cost['lines'][0]['supplier_id'],1)
        self.assertEqual(fast['lines'][0]['supplier_id'],2)
        self.assertEqual(cost['lines'][0]['alternatives'],2)
        partial=data.purchase_plan(stock,'costo',5000,True)
        self.assertEqual(partial['comparison']['uncovered_units'],35)
        self.assertEqual(partial['lines'][0]['quantity'],5)

    def test_followup_tracks_partial_receipt_cancellation_and_stock(self):
        from backend.services.agent_followup import followup
        rid=self.proposal(); orders=data.approve(rid,1,True)
        with db.connect() as c:item=dict(c.execute('SELECT * FROM purchase_items WHERE purchase_order_id=?',(orders[0],)).fetchone())
        receipt={'request_key':'receipt-followup-test','items':[{'id':item['id'],'quantity':3}]}
        suppliers.receive(orders[0],1,receipt)
        suppliers.receive(orders[0],1,receipt)
        suppliers.cancel_pending(orders[0],1,'Cancelar saldo de control')
        suppliers.receive(orders[1],1)
        result=followup(data.get_run(rid))
        self.assertEqual(result['received'],23)
        self.assertEqual(result['pending'],0)
        self.assertEqual(result['cancelled'],17)
        self.assertEqual(result['received_cost_cents'],23000)
        self.assertEqual(sum(p['stock'] for p in result['products']),23)

    def test_current_ml_evidence_drives_target(self):
        # Verify the integration at its forecast read boundary, retaining inventory calculations.
        original=data.rows
        def forecast_rows(c,sql,args=()):
            if 'FROM ml_predictions' in sql:return [{'product_id':1,'prediction':40,'review':0}]
            return original(c,sql,args)
        evidence={'usable':True,'operational_run':{'id':99},'horizon_days':7,'note':'Control aislado'}
        with patch.object(data,'demand',return_value=evidence),patch.object(data,'rows',side_effect=forecast_rows):
            result=data.candidates(5)
        first=next(p for p in result['items'] if p['id']==1)
        self.assertEqual(first['basis'],'ml_operativo')
        self.assertEqual(first['needed'],40)

    def test_http_roles_are_enforced(self):
        from fastapi.testclient import TestClient
        from backend.app import app,current_user
        try:
            client=TestClient(app,raise_server_exceptions=True)
            try:
                for role,expected in [('cliente',403),('empleado',403),('admin',200)]:
                    app.dependency_overrides[current_user]=lambda r=role:{'id':1,'role':r}
                    self.assertEqual(client.get('/api/admin/agents/runs').status_code,expected)
                    self.assertEqual(client.get('/api/admin/agents/schedule').status_code,expected)
                    self.assertEqual(client.get('/api/admin/agents/controls').status_code,expected)
                    if role!='admin':
                        self.assertEqual(client.post('/api/admin/agents/controls',json={}).status_code,403)
                        self.assertEqual(client.put('/api/admin/agents/schedule',json={'enabled':True}).status_code,403)
                        self.assertEqual(client.post('/api/admin/agents/offers/references').status_code,403)
                with patch.object(agents,'status',return_value={'configured':True}):
                    body={'kind':'pedidos','budget_cents':10000,'product_limit':5,'request_key':'http-valid-request'}
                    response=client.post('/api/admin/agents/runs',json=body)
                    self.assertEqual(response.status_code,200)
                    self.assertEqual(client.post('/api/admin/agents/runs',json=body).json()['id'],response.json()['id'])
                    self.assertEqual(client.post('/api/admin/agents/runs',json={**body,'budget_cents':1.5}).status_code,422)
                app.dependency_overrides[current_user]=lambda:None
                self.assertEqual(client.get('/api/admin/agents/status').status_code,401)
            finally:client.close()
        finally:app.dependency_overrides.clear()

    def test_unresolved_review_blocks_and_auditor_receives_evidence(self):
        seen=[]
        async def fake(role,run,messages,evidence,forced_strategy=None):
            if role=='auditor':seen.append(evidence['auditoria'])
            return agents.Decision(action='finish',message='Hace falta comprobar datos.',decision='revisar' if role=='calidad' else 'continuar')
        rid=data.create_run(data.RunInput(kind='reposicion',request_key='unresolved-review-check'),1,'test')
        with patch.object(agents,'ask',side_effect=fake):asyncio.run(agents.execute(agents.claim()))
        result=data.get_run(rid)
        self.assertEqual(result['status'],'bloqueada')
        self.assertIn('calidad_correccion',result['result']['decisions'])
        self.assertIn('quality',seen[0]['expediente'])
        self.assertFalse(seen[0]['passed'])

    def test_delivery_risk_does_not_invent_demand_or_incoming_arrivals(self):
        p={'available':3,'sold_30':30,'incoming':100}
        risk=data.delivery_risk(p,7)
        self.assertEqual(risk['coverage_days'],3)
        self.assertEqual(risk['uncovered_wait_days'],4)
        self.assertEqual(risk['level'],'espera_con_riesgo')
        self.assertIsNone(data.delivery_risk({**p,'sold_30':0},7)['coverage_days'])

    def test_dominated_offer_requires_explanation_and_auditor_sees_it(self):
        for sid,cost,lead in [(1,900,2),(2,1100,5)]:
            data.save_offer(data.OfferInput(product_id=1,supplier_id=sid,cost_cents=cost,lead_days=lead,pack_size=1,minimum_quantity=1,valid_until='2099-01-01'),1)
        with db.connect() as c:offer=c.execute('SELECT id FROM supplier_offers WHERE product_id=1 AND supplier_id=2').fetchone()[0]
        plan=data.purchase_plan(data.candidates(12),'costo',50000,selections={1:offer})
        self.assertTrue(any(w['kind']=='alternativa_superior' for w in plan['warnings']))
        run={'kind':'reposicion','budget_cents':50000}
        self.assertFalse(data.audit_result(run,{'plan':plan})['passed'])
        plan['lines'][0]['agent_reason']='Excepción que debe revisar el administrador.'
        self.assertTrue(data.audit_result(run,{'plan':plan})['passed'])

    def test_ml_horizon_cannot_be_extrapolated_by_selecting_slow_supplier(self):
        stock=data.candidates(12)
        stock['items'][0]['basis']='ml_operativo'
        stock['demand']['horizon_days']=7
        with db.transaction() as c:c.execute('UPDATE supplier_offers SET lead_days=10 WHERE product_id=1')
        plan=data.purchase_plan(stock,'costo',50000)
        self.assertNotIn(1,[line['product_id'] for line in plan['lines']])
        self.assertIn('horizonte',plan['excluded'][0]['options'][0]['reason'])

    def test_finance_block_never_triggers_budget_retry(self):
        visits=[]
        async def fake(role,run,messages,evidence,forced_strategy=None):
            visits.append(role)
            return agents.Decision(action='finish',message='Requiere intervención.' if role=='finanzas' else 'Evidencia revisada.',decision='bloquear' if role=='finanzas' else 'continuar')
        rid=data.create_run(data.RunInput(kind='reposicion',budget_cents=1000,request_key='hard-finance-block-test'),1,'test')
        with patch.object(agents,'ask',side_effect=fake):asyncio.run(agents.execute(agents.claim()))
        result=data.get_run(rid)
        self.assertEqual(result['status'],'bloqueada')
        self.assertEqual(visits.count('compras'),1)
        self.assertNotIn('compras_revision',result['result']['decisions'])

    def test_resolved_review_records_reason_for_auditor(self):
        calls={};seen=[]
        async def fake(role,run,messages,evidence,forced_strategy=None):
            calls[role]=calls.get(role,0)+1
            if role=='auditor':seen.append(evidence['auditoria']['expediente'])
            return agents.Decision(action='finish',message='Revisar origen.' if role=='calidad' and calls[role]==1 else 'Origen comprobado.',decision='revisar' if role=='calidad' and calls[role]==1 else 'continuar')
        rid=data.create_run(data.RunInput(kind='reposicion',request_key='resolved-review-evidence'),1,'test')
        with patch.object(agents,'ask',side_effect=fake):asyncio.run(agents.execute(agents.claim()))
        self.assertEqual(data.get_run(rid)['status'],'revision')
        self.assertTrue(seen[0]['review_log']['calidad']['resolved'])
        self.assertIn('compras',seen[0]['conclusions'])

    def test_purchasing_budget_review_changes_evidence_before_finance(self):
        totals=[]
        async def fake(role,run,messages,evidence,forced_strategy=None):
            over=False
            if role=='compras':
                total=evidence['ofertas']['total_cents'];totals.append(total)
                over=total>run['budget_cents']
            return agents.Decision(action='finish',message='Ajustar presupuesto.' if over else 'Lotes revisados.',decision='revisar' if over else 'continuar')
        rid=data.create_run(data.RunInput(kind='reposicion',budget_cents=5000,request_key='purchasing-review-budget'),1,'test')
        with patch.object(agents,'ask',side_effect=fake):asyncio.run(agents.execute(agents.claim()))
        result=data.get_run(rid)
        self.assertEqual(result['status'],'revision')
        self.assertGreater(totals[0],5000)
        self.assertLessEqual(totals[1],5000)
        self.assertTrue(result['result']['review_log']['compras']['resolved'])

    def test_inventory_budget_review_reaches_purchasing_and_auditor(self):
        visits=[]
        async def fake(role,run,messages,evidence,forced_strategy=None):
            visits.append(role)
            over=role=='compras' and evidence['ofertas']['total_cents']>run['budget_cents']
            decision='revisar' if role=='inventario' or over else 'continuar'
            return agents.Decision(action='finish',message='Ajustar lote.' if decision=='revisar' else 'Comprobado.',decision=decision)
        rid=data.create_run(data.RunInput(kind='reposicion',budget_cents=5000,request_key='inventory-budget-handoff'),1,'test')
        with patch.object(agents,'ask',side_effect=fake):asyncio.run(agents.execute(agents.claim()))
        result=data.get_run(rid)
        self.assertEqual(result['status'],'revision')
        self.assertEqual(visits.count('inventario'),1)
        self.assertIn('compras',visits)
        self.assertIn('finanzas',visits)
        self.assertTrue(result['result']['review_log']['inventario']['resolved'])
        self.assertTrue(result['result']['audit']['passed'])

    def test_invalid_purchasing_selection_gets_bounded_correction(self):
        visits=[]
        async def fake(role,run,messages,evidence,forced_strategy=None):
            visits.append(role)
            selections=[agents.OfferChoice(product_id=999,offer_id=999,reason='Selección errónea de prueba.')] if role=='compras' and visits.count(role)==1 else []
            return agents.Decision(action='finish',message='Alternativas revisadas.',selections=selections)
        rid=data.create_run(data.RunInput(kind='reposicion',request_key='invalid-purchasing-retry'),1,'test')
        with patch.object(agents,'ask',side_effect=fake):asyncio.run(agents.execute(agents.claim()))
        result=data.get_run(rid)
        self.assertEqual(result['status'],'revision')
        self.assertEqual(visits.count('compras'),2)
        self.assertTrue(any(s['agent']=='compras' and s['kind']=='validacion' for s in result['steps']))
        self.assertIn('finanzas',visits)
        with db.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)

    def test_invalid_provider_decision_is_corrected_without_writes(self):
        visits=[]
        async def fake(role,run,messages,evidence,forced_strategy=None):
            visits.append(role)
            if role=='orquestador' and visits.count(role)==1:
                raise agents.InvalidDecision('La respuesta no cumple el formato permitido: message: string_too_long')
            return agents.Decision(action='finish',message='Evidencia revisada.',decision='continuar')
        rid=data.create_run(data.RunInput(kind='reposicion',request_key='invalid-provider-decision'),1,'test')
        with patch.object(agents,'ask',side_effect=fake):asyncio.run(agents.execute(agents.claim()))
        result=data.get_run(rid)
        self.assertEqual(result['status'],'revision')
        self.assertEqual(visits.count('orquestador'),2)
        self.assertTrue(any(s['agent']=='orquestador' and s['kind']=='validacion' for s in result['steps']))
        self.assertIn('finanzas',visits)
        self.assertIn('auditor',visits)
        with db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT SUM(stock) FROM products').fetchone()[0],0)

    def test_transient_provider_failure_retries_without_writes(self):
        visits=[]
        async def fake(role,run,messages,evidence,forced_strategy=None):
            visits.append(role)
            if role=='orquestador' and visits.count(role)==1:
                raise agents.ProviderTransient('Fallo temporal de lectura.')
            return agents.Decision(action='finish',message='Evidencia revisada.',decision='continuar')
        rid=data.create_run(data.RunInput(kind='reposicion',request_key='transient-provider-retry'),1,'test')
        with patch.object(agents,'ask',side_effect=fake):asyncio.run(agents.execute(agents.claim()))
        result=data.get_run(rid)
        self.assertEqual(result['status'],'revision')
        self.assertEqual(visits.count('orquestador'),2)
        self.assertTrue(any(s['agent']=='orquestador' and s['kind']=='proveedor' for s in result['steps']))
        self.assertIn('finanzas',visits)
        self.assertIn('auditor',visits)
        with db.connect() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)
            self.assertEqual(c.execute('SELECT SUM(stock) FROM products').fetchone()[0],0)

    def test_changed_evidence_during_purchasing_selection_does_not_retry(self):
        visits=[]
        async def fake(role,run,messages,evidence,forced_strategy=None):
            visits.append(role)
            if role=='compras':
                line=evidence['ofertas']['lines'][0]
                with db.transaction() as c:c.execute('UPDATE products SET stock=1 WHERE id=?',(line['product_id'],))
                selection=agents.OfferChoice(product_id=line['product_id'],offer_id=line['offer_id'],reason='Oferta del análisis.')
                return agents.Decision(action='finish',message='Oferta revisada.',selections=[selection])
            return agents.Decision(action='finish',message='Evidencia revisada.',decision='continuar')
        data.create_run(data.RunInput(kind='reposicion',request_key='changed-evidence-purchasing'),1,'test')
        with patch.object(agents,'ask',side_effect=fake):
            with self.assertRaises(data.EvidenceChanged):asyncio.run(agents.execute(agents.claim()))
        self.assertEqual(visits.count('compras'),1)
        self.assertNotIn('finanzas',visits)
        with db.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)

    def test_cancelled_elapsed_stops_at_cancellation(self):
        from backend.services import agent_followup
        rid=self.proposal();orders=data.approve(rid,1,True)
        suppliers.cancel_pending(orders[0],1,'Cancelación de prueba')
        before=agent_followup.followup(data.get_run(rid))['orders'][0]['elapsed_days']
        with patch.object(agent_followup,'now',return_value='2099-12-31T12:00:00-05:00'):
            after=agent_followup.followup(data.get_run(rid))['orders'][0]['elapsed_days']
        self.assertEqual(before,after)

    def test_presentation_is_admin_only_idempotent_and_single_pending(self):
        from backend.services import agent_presentation as presentation
        with patch.object(agents,'status',return_value={'configured':True}):
            for uid in [2,3]:
                with self.assertRaises(ValueError):presentation.start(uid,'presentation-role-test')
            first=presentation.start(1,'presentation-role-test')
            self.assertEqual(first,presentation.start(1,'presentation-role-test'))
            with self.assertRaisesRegex(ValueError,'pendiente'):presentation.start(1,'presentation-other-test')
        self.assertEqual(presentation.latest()['status'],'en_cola')
        with db.connect() as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0],0)

    def test_presentation_records_failed_case_instead_of_hiding_it(self):
        from backend.agent_presentation import case
        result=case('llm','Caso','Resultado esperado',{'gemini':False,'validacion':True},{},0.3)
        self.assertFalse(result['passed'])

    def test_presentation_worker_uses_fresh_database_and_keeps_failures(self):
        from backend.services import agent_presentation as presentation
        from unittest.mock import Mock
        with patch.object(agents,'status',return_value={'configured':True}):presentation.start(1,'presentation-isolation-test')
        process=Mock(returncode=0)
        process.communicate=AsyncMock(return_value=(b'{"cases":[{"passed":false}]}',b''))
        launch=AsyncMock(return_value=process)
        with patch.object(presentation.asyncio,'create_subprocess_exec',launch):
            self.assertTrue(asyncio.run(presentation.execute_next()))
        target=Path(launch.call_args.kwargs['env']['DATABASE_PATH'])
        self.assertNotEqual(target,db.DB)
        self.assertTrue(target.is_relative_to(db.ROOT/'.tmp'))
        result=presentation.latest()
        self.assertEqual(result['status'],'completada')
        self.assertFalse(result['result']['cases'][0]['passed'])

    def test_presentation_endpoint_requires_admin(self):
        from fastapi.testclient import TestClient
        from backend.app import app,current_user
        try:
            with TestClient(app) as client:
                for role in ['cliente','empleado']:
                    app.dependency_overrides[current_user]=lambda r=role:{'id':1,'role':r}
                    self.assertEqual(client.get('/api/admin/agents/presentation').status_code,403)
                    self.assertEqual(client.post('/api/admin/agents/presentation',json={'request_key':'presentation-role-http'}).status_code,403)
        finally:app.dependency_overrides.clear()

if __name__=='__main__':unittest.main(verbosity=2)
