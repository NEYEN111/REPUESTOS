import json,unicodedata,difflib,re
from backend.db import connect,rows,one,transaction,now,audit

def normalize(s): return ''.join(c for c in unicodedata.normalize('NFKD',s.lower()) if not unicodedata.combining(c))
BASE='''SELECT p.*,b.name brand,c.name category,c.slug category_slug,c.parent_id,
(SELECT name FROM categories WHERE id=c.parent_id) parent_name,
COALESCE((SELECT url FROM product_images WHERE product_id=p.id ORDER BY is_primary DESC,id LIMIT 1),c.image) image,
COALESCE((SELECT thumb FROM product_images WHERE product_id=p.id ORDER BY is_primary DESC,id LIMIT 1),c.image) thumb
FROM products p JOIN brands b ON p.brand_id=b.id JOIN categories c ON c.id=p.category_id'''
def compatible(c,p,v):
    if p['universal']: return True
    return bool(one(c,"SELECT id FROM compatibility WHERE product_id=? AND brand=? AND model=? AND year_from<=? AND year_to>=? AND (version='' OR version=?)",(p['id'],v['brand'],v['model'],v['year'],v['year'],v['version'])))
def buscar_repuestos(vehiculo=None,texto='',category='',brand='',sort='recommended',page=1,limit=20,in_stock=False,offer=False,max_price=None,admin=False,direction='asc',status=''):
    with connect() as c:
        where=[];args=[]
        if not admin: where.append('p.active=1')
        if admin and status in ['activo','oculto']: where.append('p.active=?');args.append(int(status=='activo'))
        if category:
            where.append('(c.slug=? OR c.parent_id=(SELECT id FROM categories WHERE slug=?))');args.extend([category,category])
        if brand: where.append('b.name=?');args.append(brand)
        if in_stock: where.append('p.stock>p.reserved')
        if offer: where.append('p.old_price_cents>p.price_cents')
        if max_price: where.append('p.price_cents<=?');args.append(int(max_price))
        result=rows(c,BASE+(' WHERE '+' AND '.join(where) if where else ''),args)
        v=one(c,'SELECT * FROM vehicles WHERE id=?',(vehiculo,)) if vehiculo else None
        if v: result=[p for p in result if compatible(c,p,v)]
        if texto:
            query=normalize(texto).split()
            def match(p):
                s=normalize(' '.join(str(p[k]) for k in ['name','sku','oem','brand','category','parent_name','specs']))
                words=s.split()
                return all(q in s or (len(q)>3 and not any(char.isdigit() for char in q) and any(difflib.SequenceMatcher(None,q,w).ratio()>=.78 for w in words)) for q in query)
            exact=[p for p in result if normalize(p['sku'])==normalize(texto.strip())]
            result=exact or [p for p in result if match(p)]
        key={'price_asc':lambda p:p['price_cents'],'price_desc':lambda p:-p['price_cents'],'name':lambda p:p['name'],'stock':lambda p:p['stock']}.get(sort,lambda p:(-p['featured'],p['id']))
        if admin and sort in ['sku','brand','price_cents','stock','active','name']:
            result.sort(key=lambda p:p[sort],reverse=direction=='desc')
        else: result.sort(key=key)
        total=len(result);page=max(1,int(page));limit=min(100,max(1,int(limit)))
        for p in result: p['available']=p['stock']-p['reserved'];p['compatible']=True if v else None
        if not admin:
            for p in result: p.pop('cost_cents',None)
        return {'items':result[(page-1)*limit:page*limit],'total':total,'page':page,'pages':(total+limit-1)//limit}
def product_detail(product_id,vehicle_id=None,admin=False):
    with connect() as c:
        p=one(c,BASE+' WHERE p.id=?'+('' if admin else ' AND p.active=1'),(product_id,))
        if not p: raise ValueError('No encontramos este producto.')
        p['specs']=json.loads(p['specs']);p['images']=rows(c,'SELECT * FROM product_images WHERE product_id=? ORDER BY is_primary DESC,id',(product_id,))
        p['compatibility']=rows(c,'SELECT * FROM compatibility WHERE product_id=?',(product_id,))
        p['quality']=one(c,'SELECT source,presentation_source,compatibility_source,image_kind FROM catalog_quality WHERE product_id=?',(product_id,)) or {}
        p['available']=p['stock']-p['reserved'];v=one(c,'SELECT * FROM vehicles WHERE id=?',(vehicle_id,)) if vehicle_id else None
        p['compatible']=compatible(c,p,v) if v else None
        if not admin: p.pop('cost_cents',None)
        return p
def save_product(d,user_id,product_id=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',str(d.get('sku',''))): raise ValueError('El SKU solo admite letras, números, guiones y guiones bajos.')
    for key in ['sku','name','brand_id','category_id','price_cents','cost_cents','minimum']:
        if key not in d or d[key]=='': raise ValueError('Completa SKU, nombre, marca, categoría, precio, costo y stock mínimo.')
    for k in ['price_cents','cost_cents','minimum','old_price_cents']:
        if type(d.get(k,0)) is not int or d.get(k,0)<0: raise ValueError('Precios y cantidades deben ser enteros positivos.')
    if d['price_cents']==0: raise ValueError('El precio debe ser mayor a cero.')
    if not isinstance(d.get('specs',{}),dict): raise ValueError('Las especificaciones deben contener pares de característica y valor.')
    if re.fullmatch(r'REF-\d+',str(d.get('oem',''))): raise ValueError('REF- es una referencia interna. Guárdala en las especificaciones, no como código OEM.')
    if not d.get('universal') and not d.get('compatibility'): raise ValueError('Agrega una compatibilidad o marca el producto como universal.')
    fields=['sku','name','brand_id','category_id','price_cents','cost_cents','minimum','old_price_cents','universal','active','featured','oem','specs','description']
    values=[json.dumps(d.get(k,{}),ensure_ascii=False) if k=='specs' else d.get(k,1 if k=='active' else 0 if k in ['old_price_cents','universal','featured'] else '') for k in fields]
    with transaction() as c:
        if not one(c,'SELECT id FROM brands WHERE id=?',(d['brand_id'],)): raise ValueError('Selecciona una marca del catálogo.')
        category=one(c,'SELECT id,slug,parent_id FROM categories WHERE id=?',(d['category_id'],))
        if not category or not category['parent_id']: raise ValueError('Selecciona una subcategoría de productos.')
        for v in d.get('compatibility',[]):
            try: lo,hi=int(v['year_from']),int(v['year_to'])
            except (KeyError,TypeError,ValueError): raise ValueError('Revisa el rango de años de la compatibilidad.')
            if lo>hi or not one(c,"SELECT id FROM vehicles WHERE brand=? AND model=? AND year BETWEEN ? AND ? AND (?='' OR version=?)",
                (v.get('brand',''),v.get('model',''),lo,hi,v.get('version',''),v.get('version',''))):
                raise ValueError('La compatibilidad debe coincidir con un vehículo, versión y rango de años del catálogo.')
            if category['slug']=='bujias-de-precalentamiento' and ('diésel' not in v.get('version','').lower() and 'diesel' not in v.get('version','').lower()):
                raise ValueError('Las bujías de precalentamiento requieren una versión diésel.')
        duplicate=one(c,'SELECT id FROM products WHERE sku=? AND id!=?',(d['sku'],product_id or 0))
        if duplicate: raise ValueError('Ya existe un producto con ese SKU.')
        if product_id:
            previous=one(c,'SELECT price_cents,cost_cents,specs FROM products WHERE id=?',(product_id,))
            if not previous: raise ValueError('Producto no encontrado.')
            if previous['price_cents']!=d['price_cents'] or previous['cost_cents']!=d['cost_cents']:
                c.execute('INSERT INTO product_price_history(product_id,old_price_cents,new_price_cents,old_cost_cents,new_cost_cents,reason,user_id,created_at) VALUES(?,?,?,?,?,?,?,?)',
                  (product_id,previous['price_cents'],d['price_cents'],previous['cost_cents'],d['cost_cents'],'Edición de catálogo',user_id,now()))
            c.execute('UPDATE products SET '+','.join(k+'=?' for k in fields)+' WHERE id=?',values+[product_id])
            if json.loads(previous['specs']).get('Presentación')!=d.get('specs',{}).get('Presentación'):
                c.execute("UPDATE catalog_quality SET presentation_source='manual',updated_at=? WHERE product_id=?",(now(),product_id))
        else:
            product_id=c.execute('INSERT INTO products('+','.join(fields)+',created_at) VALUES('+','.join('?' for _ in fields)+',?)',values+[now()]).lastrowid
        c.execute('DELETE FROM compatibility WHERE product_id=?',(product_id,))
        for v in d.get('compatibility',[]):
            c.execute('INSERT INTO compatibility(product_id,brand,model,year_from,year_to,version) VALUES(?,?,?,?,?,?)',(product_id,v['brand'],v['model'],int(v['year_from']),int(v['year_to']),v.get('version','')))
        from backend.services.inventory import refresh_alert
        from backend.db import is_postgres
        greatest = 'GREATEST' if is_postgres() else 'MAX'
        c.execute(f'UPDATE inventory_policy SET maximum={greatest}(maximum,?) WHERE product_id=?',(d['minimum'],product_id))
        refresh_alert(c,product_id)
        audit(c,'products',product_id,'guardar',user_id)
        return product_id
