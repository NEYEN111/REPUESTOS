"""Authoritative tools and durable proposals for the administrative agents."""
import hashlib
import json
import math
from datetime import datetime, timedelta, date
from pydantic import BaseModel, Field, ConfigDict
from typing import Literal
from backend.db import ROOT, connect, transaction, rows, one, now, audit, postgres_schema, is_postgres
from backend.services import operations, reports, predictions, catalog_quality, suppliers

ROLES = {
    'orquestador': ('Orquestador', 'Organiza el equipo y solicita revisiones.'),
    'calidad': ('Calidad de datos', 'Comprueba la evidencia y las inconsistencias.'),
    'demanda': ('Demanda ML', 'Interpreta el pronóstico y su vigencia.'),
    'inventario': ('Inventario', 'Calcula necesidades descontando compras pendientes.'),
    'compras': ('Compras y proveedores', 'Compara ofertas y prepara la reposición.'),
    'finanzas': ('Finanzas', 'Revisa presupuesto y margen comercial.'),
    'pedidos': ('Pedidos y envíos', 'Detecta atrasos y bloqueos de entrega.'),
    'auditor': ('Auditor', 'Verifica el resultado antes de presentarlo.'),
}
TEAMS = {
    'reposicion': ['calidad', 'demanda', 'inventario', 'compras', 'finanzas', 'auditor'],
    'catalogo': ['calidad', 'auditor'],
    'finanzas': ['calidad', 'finanzas', 'auditor'],
    'pedidos': ['calidad', 'inventario', 'pedidos', 'auditor'],
}

class RunInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['reposicion', 'catalogo', 'finanzas', 'pedidos']
    budget_cents: int = Field(default=200000, strict=True, ge=100, le=100000000)
    product_limit: int = Field(default=12, strict=True, ge=1, le=20)
    request_key: str = Field(min_length=12, max_length=100, pattern=r'^[a-zA-Z0-9_-]+$')

class OfferInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    product_id: int = Field(strict=True, gt=0)
    supplier_id: int = Field(strict=True, gt=0)
    cost_cents: int = Field(strict=True, gt=0, le=100000000)
    lead_days: int = Field(strict=True, ge=1, le=365)
    pack_size: int = Field(strict=True, ge=1, le=10000)
    minimum_quantity: int = Field(strict=True, ge=1, le=10000)
    valid_until: date

def dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

def model_view(value):
    """Supply exact display amounts so agents need not do monetary arithmetic."""
    if isinstance(value,list): return [model_view(v) for v in value]
    if not isinstance(value,dict): return value
    result={k:model_view(v) for k,v in value.items() if k!='fingerprint'}
    amounts={}
    for key, cents in value.items():
        if type(cents) is int and (key.endswith('_cents') or key in {'revenue','cost','profit'}):
            n=abs(cents)
            amounts[key]=f"{'-' if cents<0 else ''}S/ {n//100:,}.{n%100:02d}"
    if amounts: result['amounts_soles']=amounts
    return result

def init():
    with connect() as c:
        schema = (ROOT / 'backend/agents_schema.sql').read_text(encoding='utf-8')
        c.executescript(postgres_schema(schema))
        if 'checkpoint' not in {r[1] for r in c.execute('PRAGMA table_info(agent_runs)')}:
            c.execute("ALTER TABLE agent_runs ADD COLUMN checkpoint TEXT NOT NULL DEFAULT '{}'")

def require_admin(c, uid):
    if not one(c, "SELECT id FROM users WHERE id=? AND role='admin'", (uid,)):
        raise ValueError('Esta operación requiere una cuenta administradora.')

def event(rid, agent, kind, message, data=None, target=''):
    with transaction() as c:
        c.execute('INSERT INTO agent_steps(run_id,agent,kind,target,message,data,created_at) VALUES(?,?,?,?,?,?,?)',
                  (rid, agent, kind, target, message[:2000], dump(data or {}), now()))

