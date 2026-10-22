"""Current evidence for preparation and the receiving side of approved proposals."""
from datetime import date
from backend.db import connect, rows, one, now
from backend.services import agent_data as data

def readiness():
    stock=data.candidates(20)
    items=[]
    with connect() as c:
        for p in stock['items']:
            offers=rows(c,'''SELECT o.source,o.lead_days FROM supplier_offers o JOIN suppliers s ON s.id=o.supplier_id
                WHERE o.product_id=? AND o.active=1 AND s.active=1 AND o.valid_until>=? AND o.cost_cents<?''',
                (p['id'],now()[:10],p['price_cents']))
            manual=sum(o['source']=='manual' for o in offers)
            items.append({'id':p['id'],'sku':p['sku'],'name':p['name'],'needed':p['needed'],
                'manual_offers':manual,'reference_offers':len(offers)-manual,'basis':p['basis'],
                'next_step':'Comparación disponible' if manual>=2 else 'Registrar otra oferta' if manual else 'Registrar ofertas de proveedores'})
    return {'demand':stock['demand'],'items':items,'total_candidates':stock['total_candidates'],
        'comparable':sum(p['manual_offers']>=2 for p in items),'ml_applied':sum(p['basis']=='ml_operativo' for p in items),
        'checked_at':now()}

def followup(run):
    if run['status']!='ejecutada': return None
    orders=[]; products={}
    with connect() as c:
        for oid in run['result'].get('purchase_ids',[]):
            po=one(c,'''SELECT po.*,s.name supplier FROM purchase_orders po JOIN suppliers s ON s.id=po.supplier_id
                WHERE po.id=?''',(oid,))
            if not po or po['request_key']!=f"agent-{run['id']}-supplier-{po['supplier_id']}": continue
            lines=rows(c,'SELECT * FROM purchase_items WHERE purchase_order_id=?',(oid,))
            ordered=sum(i['quantity'] for i in lines);received=sum(i['received_quantity'] for i in lines)
            outstanding=ordered-received
            closed=po['received_at']
            if po['status']=='cancelada':
                cancellation=one(c,"SELECT created_at FROM audit WHERE entity='purchase_orders' AND entity_id=? AND action='cancelar_saldo' ORDER BY id DESC LIMIT 1",(str(oid),))
                closed=cancellation['created_at'] if cancellation else None
            elapsed=None if po['status']=='cancelada' and not closed else (date.fromisoformat((closed or now())[:10])-date.fromisoformat(po['created_at'][:10])).days
            orders.append({'id':oid,'code':po['code'],'supplier':po['supplier'],'status':po['status'],
                'ordered':ordered,'received':received,'pending':outstanding if po['status'] in ['pendiente','parcial'] else 0,
                'cancelled':outstanding if po['status']=='cancelada' else 0,'elapsed_days':elapsed,
                'expected_at':po['expected_at'],'late':bool(po['expected_at'] and po['expected_at']<(po['received_at'] or now())[:10] and po['status']!='cancelada'),
                'received_cost_cents':sum(i['received_quantity']*i['cost_cents'] for i in lines)})
            for i in lines:
                p=one(c,'SELECT id,sku,name,stock,reserved,minimum FROM products WHERE id=?',(i['product_id'],))
                p['available']=p['stock']-p['reserved'];p['below_minimum']=p['available']<=p['minimum']
                products[p['id']]=p
    return {'orders':orders,'products':list(products.values()),'received':sum(o['received'] for o in orders),
        'pending':sum(o['pending'] for o in orders),'cancelled':sum(o['cancelled'] for o in orders),
        'received_cost_cents':sum(o['received_cost_cents'] for o in orders),'checked_at':now(),
        'note':'Las recepciones provienen de estas compras. El stock actual también refleja ventas y otros movimientos; no demuestra por sí solo una mejora causada por los agentes.'}
