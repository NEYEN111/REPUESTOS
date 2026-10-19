import secrets,re
from datetime import datetime,timedelta
from decimal import Decimal,ROUND_HALF_UP
from backend.db import transaction,connect,one,rows,now,config,audit
from backend.services.inventory import move

STATES={'pendiente de pago':['pago por verificar','cancelado','vencido'],'pago por verificar':['pagado','pendiente de pago','cancelado','vencido'],'pagado':['preparando'],'preparando':['enviado','listo para recojo'],'enviado':['entregado'],'listo para recojo':['entregado'],'entregado':[],'cancelado':[],'vencido':[]}
def code(prefix): return prefix+'-'+datetime.fromisoformat(now()).strftime('%y%m')+'-'+secrets.token_hex(3).upper()
def checked_items(c,items):
    if not items or len(items)>100: raise ValueError('Agrega entre 1 y 100 productos.')
    merged={}
    for i in items:
        if type(i.get('quantity')) is not int or not 1<=i['quantity']<=999: raise ValueError('Cantidad no válida.')
        merged[int(i['product_id'])]=merged.get(int(i['product_id']),0)+i['quantity']
    result=[]
    for pid,qty in merged.items():
        p=one(c,'SELECT * FROM products WHERE id=? AND active=1',(pid,))
        if not p: raise ValueError('Un producto ya no está disponible.')
        if p['stock']-p['reserved']<qty: raise ValueError(f"Solo quedan {p['stock']-p['reserved']} unidades de {p['name']}.")
        p['quantity']=qty;result.append(p)
    return result
def crear_cotizacion(items,user_id=None,customer_name='Cliente',actor='usuario'):
    with transaction() as c:
        products=checked_items(c,items);total=sum(p['quantity']*p['price_cents'] for p in products)
        qcode=code('COT');token=secrets.token_urlsafe(24)
        qid=c.execute('INSERT INTO quotes(code,user_id,guest_token,customer_name,total_cents,created_at,expires_at) VALUES(?,?,?,?,?,?,?)',(qcode,user_id,token,customer_name,total,now(),(datetime.fromisoformat(now())+timedelta(days=7)).isoformat())).lastrowid
        for p in products: c.execute('INSERT INTO quote_items(quote_id,product_id,quantity,price_cents) VALUES(?,?,?,?)',(qid,p['id'],p['quantity'],p['price_cents']))
        audit(c,'quotes',qid,'crear',user_id,actor)
        return {'id':qid,'code':qcode,'token':token}
def expire(c):
    c.execute("UPDATE quotes SET status='vencida' WHERE status='vigente' AND expires_at<?",(now(),))
    for o in rows(c,"SELECT * FROM orders WHERE status IN ('pendiente de pago','pago por verificar') AND expires_at<?",(now(),)):
        transition(c,o,'vencido',None,'sistema','Reserva vencida después de 24 horas.')
def transition(c,o,state,user_id,actor='usuario',note=''):
    if state not in STATES.get(o['status'],[]): raise ValueError('Este cambio de estado no está permitido.')
    if state=='enviado' and o['delivery']=='retiro': raise ValueError('Este pedido es para retiro en tienda.')
    if state=='listo para recojo' and o['delivery']!='retiro': raise ValueError('Este pedido es para envío.')
    for item in rows(c,'SELECT * FROM order_items WHERE order_id=?',(o['id'],)):
        if state in ['cancelado','vencido']: move(c,item['product_id'],reserved_delta=-item['quantity'],kind='liberación',reason=state,user_id=user_id,actor=actor,order_id=o['id'])
        if state=='pagado': move(c,item['product_id'],quantity=-item['quantity'],reserved_delta=-item['quantity'],kind='venta',reason='Pago confirmado',user_id=user_id,actor=actor,order_id=o['id'])
    c.execute('UPDATE orders SET status=? WHERE id=?',(state,o['id']))
    if state=='pagado': c.execute('UPDATE orders SET paid_at=? WHERE id=?',(now(),o['id']))
    if state in ['cancelado','vencido']: c.execute("UPDATE payments SET status=? WHERE order_id=?",(state,o['id']))
    c.execute('INSERT INTO order_history(order_id,status,note,user_id,actor,created_at) VALUES(?,?,?,?,?,?)',(o['id'],state,note,user_id,actor,now()))
    audit(c,'orders',o['id'],state,user_id,actor)
