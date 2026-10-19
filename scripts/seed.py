import sys,json,random,shutil,argparse,calendar,sqlite3
from pathlib import Path
from datetime import datetime,timedelta
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backend.db import init_db,transaction,one,rows,now,DB
from backend.services.customers import password_hash
from backend.services.inventory import refresh_alert

def seed(reset=False):
    init_db()
    if reset and DB.exists():
        backup=DB.with_suffix('.backup.db')
        with sqlite3.connect(DB) as source,sqlite3.connect(backup) as target: source.backup(target)
        with transaction() as c:
            # Explicit reset is for the academic dataset; preserve a recoverable backup.
            c.execute('PRAGMA defer_foreign_keys=ON')
            for table in ['catalog_quality','product_price_history','stock_observations','shipments','inventory_counts','inventory_policy','purchase_receipt_items','purchase_receipts','daily_stock','audit','alerts','events','complaints','purchase_items','purchase_orders','suppliers','inventory_movements','order_history','payments','order_items','orders','quote_items','quotes','addresses','garage','product_images','compatibility','products','vehicles','categories','brands','sessions','users','ubigeo']: c.execute('DELETE FROM '+table)
    init_db()
    with transaction() as c:
        if one(c,'SELECT id FROM products LIMIT 1'):
            print('La base ya contiene datos. Usa --reset para regenerar (crea una copia de respaldo).');return
        rng=random.Random(20261013);stamp=now();today=datetime.fromisoformat(stamp).date()
        for name,email,role in [('Administrador','admin@roda.pe','admin'),('Valeria Torres','empleado@roda.pe','empleado'),('Diego Mendoza','cliente@roda.pe','cliente'),('Lucía Salazar','lucia@example.com','cliente'),('Carlos Ramos','carlos@example.com','cliente'),('Ana Paredes','ana@example.com','cliente'),('José Quispe','jose@example.com','cliente'),('María Vargas','maria@example.com','cliente')]:
            c.execute('INSERT INTO users(name,email,password_hash,role,phone,document,consent_at,created_at) VALUES(?,?,?,?,?,?,?,?)',(name,email,password_hash('Roda2026!'),role,'987654321','12345678',stamp,stamp))
        models={'Toyota':[('Yaris','1.3 / 1.5 VVT-i'),('Corolla','1.8 VVT-i'),('Hilux','2.8 diésel'),('RAV4','2.0 gasolina')],'Hyundai':[('Accent','1.4 / 1.6 MPI'),('Elantra','1.6 MPI'),('Tucson','2.0 MPI'),('Grand i10','1.2 MPI')],'Kia':[('Rio','1.4 MPI'),('Picanto','1.0 / 1.2 MPI'),('Sportage','2.0 MPI'),('Cerato','1.6 MPI')],'Nissan':[('Versa','1.6'),('Sentra','1.8'),('March','1.6'),('Frontier','2.5 diésel')],'Suzuki':[('Swift','1.2'),('Vitara','1.6'),('Alto','0.8 / 1.0'),('Ertiga','1.4 / 1.5')],'Chevrolet':[('Sail','1.4'),('Spark','1.2')],'Mitsubishi':[('L200','2.4 diésel')],'Mazda':[('Mazda 3','2.0 Skyactiv')]}
        vehicle_models=[]
        for brand,items in models.items():
            for model,version in items:
                vehicle_models.append((brand,model,version))
                for year in range(2012,2025): c.execute('INSERT INTO vehicles(brand,model,year,version) VALUES(?,?,?,?)',(brand,model,year,version))
        yaris=c.execute("SELECT id FROM vehicles WHERE brand='Toyota' AND model='Yaris' AND year=2018").fetchone()[0]
        c.execute('INSERT INTO garage(user_id,vehicle_id,active) VALUES(3,?,1)',(yaris,))
        cats=json.loads((ROOT/'data/catalog_seed.json').read_text(encoding='utf-8'))
        for cat in cats:
            first=cat['subcategories'][0];image=first['image'].replace('/static/','/media/')
            parent=c.execute('INSERT INTO categories(name,slug,image) VALUES(?,?,?)',(cat['name'],cat['slug'],image)).lastrowid
            for sub in cat['subcategories']:
                subid=c.execute('INSERT INTO categories(name,slug,parent_id,image) VALUES(?,?,?,?)',(sub['name'],sub['slug'],parent,sub['image'].replace('/static/','/media/'))).lastrowid
                # Eight demonstrative variants per family: five popular makes plus three additional models.
                groups=[('Toyota','Yaris','1.3 / 1.5 VVT-i'),('Hyundai','Accent','1.4 / 1.6 MPI'),('Kia','Rio','1.4 MPI'),('Nissan','Versa','1.6'),('Suzuki','Swift','1.2'),vehicle_models[(subid*3)%len(vehicle_models)],vehicle_models[(subid*7)%len(vehicle_models)],vehicle_models[(subid*11)%len(vehicle_models)]]
                for ix,v in enumerate(groups):
                    brand=sub['brands'][ix%len(sub['brands'])];c.execute('INSERT OR IGNORE INTO brands(name) VALUES(?)',(brand,));bid=c.execute('SELECT id FROM brands WHERE name=?',(brand,)).fetchone()[0]
                    sku=f'RP-{subid:03}-{ix+1:02}';universal=sub['universal'];price=max(1200,int(sub['base_price_cents']*(85+ix*7)//100)//100*100+90)
                    name=f"{sub['name']} {brand}"+(f' · {v[0]} {v[1]}' if not universal else f' · línea {['Estándar','Plus','Pro','Touring'][ix%4]}')
                    pid=c.execute('INSERT INTO products(sku,name,brand_id,category_id,price_cents,cost_cents,old_price_cents,stock,minimum,universal,featured,oem,specs,description,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(sku,name,bid,subid,price,price*62//100,price*120//100 if ix in [0,3] else 0,0,5,int(universal),int(ix==0 and cat['slug'] in ['frenos','filtros','suspension','aceites','encendido']),f'REF-{subid:03}{ix:03}',json.dumps({'Condición':'Nuevo','Presentación':'Unidad o juego según referencia','Aplicación':'Universal' if universal else f'{v[0]} {v[1]}','Garantía':'6 meses por defecto de fabricación'},ensure_ascii=False),'Repuesto de mantenimiento para tu auto. Verifica la aplicación y las medidas antes de instalar. Fotografía referencial del tipo de pieza. Compatibilidad y códigos del catálogo académico: validar con ficha del fabricante antes de un uso real.',stamp)).lastrowid
                    if not universal:
                        # Separate year bands allow a later exact technical catalog without schema changes.
                        for lo,hi in [(2012,2016),(2017,2020),(2021,2024)]: c.execute('INSERT INTO compatibility(product_id,brand,model,year_from,year_to,version) VALUES(?,?,?,?,?,?)',(pid,v[0],v[1],lo,hi,v[2]))
                    folder=ROOT/'backend/static/products'/sku;folder.mkdir(parents=True,exist_ok=True)
                    for source,target in [(sub['slug']+'.webp','main.webp'),(sub['slug']+'-thumb.webp','thumb.webp')]: shutil.copy2(ROOT/'backend/static/category'/source,folder/target)
                    c.execute('INSERT INTO product_images(product_id,url,thumb,source_url,is_primary) VALUES(?,?,?,?,1)',(pid,f'/media/products/{sku}/main.webp',f'/media/products/{sku}/thumb.webp',sub['source_url']))
        for name in ['Autopartes Andinas','Distribuidora Nippon Perú','Frenos del Pacífico','Importaciones Motor Sur','Lubricantes Lima','Accesorios Central']:
            i=c.execute('SELECT COUNT(*) FROM suppliers').fetchone()[0]
            c.execute('INSERT INTO suppliers(name,ruc,email,phone,contact) VALUES(?,?,?,?,?)',(name,f'2010000000{i}',f'ventas{i}@proveedor.example','+51 900 000 000','Área comercial'))
        ubpath=ROOT/'data/ubigeo.json'
        if ubpath.exists():
            for r in json.loads(ubpath.read_text(encoding='utf-8-sig')): c.execute('INSERT OR IGNORE INTO ubigeo VALUES(?,?,?,?)',(r['code'],r['department'],r['province'],r['district']))
        else:
            for code,dep,prov,dist in [('150101','Lima','Lima','Lima'),('150141','Lima','Lima','Surquillo'),('150122','Lima','Lima','Miraflores'),('070101','Callao','Callao','Callao')]: c.execute('INSERT INTO ubigeo VALUES(?,?,?,?)',(code,dep,prov,dist))
        c.execute("INSERT INTO addresses(user_id,label,street,ubigeo,reference) VALUES(3,'Casa','Av. Los Álamos 245','150141','Frente al parque')")
        products=rows(c,'SELECT * FROM products');stock={p['id']:rng.randint(15,40) for p in products};start=today-timedelta(days=364)
        def movement(pid,qty,kind,reason,at,oid=None):
            stock[pid]+=qty
            c.execute('INSERT INTO inventory_movements(product_id,kind,quantity,balance,reason,order_id,actor,created_at) VALUES(?,?,?,?,?,?,?,?)',(pid,kind,qty,stock[pid],reason,oid,'sistema',at))
        for p in products:
            initial=stock[p['id']];stock[p['id']]=0;movement(p['id'],initial,'apertura','Saldo inicial simulado',start.isoformat()+'T08:00:00-05:00')
        order_count=0;event_batch=[];daily_batch=[];byid={p['id']:p for p in products}
        weights=[12 if p['featured'] else 3 if p['id']%4==0 else 1 for p in products]
        for daynum in range(365):
            day=start+timedelta(days=daynum);ds=day.isoformat();demand={}
            # Replenishment every fortnight, selective low-rotation supply; genuine stockout days.
            if daynum%14==0:
                for p in products:
                    pid=p['id']
                    if stock[pid]<8 and rng.random()<.8: movement(pid,rng.randint(12,35),'compra','Reposición histórica simulada',ds+'T08:00:00-05:00')
            count=rng.randint(7,14)+(5 if day.month in [7,12] else 0)+(3 if day.weekday()==5 else 0)
            for k in range(count):
                chosen=rng.choices(products,weights=weights,k=rng.randint(1,3));items=[]
                for p in {p['id']:p for p in chosen}.values():
                    qty=rng.randint(1,2);pid=p['id'];demand[pid]=demand.get(pid,0)+qty
                    event_batch.append(('product_view',pid,None,None,f'seed-{daynum}-{k}','{}',ds+'T10:00:00-05:00'))
                    if stock[pid]>=qty: items.append((p,qty))
                if not items: continue
                order_count+=1;total=sum(p['price_cents']*qty for p,qty in items);base=(total*100+59)//118;uid=rng.randint(3,8);user=one(c,'SELECT * FROM users WHERE id=?',(uid,));date=f'{ds}T{9+k%10:02}:15:00-05:00';status='entregado' if daynum<362 else rng.choice(['pagado','preparando','listo para recojo','entregado'])
                oc=f'PED-{day.strftime('%y%m')}-{order_count:06}'
                oid=c.execute('INSERT INTO orders(code,user_id,guest_token,customer_name,email,phone,document_type,document,delivery,shipping_cents,total_cents,base_cents,tax_cents,status,payment_method,actor,created_at,expires_at,paid_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(oc,uid,f'seed-token-{order_count}',user['name'],user['email'],user['phone'],'boleta','12345678','retiro',0,total,base,total-base,status,rng.choice(['Yape','Plin','Transferencia','Pago en tienda']),'sistema',date,date,date)).lastrowid
                for p,qty in items:
                    c.execute('INSERT INTO order_items(order_id,product_id,sku,name,quantity,price_cents,cost_cents) VALUES(?,?,?,?,?,?,?)',(oid,p['id'],p['sku'],p['name'],qty,p['price_cents'],p['cost_cents']))
                    movement(p['id'],-qty,'venta','Venta histórica simulada',date,oid)
                    event_batch.append(('cart_add',p['id'],None,uid,f'seed-{daynum}-{k}',json.dumps({'quantity':qty}),date))
                c.execute("INSERT INTO payments(order_id,method,amount_cents,status,created_at,verified_at) SELECT id,payment_method,total_cents,'confirmado',created_at,paid_at FROM orders WHERE id=?",(oid,))
                for state in ['pendiente de pago','pago por verificar','pagado']+(['preparando',status] if status not in ['pagado','preparando'] else ['preparando'] if status=='preparando' else []): c.execute('INSERT INTO order_history(order_id,status,note,actor,created_at) VALUES(?,?,?,?,?)',(oid,state,'Historial académico simulado','sistema',date))
                event_batch.append(('search',None,yaris,uid,f'seed-{daynum}-{k}',json.dumps({'query':rng.choice(['pastillas de freno','filtro de aceite','amortiguador','bujías','batería'])}),date))
            for p in products: daily_batch.append((p['id'],ds,stock[p['id']],demand.get(p['id'],0),int(stock[p['id']]==0)))
        c.executemany('INSERT INTO events(type,product_id,vehicle_id,user_id,session_id,payload,created_at) VALUES(?,?,?,?,?,?,?)',event_batch)
        c.executemany('INSERT INTO daily_stock(product_id,date,stock,demand,stockout) VALUES(?,?,?,?,?)',daily_batch)
        for p in products:
            pid=p['id'];target=2 if pid%43==0 else 0 if pid%97==0 else max(stock[pid],12) if p['featured'] else stock[pid]
            if target!=stock[pid]: movement(pid,target-stock[pid],'ajuste','Conteo final simulado',stamp)
            c.execute('UPDATE products SET stock=? WHERE id=?',(stock[pid],pid));refresh_alert(c,pid)
        c.execute("INSERT INTO complaints(code,user_id,name,email,document,phone,type,detail,request,created_at) VALUES('REC-DEMO-001',3,'Diego Mendoza','cliente@roda.pe','12345678','987654321','Reclamo','La entrega demoró un día más de lo indicado.','Solicito revisar el plazo de envío.',?)",(stamp,))
    # Pending payment example via the same business services used by HTTP.
    from backend.services.orders import create_order
    from backend.services.payments import provider
    demo=create_order({'items':[{'product_id':1,'quantity':1}],'customer_name':'Diego Mendoza','email':'cliente@roda.pe','phone':'987654321','document_type':'boleta','document':'12345678','delivery':'retiro','payment_method':'Pago en tienda'},3);provider.submit(demo['id'],'',3)
    from backend.services.catalog_quality import normalize_demo
    normalize_demo()
    print(f'Seed completo: {len(products)} productos, {len(cats)} categorías, {order_count} pedidos y 365 días de historial.')
    print('Credenciales locales de demostración (contraseña común: Roda2026!):')
    print('Admin: admin@roda.pe | Empleado: empleado@roda.pe | Cliente: cliente@roda.pe')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--reset',action='store_true');args=parser.parse_args();seed(args.reset)
