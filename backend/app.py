import json,secrets,sqlite3,io,csv,asyncio,logging
from contextlib import asynccontextmanager
from pathlib import Path
from PIL import Image,UnidentifiedImageError
from fastapi import FastAPI,Request,Response,Depends,HTTPException,UploadFile,File,Form
from fastapi.responses import FileResponse,JSONResponse,StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from backend.db import ROOT,connect,transaction,rows,one,now,config,init_db,audit
from backend.services import catalog,customers,orders,inventory,suppliers,reports,operations,catalog_quality,ml_history,predictions,ml_lab,ml_automation
from backend.services.payments import provider

async def expiration_loop():
    while True:
        await asyncio.sleep(60)
        try:
            with transaction() as c: orders.expire(c)
            operations.snapshot()
            await asyncio.to_thread(ml_history.capture)
            await asyncio.to_thread(ml_automation.tick)
        except Exception: logging.exception('No se pudo actualizar el cierre operativo.')
@asynccontextmanager
async def lifespan(app):
    init_db()
    ml_lab.recover_jobs()
    ml_automation.init()
    ml_automation.recover()
    with transaction() as c: orders.expire(c)
    operations.snapshot()
    await asyncio.to_thread(ml_history.capture)
    await asyncio.to_thread(ml_automation.tick)
    task=asyncio.create_task(expiration_loop())
    yield
    task.cancel()
