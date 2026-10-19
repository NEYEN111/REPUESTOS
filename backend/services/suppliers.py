from backend.db import transaction,one,rows,now,audit
from backend.services.orders import code
from backend.services.inventory import move

def crear_orden_compra(proveedor,items,user_id=None,actor='usuario',expected_at='',note='',request_key=None):
    from backend.services.operations import valid_date
    expected_at=valid_date(expected_at)
    if not items: raise ValueError('Agrega productos a la orden de compra.')
    with transaction() as c:
        if request_key:
            prior=one(c,'SELECT id FROM purchase_orders WHERE request_key=?',(request_key,))
            if prior: return prior['id']
        if not one(c,'SELECT id FROM suppliers WHERE id=? AND active=1',(proveedor,)): raise ValueError('Selecciona un proveedor activo.')
        total=0;seen=set()
        for i in items:
            if type(i.get('quantity')) is not int or i['quantity']<=0 or type(i.get('cost_cents')) is not int or i['cost_cents']<0: raise ValueError('Cantidad o costo no válido.')
            if not one(c,'SELECT id FROM products WHERE id=?',(i['product_id'],)): raise ValueError('Producto no encontrado.')
            if i['product_id'] in seen: raise ValueError('Agrupa las cantidades de cada producto en una sola fila.')
            seen.add(i['product_id'])
            total+=i['quantity']*i['cost_cents']
        oid=c.execute('INSERT INTO purchase_orders(code,supplier_id,total_cents,actor,user_id,created_at,expected_at,note) VALUES(?,?,?,?,?,?,?,?)',(code('OC'),proveedor,total,actor,user_id,now(),expected_at,str(note)[:1000])).lastrowid
        for i in items: c.execute('INSERT INTO purchase_items(purchase_order_id,product_id,quantity,cost_cents) VALUES(?,?,?,?)',(oid,i['product_id'],i['quantity'],i['cost_cents']))
        if request_key: c.execute('UPDATE purchase_orders SET request_key=? WHERE id=?',(request_key,oid))
        audit(c,'purchase_orders',oid,'crear',user_id,actor);return oid
def receive(oid,user_id,d=None):
    d=d or {}
    with transaction() as c:
        key=str(d.get('request_key') or '')
        if key:
            prior=one(c,'SELECT * FROM purchase_receipts WHERE request_key=?',(key,))
            if prior:
                if prior['purchase_order_id']!=oid: raise ValueError('La referencia de recepción pertenece a otra compra.')
                return prior['id']
        po=one(c,'SELECT * FROM purchase_orders WHERE id=?',(oid,))
        if not po or po['status'] not in ['pendiente','parcial']: raise ValueError('Esta compra ya fue recibida o cancelada.')
        items=rows(c,'SELECT * FROM purchase_items WHERE purchase_order_id=?',(oid,))
        quantities={i['id']:i['quantity']-i['received_quantity'] for i in items}
        if 'items' in d:
            quantities={}
            for line in d['items']:
                if line.get('id') in quantities or line.get('id') not in {i['id'] for i in items}: raise ValueError('La recepción tiene una fila repetida o ajena a esta compra.')
                quantities[line['id']]=line.get('quantity')
        if not quantities or any(type(q) is not int or q<0 for q in quantities.values()) or not any(quantities.values()): raise ValueError('Ingresa al menos una unidad recibida.')
        for i in items:
            if quantities.get(i['id'],0)>i['quantity']-i['received_quantity']: raise ValueError('No puedes recibir más unidades de las pendientes.')
        rid=c.execute('INSERT INTO purchase_receipts(purchase_order_id,request_key,note,user_id,created_at) VALUES(?,?,?,?,?)',
          (oid,key or code('REC-OC'),str(d.get('note',''))[:1000],user_id,now())).lastrowid
        for i in items:
            qty=quantities.get(i['id'],0)
            if not qty: continue
            p=one(c,'SELECT stock,cost_cents,price_cents FROM products WHERE id=?',(i['product_id'],))
            cost=(p['stock']*p['cost_cents']+qty*i['cost_cents']+(p['stock']+qty)//2)//(p['stock']+qty)
            move(c,i['product_id'],quantity=qty,kind='compra',reason=f"{po['code']} · recepción #{rid}",user_id=user_id)
            c.execute('UPDATE products SET cost_cents=? WHERE id=?',(cost,i['product_id']))
            if cost!=p['cost_cents']:
                c.execute('INSERT INTO product_price_history(product_id,old_price_cents,new_price_cents,old_cost_cents,new_cost_cents,reason,user_id,created_at) VALUES(?,?,?,?,?,?,?,?)',
                  (i['product_id'],p['price_cents'],p['price_cents'],p['cost_cents'],cost,f"Costo ponderado · {po['code']}",user_id,now()))
            c.execute('UPDATE purchase_items SET received_quantity=received_quantity+? WHERE id=?',(qty,i['id']))
            c.execute('INSERT INTO purchase_receipt_items(receipt_id,purchase_item_id,quantity) VALUES(?,?,?)',(rid,i['id'],qty))
        remaining=one(c,'SELECT SUM(quantity-received_quantity) n FROM purchase_items WHERE purchase_order_id=?',(oid,))['n']
        c.execute('UPDATE purchase_orders SET status=?,received_at=? WHERE id=?',('parcial' if remaining else 'recibida',None if remaining else now(),oid))
        audit(c,'purchase_orders',oid,'recibir',user_id,detail={'receipt_id':rid,'quantities':quantities});return rid

def cancel_pending(oid,uid,reason):
    if len(str(reason).strip())<5: raise ValueError('Indica por qué cancelas el saldo pendiente.')
    with transaction() as c:
        po=one(c,'SELECT * FROM purchase_orders WHERE id=?',(oid,))
        if not po or po['status'] not in ['pendiente','parcial']: raise ValueError('Esta compra ya está cerrada.')
        c.execute("UPDATE purchase_orders SET status='cancelada' WHERE id=?",(oid,))
        audit(c,'purchase_orders',oid,'cancelar_saldo',uid,detail={'reason':reason})

def schedule(oid,uid,expected_at):
    from backend.services.operations import valid_date
    expected_at=valid_date(expected_at)
    if not expected_at: raise ValueError('Indica la fecha prevista de recepción.')
    with transaction() as c:
        po=one(c,'SELECT status FROM purchase_orders WHERE id=?',(oid,))
        if not po or po['status'] not in ['pendiente','parcial']: raise ValueError('Solo puedes reprogramar una compra abierta.')
        c.execute('UPDATE purchase_orders SET expected_at=? WHERE id=?',(expected_at,oid))
        audit(c,'purchase_orders',oid,'programar',uid,detail={'expected_at':expected_at})
