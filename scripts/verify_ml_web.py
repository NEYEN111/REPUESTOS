"""Focused integration checks on a disposable database copy."""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
(ROOT/'.tmp').mkdir(exist_ok=True)
fd,target=tempfile.mkstemp(suffix='.db',dir=ROOT/'.tmp');os.close(fd)
with sqlite3.connect(ROOT/'data/store.db') as src, sqlite3.connect(target) as dst: src.backup(dst)
os.environ['DATABASE_PATH']=target
from fastapi.testclient import TestClient
from backend.app import app
from backend.db import connect, transaction, now
from backend.services import ml_history, predictions


def run():
    with TestClient(app) as client:
        for role,expected in [(None,401),('cliente',403),('empleado',403),('admin',200)]:
            client.cookies.clear()
            if role:
                r=client.post('/api/auth/login',json={'email':role+'@roda.pe','password':'Roda2026!'})
                assert r.status_code==200,r.text
            for path in ['/overview','/evaluation','/images/04_matriz_metricas.png','/runs/1','/predictions/1','/runs/1/export']:
                r=client.get('/api/admin/ml'+path)
                if expected!=200: assert r.status_code==expected,(role,path,r.text)
            if expected!=200:
                for path in ['/calculate','/capture']:
                    assert client.post('/api/admin/ml'+path,json={'source':'referencia'}).status_code==expected
        r=client.get('/api/admin/ml/overview');assert r.status_code==200,r.text
        assert r.json()['model']=='Ridge'
        evaluation=client.get('/api/admin/ml/evaluation').json()
        assert len([m for m in evaluation['selection']['comparisons'] if m['kind']=='ML'])==5
        for asset in evaluation['assets']:
            r=client.get('/api/admin/ml/images/'+Path(asset['png']).name)
            assert r.status_code==200 and r.headers['content-type']=='image/png'
        with connect() as c: before=[tuple(r) for r in c.execute('SELECT id,stock,reserved FROM products ORDER BY id')]
        r=client.post('/api/admin/ml/calculate',json={'source':'referencia'});assert r.status_code==200,r.text
        rid=r.json()['id']
        repeat=client.post('/api/admin/ml/calculate',json={'source':'referencia'}).json()
        assert repeat=={'id':rid,'reused':True}
        data=client.get(f'/api/admin/ml/runs/{rid}').json()
        assert data['total']==952 and len(data['items'])==15,data
        p=client.get('/api/admin/ml/predictions/'+str(data['items'][0]['id'])).json()
        assert len(p['history'])==56 and 0<=p['lower_bound']<=p['prediction']<=p['upper_bound']
        assert p['features']['disponible_fin']==p['available']
        assert client.get(f'/api/admin/ml/runs/{rid}?q=not-a-product').json()['total']==0
        assert len(client.get(f'/api/admin/ml/runs/{rid}/export').text.splitlines())==953
        assert client.post('/api/admin/ml/calculate',json={'source':'invalid'}).status_code==400
        with connect() as c:
            assert before==[tuple(r) for r in c.execute('SELECT id,stock,reserved FROM products ORDER BY id')]
            count=c.execute('SELECT COUNT(*) FROM ml_samples').fetchone()[0]
        ml_history.capture();ml_history.capture()
        with connect() as c: assert c.execute('SELECT COUNT(*) FROM ml_samples').fetchone()[0]==count
        assert client.post('/api/admin/ml/calculate',json={'source':'operacion'}).status_code==400
        # A sale before a missing day does not make the continuous history usable.
        cutoff=date.fromisoformat(now()[:10])-timedelta(days=1)
        # A complete day closes only if the final business snapshot stayed valid.
        with transaction() as c:
            sample=c.execute('SELECT product_id,payload FROM ml_daily ORDER BY product_id LIMIT 1 OFFSET 1').fetchone()
            closed_pid=sample[0];closed_raw=json.loads(sample[1]);closed_day=cutoff.isoformat()
            closed_raw.update(fecha=closed_day,_missing_policy=0)
            closed_raw['_audit_max']=c.execute('SELECT COALESCE(MAX(id),0) FROM audit').fetchone()[0]
            c.execute('INSERT OR REPLACE INTO ml_daily VALUES(?,?,?,?,?,0)',(closed_pid,closed_day,json.dumps(closed_raw),closed_day+'T00:01:00-05:00',closed_day+'T23:59:10-05:00'))
            c.executemany('INSERT OR REPLACE INTO ml_samples VALUES(?,?,?,?,?)',[(closed_pid,closed_day,i,3,closed_day+'T00:01:00-05:00') for i in range(12)])
        ml_history.capture()
        with transaction() as c:
            assert c.execute('SELECT complete FROM ml_daily WHERE product_id=? AND date=?',(closed_pid,closed_day)).fetchone()[0]==1
            c.execute('UPDATE ml_daily SET complete=0 WHERE product_id=? AND date=?',(closed_pid,closed_day))
            c.execute("INSERT INTO audit(entity,entity_id,action,actor,detail,created_at) VALUES('inventory',?,'ajuste','usuario','{}',?)",(str(closed_pid),closed_day+'T23:59:59-05:00'))
        ml_history.capture()
        with connect() as c:
            assert c.execute('SELECT complete FROM ml_daily WHERE product_id=? AND date=?',(closed_pid,closed_day)).fetchone()[0]==0
        with transaction() as c:
            pid,sku=c.execute('SELECT id,sku FROM products WHERE active=1 ORDER BY id LIMIT 1').fetchone()
            raw=json.loads(c.execute('SELECT payload FROM ml_daily WHERE product_id=? ORDER BY date DESC LIMIT 1',(pid,)).fetchone()[0])
            for offset in [*range(56),57]:
                day=(cutoff-timedelta(days=offset)).isoformat();raw.update(fecha=day,ventas_pagadas=int(offset==57))
                c.execute('INSERT OR REPLACE INTO ml_daily VALUES(?,?,?,?,?,1)',(pid,day,json.dumps(raw),day+'T00:00:00-05:00',day+'T23:59:59-05:00'))
        assert not next(p for p in predictions.readiness()['products'] if p['id']==pid)['ready']
        with transaction() as c:
            raw.update(fecha=cutoff.isoformat(),ventas_pagadas=2)
            c.execute('UPDATE ml_daily SET payload=? WHERE product_id=? AND date=?',(json.dumps(raw),pid,cutoff.isoformat()))
        assert next(p for p in predictions.readiness()['products'] if p['id']==pid)['ready']
        r=client.post('/api/admin/ml/calculate',json={'source':'operacion'});assert r.status_code==200,r.text
        operational=client.get('/api/admin/ml/runs/'+str(r.json()['id'])).json()
        assert operational['total']==1
        # Only seven complete subsequent observations can resolve a forecast.
        op=operational['items'][0]
        with transaction() as c:
            for i in range(1,8):
                day=(cutoff+timedelta(days=i)).isoformat();raw.update(fecha=day,ventas_pagadas=1)
                c.execute('INSERT OR REPLACE INTO ml_daily VALUES(?,?,?,?,?,?)',(pid,day,json.dumps(raw),day+'T00:00:00-05:00',day+'T23:59:59-05:00',int(i!=7)))
            after=(cutoff+timedelta(days=8)).isoformat()
            ml_history.evaluate_matured(c,after,after)
            assert c.execute('SELECT actual FROM ml_predictions WHERE id=?',(op['id'],)).fetchone()[0] is None
            c.execute('UPDATE ml_daily SET complete=1 WHERE product_id=?',(pid,))
            ml_history.evaluate_matured(c,after,after)
            assert c.execute('SELECT actual FROM ml_predictions WHERE id=?',(op['id'],)).fetchone()[0]==7
        print('OK: roles, 16 graphs, 952 forecasts, immutable reuse, CSV, stock unchanged, sampling, gaps and observed outcomes.')

try: run()
finally:
    for suffix in ('','-wal','-shm'):
        try: Path(target+suffix).unlink(missing_ok=True)
        except PermissionError: pass
