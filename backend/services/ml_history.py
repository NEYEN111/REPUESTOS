"""Observaciones de la operación. Un día incompleto nunca se rellena con ceros."""
import json
from datetime import date, timedelta
from backend.db import transaction, rows, now


def capture():
    stamp = now()
    day, slot = stamp[:10], int(stamp[11:13])//2
    with transaction() as c:
        # A closed day requires observations at both ends and all twelve 2h slots.
        eligible=rows(c,'''SELECT * FROM ml_daily WHERE date<? AND complete=0
          AND substr(first_seen,12,5)<='00:02' AND substr(last_seen,12,5)>='23:59'
          AND json_extract(payload,'$._missing_policy')=0
          AND json_extract(payload,'$._incomplete_reason') IS NULL
          AND (SELECT COUNT(*) FROM ml_samples s WHERE s.product_id=ml_daily.product_id AND s.date=ml_daily.date)=12''',(day,))
        closed_events={}
        for closed_day in {r['date'] for r in eligible}:
            closed_events[closed_day]={(r['product_id'],r['type']):r['n'] for r in rows(c,
                'SELECT product_id,type,COUNT(*) n FROM events WHERE created_at>=? AND created_at<? GROUP BY product_id,type',
                (closed_day,closed_day+'T99'))}
        for observation in eligible:
            raw=json.loads(observation['payload']);closed_day=observation['date']
            # Do not call the last-minute snapshot a complete close if business data changed afterwards.
            late=c.execute('''SELECT 1 FROM audit WHERE id>? AND created_at>=? AND created_at<?
              AND entity IN ('products','inventory','inventory_policy','inventory_counts','orders','purchase_orders','categories','brands') LIMIT 1''',
              (raw.get('_audit_max',-1),closed_day,closed_day+'T99')).fetchone()
            if late:
                raw['_incomplete_reason']='Cambios posteriores a la última observación del cierre.'
                c.execute('UPDATE ml_daily SET payload=? WHERE product_id=? AND date=?',
                    (json.dumps(raw,ensure_ascii=False),observation['product_id'],closed_day))
                continue
            counts=closed_events[closed_day]
            raw['vistas_producto']=counts.get((observation['product_id'],'product_view'),0)
            raw['adiciones_carrito']=counts.get((observation['product_id'],'cart_add'),0)
            c.execute('UPDATE ml_daily SET complete=1,payload=? WHERE product_id=? AND date=?',
                (json.dumps(raw,ensure_ascii=False),observation['product_id'],closed_day))
        audit_max=c.execute('SELECT COALESCE(MAX(id),0) FROM audit').fetchone()[0]
        products = rows(c, '''SELECT p.*,c.slug categoria,parent.slug familia,b.name marca,
            ip.maximum,ip.lead_days,ip.pack_size FROM products p
            JOIN categories c ON c.id=p.category_id LEFT JOIN categories parent ON parent.id=c.parent_id
            JOIN brands b ON b.id=p.brand_id LEFT JOIN inventory_policy ip ON ip.product_id=p.id''')
        c.executemany('INSERT OR IGNORE INTO ml_samples VALUES(?,?,?,?,?)',
                      [(p['id'],day,slot,p['stock']-p['reserved'],stamp) for p in products])
        samples = {r['product_id']:r for r in rows(c, '''SELECT product_id,COUNT(*) checks,
           SUM(available>0) stocked FROM ml_samples WHERE date=? GROUP BY product_id''', (day,))}
        movement = {}
        for m in rows(c, 'SELECT product_id,kind,SUM(quantity) qty,SUM(reserved_delta) res FROM inventory_movements WHERE created_at>=? AND created_at<? GROUP BY product_id,kind', (day,day+'T99')):
            movement.setdefault(m['product_id'], {})[m['kind']] = m
        events = {(r['product_id'],r['type']):r['n'] for r in rows(c, 'SELECT product_id,type,COUNT(*) n FROM events WHERE created_at>=? AND created_at<? GROUP BY product_id,type', (day,day+'T99'))}
        sales = {r['product_id']:r for r in rows(c, '''SELECT i.product_id,SUM(i.quantity) qty,
          SUM(i.quantity*i.price_cents) revenue FROM order_items i JOIN orders o ON o.id=i.order_id
          WHERE o.paid_at>=? AND o.paid_at<? GROUP BY i.product_id''', (day,day+'T99'))}
        purchases = {r['product_id']:r for r in rows(c, '''SELECT i.product_id,
          SUM(CASE WHEN po.status IN ('pendiente','parcial') THEN i.quantity-i.received_quantity ELSE 0 END) incoming,
          SUM(CASE WHEN po.status IN ('pendiente','parcial') AND po.expected_at!='' AND po.expected_at<? THEN i.quantity-i.received_quantity ELSE 0 END) overdue,
          SUM(CASE WHEN po.status IN ('pendiente','parcial') AND po.expected_at='' THEN 1 ELSE 0 END) unknown_eta,
          SUM(CASE WHEN substr(po.created_at,1,10)=? THEN i.quantity ELSE 0 END) requested
          FROM purchase_items i JOIN purchase_orders po ON po.id=i.purchase_order_id GROUP BY i.product_id''', (day,day))}
        for p in products:
            pid=p['id']; mov=movement.get(pid,{}); sample=samples[pid]; sale=sales.get(pid,{}); po=purchases.get(pid,{})
            quantity=lambda k: mov.get(k,{}).get('qty',0)
            reservation=lambda k: mov.get(k,{}).get('res',0)
            raw={'fecha':day,'sku':p['sku'],'categoria':p['categoria'],'familia':p['familia'] or p['categoria'],
                 'marca':p['marca'],'universal':p['universal'],'fuente_datos':'operacion',
                 'stock_inicio':p['stock']-sum(m['qty'] for m in mov.values()),
                 'reservado_inicio':p['reserved']-sum(m['res'] for m in mov.values()),
                 'ingresos_compra':quantity('compra'),'devoluciones_reingresadas':quantity('devolucion'),
                 'mermas':-quantity('merma'),'ventas_pagadas':sale.get('qty',0),
                 'reservas_creadas':reservation('reserva'),'reservas_pagadas':-reservation('venta'),
                 'reservas_canceladas':-reservation('liberación'),
                 'stock_fin':p['stock'],'reservado_fin':p['reserved'],'disponible_fin':p['stock']-p['reserved'],
                 'compras_solicitadas':po.get('requested',0),'compras_transito_fin':po.get('incoming',0),
                 'compras_vencidas_fin':po.get('overdue',0),'minimo':p['minimum'],'maximo':p['maximum'],
                 'plazo_proveedor_dias':p['lead_days'],'lote_compra':p['pack_size'],
                 'precio_lista_centimos':max(p['old_price_cents'],p['price_cents']),
                 'precio_centimos':p['price_cents'],'costo_unitario_centimos':p['cost_cents'],
                 'descuento_pct':round(100*(1-p['price_cents']/max(p['old_price_cents'],p['price_cents'])),2),
                 'ingreso_bruto_centimos':sale.get('revenue',0),'importe_devuelto_centimos':0,
                 'unidades_devueltas':quantity('devolucion'),
                 'vistas_producto':events.get((pid,'product_view'),0),'adiciones_carrito':events.get((pid,'cart_add'),0),
                 'chequeos_disponibilidad':sample['checks'],'chequeos_con_stock':sample['stocked'],
                 'quiebre_observado':int(sample['stocked']<sample['checks'] or p['stock']==p['reserved']),
                 '_missing_policy':int(p['maximum'] is None or p['lead_days'] is None or p['pack_size'] is None or bool(po.get('unknown_eta',0))),
                 '_audit_max':audit_max}
            c.execute('''INSERT INTO ml_daily(product_id,date,payload,first_seen,last_seen) VALUES(?,?,?,?,?)
             ON CONFLICT(product_id,date) DO UPDATE SET payload=excluded.payload,last_seen=excluded.last_seen''',
             (pid,day,json.dumps(raw,ensure_ascii=False),stamp,stamp))
        evaluate_matured(c,day,stamp)


def evaluate_matured(c, today, stamp):
    pending=rows(c, '''SELECT p.id,p.product_id,r.cutoff FROM ml_predictions p JOIN ml_runs r ON r.id=p.run_id
        WHERE r.source='operacion' AND p.actual IS NULL AND date(r.cutoff,'+7 days')<?''',(today,))
    for p in pending:
        end=(date.fromisoformat(p['cutoff'])+timedelta(days=7)).isoformat()
        days=rows(c, 'SELECT payload FROM ml_daily WHERE product_id=? AND date>? AND date<=? AND complete=1', (p['product_id'],p['cutoff'],end))
        if len(days)==7:
            actual=sum(json.loads(d['payload'])['ventas_pagadas'] for d in days)
            c.execute('UPDATE ml_predictions SET actual=?,evaluated_at=? WHERE id=?',(actual,stamp,p['id']))
