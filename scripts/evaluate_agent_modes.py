"""Small reproducible comparison using isolated business data and real Gemini calls."""
import asyncio,json,sys,tempfile,time,gc
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import db
from backend.agent_scenarios import seed
from backend.services import agents,agent_data as data

async def evaluate():
    results=[]
    original=db.DB
    for case,budget in [('presupuesto',5000),('ofertas',25000),('vencidas',25000)]:
        for mode in ['reglas','un_agente','multiagente']:
            with tempfile.TemporaryDirectory(prefix='agent-controls-eval-',dir=db.ROOT/'.tmp') as folder:
                db.DB=Path(folder)/'control.db'
                seed()
                if case=='vencidas':
                    with db.transaction() as c:c.execute("UPDATE supplier_offers SET valid_until='2000-01-01'")
                rid=data.create_run(data.RunInput(kind='reposicion',budget_cents=budget,product_limit=5,request_key=f'evaluation-{case}-{mode}'),1,agents.model_name())
                run=agents.claim();started=time.monotonic();error=''
                try:
                    if mode=='multiagente':
                        await asyncio.wait_for(agents.execute(run),360)
                    else:
                        state={'quality':data.quality('reposicion'),'inventory':data.candidates(5)}
                        state['plan']=data.purchase_plan(state['inventory'],'costo',budget,True)
                        if mode=='un_agente':
                            dossier={**data.model_view(state['plan']),'quality':state['quality'],'inventory':data.model_view(state['inventory'])}
                            decision=await agents.ask('compras',run,[],{'ofertas':dossier,'demanda':data.demand()})
                            if decision.action!='finish' or decision.decision!='continuar':state['blocked_reason']=decision.message or 'Revisión pendiente'
                            if decision.selections:
                                state['plan']=data.purchase_plan(state['inventory'],'costo',budget,True,{v.product_id:v.offer_id for v in decision.selections})
                            state['explanation']=decision.message
                        state['audit']=data.audit_result(run,state)
                        agents.finish(run,'revision' if state['audit']['passed'] and not state.get('blocked_reason') else 'bloqueada',state)
                except Exception as exc:
                    error=type(exc).__name__
                    agents.finish(run,'error',{'error_type':error})
                result=data.get_run(rid);plan=result['result'].get('plan',{})
                criteria={'estado_esperado':result['status']==('bloqueada' if case=='vencidas' else 'revision'),
                    'presupuesto':plan.get('total_cents',0)<=budget,
                    'ofertas_vigentes':all(l['source']=='manual' for l in plan.get('lines',[])) and (not plan.get('lines') if case=='vencidas' else bool(plan.get('lines')))}
                with db.connect() as c:criteria['sin_compras_automaticas']=c.execute('SELECT COUNT(*) FROM purchase_orders').fetchone()[0]==0
                results.append({'case':case,'mode':mode,'passed':all(criteria.values()),'criteria':criteria,
                    'status':result['status'],'calls':result['calls'],'tokens':result['tokens'],
                    'seconds':round(time.monotonic()-started,2),'total_cents':plan.get('total_cents',0),
                    'error':error,'evidence':result})
                print(f'{case} / {mode}: {result["status"]}',flush=True)
                c.close();db.DB=original;gc.collect()
    output={'created_at':db.now(),'model':agents.model_name(),'repetitions':1,'real_provider_calls':True,
        'note':'Evaluación exploratoria con tres casos académicos aislados y una repetición por modalidad. Los criterios verifican validez operativa, no calidad completa del razonamiento ni superioridad estadística. Las tres modalidades usan los mismos cálculos y controles Python.',
        'results':results}
    path=db.ROOT/'artifacts/agent-mode-evaluation.json'
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    release=db.ROOT/'ml/evaluations/agents/mode-comparison.json'
    release.parent.mkdir(parents=True,exist_ok=True)
    release.write_text(json.dumps({**output,'results':[
        {key:value for key,value in result.items() if key!='evidence'} for result in results
    ]},ensure_ascii=False,indent=2),encoding='utf-8')
    print(str(path),flush=True)

if __name__=='__main__':asyncio.run(evaluate())
