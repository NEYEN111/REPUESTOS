from datetime import date, datetime, timedelta
import math
from backend.db import connect, transaction, rows, one, now, audit, is_postgres
from backend.services.catalog import normalize
from backend.services.inventory import move, refresh_alert

_MAX = 'GREATEST' if is_postgres() else 'MAX'
INVENTORY_SQL = f'''SELECT p.id,p.sku,p.name,p.category_id,p.stock,p.reserved,p.stock-p.reserved available,p.minimum,p.active,
 p.price_cents,p.cost_cents,c.name category,b.name brand,
 COALESCE(ip.location,'') location,COALESCE(ip.maximum,{_MAX}(p.minimum*3,10)) maximum,
 COALESCE(ip.lead_days,7) lead_days,COALESCE(ip.pack_size,1) pack_size,ip.supplier_id,s.name supplier,
 COALESCE(ip.source,'pendiente') policy_source,
 (SELECT thumb FROM product_images WHERE product_id=p.id ORDER BY is_primary DESC,id LIMIT 1) image,
 COALESCE((SELECT SUM(i.quantity-i.received_quantity) FROM purchase_items i JOIN purchase_orders po ON po.id=i.purchase_order_id
   WHERE i.product_id=p.id AND po.status IN ('pendiente','parcial')),0) incoming,
 COALESCE((SELECT SUM(i.quantity) FROM order_items i JOIN orders o ON o.id=i.order_id
   WHERE i.product_id=p.id AND o.paid_at>=? AND o.paid_at<=?),0) sold_30
 FROM products p JOIN categories c ON c.id=p.category_id JOIN brands b ON b.id=p.brand_id
 LEFT JOIN inventory_policy ip ON ip.product_id=p.id LEFT JOIN suppliers s ON s.id=ip.supplier_id'''

def inventory_rows():
    stamp=now(); start=(datetime.fromisoformat(stamp)-timedelta(days=30)).isoformat()
    with connect() as c: data=rows(c,INVENTORY_SQL,(start,stamp))
    for r in data:
        r['maximum']=max(r['maximum'],r['minimum'])
        r['projected']=r['available']+r['incoming']
        r['coverage_days']=round(r['available']*30/r['sold_30'],1) if r['sold_30'] else None
        r['suggested']=math.ceil(max(0,r['maximum']-r['projected'])/r['pack_size'])*r['pack_size'] if r['active'] and r['projected']<=r['minimum'] else 0
        r['status']='oculto' if not r['active'] else 'agotado' if r['available']==0 else 'bajo' if r['available']<=r['minimum'] else 'exceso' if r['available']>r['maximum'] else 'normal'
        r['value_cents']=r['stock']*r['cost_cents']
    return data

def page(data,q='',status='',sort='name',direction='asc',page=1,limit=20):
    if q: data=[r for r in data if normalize(q) in normalize(' '.join(str(v) for v in r.values()))]
    if status: data=[r for r in data if r.get('status')==status]
    if data and sort in data[0]: data.sort(key=lambda r:(r.get(sort) is None,r.get(sort)),reverse=direction=='desc')
    total=len(data);limit=min(100,max(1,limit));page=max(1,page)
    return {'items':data[(page-1)*limit:page*limit],'total':total,'pages':math.ceil(total/limit),'page':page}