def create_run(d, uid, model):
    with transaction() as c:
        require_admin(c, uid)
        previous = one(c, 'SELECT id FROM agent_runs WHERE request_key=? AND user_id=?', (d.request_key, uid))
        if previous: return previous['id']
        if one(c, "SELECT COUNT(*) n FROM agent_runs WHERE status IN ('en_cola','en_curso')")['n'] >= 3:
            raise ValueError('Ya hay tres análisis pendientes. Espera a que terminen.')
        rid = c.execute('''INSERT INTO agent_runs(kind,request_key,user_id,budget_cents,product_limit,created_at,model)
            VALUES(?,?,?,?,?,?,?)''', (d.kind,d.request_key,uid,d.budget_cents,d.product_limit,now(),model)).lastrowid
        audit(c, 'agent_runs', rid, 'solicitar', uid, detail={'kind': d.kind})
        return rid

def get_run(rid):
    with connect() as c:
        run = one(c, 'SELECT * FROM agent_runs WHERE id=?', (rid,))
        if not run: raise ValueError('Análisis no encontrado.')
        run['result'] = json.loads(run['result'])
        checkpoint=json.loads(run.pop('checkpoint','{}'))
        run['can_resume']=run['status']=='error' and bool(checkpoint) and run['calls']<30
        run['steps'] = rows(c, 'SELECT * FROM agent_steps WHERE run_id=? ORDER BY id', (rid,))
        for step in run['steps']: step['data'] = json.loads(step['data'])
        return run

def resume(rid,uid):
    with transaction() as c:
        require_admin(c,uid)
        run=one(c,'SELECT * FROM agent_runs WHERE id=?',(rid,))
        if not run or run['status']!='error' or not json.loads(run['checkpoint']) or run['calls']>=30:
            raise ValueError('Este análisis no se puede retomar. Inicia una revisión nueva.')
        if datetime.fromisoformat(run['created_at'])<datetime.fromisoformat(now())-timedelta(hours=24):
            raise ValueError('La evidencia tiene más de 24 horas. Inicia una revisión nueva.')
        if one(c,"SELECT COUNT(*) n FROM agent_runs WHERE status IN ('en_cola','en_curso')")['n']>=3:
            raise ValueError('Hay tres análisis pendientes. Espera a que terminen.')
        c.execute("UPDATE agent_runs SET status='en_cola',finished_at=NULL,lease_until=NULL,error='' WHERE id=?",(rid,))
        audit(c,'agent_runs',rid,'retomar',uid)

def list_runs(page=1, status=''):
    page=max(1,page)
    where='WHERE status=?' if status else ''
    args=(status,) if status else ()
    with connect() as c:
        return {'items':rows(c,f'''SELECT id,kind,status,budget_cents,created_at,finished_at,calls,tokens,error
            FROM agent_runs {where} ORDER BY id DESC LIMIT 12 OFFSET ?''', (*args,(page-1)*12)),
            'total':one(c,f'SELECT COUNT(*) n FROM agent_runs {where}',args)['n'], 'page':page}

def cancel(rid, uid):
    with transaction() as c:
        require_admin(c, uid)
        changed=c.execute("UPDATE agent_runs SET status='cancelada',finished_at=? WHERE id=? AND status IN ('en_cola','en_curso','revision')",(now(),rid)).rowcount
        if not changed: raise ValueError('Este análisis ya está cerrado.')
        audit(c,'agent_runs',rid,'cancelar',uid)

def offer_rows(q='', page=1):
    q=q.strip()[:100]; page=max(1,page)
    with connect() as c:
        where="WHERE o.active=1 AND (p.sku LIKE ? OR p.name LIKE ? OR s.name LIKE ?)"
        args=(f'%{q}%',)*3
        base='FROM supplier_offers o JOIN products p ON p.id=o.product_id JOIN suppliers s ON s.id=o.supplier_id '
        return {'items':rows(c,'SELECT o.*,p.name,p.sku,s.name supplier '+base+where+' ORDER BY o.updated_at DESC,o.id DESC LIMIT 15 OFFSET ?',(*args,(page-1)*15)),
            'total':one(c,'SELECT COUNT(*) n '+base+where,args)['n'],'page':page,
            'suppliers':rows(c,'SELECT id,name FROM suppliers WHERE active=1 ORDER BY name')}

