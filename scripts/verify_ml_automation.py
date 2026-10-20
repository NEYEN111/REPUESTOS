"""Verificación del ciclo sobre bases desechables; nunca añade ventas a la tienda."""
import json
import os
import sqlite3
import sys
import tempfile
import time
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
folder = Path(tempfile.mkdtemp(prefix='ml-auto-', dir=ROOT/'.tmp'))
os.environ['DATABASE_PATH'] = str(folder/'store.db')
os.environ['ML_LAB_DIR'] = str(folder/'lab')
with sqlite3.connect(ROOT/'data/store.db') as src, sqlite3.connect(folder/'store.db') as dst:
    src.backup(dst)
from backend.db import init_db, connect, now
from backend.services import ml_automation as auto, ml_lab as lab
from backend.app import app
from fastapi.testclient import TestClient


def run():
    init_db()
    auto.init()
    with connect() as c:
        c.execute('DELETE FROM ml_daily')
        before = list(c.execute('SELECT id,stock,reserved FROM products ORDER BY id'))
        products = list(c.execute('SELECT id,sku FROM products ORDER BY id LIMIT 8'))
    assert not auto.sync()['ready']
    with TestClient(app) as client:
        for role, expected in [(None, 401), ('cliente', 403), ('empleado', 403), ('admin', 200)]:
            client.cookies.clear()
            if role:
                assert client.post('/api/auth/login', json={'email': role+'@roda.pe', 'password': 'Roda2026!'}).status_code == 200
            assert client.get('/api/admin/ml/automation').status_code == expected
            assert client.post('/api/admin/ml/automation/review').status_code == expected
        assert client.post('/api/admin/ml/automation/settings', json={'enabled': False}).status_code == 200
        assert auto.tick() is None
        # Manual review still checks quality while scheduling is paused.
        assert 'No se entrena' in client.post('/api/admin/ml/automation/review').json()['message']
        assert client.post('/api/admin/ml/automation/settings', json={'enabled': 'yes'}).status_code == 400
        assert client.post(f'/api/admin/ml/lab/datasets/{auto.DATASET}/jobs', json={'action': 'train'}).status_code == 400
        assert client.post(f'/api/admin/ml/lab/datasets/{auto.DATASET}/activate', json={'version': 'any'}).status_code == 400
        assert client.post('/api/admin/ml/lab/preview', data={'dataset': auto.DATASET},
                           files={'file': ('ventas.csv', b'periodo,sku,unidades\n2020-01-01,A,4')}).status_code == 400
    today = date.fromisoformat(now()[:10])
    with connect() as c:
        c.execute('DELETE FROM ml_daily')
        for product in products:
            for offset in range(1, 91):
                day = (today-timedelta(days=offset)).isoformat()
                raw = {'sku': product['sku'], 'ventas_pagadas': 1 if offset % 3 else 0, 'fuente_datos': 'operacion'}
                c.execute('INSERT INTO ml_daily VALUES(?,?,?,?,?,?)',
                          (product['id'], day, json.dumps(raw), day+'T00:00:00', day+'T23:59:59', 1))
        # Incomplete rows, current day and fabricated-source rows must not enter training.
        raw = {'sku': 'IGNORE', 'ventas_pagadas': 100, 'fuente_datos': 'referencia'}
        c.execute('INSERT INTO ml_daily VALUES(?,?,?,?,?,?)',
                  (products[0]['id'], today.isoformat(), json.dumps(raw), now(), now(), 0))
    quality = auto.sync()
    assert quality['ready'] and quality['rows'] == 720 and quality['training_rows'] == 112
    assert auto.sync()['rows'] == 720  # Idempotent collection.
    with lab.connection() as c:
        count = c.execute('SELECT COUNT(*) FROM observations WHERE units=0').fetchone()[0]
        assert count == 240
    with patch.object(lab, 'start_job', return_value={'id': 'training'}) as start:
        message = auto.tick(force=True)['message']
        assert 'cinco' in message and start.call_count == 1
    cutoff = (today-timedelta(days=1)).isoformat()
    def completed(jid, action, result):
        with lab.connection() as c:
            c.execute('INSERT OR REPLACE INTO jobs VALUES(?,?,?,?,?,?,?,?,?)',
                      (jid, auto.DATASET, action, 'done', json.dumps(result), None, now(), now(), None))
        auto.update(pending_job=jid)
    # A completed model that loses to the baseline must not be activated.
    report = {'cutoff': cutoff, 'beats_baseline': False, 'candidates': [{'mae': 2}],
              'validation_baseline': {'mae': 1}}
    completed('training', 'train', report)
    assert 'sin activar' in auto.tick(force=True)['message']
    assert auto.status()['active_version'] is None
    with patch.object(lab, 'start_job') as start:
        auto.tick(force=True)
        start.assert_not_called()  # Same month is not trained again.
    # A first version that passes validation still needs genuinely later observations.
    first_report = {'cutoff': (today-timedelta(days=29)).isoformat(),
                    'beats_baseline': True, 'candidates': [{'mae': .7}],
                    'validation_baseline': {'mae': 1}}
    with lab.connection() as c:
        c.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?)',
                  ('first-v1', auto.DATASET, 'V1', 'unused.joblib', json.dumps(first_report), 'first', now()))
    completed('first-v1', 'train', first_report)
    assert 'sin activar' in auto.tick(force=True)['message']
    assert auto.status()['active_version'] is None
    with patch.object(lab, 'start_job', return_value={'id': 'first-comparison'}) as start:
        auto.tick(force=True)
        assert start.call_args.args[1] == 'compare'
        assert start.call_args.args[3] == ['first-v1']
    first_comparison = {'scores': [{'version': 'first-v1', 'mae': .7}],
                        'baseline': {'mae': .9}, 'recommended': 'first-v1',
                        'snapshot_rows': 720}
    completed('first-comparison', 'compare', first_comparison)
    with patch.object(lab, 'start_job', return_value={'id': 'first-prediction'}):
        assert 'aprobada' in auto.tick(force=True)['message']
    assert auto.status()['active_version'] == 'first-v1'
    # Lease protects concurrent review and survives process instances.
    with lab.connection() as c:
        c.execute("UPDATE automation SET lease_until='2099-01-01',lease_token='other' WHERE id=1")
    assert 'en curso' in auto.tick(force=True)['message']
    with lab.connection() as c:
        c.execute("UPDATE automation SET lease_until=NULL,lease_token=NULL WHERE id=1")
        for vid in ['v1', 'v2']:
            c.execute('INSERT INTO versions VALUES(?,?,?,?,?,?,?)',
                      (vid, auto.DATASET, vid.upper(), 'unused.joblib', json.dumps(report), vid, now()))
        c.execute('UPDATE datasets SET active_version=? WHERE id=?', ('v1', auto.DATASET))
    auto.update(candidate='v2')
    # Better than incumbent but worse than baseline: retain incumbent.
    comparison = {'scores': [{'version': 'v1', 'mae': 1}, {'version': 'v2', 'mae': .8}],
                  'baseline': {'mae': .7}, 'recommended': 'v2', 'snapshot_rows': 720}
    completed('comparison1', 'compare', comparison)
    with patch.object(lab, 'start_job', return_value={'id': 'prediction'}):
        assert 'conserva' in auto.tick(force=True)['message']
    assert auto.status()['active_version'] == 'v1'
    # Beats both by >1%: promote, audited and a new prediction requested.
    auto.update(candidate='v2')
    comparison['baseline']['mae'] = .9
    completed('comparison2', 'compare', comparison)
    with patch.object(lab, 'start_job', return_value={'id': 'prediction'}) as start:
        assert 'aprobada' in auto.tick(force=True)['message']
        assert start.call_args.args[3] == ['v2']
    assert auto.status()['active_version'] == 'v2'
    # Waiting for a candidate must not freeze the incumbent's daily forecasts.
    auto.update(pending_job=None, candidate='v1')
    with patch.object(lab, 'start_job', return_value={'id': 'waiting-prediction'}) as start:
        assert 'mientras' in auto.tick(force=True)['message']
        assert start.call_args.args[3] == ['v2']
    # A restarted orchestrator releases its interrupted lease and resumes pending work.
    with lab.connection() as c:
        c.execute("UPDATE automation SET lease_until='2099-01-01',lease_token='interrupted',pending_job='interrupted' WHERE id=1")
    auto.recover()
    assert auto.status()['lease_until'] is None and auto.status()['pending_job'] == 'interrupted'
    # Retry state and immutable closure conflict detection.
    with connect() as c:
        raw = {'sku': products[0]['sku'], 'ventas_pagadas': 77, 'fuente_datos': 'operacion'}
        c.execute('UPDATE ml_daily SET payload=? WHERE product_id=? AND date=?', (json.dumps(raw), products[0]['id'], cutoff))
    assert 'cambió' in auto.tick(force=True)['message']
    with connect() as c:
        original = {'sku': products[0]['sku'], 'ventas_pagadas': 1, 'fuente_datos': 'operacion'}
        c.execute('UPDATE ml_daily SET payload=? WHERE product_id=? AND date=?', (json.dumps(original), products[0]['id'], cutoff))
        c.execute('UPDATE ml_daily SET complete=0 WHERE product_id=? AND date=?', (products[0]['id'], cutoff))
    assert 'dejó de estar completo' in auto.tick(force=True)['message']
    # Run the actual subprocess pipeline on a separate fixture history.
    did = lab.create('Prueba aislada', 'daily', 'Fixture artificial exclusivamente para verificar el software', None)
    with lab.connection() as c:
        c.execute('INSERT INTO observations SELECT ?,sku,period,units,NULL FROM observations WHERE dataset=?', (did, auto.DATASET))
    job = lab.start_job(did, 'train', None)
    deadline = time.monotonic()+120
    while time.monotonic() < deadline:
        with lab.connection() as c:
            job_state = lab.row(c, 'SELECT * FROM jobs WHERE id=?', (job['id'],))
        if job_state['status'] != 'running':
            break
        time.sleep(.2)
    assert job_state['status'] == 'done', job_state.get('error')
    report = json.loads(job_state['result'])
    assert len(report['candidates']) == 5 and report['temporal_windows'] == 3
    assert all(w['training_end'] <= w['validation_start'] for w in report['windows'])
    path, label = lab.version_file(job['id'])
    assert path.exists() and label == 'V1'
    with connect() as c:
        assert [tuple(x) for x in before] == [tuple(x) for x in c.execute('SELECT id,stock,reserved FROM products ORDER BY id')]
    print('PASS: permisos, cierres, ceros, aislamiento, pausas, revisión manual, idempotencia, primera versión en observación, comparación, promoción y auditoría.')


if __name__ == '__main__':
    run()
