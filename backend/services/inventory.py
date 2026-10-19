from backend.db import transaction,connect,one,rows,now,audit

def refresh_alert(c,product_id):
    p=one(c,'SELECT * FROM products WHERE id=?',(product_id,))
    if p['stock']-p['reserved']<=p['minimum']:
        c.execute("INSERT INTO alerts(product_id,message,created_at) VALUES(?,?,?) ON CONFLICT(product_id) DO UPDATE SET status='activa',message=excluded.message,resolved_at=NULL",(product_id,f"{p['name']}: {p['stock']-p['reserved']} disponibles · mínimo {p['minimum']}",now()))
    else: c.execute("UPDATE alerts SET status='resuelta',resolved_at=? WHERE product_id=? AND status='activa'",(now(),product_id))
def move(c,product_id,quantity=0,reserved_delta=0,kind='ajuste',reason='',user_id=None,actor='usuario',order_id=None,at=None):
    p=one(c,'SELECT * FROM products WHERE id=?',(product_id,))
    if not p: raise ValueError('Producto no encontrado.')
    stock=p['stock']+quantity;reserved=p['reserved']+reserved_delta
    if stock<0 or reserved<0 or reserved>stock: raise ValueError(f"Stock insuficiente para {p['name']}.")
    c.execute('UPDATE products SET stock=?,reserved=? WHERE id=?',(stock,reserved,product_id))
    c.execute('INSERT INTO inventory_movements(product_id,kind,quantity,reserved_delta,balance,reason,order_id,user_id,actor,created_at,reserved_balance,available_before,available_after) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
              (product_id,kind,quantity,reserved_delta,stock,reason,order_id,user_id,actor,at or now(),reserved,p['stock']-p['reserved'],stock-reserved))
    refresh_alert(c,product_id)
def verificar_stock(sku):
    with connect() as c:
        p=one(c,'SELECT id,sku,stock,reserved,minimum FROM products WHERE sku=?',(sku,))
        if not p: raise ValueError('SKU no encontrado.')
        p['available']=p['stock']-p['reserved'];return p
def adjust(d,user_id):
    if not d.get('reason','').strip(): raise ValueError('Indica el motivo del movimiento.')
    if type(d.get('quantity')) is not int or not d['quantity']: raise ValueError('La cantidad debe ser un entero distinto de cero.')
    kind=d.get('kind','ajuste')
    if kind not in ['ajuste','merma','ingreso']: raise ValueError('Tipo de movimiento no permitido.')
    if kind=='merma' and d['quantity']>0: raise ValueError('Una merma debe retirar unidades.')
    if kind=='ingreso' and d['quantity']<0: raise ValueError('Un ingreso debe sumar unidades.')
    with transaction() as c:
        move(c,d['product_id'],d['quantity'],kind=d.get('kind','ajuste'),reason=d['reason'],user_id=user_id)
        audit(c,'inventory',d['product_id'],'ajuste',user_id,detail=d)
