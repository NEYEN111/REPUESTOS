"""Short transaction and access-control verification against an isolated database copy."""
import os,sys,sqlite3,json,tempfile,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
folder=ROOT/'.tmp';folder.mkdir(exist_ok=True)
fd,target=tempfile.mkstemp(suffix='.db',dir=folder);os.close(fd)
src=sqlite3.connect(ROOT/'data/store.db');dst=sqlite3.connect(target);src.backup(dst);dst.close();src.close()
os.environ['DATABASE_PATH']=target
os.environ['ML_LAB_DIR']=target+'.lab'
from fastapi.testclient import TestClient
from PIL import Image
from backend.app import app
from backend.db import connect,transaction,one
from backend.services.orders import expire

def run():
    with TestClient(app) as customer,TestClient(app) as admin,TestClient(app) as employee:
        def get(client,path):
            r=client.get('/api'+path);assert r.status_code==200,(path,r.text);return r.json()
        def post(client,path,d):
            r=client.post('/api'+path,json=d);assert r.status_code==200,(path,r.text);return r.json()
        post(customer,'/auth/login',{'email':'cliente@roda.pe','password':'Roda2026!'})
        post(admin,'/auth/login',{'email':'admin@roda.pe','password':'Roda2026!'})
        post(employee,'/auth/login',{'email':'empleado@roda.pe','password':'Roda2026!'})
        assert employee.get('/api/admin/reports?start=2026-01-01&end=2026-12-31').status_code==403
        assert employee.put('/api/admin/config',json={}).status_code==403
        assert customer.get('/api/admin/dashboard').status_code==403
        vehicles=get(customer,'/vehicles');v=next(v for v in vehicles if v['brand']=='Toyota' and v['model']=='Yaris' and v['year']==2018)
        products=get(customer,f"/products?category=frenos&vehicle={v['id']}")['items'];assert products and all(p['compatible'] for p in products)
        assert get(customer,'/products?q=pastilas')['total']>0
        exact=get(admin,'/admin/products?q=RP-025-04&limit=8')
        assert exact['total']==1 and exact['items'][0]['sku']=='RP-025-04'
        assert get(admin,'/admin/products?q=RP-999-99&limit=8')['total']==0
        p=next(p for p in products if p['available']>2);pid=p['id'];start=get(admin,f'/admin/products/{pid}')
        quote=post(customer,'/quotes',{'items':[{'product_id':pid,'quantity':1}]})
        q=get(customer,f"/quotes/{quote['id']}");assert q['total_cents']==p['price_cents']
        d={'items':[{'product_id':pid,'quantity':1}],'customer_name':'Prueba integral','email':'test@example.com','phone':'987654321','document_type':'boleta','document':'12345678','delivery':'retiro','payment_method':'Yape','quote_id':quote['id'],'idempotency_key':'qa-order-1'}
        order=post(customer,'/orders',d);oid=order['id']
        assert post(customer,'/orders',d)['id']==oid
        reserved=get(admin,f'/admin/products/{pid}');assert reserved['stock']==start['stock'] and reserved['reserved']==start['reserved']+1
        with TestClient(app) as stranger: assert stranger.get(f'/api/orders/{oid}').status_code==403
        image=io.BytesIO();Image.new('RGB',(200,100),'white').save(image,format='PNG')
        r=customer.post(f'/api/orders/{oid}/payment',files={'file':('demo.png',image.getvalue(),'image/png')});assert r.status_code==200,r.text
        assert get(customer,f'/orders/{oid}')['status']=='pago por verificar'
        assert admin.get(f'/api/orders/{oid}/voucher').status_code==200
        assert customer.get('/media/'+get(customer,f'/orders/{oid}')['payment']['voucher']).status_code==404
        before=get(admin,'/admin/dashboard')
        post(admin,f'/admin/orders/{oid}/verify',{'accepted':True})
        assert admin.post(f'/api/admin/orders/{oid}/verify',json={'accepted':True}).status_code==400
        paid=get(admin,f'/admin/products/{pid}');assert paid['stock']==start['stock']-1 and paid['reserved']==start['reserved']
        with connect() as c:
            movement=one(c,"SELECT available_before,available_after FROM inventory_movements WHERE order_id=? AND kind='reserva'",(oid,))
            assert movement['available_before']==start['stock']-start['reserved']
            assert movement['available_after']==movement['available_before']-1
        after=get(admin,'/admin/dashboard');assert after['today']==before['today']+p['price_cents'] and after['profit']>before['profit']
        for state in ['preparando','listo para recojo','entregado']:
            r=admin.put(f'/api/admin/orders/{oid}/status',json={'status':state,'recipient':'Cliente de prueba'});assert r.status_code==200,r.text
        assert get(customer,f'/orders/{oid}')['status']=='entregado'
        qty=paid['stock']-paid['reserved']-2
        if qty: post(admin,'/admin/inventory',{'product_id':pid,'quantity':-qty,'kind':'ajuste','reason':'Verificar alerta'})
        assert any(a['product_id']==pid for a in get(admin,'/admin/list/alerts?status=activa&limit=500')['items'])
        purchase=post(admin,'/admin/purchases',{'supplier_id':1,'items':[{'product_id':pid,'quantity':20,'cost_cents':paid['cost_cents']}]})
        post(admin,f"/admin/purchases/{purchase['id']}/receive",{})
        assert admin.post(f"/api/admin/purchases/{purchase['id']}/receive").status_code==400
        assert get(admin,f'/admin/products/{pid}')['available']==22
        assert not any(a['product_id']==pid for a in get(admin,'/admin/list/alerts?status=activa&limit=500')['items'])
        for mode in ['cancel','expire']:
            d.pop('quote_id',None);d['idempotency_key']='qa-'+mode
            o=post(customer,'/orders',d)
            if mode=='cancel':post(customer,f"/orders/{o['id']}/cancel",{})
            else:
                with transaction() as c:c.execute("UPDATE orders SET expires_at='2000-01-01' WHERE id=?",(o['id'],));expire(c)
            assert get(admin,f'/admin/products/{pid}')['available']==22
        assert customer.post('/api/orders',json={**d,'idempotency_key':'bad-qty','items':[{'product_id':pid,'quantity':999}]}).status_code==400
        # Partial receipts, retry protection, cancelled balances and optimistic counts.
        po=post(admin,'/admin/purchases',{'supplier_id':1,'expected_at':'2026-12-20','items':[{'product_id':pid,'quantity':8,'cost_cents':paid['cost_cents']}]})
        poid=po['id'];line=get(admin,f'/admin/purchases/{poid}')['items'][0]['id']
        assert admin.put(f'/api/admin/purchases/{poid}/schedule',json={'expected_at':'2026-12-21'}).status_code==200
        assert get(admin,f'/admin/purchases/{poid}')['expected_at']=='2026-12-21'
        body={'request_key':'qa-partial-1','items':[{'id':line,'quantity':3}],'note':'Recepcion de prueba'}
        receipt=post(admin,f'/admin/purchases/{poid}/receive',body)
        assert post(admin,f'/admin/purchases/{poid}/receive',body)==receipt
        assert get(admin,f'/admin/purchases/{poid}')['status']=='parcial'
        assert get(admin,f'/admin/products/{pid}')['available']==25
        assert admin.post(f'/api/admin/purchases/{poid}/receive',json={'items':[{'id':line,'quantity':6}]}).status_code==400
        assert admin.post(f'/api/admin/purchases/{poid}/receive',json={'items':[{'id':line,'quantity':-1}]}).status_code==400
        post(admin,f'/admin/purchases/{poid}/cancel',{'reason':'Saldo cancelado por prueba'})
        assert get(admin,f'/admin/products/{pid}')['available']==25
        assert admin.post(f'/api/admin/purchases/{poid}/receive',json={}).status_code==400
        r=admin.put(f'/api/admin/operations/inventory/{pid}/policy',json={'minimum':5,'maximum':30,'lead_days':7,'pack_size':4,'supplier_id':1,'location':'QA-01'})
        assert r.status_code==200,r.text
        live=get(admin,f'/admin/products/{pid}')
        count={'counted':live['stock']+1,'expected_stock':live['stock'],'expected_reserved':live['reserved'],'reason':'Conteo verificado en prueba'}
        post(admin,f'/admin/operations/inventory/{pid}/count',count)
        assert admin.post(f'/api/admin/operations/inventory/{pid}/count',json=count).status_code==400
        assert admin.post('/api/admin/inventory',json={'product_id':pid,'kind':'merma','quantity':1,'reason':'Prueba de validacion'}).status_code==400
        assert admin.post('/api/admin/inventory',json={'product_id':pid,'kind':'venta','quantity':-1,'reason':'Prueba de validacion'}).status_code==400
        # Dispatch requires a carrier and tracking; delivery requires a recipient.
        shipped=post(customer,'/orders',{**d,'idempotency_key':'qa-dispatch','delivery':'envio','address':'Direccion de prueba 123','ubigeo':'150101','shipping_zone':get(customer,'/config')['shipping'][0]['name']})
        sid=shipped['id']
        image.seek(0)
        assert customer.post(f'/api/orders/{sid}/payment',files={'file':('demo.png',image.getvalue(),'image/png')}).status_code==200
        post(admin,f'/admin/orders/{sid}/verify',{'accepted':True})
        assert admin.put(f'/api/admin/operations/shipments/{sid}',json={'status':'preparando'}).status_code==200
        assert admin.put(f'/api/admin/operations/shipments/{sid}',json={'status':'enviado'}).status_code==400
        assert admin.put(f'/api/admin/operations/shipments/{sid}',json={'status':'enviado','carrier':'Agencia de prueba','tracking':'GUIA-QA'}).status_code==200
        assert admin.put(f'/api/admin/operations/shipments/{sid}',json={'status':'entregado'}).status_code==400
        assert admin.put(f'/api/admin/operations/shipments/{sid}',json={'status':'entregado','recipient':'Cliente prueba'}).status_code==200
        assert get(customer,f'/orders/{sid}')['tracking']=='GUIA-QA'
        from backend.services.operations import snapshot
        snapshot();snapshot()
        with connect() as c:
            day=one(c,'SELECT MAX(date) day FROM stock_observations')['day']
            assert one(c,'SELECT COUNT(*) n FROM stock_observations WHERE date=?',(day,))['n']==one(c,'SELECT COUNT(*) n FROM products')['n']
        for url in ['/admin/operations/quality','/admin/operations/catalog-audit','/admin/operations/export/catalog','/admin/operations/export/catalog-issues','/admin/list/audit','/admin/operations/export/observations']:
            assert employee.get('/api'+url).status_code==403
            assert customer.get('/api'+url).status_code==403
        assert customer.get('/api/admin/operations/inventory').status_code==403
        assert get(admin,'/admin/operations/quality')['checks'][0]['count']==0
        current=get(admin,f'/admin/products/{pid}')
        original_item=get(customer,f'/orders/{oid}')['items'][0]['price_cents']
        current['price_cents']+=100
        assert admin.put(f'/api/admin/products/{pid}',json=current).status_code==200
        assert get(customer,f'/orders/{oid}')['items'][0]['price_cents']==original_item
        catalog_audit=get(admin,'/admin/operations/catalog-audit?severity=error')
        assert all(i['severity']=='error' for i in catalog_audit['items'])
        assert catalog_audit['products']>0 and catalog_audit['summary']['external_price_products']<=catalog_audit['products']
        invalid={**current,'oem':'REF-123456'}
        assert admin.put(f'/api/admin/products/{pid}',json=invalid).status_code==400
        invalid={**current,'compatibility':[{'brand':'Toyota','model':'No existe','year_from':2012,'year_to':2024,'version':''}]}
        assert admin.put(f'/api/admin/products/{pid}',json=invalid).status_code==400
        for name in ['inventory','observations','movements','prices','catalog','catalog-issues']:
            exported=admin.get('/api/admin/operations/export/'+name)
            assert exported.status_code==200 and 'text/csv' in exported.headers['content-type']
        with connect() as c:
            assert not c.execute('PRAGMA foreign_key_check').fetchall()
            assert not c.execute('SELECT id FROM products WHERE reserved<0 OR stock<reserved').fetchall()
            for row in c.execute('SELECT url,thumb FROM product_images'):
                for url in row:assert (ROOT/'backend/static'/url.removeprefix('/media/')).is_file(),url
        print('PASS: flujos de tienda, pagos, stock, compras parciales, reintentos, cancelacion de saldo, conteos concurrentes, validaciones, captura diaria, roles, finanzas e imagenes.')
if __name__=='__main__':
    try:run()
    finally:
        for suffix in ['', '-wal','-shm']:
            path=Path(target+suffix)
            try:path.unlink(missing_ok=True)
            except PermissionError:pass
