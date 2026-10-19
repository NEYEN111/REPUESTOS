from datetime import datetime,timedelta
from backend.db import connect,rows,one,now,config

def resumen_ventas(rango=None):
    today=datetime.fromisoformat(now()).date();start,end=rango or ((today-timedelta(days=29)).isoformat(),today.isoformat())
    try:
        a,b=datetime.fromisoformat(start).date(),datetime.fromisoformat(end).date()
    except ValueError: raise ValueError('Selecciona fechas válidas para el reporte.')
    if b<a or (b-a).days>3660: raise ValueError('El periodo debe estar ordenado y no superar 10 años.')
    with connect() as c:
        revenue=one(c,"SELECT COALESCE(SUM(total_cents),0) revenue,COUNT(*) orders,COALESCE(SUM(tax_cents),0) tax FROM orders WHERE paid_at IS NOT NULL AND substr(paid_at,1,10) BETWEEN ? AND ?",(start,end))
        cost=one(c,'SELECT COALESCE(SUM(i.quantity*i.cost_cents),0) cost FROM order_items i JOIN orders o ON o.id=i.order_id WHERE o.paid_at IS NOT NULL AND substr(o.paid_at,1,10) BETWEEN ? AND ?',(start,end))['cost']
        product_sales=rows(c,'SELECT p.id,p.sku,p.name,c.name category,SUM(i.quantity) units,SUM(i.quantity*i.price_cents) revenue,SUM(i.quantity*i.cost_cents) cost FROM order_items i JOIN orders o ON o.id=i.order_id JOIN products p ON p.id=i.product_id JOIN categories c ON c.id=p.category_id WHERE o.paid_at IS NOT NULL AND substr(o.paid_at,1,10) BETWEEN ? AND ? GROUP BY p.id ORDER BY revenue DESC',(start,end))
        # Sale and purchase prices both include IGV; estimated trading margin excludes it.
        from decimal import Decimal,ROUND_HALF_UP
        factor=1+Decimal(str(config()['igv_percent']))/100
        def net(v): return int((Decimal(v)/factor).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        merchandise=sum(p['revenue'] for p in product_sales)
        profit=net(merchandise)-net(cost)
        for p in product_sales: p['profit']=net(p['revenue'])-net(p['cost'])
        daily=rows(c,'SELECT substr(paid_at,1,10) date,SUM(total_cents) total FROM orders WHERE paid_at IS NOT NULL AND substr(paid_at,1,10) BETWEEN ? AND ? GROUP BY date',(start,end))
        dm={d['date']:d['total'] for d in daily}
        dates=[];day=datetime.fromisoformat(start).date();last=datetime.fromisoformat(end).date()
        while day<=last: dates.append({'date':day.isoformat(),'total':dm.get(day.isoformat(),0)});day+=timedelta(days=1)
        cats={}
        for p in product_sales:
            cat=cats.setdefault(p['category'],{'name':p['category'],'revenue':0,'cost':0,'profit':0})
            for k in ['revenue','cost','profit']: cat[k]+=p[k]
        return {**revenue,'cost':cost,'profit':profit,'margin':round(profit/net(merchandise)*100,1) if merchandise else 0,'daily':dates,'products':product_sales,'categories':list(cats.values()),'start':start,'end':end}
def dashboard():
    today=datetime.fromisoformat(now()).date();r=resumen_ventas()
    with connect() as c:
        r['today']=one(c,'SELECT COALESCE(SUM(total_cents),0) n FROM orders WHERE substr(paid_at,1,10)=?',(today.isoformat(),))['n']
        r['week']=one(c,'SELECT COALESCE(SUM(total_cents),0) n FROM orders WHERE substr(paid_at,1,10)>=?',((today-timedelta(days=today.weekday())).isoformat(),))['n']
        r['month']=one(c,'SELECT COALESCE(SUM(total_cents),0) n FROM orders WHERE substr(paid_at,1,7)=?',(today.isoformat()[:7],))['n']
        r['states']=rows(c,'SELECT status,COUNT(*) count FROM orders GROUP BY status')
        r['pending']=one(c,"SELECT COUNT(*) n FROM payments WHERE status='por verificar'")['n']
        r['alerts']=rows(c,"SELECT a.*,p.sku,p.stock-p.reserved available,p.minimum FROM alerts a JOIN products p ON p.id=a.product_id WHERE a.status='activa' ORDER BY available LIMIT 10")
        r['low_stock']=one(c,"SELECT COUNT(*) n FROM alerts WHERE status='activa'")['n']
        r['recent']=rows(c,'SELECT id,code,customer_name,created_at,status,total_cents,payment_method FROM orders ORDER BY created_at DESC LIMIT 8')
        return r
