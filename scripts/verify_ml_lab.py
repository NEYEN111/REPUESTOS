"""Checks de importación y aislamiento sobre bases desechables."""
import io
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
folder = Path(tempfile.mkdtemp(prefix='ml-lab-', dir=ROOT/'.tmp'))
os.environ['DATABASE_PATH'] = str(folder/'store.db')
os.environ['ML_LAB_DIR'] = str(folder/'lab')
with sqlite3.connect(ROOT/'data/store.db') as src, sqlite3.connect(folder/'store.db') as dst:
    src.backup(dst)
from fastapi.testclient import TestClient
from backend.app import app
from backend.services import ml_lab
from backend.db import now
from openpyxl import Workbook


def run():
    with TestClient(app) as client:
        base = '/api/admin/ml/lab'
        for role, status in [(None, 401), ('cliente', 403), ('empleado', 403), ('admin', 200)]:
            client.cookies.clear()
            if role:
                assert client.post('/api/auth/login', json={'email': role+'@roda.pe', 'password': 'Roda2026!'}).status_code == 200
            assert client.get(base).status_code == status
            if role != 'admin':
                assert client.post(base+'/demo').status_code == status
        def post(path, body=None):
            r = client.post(base+path, json=body)
            assert r.status_code == 200, r.text
            return r.json()
        did = post('/datasets', {'name': 'Verificación', 'frequency': 'monthly', 'source': 'Fixture de prueba; no ventas reales'})['id']
        def upload(content, filename='ventas.csv', mapping=None):
            r = client.post(base+'/preview', data={'dataset': did, 'mapping': json.dumps(mapping or {})}, files={'file': (filename, content)})
            assert r.status_code == 200, r.text
            return r.json()
        r = upload(b'periodo,sku,unidades\n2020-01,A,0\n2020-02,A,\n2020-03,A,4\n')
        assert (r['accepted'],r['missing'],r['invalid']) == (3,1,0)
        post('/batches/'+r['id']+'/confirm')
        assert post('/batches/'+r['id']+'/confirm')['reused']
        r = upload(b'periodo,sku,unidades\n2020-01,A,0\n2020-02,A,\n')
        assert r['duplicates'] == 2 and r['accepted'] == 0
        r = upload(b'periodo,sku,unidades\n2020-01,A,10\n2020-04,A,2\n')
        assert r['conflicts'] == 1
        assert client.post(base+'/batches/'+r['id']+'/confirm').status_code == 400
        r = upload(b'periodo,sku,unidades\n2020-05,A,-2\n2020-06,A,NaN\n2020-07,A,1.2\n')
        assert r['invalid'] == 3
        assert upload(('periodo,sku,unidades\n'+now()[:7]+',A,5\n').encode())['invalid'] == 1
        daily = post('/datasets', {'name':'Control diario','frequency':'daily','source':'Fixture de validación'})['id']
        current = client.post(base+'/preview',data={'dataset':daily},files={'file':('dia.csv',('periodo,sku,unidades\n'+now()[:10]+',A,3\n').encode())})
        assert current.status_code == 200 and current.json()['invalid'] == 1
        # An Excel input uses column mapping, preserves true zero, and rejects formulas.
        book = Workbook(); sheet = book.active
        sheet.append(['mes','pieza','cantidad']); sheet.append(['2020-04','A',0])
        stream = io.BytesIO(); book.save(stream)
        r = upload(stream.getvalue(), 'ventas.xlsx')
        assert r['needs_mapping']
        r = upload(stream.getvalue(), 'ventas.xlsx', {'periodo':'mes','sku':'pieza','unidades':'cantidad'})
        assert r['accepted'] == 1 and r['preview'][0]['units'] == 0
        post('/batches/'+r['id']+'/confirm')
        sheet.append(['2020-05','A','=1+1']); stream=io.BytesIO(); book.save(stream)
        assert client.post(base+'/preview',data={'dataset':did},files={'file':('ventas.xlsx',stream.getvalue())}).status_code == 400
        with ml_lab.connection() as c:
            rows=[tuple(r) for r in c.execute('SELECT period,units FROM observations WHERE dataset=? ORDER BY period',(did,))]
        assert rows == [('2020-01',0),('2020-02',None),('2020-03',4),('2020-04',0)], rows
        assert client.post(base+f'/datasets/{did}/reset').status_code == 400
        with sqlite3.connect(folder/'store.db') as c:
            before=c.execute('SELECT id,stock,reserved FROM products ORDER BY id').fetchall()
            orders=c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        demo=post('/demo')['id']
        new=post(f'/datasets/{demo}/reset')['id']
        assert demo != new
        old=client.get(base+'?dataset='+demo).json()
        assert old['selected']['archived'] and old['stats']['rows'] == 96264
        assert client.get(base+'?dataset='+new).json()['stats']['rows'] == 96264
        with sqlite3.connect(folder/'store.db') as c:
            assert before == c.execute('SELECT id,stock,reserved FROM products ORDER BY id').fetchall()
            assert orders == c.execute('SELECT COUNT(*) FROM orders').fetchone()[0]
        assert client.get(base+'/examples/no.csv').status_code == 400
        assert client.get(base+'/examples/02_datos_nuevos.csv').status_code == 200
        excel = client.get(base+'/examples/02_datos_nuevos.xlsx')
        assert excel.status_code == 200
        headers, values = ml_lab.read_file(excel.content, '02_datos_nuevos.xlsx')
        assert headers == ['periodo', 'sku', 'unidades'] and len(values) == 24066
        # A trained version must not be approved just because it won among the five candidates.
        with ml_lab.connection() as c:
            report = {'candidates': [{'mae': .8}], 'validation_baseline': {'mae': 1.0}}
            c.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?)',
                      ('gate-v1', did, 'V1', '', json.dumps(report), 'gate-1', now()))
        assert client.post(base+f'/datasets/{did}/activate', json={'version': 'gate-v1'}).status_code == 400
        with ml_lab.connection() as c:
            later = {'scores': [{'version': 'gate-v1', 'mae': .7}], 'baseline': {'mae': .6}}
            c.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',
                      ('gate-compare', did, 'compare', 'done', json.dumps(later), None, now(), now(), None))
        assert client.post(base+f'/datasets/{did}/activate', json={'version': 'gate-v1'}).status_code == 400
        with ml_lab.connection() as c:
            later = {'scores': [{'version': 'gate-v1', 'mae': .7}], 'baseline': {'mae': .9},
                     'recommended': 'gate-v1', 'snapshot_rows': 4}
            c.execute('UPDATE jobs SET result=? WHERE id=?', (json.dumps(later), 'gate-compare'))
        assert client.post(base+f'/datasets/{did}/activate', json={'version': 'gate-v1'}).status_code == 200
        with ml_lab.connection() as c:
            c.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?)',
                      ('gate-v2', did, 'V2', '', json.dumps(report), 'gate-2', now()))
            later = {'scores': [{'version': 'gate-v1', 'mae': .8}, {'version': 'gate-v2', 'mae': .6}],
                     'baseline': {'mae': .9}, 'recommended': 'gate-v2', 'snapshot_rows': 4}
            c.execute('UPDATE jobs SET result=? WHERE id=?', (json.dumps(later), 'gate-compare'))
        new_batch = upload(b'periodo,sku,unidades\n2020-06,A,3\n')
        post('/batches/'+new_batch['id']+'/confirm')
        assert client.post(base+f'/datasets/{did}/activate', json={'version': 'gate-v2'}).status_code == 400
        with ml_lab.connection() as c:
            assert ml_lab.dataset(c, did)['active_version'] == 'gate-v1'
    print('PASS: roles, CSV/XLSX, mapping, missing vs zero, duplicates, conflicts, formulas, version gate and unchanged inventory/orders.')


if __name__ == '__main__':
    run()
