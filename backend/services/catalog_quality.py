"""Catalog diagnostics and explicit, reproducible normalization of academic data."""
import json
import math
import re
from datetime import datetime, timedelta
from functools import lru_cache
from backend.db import ROOT, connect, transaction, rows, one, now, audit
from backend.services.inventory import refresh_alert


@lru_cache(maxsize=1)
def rules():
    return json.loads((ROOT / 'data/catalog_rules.json').read_text(encoding='utf-8'))


def image_path(url):
    if not url or not url.startswith('/media/'):
        return None
    root = (ROOT / 'backend/static').resolve()
    path = (root / url.removeprefix('/media/')).resolve()
    return path if path.is_relative_to(root) else None


def audit_catalog():
    stamp = now()
    with connect() as c:
        products = rows(c, '''SELECT p.*,b.name brand,c.slug category_slug,c.name category,pa.slug family,
          ip.location,ip.maximum,ip.lead_days,ip.pack_size,ip.supplier_id,ip.source policy_source,s.active supplier_active,
          cq.source data_source,cq.presentation_source,cq.compatibility_source,cq.image_kind,cq.manufacturer_reference
          FROM products p JOIN brands b ON b.id=p.brand_id JOIN categories c ON c.id=p.category_id
          LEFT JOIN categories pa ON pa.id=c.parent_id LEFT JOIN inventory_policy ip ON ip.product_id=p.id
          LEFT JOIN suppliers s ON s.id=ip.supplier_id LEFT JOIN catalog_quality cq ON cq.product_id=p.id''')
        images = rows(c, 'SELECT * FROM product_images')
        compat = rows(c, 'SELECT * FROM compatibility')
        vehicles = rows(c, 'SELECT brand,model,year,version FROM vehicles')
        categories = rows(c, '''SELECT c.id,c.name,COUNT(p.id) n FROM categories c LEFT JOIN products p ON p.category_id=c.id
          WHERE c.parent_id IS NOT NULL GROUP BY c.id''')
    by_image, by_compat = {}, {}
    for i in images: by_image.setdefault(i['product_id'], []).append(i)
    for v in compat: by_compat.setdefault(v['product_id'], []).append(v)
    vehicle_keys = {}
    for v in vehicles: vehicle_keys.setdefault((v['brand'],v['model']), []).append(v)
    issues, export = [], []
    def add(p, code, label, severity='revisar'):
        issues.append({'product_id':p['id'],'sku':p['sku'],'name':p['name'],'category':p['category'],
                       'category_slug':p['category_slug'],'code':code,'issue':label,'severity':severity})
    for p in products:
        start = len(issues)
        try: specs = json.loads(p['specs']); assert isinstance(specs,dict)
        except (ValueError, AssertionError, TypeError): specs = {}; add(p,'specs','Especificaciones inválidas','error')
        presentation = str(specs.get('Presentación',''))
        if not presentation or 'según referencia' in presentation: add(p,'presentation','Presentación sin definir','pendiente')
        if p['presentation_source'] == 'supuesto_demo': add(p,'presentation_demo','Presentación académica; confirmar envase o juego','pendiente')
        if re.match(r'^REF-\d+$',p['oem']): add(p,'internal_oem','Referencia interna guardada como OEM','error')
        if not p['data_source']: add(p,'provenance','Procedencia del catálogo pendiente','pendiente')
        if p['compatibility_source'] != 'fabricante' and not p['universal']:
            add(p,'compatibility_review','Compatibilidad académica sin ficha del fabricante','pendiente')
        if p['universal'] and p['family'] in ('aceites','neumaticos','iluminacion','interior'):
            add(p,'universal_review','Aplicación universal: revisar medidas o especificación','pendiente')
        bands = by_compat.get(p['id'],[])
        if not p['universal'] and not bands: add(p,'compatibility_missing','Sin aplicación ni marca universal','error')
        if any(not any(b['year_from'] <= v['year'] <= b['year_to'] and (not b['version'] or b['version']==v['version'])
                       for v in vehicle_keys.get((b['brand'],b['model']),[])) for b in bands):
            add(p,'compatibility_invalid','Aplicación sin coincidencia en vehículos','error')
        if p['category_slug']=='bujias-de-precalentamiento' and any('diésel' not in b['version'].lower() for b in bands):
            add(p,'diesel','Bujía de precalentamiento asignada a versión sin diésel','error')
        if p['category_slug']=='distribuidores' and bands:
            add(p,'ignition','Distribuidor: validar sistema de encendido de la versión','revisar')
        pics = by_image.get(p['id'],[])
        if not pics: add(p,'image_missing','Producto sin fotografía','error')
        elif sum(bool(i['is_primary']) for i in pics)!=1: add(p,'image_primary','Debe existir una sola fotografía principal','error')
        if any(not image_path(i[k]) or not image_path(i[k]).is_file() for i in pics for k in ('url','thumb')):
            add(p,'image_file','Archivo de imagen o miniatura ausente','error')
        if any(not i['source_url'] for i in pics): add(p,'image_origin','Imagen sin URL de origen','pendiente')
        if p['image_kind']!='exacta': add(p,'image_reference','Foto referencial de familia; validar marca y pieza','pendiente')
        if not p['supplier_id'] or not p['supplier_active']: add(p,'supplier','Sin proveedor preferido activo','pendiente')
        if not p['location']: add(p,'location','Sin ubicación de almacén','pendiente')
        if p['maximum'] is None: add(p,'policy','Reglas de reposición sin guardar','pendiente')
        elif p['maximum']<p['minimum'] or p['pack_size']<1 or not 0<=p['lead_days']<=365:
            add(p,'policy_invalid','Reglas de reposición inconsistentes','error')
        if p['policy_source']=='simulado': add(p,'policy_demo','Ubicación y plazo de proveedor simulados','pendiente')
        if p['cost_cents']<=0 or p['cost_cents']>=p['price_cents']: add(p,'cost','Revisar costo y margen','revisar')
        if p['data_source']=='seed_simulado': add(p,'cost_source','Costo académico; falta cotización de proveedor','pendiente')
        if p['old_price_cents'] and p['old_price_cents']<=p['price_cents']: add(p,'offer','Precio anterior no supera al vigente','revisar')
        benchmark = rules()['benchmarks'].get(p['category_slug'])
        if not benchmark: add(p,'price_reference','Sin contraste externo de precio por familia','pendiente')
        elif not benchmark['min_cents']<=p['price_cents']<=benchmark['max_cents']:
            add(p,'price_range','Precio fuera del rango orientativo de la familia','revisar')
        findings = issues[start:]
        export.append({'product_id':p['id'],'sku':p['sku'],'name':p['name'],'category':p['category'],
          'price_cents':p['price_cents'],'cost_cents':p['cost_cents'],'presentation':presentation,
          'data_source':p['data_source'] or 'pendiente','policy_source':p['policy_source'] or 'pendiente',
          'location':p['location'] or '', 'supplier_id':p['supplier_id'] or '',
          'compatibility_source':p['compatibility_source'] or 'pendiente','image_kind':p['image_kind'] or 'pendiente',
          'errors':sum(i['severity']=='error' for i in findings),'issues':'; '.join(i['code'] for i in findings)})
    counts = {}
    for i in issues:
        if i['code'] not in counts: counts[i['code']]={'code':i['code'],'name':i['issue'],'severity':i['severity'],'count':0}
        counts[i['code']]['count']+=1
    return {'checked_at':stamp,'products':len(products),'issues':issues,'rows':export,'checks':list(counts.values()),
            'empty_categories':[c['name'] for c in categories if not c['n']],
            'summary':{'errors':sum(i['severity']=='error' for i in issues),
              'pending_products':len({i['product_id'] for i in issues}),
              'policies':sum(p['maximum'] is not None for p in products),
              'external_price_products':sum(p['category_slug'] in rules()['benchmarks'] for p in products)},
            'benchmarks':[{'category_slug':k,**v} for k,v in rules()['benchmarks'].items()]}


