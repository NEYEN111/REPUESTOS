"""Executable controls using the same business services, in an isolated SQLite process."""
import json
from backend import db
from backend.services import agent_data as data,suppliers

def seed():
    db.init_db();data.init()
    with db.transaction() as c:
        c.execute("INSERT INTO users(id,name,email,password_hash,role,consent_at,created_at) VALUES(1,'Control académico','control@example.invalid','unused','admin',?,?)",(db.now(),db.now()))
        c.execute("INSERT INTO categories(id,name,slug) VALUES(1,'Frenos','control-frenos')")
        c.execute("INSERT INTO brands(id,name) VALUES(1,'Catálogo de control')")
        for sid,name in [(1,'Proveedor de control A'),(2,'Proveedor de control B')]:
            c.execute('INSERT INTO suppliers(id,name,ruc,email,phone) VALUES(?,?,?,?,?)',(sid,name,'','',''))
        c.execute("INSERT INTO products(id,sku,name,brand_id,category_id,price_cents,cost_cents,stock,minimum,created_at) VALUES(1,'CONTROL-001','Pastillas de freno de ejemplo',1,1,2000,1000,0,5,?)",(db.now(),))
        c.execute("INSERT INTO product_images(product_id,url,thumb) VALUES(1,'/media/control.webp','/media/control.webp')")
        c.execute("INSERT INTO inventory_policy(product_id,location,maximum,lead_days,pack_size,supplier_id,updated_at) VALUES(1,'CONTROL',20,5,1,1,?)",(db.now(),))
    for sid,cost,lead in [(1,1000,5),(2,1100,2)]:
        data.save_offer(data.OfferInput(product_id=1,supplier_id=sid,cost_cents=cost,lead_days=lead,pack_size=1,minimum_quantity=1,valid_until='2099-12-31'),1)

def evaluate():
    seed()
    stock=data.candidates(5)
    initial=data.purchase_plan(stock,'costo',5000)
    fastest=data.purchase_plan(stock,'rapidez',5000)
    adjusted=data.purchase_plan(stock,'costo',5000,True)
    check=data.audit_result({'kind':'reposicion','budget_cents':5000},{'quality':{'blocking_errors':0},'plan':adjusted})
    budget={'id':'presupuesto','title':'Presupuesto insuficiente','expected':'Finanzas pide ajustar la compra y el Auditor solo deja pasar un importe dentro del límite.',
        'agents':['inventario','compras','finanzas','auditor'],
        'metrics':{'budget_cents':5000,'initial_cents':initial['total_cents'],'adjusted_cents':adjusted['total_cents'],
                   'needed_units':20,'approved_units':sum(i['quantity'] for i in adjusted['lines'])},
        'passed':initial['total_cents']>5000 and adjusted['total_cents']<=5000 and check['passed'],
        'evidence':{'initial_plan':data.model_view(initial),'fast_plan':data.model_view(fastest),'adjusted_plan':data.model_view(adjusted),'audit':check}}
    rid=data.create_run(data.RunInput(kind='reposicion',budget_cents=20000,request_key='control-full-cycle'),1,'control-sin-llm')
    plan=data.purchase_plan(stock,'costo',20000)
    audit=data.audit_result({'kind':'reposicion','budget_cents':20000},{'quality':data.quality('reposicion'),'plan':plan})
    with db.transaction() as c:
        c.execute("UPDATE agent_runs SET status='revision',finished_at=?,result=? WHERE id=?",(db.now(),data.dump({'inventory':stock,'plan':plan,'audit':audit}),rid))
    po=data.approve(rid,1)[0]
    after=data.candidates(5)
    with db.connect() as c: p=db.one(c,'SELECT stock,reserved FROM products WHERE id=1')
    incoming={'id':'pendiente','title':'Evitar una compra duplicada','expected':'Las 20 unidades en camino cubren el objetivo. No se solicita otra reposición.',
        'agents':['inventario','compras','auditor'],
        'metrics':{'stock':p['stock'],'incoming':20,'target':20,'new_candidates':after['total_candidates']},
        'passed':after['total_candidates']==0 and p['stock']==0,
        'evidence':{'existing_purchase_id':po,'inventory_after':data.model_view(after),'note':'Crear una compra pendiente no incrementa el stock físico.'}}
    suppliers.receive(po,1,{'request_key':'control-full-cycle-receipt'})
    from backend.services.agent_followup import followup
    outcome=followup(data.get_run(rid))
    incoming['evidence']['followup']=outcome
    incoming['evidence']['note']='Compra aprobada: 20 en camino y stock 0. Después de recibir: 20 recibidas, stock 20 y ninguna unidad pendiente.'
    incoming['passed']=incoming['passed'] and outcome['received']==20 and outcome['pending']==0 and outcome['products'][0]['stock']==20
    with db.transaction() as c:
        c.execute('UPDATE products SET stock=10,reserved=2,minimum=10 WHERE id=1')
    quality=data.quality('reposicion')
    blocked_plan=data.purchase_plan(data.candidates(5),'costo',5000,True)
    blocked=data.audit_result({'kind':'reposicion','budget_cents':5000},{'quality':quality,'plan':blocked_plan})
    inconsistency={'id':'inconsistencia','title':'Reservas sin respaldo','expected':'Calidad detecta una reserva sin pedido y el Auditor bloquea la propuesta.',
        'agents':['calidad','auditor'],'metrics':{'reserved_without_order':2,'blocking_errors':quality['blocking_errors']},
        'passed':quality['blocking_errors']>0 and not blocked['passed'],
        'evidence':{'quality':quality,'audit':blocked}}
    return {'checked_at':db.now(),'mode':'controles_aislados','uses_llm':False,
        'description':'Casos de reglas y servicios Python con datos académicos de ejemplo. No ejecutan el LLM ni alteran la tienda.',
        'cases':[budget,incoming,inconsistency]}

if __name__=='__main__':
    from pathlib import Path
    target=db.DB.resolve()
    if (target.exists() or not target.is_relative_to((db.ROOT/'.tmp').resolve())
            or not target.parent.name.startswith('agent-controls-')):
        raise SystemExit('Los casos solo se ejecutan con una base temporal explícita.')
    print(json.dumps(evaluate(),ensure_ascii=False))