def save_policy(pid,d,uid):
    for k in ['minimum','maximum','lead_days','pack_size']:
        if type(d.get(k)) is not int or not 0<=d[k]<=100000: raise ValueError('Revisa mínimos, máximos, plazo y múltiplo de compra.')
    if d['maximum']<d['minimum'] or d['pack_size']<1 or d['lead_days']>365: raise ValueError('El máximo debe cubrir el mínimo; el múltiplo debe ser positivo y el plazo no superar 365 días.')
    with transaction() as c:
        if not one(c,'SELECT id FROM products WHERE id=?',(pid,)): raise ValueError('Producto no encontrado.')
        if d.get('supplier_id') and not one(c,'SELECT id FROM suppliers WHERE id=? AND active=1',(d['supplier_id'],)): raise ValueError('Selecciona un proveedor activo.')
        c.execute('UPDATE products SET minimum=? WHERE id=?',(d['minimum'],pid))
        c.execute('''INSERT INTO inventory_policy(product_id,location,maximum,lead_days,pack_size,supplier_id,updated_at) VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(product_id) DO UPDATE SET location=excluded.location,maximum=excluded.maximum,lead_days=excluded.lead_days,
          pack_size=excluded.pack_size,supplier_id=excluded.supplier_id,updated_at=excluded.updated_at,source='manual' ''',
          (pid,str(d.get('location','')).strip()[:80],d['maximum'],d['lead_days'],d['pack_size'],d.get('supplier_id') or None,now()))
        refresh_alert(c,pid);audit(c,'inventory_policy',pid,'guardar',uid,detail=d)

def count_stock(pid,d,uid):
    if type(d.get('counted')) is not int or d['counted']<0: raise ValueError('El conteo debe ser un entero igual o mayor que cero.')
    reason=str(d.get('reason','')).strip()
    if len(reason)<5: raise ValueError('Describe el motivo del conteo (mínimo 5 caracteres).')
    with transaction() as c:
        p=one(c,'SELECT * FROM products WHERE id=?',(pid,))
        if not p: raise ValueError('Producto no encontrado.')
        if p['stock']!=d.get('expected_stock') or p['reserved']!=d.get('expected_reserved'):
            raise ValueError('Las existencias cambiaron mientras contabas. Cierra y vuelve a abrir el producto antes de confirmar.')
        delta=d['counted']-p['stock']
        if d['counted']<p['reserved']: raise ValueError('El conteo no puede ser menor que las unidades reservadas. Revisa los pedidos pendientes.')
        cid=c.execute('INSERT INTO inventory_counts(product_id,expected,counted,difference,reason,user_id,created_at) VALUES(?,?,?,?,?,?,?)',
            (pid,p['stock'],d['counted'],delta,reason,uid,now())).lastrowid
        if delta: move(c,pid,delta,kind='conteo',reason=f'Conteo #{cid}: {reason}',user_id=uid)
        audit(c,'inventory_counts',cid,'confirmar',uid,detail={'product_id':pid,'difference':delta})
        return {'difference':delta}

def snapshot():
    stamp=now()
    with transaction() as c:
        c.execute('''INSERT INTO stock_observations(product_id,date,stock,reserved,available,incoming,price_cents,cost_cents,minimum,captured_at)
        SELECT p.id,?,p.stock,p.reserved,p.stock-p.reserved,
          COALESCE((SELECT SUM(i.quantity-i.received_quantity) FROM purchase_items i JOIN purchase_orders po ON po.id=i.purchase_order_id
            WHERE i.product_id=p.id AND po.status IN ('pendiente','parcial')),0),p.price_cents,p.cost_cents,p.minimum,? FROM products p WHERE 1=1
        ON CONFLICT(product_id,date) DO UPDATE SET stock=excluded.stock,reserved=excluded.reserved,available=excluded.available,
          incoming=excluded.incoming,price_cents=excluded.price_cents,cost_cents=excluded.cost_cents,minimum=excluded.minimum,captured_at=excluded.captured_at''',
          (stamp[:10],stamp))