def create_order(d,user_id=None):
    for k in ['customer_name','email','phone','document','document_type','delivery','payment_method']:
        if not d.get(k): raise ValueError('Completa todos los datos de contacto y comprobante.')
    if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',d['email']): raise ValueError('Ingresa un correo válido.')
    if not re.fullmatch(r'(?:\+?51\s?)?9\d{8}',d['phone'].replace(' ','')): raise ValueError('Ingresa un celular peruano de 9 dígitos.')
    if d['document_type'] not in ['boleta','factura']: raise ValueError('Selecciona boleta o factura.')
    if not re.fullmatch(r'\d{11}' if d['document_type']=='factura' else r'\d{8}',d['document']): raise ValueError('El RUC debe tener 11 dígitos y el DNI 8 dígitos.')
    if d['document_type']=='factura' and not d.get('business_name'): raise ValueError('Ingresa la razón social.')
    cfg=config()
    if d['payment_method'] not in cfg['payments']: raise ValueError('Método de pago no disponible.')
    if d['delivery'] not in ['retiro','envio']: raise ValueError('Selecciona una forma de entrega.')
    shipping=0
    if d['delivery']=='envio':
        zone=next((z for z in cfg['shipping'] if z['name']==d.get('shipping_zone')),None)
        if not zone or not d.get('address') or not d.get('ubigeo'): raise ValueError('Completa dirección, distrito y zona de envío.')
        shipping=zone['cents']
    with transaction() as c:
        expire(c)
        if d.get('idempotency_key'):
            prior=one(c,'SELECT id,code,guest_token token FROM orders WHERE idempotency_key=?',(d['idempotency_key'],))
            if prior: return prior
        if d['delivery']=='envio' and not one(c,'SELECT code FROM ubigeo WHERE code=?',(d['ubigeo'],)): raise ValueError('Selecciona un distrito válido.')
        products=checked_items(c,d.get('items',[]))
        quote=None
        if d.get('quote_id'):
            quote=one(c,'SELECT * FROM quotes WHERE id=?',(d['quote_id'],))
            if not quote or not ((user_id and quote['user_id']==user_id) or secrets.compare_digest(quote['guest_token'],d.get('quote_token',''))): raise ValueError('Cotización no disponible.')
            if quote['expires_at']<now() or quote['status']!='vigente': raise ValueError('Esta cotización venció o ya fue convertida.')
            qi=rows(c,'SELECT * FROM quote_items WHERE quote_id=?',(quote['id'],))
            if {(x['product_id'],x['quantity']) for x in qi}!={(p['id'],p['quantity']) for p in products}: raise ValueError('Los productos no coinciden con la cotización.')
            for p in products: p['price_cents']=next(x['price_cents'] for x in qi if x['product_id']==p['id'])
        total=sum(p['quantity']*p['price_cents'] for p in products)+shipping
        base=int((Decimal(total)/(1+Decimal(str(cfg['igv_percent']))/100)).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        token=secrets.token_urlsafe(24);oc=code('PED');stamp=now()
        columns=['code','user_id','guest_token','customer_name','email','phone','document_type','document','business_name','delivery','address','ubigeo','shipping_zone','shipping_cents','total_cents','base_cents','tax_cents','status','payment_method','created_at','expires_at','idempotency_key']
        values=[oc,user_id,token,d['customer_name'],d['email'],d['phone'],d['document_type'],d['document'],d.get('business_name',''),d['delivery'],d.get('address',''),d.get('ubigeo',''),d.get('shipping_zone',''),shipping,total,base,total-base,'pendiente de pago',d['payment_method'],stamp,(datetime.fromisoformat(stamp)+timedelta(hours=24)).isoformat(),d.get('idempotency_key') or secrets.token_hex(20)]
        oid=c.execute('INSERT INTO orders('+','.join(columns)+') VALUES('+','.join('?' for _ in values)+')',values).lastrowid
        for p in products:
            c.execute('INSERT INTO order_items(order_id,product_id,sku,name,quantity,price_cents,cost_cents) VALUES(?,?,?,?,?,?,?)',(oid,p['id'],p['sku'],p['name'],p['quantity'],p['price_cents'],p['cost_cents']))
            move(c,p['id'],reserved_delta=p['quantity'],kind='reserva',reason=oc,user_id=user_id,order_id=oid)
        c.execute('INSERT INTO payments(order_id,method,amount_cents,created_at) VALUES(?,?,?,?)',(oid,d['payment_method'],total,stamp))
        c.execute('INSERT INTO order_history(order_id,status,note,user_id,created_at) VALUES(?,?,?,?,?)',(oid,'pendiente de pago','Pedido creado. Reserva por 24 horas.',user_id,stamp))
        if quote: c.execute("UPDATE quotes SET status='convertida',order_id=? WHERE id=?",(oid,quote['id']))
        audit(c,'orders',oid,'crear',user_id)
        return {'id':oid,'code':oc,'token':token}
def order_detail(oid):
    with transaction() as c:
        expire(c);o=one(c,'SELECT * FROM orders WHERE id=?',(oid,))
        if not o: raise ValueError('Pedido no encontrado.')
        o['items']=rows(c,'SELECT i.*,COALESCE((SELECT thumb FROM product_images WHERE product_id=i.product_id ORDER BY is_primary DESC,id LIMIT 1),\'\') image FROM order_items i WHERE order_id=?',(oid,))
        o['payment']=one(c,'SELECT * FROM payments WHERE order_id=?',(oid,));o['history']=rows(c,'SELECT * FROM order_history WHERE order_id=? ORDER BY id',(oid,))
        o['shipment']=one(c,'SELECT * FROM shipments WHERE order_id=?',(oid,))
        return o
