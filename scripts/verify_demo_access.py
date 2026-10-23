"""Focused classroom access checks, with an isolated database and no external calls."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['RODA_FORCE_SQLITE'] = '1'
from backend import db
from backend.app import app
from backend.services import customers
from fastapi.testclient import TestClient

with tempfile.TemporaryDirectory(dir=db.ROOT / '.tmp') as folder:
    with patch.object(db, 'DB', Path(folder) / 'demo.db'):
        with db.transaction() as c:
            c.executescript((db.ROOT / 'backend/schema.sql').read_text(encoding='utf-8'))
            for role, email in [('admin', 'admin@roda.pe'), ('cliente', 'cliente@roda.pe')]:
                c.execute('INSERT INTO users(name,email,password_hash,role,consent_at,created_at) VALUES(?,?,?,?,?,?)',
                          (role, email, customers.password_hash('isolated-example'), role, db.now(), db.now()))
        client = TestClient(app)
        with patch.dict(os.environ, {'DEMO_ACCESS_ENABLED': 'false'}):
            assert client.post('/api/auth/demo', json={'role': 'admin'}).status_code == 404
        with patch.dict(os.environ, {'DEMO_ACCESS_ENABLED': 'true'}):
            for role in ['admin', 'cliente']:
                reply = client.post('/api/auth/demo', json={'role': role})
                assert reply.status_code == 200 and reply.json()['role'] == role
                assert 'password_hash' not in reply.json()
                assert client.get('/api/auth/me').json()['role'] == role
                if role == 'cliente':
                    assert client.put('/api/admin/config', json={}).status_code == 403
            assert client.post('/api/auth/demo', json={'role': 'empleado'}).status_code == 400
            assert client.post('/api/auth/demo', json={'role': []}).status_code == 400
            client.post('/api/auth/demo', json={'role': 'admin'})
        with patch.dict(os.environ, {'DEMO_ACCESS_ENABLED': 'false'}):
            assert client.get('/api/auth/me').json() is None
            reply = client.post('/api/auth/login', json={'email': 'admin@roda.pe', 'password': 'isolated-example'})
            assert reply.status_code == 200 and reply.json()['role'] == 'admin'
        client.close()
        import gc
        gc.collect()
print('OK: demo desactivada, dos roles, permisos, rol rechazado, revocación y login original.')