def save_offer(d, uid):
    if d.valid_until < date.fromisoformat(now()[:10]): raise ValueError('La vigencia no puede estar vencida.')
    with transaction() as c:
        require_admin(c,uid)
        if not one(c,'SELECT id FROM products WHERE id=? AND active=1',(d.product_id,)) or not one(c,'SELECT id FROM suppliers WHERE id=? AND active=1',(d.supplier_id,)):
            raise ValueError('El producto y el proveedor deben estar activos.')
        c.execute('''INSERT INTO supplier_offers(product_id,supplier_id,cost_cents,lead_days,pack_size,minimum_quantity,valid_until,source,updated_at,user_id)
            VALUES(?,?,?,?,?,?,?,'manual',?,?) ON CONFLICT(product_id,supplier_id) DO UPDATE SET
            cost_cents=excluded.cost_cents,lead_days=excluded.lead_days,pack_size=excluded.pack_size,
            minimum_quantity=excluded.minimum_quantity,valid_until=excluded.valid_until,source='manual',active=1,updated_at=excluded.updated_at,user_id=excluded.user_id''',
            (d.product_id,d.supplier_id,d.cost_cents,d.lead_days,d.pack_size,d.minimum_quantity,d.valid_until.isoformat(),now(),uid))
        audit(c,'supplier_offers',f'{d.product_id}:{d.supplier_id}','guardar',uid)

def import_references(uid):
    """Explicit academic preparation: preserve provenance, never overwrite a manual offer."""
    with transaction() as c:
        require_admin(c,uid)
        until=(date.fromisoformat(now()[:10])+timedelta(days=30)).isoformat()
        minimum_lead = 'GREATEST(1,ip.lead_days)' if is_postgres() else 'MAX(1,ip.lead_days)'
        count=c.execute(f'''INSERT OR IGNORE INTO supplier_offers(product_id,supplier_id,cost_cents,lead_days,pack_size,minimum_quantity,valid_until,source,updated_at,user_id)
            SELECT p.id,ip.supplier_id,p.cost_cents,{minimum_lead},ip.pack_size,ip.pack_size,?,'referencia_catalogo',?,?
            FROM products p JOIN inventory_policy ip ON ip.product_id=p.id JOIN suppliers s ON s.id=ip.supplier_id
            WHERE p.active=1 AND s.active=1 AND p.cost_cents>0''',(until,now(),uid)).rowcount
        audit(c,'supplier_offers','referencias','importar',uid,detail={'count':count,'source':'referencia_catalogo'})
        return count

def context(run):
    result={'task':run['kind'],'budget_cents':run['budget_cents'],'product_limit':run['product_limit'],
            'required_agents':TEAMS[run['kind']], 'available_agents':list(ROLES), 'currency':'PEN',
            'rules':['Solo propuestas; compras requieren aprobación humana.', 'No confirmar pagos, recepciones ni entregas.',
                     'Los datos de referencia se identifican; nunca inventar evidencia.']}
    if run['kind']=='reposicion':
        stock=candidates(run['product_limit'])
        result['situation']={'candidates':stock['total_candidates'],
            'stockouts':sum(p['available']==0 for p in stock['items']),
            'with_incoming':sum(p['incoming']>0 for p in stock['items']),
            'operational_forecast':stock['demand']['usable']}
        result['situation']['shipment_incidents']=shipments()['incidents']
        result['required_agents']=['calidad','inventario','compras','finanzas','auditor']
        result['optional_agents']=['demanda','pedidos']
        result['guidance']='Convoca demanda cuando operational_forecast sea verdadero y pedidos cuando shipment_incidents sea mayor que cero. Justifica cada opcional con esa evidencia. Elige rapidez si prima el plazo o costo si prima el presupuesto. No extrapoles un horizonte ML.'
    return result