def normalize_demo():
    """Initialize demo metadata once. Never change stock or rewrite historic transactions."""
    changes = {'presentations':0,'internal_references':0,'policies':0,'prices':0,'diesel_applications':0}
    stamp=now(); cutoff=(datetime.fromisoformat(stamp)-timedelta(days=90)).isoformat()
    with transaction() as c:
        products=rows(c, '''SELECT p.*,b.name brand,c.slug category_slug,pa.slug family FROM products p
          JOIN brands b ON b.id=p.brand_id JOIN categories c ON c.id=p.category_id LEFT JOIN categories pa ON pa.id=c.parent_id
          WHERE p.sku GLOB 'RP-[0-9][0-9][0-9]-[0-9][0-9]' AND p.description LIKE '%catálogo académico%' ''')
        suppliers={s['name']:s['id'] for s in rows(c,'SELECT id,name FROM suppliers WHERE active=1')}
        sold={r['product_id']:r['n'] for r in rows(c,'''SELECT i.product_id,SUM(i.quantity) n FROM order_items i
          JOIN orders o ON o.id=i.order_id WHERE o.paid_at>=? AND o.paid_at<=? GROUP BY i.product_id''',(cutoff,stamp))}
        diesel=rows(c,"SELECT brand,model,version,MIN(year) lo,MAX(year) hi FROM vehicles WHERE version LIKE '%diésel%' GROUP BY brand,model,version ORDER BY brand,model")
        for p in products:
            if one(c,'SELECT product_id FROM catalog_quality WHERE product_id=?',(p['id'],)): continue
            specs=json.loads(p['specs']); old_specs=dict(specs); old_oem=p['oem']
            internal=bool(re.fullmatch(r'REF-\d+',old_oem))
            if internal: specs['Referencia interna']=old_oem; changes['internal_references']+=1
            presentation_source='manual'
            if specs.get('Presentación')=='Unidad o juego según referencia':
                specs['Presentación']=rules()['presentations'].get(p['category_slug'],'Unidad')
                presentation_source='supuesto_demo';changes['presentations']+=1
            c.execute('UPDATE products SET specs=?,oem=? WHERE id=?',
                      (json.dumps(specs,ensure_ascii=False),'' if internal else old_oem,p['id']))
            c.execute('''INSERT INTO catalog_quality(product_id,source,presentation_source,compatibility_source,image_kind,rules_version,updated_at)
              VALUES(?,'seed_simulado',?,'seed_simulado','referencial',?,?)''',(p['id'],presentation_source,rules()['version'],stamp))
            if p['category_slug']=='bujias-de-precalentamiento' and diesel:
                before=rows(c,'SELECT * FROM compatibility WHERE product_id=?',(p['id'],))
                if any('diésel' not in v['version'].lower() for v in before):
                    v=diesel[(p['id']-1)%len(diesel)]
                    c.execute('DELETE FROM compatibility WHERE product_id=?',(p['id'],))
                    c.execute('INSERT INTO compatibility(product_id,brand,model,year_from,year_to,version) VALUES(?,?,?,?,?,?)',
                              (p['id'],v['brand'],v['model'],v['lo'],v['hi'],v['version']))
                    specs['Aplicación']=f'{v["brand"]} {v["model"]} diésel'
                    name=f'Bujías de precalentamiento {p["brand"]} · {v["brand"]} {v["model"]}'
                    c.execute('UPDATE products SET name=?,specs=? WHERE id=?',(name,json.dumps(specs,ensure_ascii=False),p['id']))
                    audit(c,'compatibility',p['id'],'corregir_aplicacion_demo',actor='sistema',detail={'previous':before,'previous_name':p['name'],'application':v})
                    changes['diesel_applications']+=1
            if not one(c,'SELECT product_id FROM inventory_policy WHERE product_id=?',(p['id'],)):
                supplier,lead=rules()['suppliers'].get(p['family'],['Autopartes Andinas',7])
                avg=sold.get(p['id'],0)/90
                minimum=max(1,math.ceil(avg*(lead+7))) if p['minimum']==5 else p['minimum']
                maximum=max(minimum+2,math.ceil(avg*(lead+28)))
                location=f'DEMO-{p["category_id"]:03}-{(p["id"]-1)%8+1:02}'
                c.execute('UPDATE products SET minimum=? WHERE id=?',(minimum,p['id']))
                c.execute('''INSERT INTO inventory_policy(product_id,location,maximum,lead_days,pack_size,supplier_id,updated_at,source)
                  VALUES(?,?,?,?,1,?,?,'simulado')''',(p['id'],location,maximum,lead,suppliers.get(supplier),stamp))
                refresh_alert(c,p['id']);changes['policies']+=1
            benchmark=rules()['benchmarks'].get(p['category_slug'],{})
            floor=benchmark.get('premium_floor_cents',0) if p['brand'] in benchmark.get('premium_brands',[]) else 0
            new_price=max(p['price_cents'],floor,benchmark.get('min_cents',0))
            # Never overwrite a price that someone has already reviewed manually.
            if new_price!=p['price_cents'] and not one(c,'SELECT id FROM product_price_history WHERE product_id=?',(p['id'],)):
                old_price=p['old_price_cents'] if p['old_price_cents']>new_price else 0
                c.execute('UPDATE products SET price_cents=?,old_price_cents=? WHERE id=?',(new_price,old_price,p['id']))
                c.execute('''INSERT INTO product_price_history(product_id,old_price_cents,new_price_cents,old_cost_cents,new_cost_cents,reason,created_at)
                  VALUES(?,?,?,?,?,?,?)''',(p['id'],p['price_cents'],new_price,p['cost_cents'],p['cost_cents'],
                  'Rango académico de familia contrastado en Perú; no corresponde a ficha técnica exacta. '+rules()['version'],stamp))
                changes['prices']+=1
            audit(c,'catalog_quality',p['id'],'normalizar_demo',actor='sistema',detail={
              'rules_version':rules()['version'],'previous_specs':old_specs,'previous_oem':old_oem,
              'presentation_source':presentation_source,'policy_source':'simulado' if not one(c,"SELECT product_id FROM inventory_policy WHERE product_id=? AND source='manual'",(p['id'],)) else 'manual',
              'basis':'Ventas pagadas de los últimos 90 días; mínimo cubre plazo supuesto + 7 días; máximo cubre plazo + 28 días; no es predicción ML.'})
    return changes
