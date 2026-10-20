import sqlite3, json, os
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.getenv('DATABASE_PATH', str(ROOT / 'data' / 'store.db')))
def now(): return datetime.now(ZoneInfo('America/Lima')).isoformat(timespec='seconds')
def config(): return json.loads((ROOT / 'store.config.json').read_text(encoding='utf-8'))
def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA journal_mode=WAL')
    return c
@contextmanager
def transaction():
    c = connect()
    try:
        c.execute('BEGIN IMMEDIATE')
        yield c
        c.commit()
    except Exception:
        c.rollback(); raise
    finally: c.close()
def rows(c, sql, args=()): return [dict(r) for r in c.execute(sql,args).fetchall()]
def one(c, sql, args=()):
    r=c.execute(sql,args).fetchone()
    return dict(r) if r else None
def audit(c, entity, entity_id, action, user_id=None, actor='usuario', detail=None):
    c.execute('INSERT INTO audit(entity,entity_id,action,user_id,actor,detail,created_at) VALUES(?,?,?,?,?,?,?)',(entity,str(entity_id),action,user_id,actor,json.dumps(detail or {},ensure_ascii=False),now()))
def init_db():
    from backend.migrations import migrate
    with connect() as c:
        c.executescript((ROOT/'backend/schema.sql').read_text(encoding='utf-8'))
        migrate(c)
        c.executescript((ROOT/'backend/ml_schema.sql').read_text(encoding='utf-8'))