def quality(kind):
    data=operations.quality()
    result={'checks':data['checks'],'blocking_errors':sum(x['count'] for x in data['checks'] if x['severity']=='error'),
            'observation_days':data['observations']['days'],'historical_source':'El sistema contiene un historial académico de referencia; comprobar origen de cada pronóstico.'}
    if kind=='catalogo':
        catalog=catalog_quality.audit_catalog()
        # Keep product descriptions, personal data and large issue lists out of the model context.
        result['catalog_summary']=catalog.get('summary',{})
        result['catalog_findings']=catalog.get('checks',[])[:20]
        result['blocking_errors']+=catalog.get('summary',{}).get('errors',0)
    return result

def demand():
    contract=predictions.contract()
    yesterday=(date.fromisoformat(now()[:10])-timedelta(days=1)).isoformat()
    with connect() as c:
        latest=one(c,'SELECT id,source,cutoff,model_hash,count FROM ml_runs ORDER BY id DESC LIMIT 1')
        operational=one(c,"SELECT id,source,cutoff,model_hash,count FROM ml_runs WHERE source='operacion' AND cutoff=? AND model_hash=? ORDER BY id DESC LIMIT 1",(yesterday,contract['model_sha256']))
    return {'model':contract['model_name'],'horizon_days':contract['horizon_days'],'latest':latest,
            'operational_run':operational,'usable':bool(operational),
            'note':'Solo se aplica un pronóstico operativo de ayer, del modelo vigente y sin observaciones por producto. En los demás casos se usa la política de inventario.'}

def candidates(limit):
    data=[p for p in operations.inventory_rows() if p['active']]
    info=demand()
    forecast={}
    if info['operational_run']:
        with connect() as c:
            forecast={p['product_id']:p for p in rows(c,'SELECT product_id,prediction,review FROM ml_predictions WHERE run_id=?',(info['operational_run']['id'],))}
    for p in data:
        f=forecast.get(p['id'])
        p['basis']='politica'; p['forecast_units']=None
        if f and not f['review'] and p['lead_days']<=info['horizon_days']:
            p['forecast_units']=math.ceil(max(0,f['prediction']))
            p['basis']='ml_operativo'
        target=p['maximum'] if p['projected']<=p['minimum'] else 0
        if p['forecast_units'] is not None and p['projected']<p['forecast_units']:
            target=max(target,p['forecast_units'],p['minimum'])
        p['needed']=max(0,target-p['projected'])
        p['target']=target
    data=[p for p in data if p['needed']>0]
    data.sort(key=lambda p:(p['available']>0,p['available']-p['minimum'],-p['sold_30'],p['id']))
    fields=['id','sku','name','active','stock','reserved','available','incoming','minimum','maximum','price_cents',
            'cost_cents','lead_days','pack_size','supplier_id','policy_source','sold_30','target','needed','basis','forecast_units']
    return {'items':[{k:p[k] for k in fields} for p in data[:limit]],'total_candidates':len(data),'limit':limit,'demand':info}

def stock_state(c, pid):
    maximum = 'GREATEST' if is_postgres() else 'MAX'
    return one(c,f'''SELECT p.stock,p.reserved,p.minimum,p.active,p.price_cents,p.cost_cents,
        {maximum}(COALESCE(ip.maximum,{maximum}(p.minimum*3,10)),p.minimum) maximum,
        COALESCE(ip.lead_days,7) lead_days,COALESCE(ip.pack_size,1) pack_size,ip.supplier_id,COALESCE(ip.source,'pendiente') policy_source,
        COALESCE((SELECT SUM(i.quantity-i.received_quantity) FROM purchase_items i JOIN purchase_orders po ON po.id=i.purchase_order_id
          WHERE i.product_id=p.id AND po.status IN ('pendiente','parcial')),0) incoming
        FROM products p LEFT JOIN inventory_policy ip ON ip.product_id=p.id WHERE p.id=?''',(pid,))

def fingerprint(c, pid, offer_id):
    p=stock_state(c,pid)
    offer=one(c,'''SELECT o.*,s.active supplier_active FROM supplier_offers o JOIN suppliers s ON s.id=o.supplier_id WHERE o.id=?''',(offer_id,))
    return hashlib.sha256(dump({'product':p,'offer':offer}).encode()).hexdigest()

