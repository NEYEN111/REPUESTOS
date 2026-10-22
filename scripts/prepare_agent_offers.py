"""Idempotent academic alternatives for the current replenishment candidates."""
import sys
from pathlib import Path
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backend import db
from backend.services import agent_data as data

def prepare():
    items=data.candidates(20)['items'];count=0
    with db.transaction() as c:
        uid=db.one(c,"SELECT id FROM users WHERE role='admin' ORDER BY id LIMIT 1")['id']
        for name,percent,lead,pack in [('Proveedor académico · Ahorro',95,7,4),('Proveedor académico · Entrega rápida',108,2,1)]:
            supplier=db.one(c,'SELECT id FROM suppliers WHERE name=?',(name,))
            sid=supplier['id'] if supplier else c.execute("INSERT INTO suppliers(name,ruc,email,phone) VALUES(?,'','','')",(name,)).lastrowid
            for p in items:
                cost=max(1,(p['cost_cents']*percent+50)//100)
                if cost>=p['price_cents']:continue
                count+=c.execute('''INSERT OR IGNORE INTO supplier_offers(product_id,supplier_id,cost_cents,lead_days,pack_size,minimum_quantity,valid_until,source,updated_at,user_id)
                    VALUES(?,?,?,?,?,?,?,'referencia_catalogo',?,?)''',(p['id'],sid,cost,lead,pack,pack,(date.fromisoformat(db.now()[:10])+timedelta(days=30)).isoformat(),db.now(),uid)).rowcount
        db.audit(c,'supplier_offers','academic','preparar_alternativas',uid,detail={'created':count,'origin':'Condiciones académicas derivadas de costos del catálogo; no son cotizaciones externas.'})
    return count
if __name__=='__main__':print({'academic_offers_created':prepare()})