app=FastAPI(title='Tienda de repuestos · API',lifespan=lifespan)
@app.exception_handler(ValueError)
async def value_error(request,exc): return JSONResponse({'detail':str(exc)},status_code=400)
@app.exception_handler(sqlite3.IntegrityError)
async def integrity_error(request,exc): return JSONResponse({'detail':'Los datos están duplicados o tienen una referencia no válida.'},status_code=400)
@app.exception_handler(RequestValidationError)
async def validation_error(request,exc): return JSONResponse({'detail':'Revisa los campos obligatorios y sus formatos.'},status_code=422)
@app.middleware('http')
async def secure_headers(request,call_next):
    if request.method not in ['GET','HEAD','OPTIONS']:
        origin=request.headers.get('origin')
        if origin and origin not in ['http://127.0.0.1:8000','http://localhost:8000','http://127.0.0.1:5173','http://localhost:5173']:
            return JSONResponse({'detail':'Origen no autorizado.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='same-origin'
    if request.url.path.startswith('/api') or response.headers.get('content-type','').startswith('text/html'):
        response.headers['Cache-Control']='no-store'
    return response
def current_user(request:Request):
    token=request.cookies.get('session','')
    with connect() as c:
        u=one(c,'SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at>?',(token,now()))
        return customers.public_user(u) if u else None
def require_user(u=Depends(current_user)):
    if not u: raise HTTPException(401,'Inicia sesión para continuar.')
    return u
def staff(u=Depends(require_user)):
    if u['role'] not in ['admin','empleado']: raise HTTPException(403,'No tienes acceso a esta sección.')
    return u
def admin(u=Depends(staff)):
    if u['role']!='admin': raise HTTPException(403,'Esta sección requiere un administrador.')
    return u
def owner(record,u,token=''):
    if not record: raise HTTPException(404,'Registro no encontrado.')
    if u and (u['role'] in ['admin','empleado'] or record['user_id']==u['id']): return
    if token and secrets.compare_digest(record['guest_token'],token): return
    raise HTTPException(403,'No tienes acceso a este registro.')
def session_response(response,result):
    token,u=result;response.set_cookie('session',token,httponly=True,samesite='lax',max_age=604800);return u
@app.get('/api/config')
def get_config(): return config()
@app.get('/api/health')
def health(): return {'ok':True}
@app.post('/api/auth/login')
def login(d:dict,response:Response): return session_response(response,customers.login(d.get('email',''),d.get('password',''),d.get('admin',False)))
@app.post('/api/auth/register')
def register(d:dict,response:Response): return session_response(response,customers.register(d))
@app.post('/api/auth/logout')
def logout(request:Request,response:Response):
    with transaction() as c: c.execute('DELETE FROM sessions WHERE token=?',(request.cookies.get('session',''),))
    response.delete_cookie('session');return {'ok':True}
@app.get('/api/auth/me')
def me(u=Depends(current_user)): return u
@app.get('/api/categories')
def categories():
    with connect() as c: return rows(c,'SELECT c.*,(SELECT COUNT(*) FROM products p WHERE p.active=1 AND (p.category_id=c.id OR p.category_id IN (SELECT id FROM categories WHERE parent_id=c.id))) count FROM categories c')
@app.get('/api/brands')
def brands():
    with connect() as c: return rows(c,'SELECT * FROM brands ORDER BY name')
@app.get('/api/vehicles')
def vehicles():
    with connect() as c: return rows(c,'SELECT * FROM vehicles ORDER BY brand,model,year DESC,version')
@app.get('/api/ubigeo')
def ubigeo():
    with connect() as c: return rows(c,'SELECT * FROM ubigeo ORDER BY department,province,district')
@app.get('/api/products')
def products(q:str='',vehicle:int|None=None,category:str='',brand:str='',sort:str='recommended',page:int=1,limit:int=20,in_stock:bool=False,offer:bool=False,max_price:int|None=None):
    return catalog.buscar_repuestos(vehicle,q,category,brand,sort,page,limit,in_stock,offer,max_price)
@app.get('/api/products/{pid}')
def product(pid:int,vehicle:int|None=None): return catalog.product_detail(pid,vehicle)
@app.post('/api/events')
def event(d:dict,u=Depends(current_user)):
    if d.get('type') not in ['search','product_view','cart_add','cart_remove','cart_update']: raise ValueError('Evento no válido.')
    with transaction() as c: c.execute('INSERT INTO events(type,product_id,vehicle_id,user_id,session_id,payload,created_at) VALUES(?,?,?,?,?,?,?)',(d['type'],d.get('product_id'),d.get('vehicle_id'),u['id'] if u else None,str(d.get('session_id','guest'))[:100],json.dumps(d.get('payload',{}))[:5000],now()))
    return {'ok':True}
@app.get('/api/account')
def account(u=Depends(require_user)): return customers.profile(u['id'])
@app.put('/api/account')
def update_account(d:dict,u=Depends(require_user)): return customers.profile(u['id'],d)
@app.put('/api/account/garage')
def garage(d:dict,u=Depends(require_user)):
    with transaction() as c:
        c.execute('DELETE FROM garage WHERE user_id=?',(u['id'],))
        for v in set(d.get('vehicles',[])): c.execute('INSERT INTO garage(user_id,vehicle_id,active) VALUES(?,?,?)',(u['id'],v,int(v==d.get('active'))))
    return {'ok':True}
@app.post('/api/account/addresses')
def address(d:dict,u=Depends(require_user)):
    if not all(d.get(k) for k in ['label','street','ubigeo']): raise ValueError('Completa la dirección.')
    with transaction() as c: c.execute('INSERT INTO addresses(user_id,label,street,ubigeo,reference) VALUES(?,?,?,?,?)',(u['id'],d['label'],d['street'],d['ubigeo'],d.get('reference','')))
    return {'ok':True}
@app.delete('/api/account/addresses/{aid}')
def delete_address(aid:int,u=Depends(require_user)):
    with transaction() as c: c.execute('DELETE FROM addresses WHERE id=? AND user_id=?',(aid,u['id']))
    return {'ok':True}
@app.post('/api/quotes')
def quote(d:dict,u=Depends(current_user)): return orders.crear_cotizacion(d.get('items',[]),u['id'] if u else None,d.get('customer_name',u['name'] if u else 'Cliente'))
@app.get('/api/quotes/{qid}')
def quote_detail(qid:int,token:str='',u=Depends(current_user)):
    with connect() as c:
        q=one(c,'SELECT * FROM quotes WHERE id=?',(qid,));owner(q,u,token)
        q['items']=rows(c,'SELECT i.*,p.name,p.sku FROM quote_items i JOIN products p ON p.id=i.product_id WHERE quote_id=?',(qid,))
        if q['status']=='vigente' and q['expires_at']<now(): q['status']='vencida'
        return q
@app.post('/api/orders')
def create_order(d:dict,u=Depends(current_user)): return orders.create_order(d,u['id'] if u else None)
@app.get('/api/account/orders')
def my_orders(u=Depends(require_user)):
    with transaction() as c:
        orders.expire(c)
        return rows(c,'SELECT id,code,created_at,status,total_cents,payment_method FROM orders WHERE user_id=? ORDER BY id DESC',(u['id'],))
@app.get('/api/account/quotes')
def my_quotes(u=Depends(require_user)):
    with connect() as c: return rows(c,'SELECT id,code,created_at,expires_at,status,total_cents FROM quotes WHERE user_id=? ORDER BY id DESC',(u['id'],))
@app.get('/api/orders/{oid}')
def order_detail(oid:int,token:str='',u=Depends(current_user)):
    o=orders.order_detail(oid);owner(o,u,token)
    if not u or u['role']=='cliente':
        for i in o['items']: i.pop('cost_cents',None)
    return o
@app.post('/api/orders/{oid}/cancel')
def cancel(oid:int,d:dict,u=Depends(current_user)):
    with transaction() as c:
        o=one(c,'SELECT * FROM orders WHERE id=?',(oid,));owner(o,u,d.get('token',''));orders.transition(c,o,'cancelado',u['id'] if u else None)
    return {'ok':True}
async def save_image(file,folder):
    raw=await file.read(8*1024*1024+1)
    if len(raw)>8*1024*1024: raise ValueError('La imagen supera los 8 MB.')
    try:
        im=Image.open(io.BytesIO(raw));im.load()
        if im.width*im.height>25000000: raise ValueError('La imagen es demasiado grande.')
        im=im.convert('RGB');im.thumbnail((1400,1400))
    except (UnidentifiedImageError,OSError): raise ValueError('Adjunta una imagen JPG, PNG o WebP válida.')
    folder.mkdir(parents=True,exist_ok=True);name=secrets.token_hex(12)
    im.save(folder/(name+'.webp'),'WEBP',quality=88);im.thumbnail((360,360));im.save(folder/(name+'-thumb.webp'),'WEBP',quality=85)
    if folder.is_relative_to(ROOT/'backend/static'):
        return '/media/'+str((folder/(name+'.webp')).relative_to(ROOT/'backend/static')).replace('\\','/'),'/media/'+str((folder/(name+'-thumb.webp')).relative_to(ROOT/'backend/static')).replace('\\','/')
    return name+'.webp',name+'-thumb.webp'
@app.post('/api/orders/{oid}/payment')
async def submit_payment(oid:int,token:str='',file:UploadFile|None=File(None),u=Depends(current_user)):
    o=orders.order_detail(oid);owner(o,u,token)
    if o['status']!='pendiente de pago': raise ValueError('Este pedido no admite un nuevo pago.')
    voucher=''
    if file: voucher,_=await save_image(file,ROOT/'data/vouchers')
    provider.submit(oid,voucher,u['id'] if u else None);return {'ok':True}
@app.get('/api/orders/{oid}/voucher')
def voucher(oid:int,token:str='',u=Depends(current_user)):
    o=orders.order_detail(oid);owner(o,u,token)
    filename=Path(o['payment']['voucher']).name
    path=ROOT/'data/vouchers'/filename
    if not filename or not path.is_file(): raise HTTPException(404,'No hay constancia adjunta.')
    return FileResponse(path,media_type='image/webp')
@app.post('/api/complaints')
def complaint(d:dict,u=Depends(current_user)):
    fields=['name','email','document','phone','type','detail','request']
    if any(not d.get(k,'').strip() for k in fields): raise ValueError('Completa los datos del reclamo.')
    if not d.get('consent'): raise ValueError('Acepta el tratamiento de datos.')
    with transaction() as c:
        code=orders.code('REC')
        c.execute('INSERT INTO complaints(code,user_id,name,email,document,phone,type,order_code,detail,request,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(code,u['id'] if u else None,d['name'],d['email'],d['document'],d['phone'],d['type'],d.get('order_code',''),d['detail'],d['request'],now()))
        return {'code':code}
@app.get('/api/admin/dashboard')
def dashboard(u=Depends(staff)):
    with transaction() as c: orders.expire(c)
    d=reports.dashboard()
    if u['role']=='empleado':
        for k in ['cost','profit','margin','categories','products']: d.pop(k,None)
    return d
@app.get('/api/admin/reports')
def report(start:str,end:str,u=Depends(admin)): return reports.resumen_ventas((start,end))
@app.get('/api/admin/products')
def admin_products(q:str='',category:str='',sort:str='recommended',direction:str='asc',status:str='',page:int=1,limit:int=20,u=Depends(staff)): return catalog.buscar_repuestos(texto=q,category=category,sort=sort,page=page,limit=limit,admin=True,direction=direction,status=status)
@app.get('/api/admin/products/{pid}')
def admin_product(pid:int,u=Depends(staff)): return catalog.product_detail(pid,admin=True)
@app.post('/api/admin/products')
def add_product(d:dict,u=Depends(staff)): return {'id':catalog.save_product(d,u['id'])}
@app.put('/api/admin/products/{pid}')
def edit_product(pid:int,d:dict,u=Depends(staff)): return {'id':catalog.save_product(d,u['id'],pid)}
@app.delete('/api/admin/products/{pid}')
def hide_product(pid:int,u=Depends(staff)):
    with transaction() as c: c.execute('UPDATE products SET active=0 WHERE id=?',(pid,));audit(c,'products',pid,'ocultar',u['id'])
    return {'ok':True}
@app.post('/api/admin/products/{pid}/images')
async def images(pid:int,files:list[UploadFile]=File(...),u=Depends(staff)):
    p=catalog.product_detail(pid,admin=True)
    if len(files)>10: raise ValueError('Sube hasta 10 imágenes por vez.')
    for file in files:
        url,thumb=await save_image(file,ROOT/'backend/static/products'/p['sku'])
        with transaction() as c:
            has_image=one(c,'SELECT id FROM product_images WHERE product_id=?',(pid,))
            c.execute('INSERT INTO product_images(product_id,url,thumb,is_primary) VALUES(?,?,?,?)',(pid,url,thumb,int(not has_image)))
    return {'ok':True}
@app.put('/api/admin/images/{iid}/primary')
def primary_image(iid:int,u=Depends(staff)):
    with transaction() as c:
        im=one(c,'SELECT * FROM product_images WHERE id=?',(iid,))
        if not im: raise ValueError('Imagen no encontrada.')
        c.execute('UPDATE product_images SET is_primary=0 WHERE product_id=?',(im['product_id'],));c.execute('UPDATE product_images SET is_primary=1 WHERE id=?',(iid,))
    return {'ok':True}
@app.delete('/api/admin/images/{iid}')
def remove_image(iid:int,u=Depends(staff)):
    with transaction() as c: c.execute('DELETE FROM product_images WHERE id=?',(iid,))
    return {'ok':True}
@app.post('/api/admin/inventory')
def adjust(d:dict,u=Depends(staff)): inventory.adjust(d,u['id']);return {'ok':True}
@app.post('/api/admin/orders/{oid}/verify')
def verify_payment(oid:int,d:dict,u=Depends(staff)): provider.verify(oid,bool(d.get('accepted')),u['id'],d.get('note',''));return {'ok':True}
@app.put('/api/admin/orders/{oid}/status')
def status(oid:int,d:dict,u=Depends(staff)):
    if d.get('status')=='pagado': raise ValueError('Confirma el pago desde la verificación de pagos.')
    if d.get('status') in ['preparando','enviado','listo para recojo','entregado']:
        operations.save_shipment(oid,d,u['id']);return {'ok':True}
    with transaction() as c:
        o=one(c,'SELECT * FROM orders WHERE id=?',(oid,))
        if not o: raise ValueError('Pedido no encontrado.')
        orders.transition(c,o,d['status'],u['id'],note=d.get('note',''))
        if d.get('tracking'): c.execute('UPDATE orders SET tracking=? WHERE id=?',(d['tracking'],oid))
    return {'ok':True}
@app.post('/api/admin/purchases')
def purchase(d:dict,u=Depends(staff)): return {'id':suppliers.crear_orden_compra(d['supplier_id'],d['items'],u['id'],expected_at=d.get('expected_at',''),note=d.get('note',''),request_key=d.get('request_key'))}
@app.post('/api/admin/purchases/{pid}/receive')
def receive(pid:int,d:dict|None=None,u=Depends(staff)): return {'ok':True,'receipt_id':suppliers.receive(pid,u['id'],d)}
@app.post('/api/admin/purchases/{pid}/cancel')
def cancel_purchase(pid:int,d:dict,u=Depends(staff)):
    suppliers.cancel_pending(pid,u['id'],d.get('reason',''));return {'ok':True}
@app.put('/api/admin/purchases/{pid}/schedule')
def schedule_purchase(pid:int,d:dict,u=Depends(staff)):
    suppliers.schedule(pid,u['id'],d.get('expected_at',''));return {'ok':True}
@app.get('/api/admin/purchases/{pid}')
def purchase_detail(pid:int,u=Depends(staff)):
    with connect() as c:
        po=one(c,'SELECT p.*,s.name supplier FROM purchase_orders p JOIN suppliers s ON s.id=p.supplier_id WHERE p.id=?',(pid,))
        if not po: raise ValueError('Compra no encontrada.')
        po['items']=rows(c,'SELECT i.*,p.name,p.sku FROM purchase_items i JOIN products p ON p.id=i.product_id WHERE purchase_order_id=?',(pid,))
        po['receipts']=rows(c,'''SELECT r.*,u.name user_name,(SELECT SUM(quantity) FROM purchase_receipt_items WHERE receipt_id=r.id) units
          FROM purchase_receipts r LEFT JOIN users u ON u.id=r.user_id WHERE purchase_order_id=? ORDER BY r.id DESC''',(pid,))
        return po
@app.get('/api/admin/operations/inventory')
def inventory_overview(q:str='',status:str='',sort:str='name',direction:str='asc',page:int=1,category:str='',supplier:str='',replenish:bool=False,u=Depends(staff)):
    data=operations.inventory_rows()
    summary={'products':len(data),'low':sum(r['status'] in ['bajo','agotado'] for r in data),
      'incoming':sum(r['incoming'] for r in data),'reserved':sum(r['reserved'] for r in data),'value_cents':sum(r['value_cents'] for r in data)}
    if u['role']!='admin':
        summary.pop('value_cents')
        for r in data: r.pop('value_cents',None)
    if category: data=[r for r in data if r['category']==category]
    if supplier: data=[r for r in data if str(r['supplier_id'])==supplier]
    if replenish: data=[r for r in data if r['suggested']>0]
    return {**operations.page(data,q,status,sort,direction,page),'summary':summary}
@app.put('/api/admin/operations/inventory/{pid}/policy')
def stock_policy(pid:int,d:dict,u=Depends(staff)): operations.save_policy(pid,d,u['id']);return {'ok':True}
@app.get('/api/admin/operations/inventory/{pid}/activity')
def stock_activity(pid:int,u=Depends(staff)):
    with connect() as c:
        reserved=rows(c,"""SELECT o.id,o.code,o.customer_name,o.status,o.expires_at,i.quantity FROM orders o JOIN order_items i ON i.order_id=o.id
          WHERE i.product_id=? AND o.status IN ('pendiente de pago','pago por verificar') ORDER BY o.expires_at""",(pid,))
        incoming=rows(c,"""SELECT po.id,po.code,po.expected_at,s.name supplier,i.quantity-i.received_quantity pending
          FROM purchase_items i JOIN purchase_orders po ON po.id=i.purchase_order_id JOIN suppliers s ON s.id=po.supplier_id
          WHERE i.product_id=? AND po.status IN ('pendiente','parcial') AND i.quantity>i.received_quantity ORDER BY po.expected_at""",(pid,))
        return {'reservations':reserved,'incoming':incoming}
@app.post('/api/admin/operations/inventory/{pid}/count')
def count_stock(pid:int,d:dict,u=Depends(staff)): return operations.count_stock(pid,d,u['id'])
@app.get('/api/admin/operations/shipments')
def shipments(q:str='',status:str='',delivery:str='',sort:str='created_at',direction:str='desc',page:int=1,incidents:bool=False,u=Depends(staff)):
    data=operations.shipment_rows()
    summary={s:sum(r['status']==s for r in data) for s in ['pagado','preparando','enviado','listo para recojo','entregado']}
    summary['incidents']=sum(bool(r['incident']) for r in data)
    if delivery: data=[r for r in data if r['delivery']==delivery]
    if incidents: data=[r for r in data if r['incident']]
    return {**operations.page(data,q,status,sort,direction,page),'summary':summary}
@app.put('/api/admin/operations/shipments/{oid}')
def edit_shipment(oid:int,d:dict,u=Depends(staff)): operations.save_shipment(oid,d,u['id']);return {'ok':True}
@app.get('/api/admin/operations/quality')
def quality(u=Depends(admin)): return operations.quality()
@app.get('/api/admin/operations/catalog-audit')
def catalog_audit(q:str='',severity:str='',issue:str='',sort:str='sku',direction:str='asc',page:int=1,u=Depends(admin)):
    report=catalog_quality.audit_catalog()
    findings=report.pop('issues');report.pop('rows')
    if severity: findings=[r for r in findings if r['severity']==severity]
    if issue: findings=[r for r in findings if r['code']==issue]
    return {**report,**operations.page(findings,q,'',sort,direction,page)}
@app.get('/api/admin/operations/export/{entity}')
def export_operations(entity:str,u=Depends(admin)):
    if entity=='inventory': return csv_response(operations.inventory_rows(),'inventario')
    if entity in ['catalog','catalog-issues']:
        report=catalog_quality.audit_catalog()
        return csv_response(report['rows'] if entity=='catalog' else report['issues'],entity)
    with connect() as c:
        if entity=='observations': query='SELECT s.*,p.sku FROM stock_observations s JOIN products p ON p.id=s.product_id ORDER BY s.date,p.id'
        elif entity=='movements': query='SELECT m.*,p.sku FROM inventory_movements m JOIN products p ON p.id=m.product_id ORDER BY m.id'
        elif entity=='prices': query='SELECT h.*,p.sku FROM product_price_history h JOIN products p ON p.id=h.product_id ORDER BY h.id'
        else: raise ValueError('Exportación no disponible.')
        cursor=c.execute(query);columns=[column[0] for column in cursor.description];data=[dict(r) for r in cursor.fetchall()]
    return csv_response(data,entity,columns)
LISTS={
 'counts':('SELECT ic.*,p.sku,p.name,u.name user_name FROM inventory_counts ic JOIN products p ON p.id=ic.product_id LEFT JOIN users u ON u.id=ic.user_id','created_at'),
 'audit':("SELECT a.*,COALESCE(u.name,'Sistema') user_name FROM audit a LEFT JOIN users u ON u.id=a.user_id",'created_at'),
 'orders':('SELECT id,code,customer_name,email,status,payment_method,total_cents,created_at FROM orders','created_at'),
 'inventory':('SELECT p.id,p.sku,p.name,b.name brand,p.stock,p.reserved,p.stock-p.reserved available,p.minimum FROM products p JOIN brands b ON b.id=p.brand_id','id'),
 'movements':('SELECT m.*,p.sku,p.name,COALESCE(u.name,\'Sistema\') user_name FROM inventory_movements m JOIN products p ON p.id=m.product_id LEFT JOIN users u ON u.id=m.user_id','created_at'),
 'suppliers':('SELECT * FROM suppliers','id'),
 'purchases':('SELECT p.*,s.name supplier FROM purchase_orders p JOIN suppliers s ON s.id=p.supplier_id','created_at'),
 'customers':("SELECT id,name,email,phone,document,created_at FROM users WHERE role='cliente'",'id'),
 'quotes':('SELECT id,code,customer_name,total_cents,status,created_at,expires_at FROM quotes','created_at'),
 'complaints':('SELECT * FROM complaints','created_at'),
 'payments':('SELECT p.*,o.code,o.customer_name FROM payments p JOIN orders o ON o.id=p.order_id','created_at'),
 'alerts':('SELECT a.*,p.sku,p.name,p.stock-p.reserved available,p.minimum FROM alerts a JOIN products p ON p.id=a.product_id','created_at'),
 'vehicles':('SELECT * FROM vehicles','id'), 'categories':('SELECT * FROM categories','id'), 'brands':('SELECT * FROM brands','id')}
@app.get('/api/admin/list/{entity}')
def listing(entity:str,q:str='',status:str='',sort:str='',direction:str='desc',page:int=1,limit:int=15,product_id:int|None=None,start:str='',end:str='',u=Depends(staff)):
    if entity not in LISTS: raise HTTPException(404,'Sección no encontrada.')
    if entity in ['payments','audit'] and u['role']!='admin': raise HTTPException(403,'Acceso reservado al administrador.')
    with connect() as c: result=rows(c,LISTS[entity][0])
    if q: result=[r for r in result if catalog.normalize(q) in catalog.normalize(' '.join(str(v) for v in r.values()))]
    if status: result=[r for r in result if r.get('status')==status]
    if start:
        operations.valid_date(start);result=[r for r in result if (r.get('created_at') or '')[:10]>=start]
    if end:
        operations.valid_date(end);result=[r for r in result if (r.get('created_at') or '')[:10]<=end]
    if product_id and entity in ['movements','alerts']: result=[r for r in result if r.get('product_id')==product_id]
    sort=sort or LISTS[entity][1]
    if result and sort in result[0]: result.sort(key=lambda r:(r[sort] is not None,r[sort]),reverse=direction!='asc')
    total=len(result);limit=min(500,max(1,limit));page=max(1,page)
    return {'items':result[(page-1)*limit:page*limit],'total':total,'page':page,'pages':(total+limit-1)//limit}
@app.post('/api/admin/manage/{entity}')
def manage(entity:str,d:dict,u=Depends(staff)):
    allowed={'suppliers':['name','ruc','email','phone','contact','active'],'categories':['name','slug','parent_id','image'],'brands':['name'],'vehicles':['brand','model','year','version','tipo_vehiculo'],'complaints':['status','response']}
    if entity not in allowed: raise ValueError('Operación no válida.')
    fields=[k for k in allowed[entity] if k in d];values=[d[k] for k in fields]
    if not fields: raise ValueError('Completa los datos.')
    with transaction() as c:
        if d.get('id'): c.execute('UPDATE '+entity+' SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',values+[d['id']]);rid=d['id']
        else: rid=c.execute('INSERT INTO '+entity+'('+','.join(fields)+') VALUES('+','.join('?' for _ in fields)+')',values).lastrowid
        audit(c,entity,rid,'guardar',u['id'])
    return {'id':rid}
@app.put('/api/admin/config')
def save_config(d:dict,u=Depends(admin)):
    cfg=config()
    for k in ['name','legal_name','ruc','address','phone','whatsapp','email','hours','bank_account','shipping','payments','igv_percent']:
        if k in d: cfg[k]=d[k]
    if not cfg['name'].strip() or not cfg['payments']: raise ValueError('Completa el nombre y al menos un medio de pago.')
    if not isinstance(cfg['igv_percent'],int) or not 0<=cfg['igv_percent']<=30: raise ValueError('IGV no válido.')
    if any(type(z.get('cents')) is not int or z['cents']<0 for z in cfg['shipping']): raise ValueError('Tarifa de envío no válida.')
    cfg['ASSISTANT_ENABLED']=False
    temp=ROOT/'store.config.tmp';temp.write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(ROOT/'store.config.json')
    with transaction() as c: audit(c,'config','store','guardar',u['id'])
    return cfg
def csv_response(data,name,columns=None):
    f=io.StringIO();f.write('\ufeff')
    if data or columns:
        w=csv.DictWriter(f,fieldnames=columns or data[0].keys());w.writeheader()
        for row in data: w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in row.items()})
    return Response(f.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{name}.csv"'})
@app.get('/api/admin/export/products')
def export_products(u=Depends(staff)):
    with connect() as c:
        data=rows(c,'SELECT id,sku,name,brand_id,category_id,price_cents,cost_cents,minimum,old_price_cents,universal,active,featured,oem,specs,description FROM products')
        for p in data:
            p['compatibility']=json.dumps(rows(c,'SELECT brand,model,year_from,year_to,version FROM compatibility WHERE product_id=?',(p.pop('id'),)),ensure_ascii=False)
        return csv_response(data,'productos')
@app.get('/api/admin/export/finance')
def export_finance(start:str,end:str,u=Depends(admin)): return csv_response(reports.resumen_ventas((start,end))['products'],'finanzas')
@app.post('/api/admin/import/products')
async def import_products(file:UploadFile=File(...),u=Depends(staff)):
    raw=await file.read(2*1024*1024+1)
    if len(raw)>2*1024*1024: raise ValueError('El CSV supera 2 MB.')
    try: data=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    except UnicodeError: raise ValueError('El archivo debe usar UTF-8.')
    if not data or len(data)>2000: raise ValueError('Importa entre 1 y 2000 filas.')
    results=[]
    for n,d in enumerate(data,2):
        try:
            for k in ['brand_id','category_id','price_cents','cost_cents','minimum','old_price_cents','universal','active','featured']: d[k]=int(d.get(k) or 0)
            d['specs']=json.loads(d.get('specs') or '{}')
            with connect() as c: p=one(c,'SELECT id FROM products WHERE sku=?',(d['sku'],))
            d['compatibility']=json.loads(d['compatibility']) if d.get('compatibility') else catalog.product_detail(p['id'],admin=True)['compatibility'] if p else []
            catalog.save_product(d,u['id'],p['id'] if p else None)
        except (ValueError,KeyError,sqlite3.Error) as e: results.append({'row':n,'error':str(e)})
    return {'imported':len(data)-len(results),'errors':results}

@app.get('/api/admin/ml/overview')
def ml_overview(u=Depends(admin)): return predictions.overview()
@app.get('/api/admin/ml/evaluation')
def ml_evaluation(u=Depends(admin)): return predictions.evaluation()
@app.get('/api/admin/ml/images/{name}')
def ml_image(name:str,u=Depends(admin)): return FileResponse(predictions.asset(name))
@app.post('/api/admin/ml/calculate')
def ml_calculate(d:dict,u=Depends(admin)): return predictions.calculate(d.get('source',''),u['id'])
@app.post('/api/admin/ml/capture')
def ml_capture(u=Depends(admin)):
    ml_history.capture()
    return predictions.readiness()
@app.get('/api/admin/ml/runs/{rid}')
def ml_run(rid:int,q:str='',rotation:str='',review:str='',sort:str='prediction',direction:str='desc',page:int=1,limit:int=15,u=Depends(admin)):
    return predictions.listing(rid,q,rotation,review,sort,direction,page,limit)
@app.get('/api/admin/ml/predictions/{pid}')
def ml_prediction(pid:int,u=Depends(admin)): return predictions.detail(pid)
@app.get('/api/admin/ml/runs/{rid}/export')
def ml_export(rid:int,u=Depends(admin)):
    return Response(predictions.export(rid),media_type='text/csv',headers={'Content-Disposition':f'attachment; filename="pronostico-{rid}.csv"'})

@app.get('/api/admin/ml/automation')
def automation_status(u=Depends(admin)): return ml_automation.status()
@app.post('/api/admin/ml/automation/review')
def automation_review(u=Depends(admin)): return ml_automation.tick(force=True,uid=u['id'])
@app.post('/api/admin/ml/automation/settings')
def automation_settings(d:dict,u=Depends(admin)): return ml_automation.configure(d.get('enabled'),u['id'])

@app.get('/api/admin/ml/lab')
def lab_list(dataset:str|None=None,u=Depends(admin)): return ml_lab.listing(dataset)
@app.post('/api/admin/ml/lab/datasets')
def lab_create(d:dict,u=Depends(admin)):
    return {'id':ml_lab.create(str(d.get('name','')),d.get('frequency'),str(d.get('source','')),u['id'])}
@app.post('/api/admin/ml/lab/demo')
def lab_demo(u=Depends(admin)): return ml_lab.demo(u['id'])
@app.post('/api/admin/ml/lab/datasets/{did}/reset')
def lab_reset(did:str,u=Depends(admin)): return ml_lab.reset(did,u['id'])
@app.post('/api/admin/ml/lab/preview')
async def lab_preview(dataset:str=Form(...),mapping:str=Form('{}'),file:UploadFile=File(...),u=Depends(admin)):
    try: columns=json.loads(mapping)
    except (ValueError,TypeError): raise ValueError('La selección de columnas no es válida.')
    if not isinstance(columns,dict): raise ValueError('La selección de columnas no es válida.')
    content=await file.read(8*1024*1024+1)
    return await asyncio.to_thread(ml_lab.preview,dataset,content,file.filename or '',columns,u['id'])
@app.post('/api/admin/ml/lab/batches/{bid}/confirm')
def lab_confirm(bid:str,u=Depends(admin)): return ml_lab.confirm(bid,u['id'])
@app.get('/api/admin/ml/lab/examples/{name}')
def lab_example(name:str,u=Depends(admin)): return FileResponse(ml_lab.example_path(name),filename=name)
@app.post('/api/admin/ml/lab/datasets/{did}/jobs')
def lab_job(did:str,d:dict,u=Depends(admin)):
    return ml_lab.start_job(did,d.get('action'),u['id'],d.get('versions'))
@app.get('/api/admin/ml/lab/jobs/{jid}')
def lab_result(jid:str,q:str='',page:int=1,u=Depends(admin)): return ml_lab.results(jid,q,page)
@app.get('/api/admin/ml/lab/jobs/{jid}/export')
def lab_export(jid:str,u=Depends(admin)):
    return Response(ml_lab.export(jid),media_type='text/csv',headers={'Content-Disposition':'attachment; filename="predicciones-laboratorio.csv"'})
@app.post('/api/admin/ml/lab/datasets/{did}/activate')
def lab_activate(did:str,d:dict,u=Depends(admin)): return ml_lab.activate(did,d.get('version'),u['id'])
@app.get('/api/admin/ml/lab/versions/{vid}/download')
def lab_model_download(vid:str,u=Depends(admin)):
    path,label=ml_lab.version_file(vid)
    return FileResponse(path,filename=f'RODA-laboratorio-{label}.joblib',media_type='application/octet-stream')

app.mount('/media',StaticFiles(directory=ROOT/'backend/static'),name='media')
DIST=ROOT/'frontend/dist'
@app.get('/{path:path}')
def frontend(path:str):
    if path.startswith('api/'): raise HTTPException(404,'Ruta no encontrada.')
    file=(DIST/path).resolve()
    if file.is_relative_to(DIST.resolve()) and file.is_file(): return FileResponse(file)
    if (DIST/'index.html').exists(): return FileResponse(DIST/'index.html')
    return JSONResponse({'detail':'Ejecuta el script de arranque para compilar la tienda.'},status_code=503)
