import json, os, re, sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DB = Path(os.getenv('DATABASE_PATH', str(ROOT / 'data' / 'store.db')))


def _database_url():
    if os.getenv('RODA_FORCE_SQLITE') == '1':
        return ''
    value = os.getenv('DATABASE_URL', '').strip()
    if value:
        return value
    try:
        for line in (ROOT / '.env').read_text(encoding='utf-8-sig').splitlines():
            key, separator, candidate = line.partition('=')
            if separator and key.strip() == 'DATABASE_URL':
                return candidate.strip().strip("\"'")
    except OSError:
        pass
    return ''


DATABASE_URL = _database_url()
try:
    import psycopg
except ImportError:
    psycopg = None

IntegrityError = psycopg.IntegrityError if psycopg else sqlite3.IntegrityError
DatabaseError = psycopg.Error if psycopg else sqlite3.Error


class _CompatRow(dict):
    """Dict-style PostgreSQL row with SQLite-compatible numeric indexing."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


def _pg_row(cursor):
    columns = [column.name for column in cursor.description] if cursor.description else []

    def make_row(record):
        return _CompatRow(zip(columns, record))

    return make_row


_SERIAL_TABLES = {
    'users', 'categories', 'brands', 'vehicles', 'products', 'compatibility',
    'product_images', 'garage', 'addresses', 'quotes', 'quote_items', 'orders',
    'order_items', 'payments', 'order_history', 'inventory_movements', 'suppliers',
    'purchase_orders', 'purchase_items', 'complaints', 'events', 'alerts', 'audit',
    'daily_stock', 'inventory_counts', 'product_price_history', 'purchase_receipts', 'purchase_receipt_items',
    'ml_runs', 'ml_predictions', 'supplier_offers', 'agent_runs', 'agent_steps',
    'agent_case_checks', 'agent_presentations',
}


class _PgCursor:
    def __init__(self, cursor):
        self._cursor = cursor
        self._lastrowid_read = False
        self._lastrowid = None

    @property
    def lastrowid(self):
        if not self._lastrowid_read:
            row = self._cursor.fetchone()
            self._lastrowid = row['id'] if row else None
            self._lastrowid_read = True
        return self._lastrowid

    def __getattr__(self, name):
        return getattr(self._cursor, name)

    def __iter__(self):
        return iter(self._cursor)


class _PgConnection:
    def __init__(self, connection):
        self._connection = connection

    @staticmethod
    def _translate(query, returning=True):
        query = query.strip()
        if query.upper().startswith('PRAGMA DEFER_FOREIGN_KEYS='):
            return 'SELECT 1'
        pragma = re.fullmatch(r'PRAGMA\s+table_info\((\w+)\)', query, re.I)
        if pragma:
            table = pragma.group(1).lower()
            if not re.fullmatch(r'[a-z_][a-z0-9_]*', table):
                raise ValueError('Nombre de tabla no válido.')
            return ('SELECT ordinal_position AS cid, column_name AS name FROM information_schema.columns '
                    'WHERE table_schema=current_schema() AND table_name=%s ORDER BY ordinal_position')
        query = re.sub(r'^BEGIN\s+IMMEDIATE\s*$', 'BEGIN', query, flags=re.I)
        ignore = bool(re.match(r'INSERT\s+OR\s+IGNORE\s+INTO\s+', query, re.I))
        if ignore:
            query = re.sub(r'^(INSERT)\s+OR\s+IGNORE\s+INTO\s+', r'\1 INTO ', query, flags=re.I)
            if not re.search(r'\bON\s+CONFLICT\b', query, re.I):
                query = query.rstrip(';') + ' ON CONFLICT DO NOTHING'
        query = _replace_placeholders(query)
        insert = re.match(r'INSERT\s+INTO\s+([a-z_][a-z0-9_]*)\b', query, re.I)
        if returning and insert and insert.group(1).lower() in _SERIAL_TABLES and not re.search(r'\bRETURNING\b', query, re.I):
            query = query.rstrip(';') + ' RETURNING id'
        return query

    def execute(self, query, params=()):
        match = re.fullmatch(r'PRAGMA\s+table_info\((\w+)\)', query.strip(), re.I)
        translated = self._translate(query)
        if match:
            return _PgCursor(self._connection.execute(translated, (match.group(1).lower(),)))
        return _PgCursor(self._connection.execute(translated, params or ()))

    def executemany(self, query, params_seq):
        translated = self._translate(query, returning=False)
        return _PgCursor(self._connection.cursor().executemany(translated, params_seq))

    def executescript(self, script):
        script = postgres_schema(script)
        for statement in script.split(';'):
            if statement.strip():
                self.execute(statement)
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            if exc_type is None:
                self._connection.commit()
            else:
                self._connection.rollback()
        finally:
            self._connection.close()

    def __getattr__(self, name):
        return getattr(self._connection, name)


def _replace_placeholders(query):
    result = []
    quote = None
    i = 0
    while i < len(query):
        char = query[i]
        if quote:
            result.append(char)
            if char == quote:
                if i + 1 < len(query) and query[i + 1] == quote:
                    result.append(query[i + 1])
                    i += 1
                else:
                    quote = None
        elif char in ("'", '"'):
            quote = char
            result.append(char)
        elif char == '?':
            result.append('%s')
        else:
            result.append(char)
        i += 1
    return ''.join(result)


def is_postgres():
    return DATABASE_URL.startswith(('postgres://', 'postgresql://'))


def now(): return datetime.now(ZoneInfo('America/Lima')).isoformat(timespec='seconds')
def config(): return json.loads((ROOT / 'store.config.json').read_text(encoding='utf-8'))
def connect():
    if is_postgres():
        if psycopg is None:
            raise RuntimeError('Instala psycopg[binary] para conectar con PostgreSQL.')
        url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        return _PgConnection(psycopg.connect(url, row_factory=_pg_row, connect_timeout=10, prepare_threshold=None))
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
        c.execute('BEGIN' if is_postgres() else 'BEGIN IMMEDIATE')
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


def table_columns(c, table):
    if not re.fullmatch(r'[a-z_][a-z0-9_]*', table):
        raise ValueError('Nombre de tabla no válido.')
    if is_postgres():
        return {row['name'] for row in c.execute(
            'SELECT column_name AS name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?',
            (table.lower(),))}
    return {row['name'] for row in c.execute(f'PRAGMA table_info({table})')}


def postgres_schema(script):
    if not is_postgres():
        return script
    return re.sub(r'\bid\s+INTEGER\s+PRIMARY\s+KEY\b', 'id SERIAL PRIMARY KEY', script, flags=re.I)


def init_db():
    from backend.migrations import migrate
    with connect() as c:
        schema = (ROOT/'backend/schema.sql').read_text(encoding='utf-8')
        ml_schema = (ROOT/'backend/ml_schema.sql').read_text(encoding='utf-8')
        c.executescript(postgres_schema(schema))
        migrate(c)
        c.executescript(postgres_schema(ml_schema))