def quality():
    with connect() as c:
        checks=[
          ('Reservas sin respaldo',"SELECT COUNT(*) n FROM products p WHERE p.reserved!=COALESCE((SELECT SUM(i.quantity) FROM order_items i JOIN orders o ON o.id=i.order_id WHERE i.product_id=p.id AND o.status IN ('pendiente de pago','pago por verificar')),0)",'error'),
          ('Recepciones fuera de rango','SELECT COUNT(*) n FROM purchase_items WHERE received_quantity<0 OR received_quantity>quantity','error'),
          ('Productos activos sin foto',"SELECT COUNT(*) n FROM products p WHERE active=1 AND NOT EXISTS(SELECT 1 FROM product_images i WHERE i.product_id=p.id)",'error'),
          ('Costo igual o mayor al precio','SELECT COUNT(*) n FROM products WHERE active=1 AND cost_cents>=price_cents','revisar'),
          ('Sin proveedor preferido','SELECT COUNT(*) n FROM products p LEFT JOIN inventory_policy ip ON ip.product_id=p.id WHERE p.active=1 AND ip.supplier_id IS NULL','pendiente'),
          ('Sin ubicación de almacén',"SELECT COUNT(*) n FROM products p LEFT JOIN inventory_policy ip ON ip.product_id=p.id WHERE p.active=1 AND COALESCE(ip.location,'')=''",'pendiente')]
        result=[{'name':name,'count':one(c,sql)['n'],'severity':severity} for name,sql,severity in checks]
        observations=one(c,'SELECT COUNT(*) count,COUNT(DISTINCT date) days,MIN(date) first,MAX(captured_at) last FROM stock_observations')
        synthetic=one(c,'SELECT COUNT(*) count,MIN(date) first,MAX(date) last FROM daily_stock')
        return {'checks':result,'observations':observations,'synthetic':synthetic}

def valid_date(value):
    if value:
        try: date.fromisoformat(value)
        except (ValueError,TypeError): raise ValueError('Usa una fecha válida con formato AAAA-MM-DD.')
    return value or ''

def save_shipment(oid,d,uid):
    from backend.services.orders import transition
    with transaction() as c:
        o=one(c,'SELECT * FROM orders WHERE id=?',(oid,))
        if not o or o['status'] in ['pendiente de pago','pago por verificar','cancelado','vencido']: raise ValueError('El pedido debe tener el pago confirmado para preparar la entrega.')
        previous=one(c,'SELECT * FROM shipments WHERE order_id=?',(oid,)) or {}
        values={k:str(d.get(k,previous.get(k,''))).strip()[:250] for k in ['carrier','tracking','recipient','incident']}
        expected=valid_date(d.get('expected_at',previous.get('expected_at','')))
        target=d.get('status',o['status'])
        if o['delivery']=='envio' and target=='enviado' and not all(values[k] for k in ['carrier','tracking']): raise ValueError('Registra la agencia y el número de seguimiento antes de despachar.')
        if target=='entregado' and target!=o['status'] and not values['recipient']: raise ValueError('Registra quién recibió el pedido.')
        if target!=o['status']: transition(c,o,target,uid,note=d.get('note','') or 'Actualización desde entregas.')
        c.execute('''INSERT INTO shipments(order_id,carrier,tracking,expected_at,recipient,incident,updated_at) VALUES(?,?,?,?,?,?,?)
          ON CONFLICT(order_id) DO UPDATE SET carrier=excluded.carrier,tracking=excluded.tracking,expected_at=excluded.expected_at,
          recipient=excluded.recipient,incident=excluded.incident,updated_at=excluded.updated_at''',
          (oid,values['carrier'],values['tracking'],expected,values['recipient'],values['incident'],now()))
        if values['tracking']: c.execute('UPDATE orders SET tracking=? WHERE id=?',(values['tracking'],oid))
        audit(c,'shipments',oid,'actualizar',uid,detail={**values,'expected_at':expected,'status':target,'note':str(d.get('note',''))[:1000]})

def shipment_rows():
    with connect() as c:
        return rows(c,"""SELECT o.id,o.code,o.customer_name,o.phone,o.delivery,o.address,o.status,o.created_at,o.paid_at,
          COALESCE(s.carrier,'') carrier,COALESCE(s.tracking,o.tracking) tracking,COALESCE(s.expected_at,'') expected_at,
          COALESCE(s.recipient,'') recipient,COALESCE(s.incident,'') incident,
          COALESCE(u.department||' / '||u.province||' / '||u.district,'') destination,
          (SELECT SUM(quantity) FROM order_items WHERE order_id=o.id) units
          FROM orders o LEFT JOIN shipments s ON s.order_id=o.id LEFT JOIN ubigeo u ON u.code=o.ubigeo
          WHERE o.status IN ('pagado','preparando','enviado','listo para recojo','entregado')""")