def delivery_risk(product, lead_days):
    """Descriptive signal, never an ML forecast or an assumed arrival of open purchases."""
    available=product['available']
    sold=product.get('sold_30',0)
    rate=sold/30 if sold else 0
    coverage=round(available/rate,1) if rate else None
    gap=round(max(0,lead_days-available/rate),1) if rate else None
    level='agotado' if available<=0 else 'espera_con_riesgo' if gap and gap>0 else 'sin_senal' if not rate else 'cubierto'
    return {'level':level,'sold_30':sold,'coverage_days':coverage,'uncovered_wait_days':gap,
        'note':'Indicador con ventas de 30 días y stock disponible. No es pronóstico ML; compras en camino no se suponen recibidas. Sin ventas no se puede estimar cobertura.'}

def annotate_alternatives(options, product):
    for option in options:
        option['delivery_risk']=delivery_risk(product,option['lead_days'])
        option['dominated_by']=[other['offer_id'] for other in options if option['eligible'] and other['eligible']
            and other['offer_id']!=option['offer_id'] and other['quantity']>=option['quantity']
            and other['line_cents']<=option['line_cents'] and other['lead_days']<=option['lead_days']
            and (other['line_cents']<option['line_cents'] or other['lead_days']<option['lead_days'])]

def purchase_plan(stock, strategy, budget, fit_budget=False, selections=None):
    lines=[]; excluded=[]; remaining=budget; today=now()[:10]
    selections=selections or {}
    if any(pid not in {p['id'] for p in stock['items']} for pid in selections):
        raise ValueError('Compras seleccionó un producto ajeno a la necesidad analizada.')
    with transaction() as c:
        for p in stock['items']:
            current=stock_state(c,p['id'])
            if not current or any(current[k]!=p[k] for k in current):
                raise ValueError('El inventario cambió durante el análisis. Inicia una revisión nueva.')
            offers=rows(c,'''SELECT o.*,s.name supplier,s.active supplier_active FROM supplier_offers o JOIN suppliers s ON s.id=o.supplier_id
                WHERE o.product_id=? ORDER BY o.id''',(p['id'],))
            choices=[]; comparisons=[]
            for o in offers:
                qty=math.ceil(max(p['needed'],o['minimum_quantity'])/o['pack_size'])*o['pack_size']
                reason=''
                if not o['active'] or not o['supplier_active']: reason='Oferta o proveedor inactivo.'
                elif o['valid_until']<today: reason='Oferta vencida.'
                elif o['cost_cents']>=p['price_cents']: reason='Costo igual o mayor al precio de venta.'
                elif p['basis']=='ml_operativo' and o['lead_days']>stock['demand']['horizon_days']:
                    reason='El plazo excede el horizonte del pronóstico utilizado; revisar con política de inventario.'
                if fit_budget:
                    qty=min(qty,(remaining//o['cost_cents']//o['pack_size'])*o['pack_size'])
                    if qty<o['minimum_quantity']: reason=reason or 'El presupuesto restante no cubre el lote mínimo.'
                comparison={'offer_id':o['id'],'supplier_id':o['supplier_id'],'supplier':o['supplier'],
                    'cost_cents':o['cost_cents'],'lead_days':o['lead_days'],'quantity':max(0,qty),
                    'line_cents':max(0,qty)*o['cost_cents'],'pack_size':o['pack_size'],
                    'minimum_quantity':o['minimum_quantity'],'valid_until':o['valid_until'],'source':o['source'],
                    'eligible':not reason,'reason':reason}
                comparisons.append(comparison)
                if not reason: choices.append({**o,'quantity':qty,'line_cents':qty*o['cost_cents']})
            if not choices:
                if p['id'] in selections:
                    raise ValueError('La alternativa elegida por Compras no cumple las condiciones o el presupuesto disponible.')
                excluded.append({'sku':p['sku'],'reason':'Sin oferta viable con las condiciones y el presupuesto actuales.','options':comparisons});continue
            if any(o['source']=='manual' for o in choices):
                for comp in comparisons:
                    if comp['source']!='manual' and comp['eligible']:
                        comp.update(eligible=False,reason='Existe una oferta registrada; la referencia se conserva solo para consulta.')
                choices=[o for o in choices if o['source']=='manual']
            annotate_alternatives(comparisons,p)
            # Prefer documented manual offers; references never masquerade as supplier quotes.
            if strategy=='rapidez':
                choices.sort(key=lambda o:(o['lead_days'],-min(o['quantity'],p['needed']),o['line_cents'],o['id']))
            elif fit_budget:
                choices.sort(key=lambda o:(-min(o['quantity'],p['needed']),o['line_cents'],o['lead_days'],o['id']))
            else:
                choices.sort(key=lambda o:(o['line_cents'],o['lead_days'],o['id']))
            o=choices[0]
            suggested_offer=o['id']
            if p['id'] in selections:
                selected=next((v for v in choices if v['id']==selections[p['id']]),None)
                if not selected: raise ValueError('La alternativa elegida por Compras no es válida o ya no cumple las condiciones.')
                o=selected
            for comp in comparisons: comp['selected']=comp['offer_id']==o['id']
            reason=('Única oferta viable; no hay una comparación efectiva entre proveedores.' if len(choices)==1 else
                    'Menor plazo entre las ofertas viables; necesidad cubierta y costo como desempates.' if strategy=='rapidez' else
                    'Mayor necesidad cubierta dentro del presupuesto; menor importe como desempate.' if fit_budget else
                    'Menor importe del lote entre las ofertas viables; se muestran sus cantidades para comparar.')
            if p['id'] in selections and o['id']!=suggested_offer:
                reason='Elegida por Compras entre ofertas viables. Revisa el motivo comunicado por el agente junto con los costos y plazos.'
            lines.append({'product_id':p['id'],'sku':p['sku'],'name':p['name'],'supplier_id':o['supplier_id'],
                'supplier':o['supplier'],'offer_id':o['id'],'quantity':o['quantity'],'cost_cents':o['cost_cents'],
                'line_cents':o['line_cents'],'lead_days':o['lead_days'],'source':o['source'],'basis':p['basis'],
                'available':p['available'],'incoming':p['incoming'],'needed':p['needed'],
                'remaining_need':max(0,p['needed']-o['quantity']), 'alternatives':len(choices),
                'options':comparisons,'selection_reason':reason,
                'delivery_risk':delivery_risk(p,o['lead_days']),
                'effect':{'projected_before':p['available']+p['incoming'],'projected_after':p['available']+p['incoming']+o['quantity'],
                    'target':p['target'],'note':'Disponibilidad proyectada al recibir la mercadería, antes de futuras ventas.'},
                'price_cents':p['price_cents'],'fingerprint':fingerprint(c,p['id'],o['id'])})
            remaining-=o['line_cents']
    warnings=[]
    for line in lines:
        chosen=next(o for o in line['options'] if o['selected'])
        if chosen['dominated_by']:
            warnings.append({'sku':line['sku'],'kind':'alternativa_superior','message':'Hay otra oferta viable con al menos la misma cantidad, sin mayor importe ni plazo. Compras debe justificar la excepción.', 'offer_ids':chosen['dominated_by']})
        if line['delivery_risk']['level'] in ['agotado','espera_con_riesgo']:
            warnings.append({'sku':line['sku'],'kind':'espera','message':'La entrega no resuelve de inmediato el faltante o la cobertura estimada es menor al plazo.'})
    return {'lines':lines,'excluded':excluded,'warnings':warnings,'total_cents':sum(i['line_cents'] for i in lines),
            'budget_cents':budget,'fit_budget':fit_budget,'strategy':strategy,
            'reference_lines':sum(i['source']=='referencia_catalogo' for i in lines),
            'comparison':{'multiple_offers':sum(i['alternatives']>1 for i in lines),'single_offer':sum(i['alternatives']==1 for i in lines),
                'uncovered_units':sum(max(0,p['needed']-next((i['quantity'] for i in lines if i['product_id']==p['id']),0)) for p in stock['items'])},
            'note':'Importes con IGV; flete no incluido. Priorización secuencial: agotados, distancia al mínimo y ventas recientes. No garantiza la combinación global de menor costo o mayor cobertura.'}

def finance(run, plan=None):
    if run['kind']=='reposicion':
        return {'budget_cents':run['budget_cents'],'total_cents':plan['total_cents'],
            'over_budget':plan['total_cents']>run['budget_cents'],
            'loss_skus':[i['sku'] for i in plan['lines'] if i['cost_cents']>=i['price_cents']],
            'note':'El límite lo fija el administrador; no se infiere efectivo disponible a partir de ventas.'}
    data=reports.resumen_ventas()
    return {k:v for k,v in data.items() if k not in ['products','daily']}

def shipments():
    data=operations.shipment_rows(); today=now()[:10]
    issues=[]
    for p in data:
        if p['status']=='entregado': continue
        reasons=[]
        if p['expected_at'] and p['expected_at']<today: reasons.append('Fecha de entrega vencida')
        if p['status'] in ['pagado','preparando'] and (p['paid_at'] or p['created_at'])[:10] < (date.fromisoformat(today)-timedelta(days=3)).isoformat(): reasons.append('Más de tres días sin despacho o recojo')
        if p['status']=='enviado' and not p['tracking']: reasons.append('Sin seguimiento registrado')
        if p['incident']: reasons.append('Incidencia registrada; revisar en el pedido')
        if reasons: issues.append({'id':p['id'],'code':p['code'],'status':p['status'],'expected_at':p['expected_at'],'reasons':reasons})
    return {'open_orders':sum(p['status']!='entregado' for p in data),'incidents':len(issues),'items':issues[:20],
            'note':'No se confirman entregas ni pagos. Los datos de contacto del cliente no se envían al modelo.'}

def audit_dossier(state):
    """Keep specialist evidence and counteroffers without repeating the entire catalog context."""
    dossier={k:state[k] for k in ['quality','demand','finance','shipments','blocked_reason','conclusions','review_log'] if k in state}
    if 'inventory' in state:
        inventory=state['inventory']
        dossier['inventory']={'total_candidates':inventory['total_candidates'],'items':[
            {k:p.get(k) for k in ['sku','available','incoming','needed','basis','forecast_units']} for p in inventory['items']]}
    if 'plan' in state:
        plan=state['plan']
        dossier['plan']={k:plan[k] for k in ['total_cents','budget_cents','strategy','comparison','warnings','note','strategy_comparison'] if k in plan}
        dossier['plan']['lines']=[]
        for line in plan['lines']:
            compact={k:line[k] for k in ['sku','supplier','offer_id','quantity','cost_cents','line_cents','lead_days','source','basis','needed','remaining_need','selection_reason','agent_reason','delivery_risk'] if k in line}
            compact['options']=[{k:o[k] for k in ['offer_id','supplier','quantity','line_cents','lead_days','minimum_quantity','pack_size','valid_until','source','eligible','reason','selected','dominated_by'] if k in o} for o in line.get('options',[])]
            dossier['plan']['lines'].append(compact)
        dossier['plan']['excluded']=[{'sku':p['sku'],'reason':p['reason']} for p in plan['excluded']]
    return dossier

def audit_result(run, state):
    errors=[]
    if state.get('blocked_reason'): errors.append('Hay una observación pendiente de resolver: '+state['blocked_reason'])
    if state.get('quality',{}).get('blocking_errors'): errors.append('Hay inconsistencias operativas que deben corregirse.')
    plan=state.get('plan',{})
    if run['kind']=='reposicion':
        if not plan.get('lines'): errors.append('No hay líneas de compra viables con las ofertas y el presupuesto actuales.')
        if plan.get('total_cents',0)>run['budget_cents']: errors.append('La propuesta supera el presupuesto.')
        if any(i['cost_cents']>=i['price_cents'] for i in plan.get('lines',[])): errors.append('Hay costos iguales o mayores que el precio de venta.')
        for line in plan.get('lines',[]):
            chosen=next((o for o in line.get('options',[]) if o.get('selected')),None)
            if chosen and chosen.get('dominated_by') and not line.get('agent_reason','').strip():
                errors.append(f"{line['sku']}: la oferta elegida tiene una alternativa superior sin justificación de Compras.")
        with connect() as c:
            for line in plan.get('lines',[]):
                if fingerprint(c,line['product_id'],line['offer_id'])!=line['fingerprint']:
                    errors.append('El inventario o la oferta cambiaron durante el análisis. Ejecuta una revisión nueva.');break
    checks=['Consistencia operativa','Origen y límites de la evidencia']
    if run['kind']=='reposicion': checks+=['Presupuesto','Margen comercial','Vigencia de ofertas y existencias']
    elif run['kind']=='finanzas': checks+=['Ventas cobradas','Costos de mercadería','Alcance del margen comercial']
    elif run['kind']=='pedidos': checks+=['Estados de pedidos','Fechas e incidencias registradas']
    else: checks+=['Errores y pendientes del catálogo']
    return {'passed':not errors,'errors':errors,'checks':checks,
            'reference_lines':plan.get('reference_lines',0),'requires_human_approval':run['kind']=='reposicion'}

def approve(rid, uid, accept_references=False):
    with transaction() as c:
        require_admin(c,uid)
        run=one(c,'SELECT * FROM agent_runs WHERE id=?',(rid,))
        if not run: raise ValueError('Análisis no encontrado.')
        result=json.loads(run['result'])
        if run['status']=='ejecutada': return result['purchase_ids']
        if run['status']!='revision' or run['kind']!='reposicion' or not result.get('audit',{}).get('passed'):
            raise ValueError('Solo se puede aprobar una propuesta revisada por el auditor.')
        if datetime.fromisoformat(run['finished_at']) < datetime.fromisoformat(now())-timedelta(hours=24):
            raise ValueError('La propuesta venció. Ejecuta un análisis nuevo.')
        plan=result['plan']
        if any(i['basis']=='ml_operativo' for i in plan['lines']):
            if demand()['operational_run']!=result['inventory']['demand']['operational_run']:
                raise ValueError('La evidencia del ML cambió o venció. Genera una propuesta nueva.')
        if plan['reference_lines'] and not accept_references: raise ValueError('Confirma el uso académico de los costos de referencia.')
        if not plan['lines'] or sum(i['quantity']*i['cost_cents'] for i in plan['lines'])>run['budget_cents']:
            raise ValueError('El presupuesto o las cantidades no son válidos.')
        groups={}
        for line in plan['lines']:
            offer=one(c,'SELECT * FROM supplier_offers WHERE id=?',(line['offer_id'],))
            if not offer or offer['valid_until']<now()[:10] or fingerprint(c,line['product_id'],line['offer_id'])!=line['fingerprint']:
                raise ValueError('El stock, la política o una oferta cambiaron. Genera una propuesta nueva antes de comprar.')
            groups.setdefault(line['supplier_id'],[]).append(line)
        ids=[]
        for supplier, lines in groups.items():
            expected=(date.fromisoformat(now()[:10])+timedelta(days=max(i['lead_days'] for i in lines))).isoformat()
            ids.append(suppliers.crear_orden_compra(supplier,lines,uid,actor='agente',expected_at=expected,
                note=f'Propuesta de agentes #{rid}, aprobada por administrador. '+plan['note'],
                request_key=f'agent-{rid}-supplier-{supplier}',connection=c))
        result['purchase_ids']=ids
        c.execute("UPDATE agent_runs SET status='ejecutada',approved_by=?,approved_at=?,result=? WHERE id=?",(uid,now(),dump(result),rid))
        audit(c,'agent_runs',rid,'aprobar_y_crear_compras',uid,actor='agente',detail={'purchase_ids':ids,'reference_costs_accepted':accept_references})
        return ids
