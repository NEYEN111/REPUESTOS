"""Additive, repeatable upgrades for existing installations."""
from backend.db import table_columns, is_postgres

def migrate(c):
    binary_type = 'BYTEA' if is_postgres() else 'BLOB'
    c.execute(f'''CREATE TABLE IF NOT EXISTS stored_media(
      name TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('product','voucher')),
      content {binary_type} NOT NULL, created_at TEXT NOT NULL)''')
    c.execute(f'''CREATE TABLE IF NOT EXISTS ml_lab_artifacts(
      name TEXT PRIMARY KEY, content {binary_type} NOT NULL, updated_at TEXT NOT NULL)''')
    for table, column, declaration in [
        ('purchase_orders', 'expected_at', "TEXT NOT NULL DEFAULT ''"),
        ('purchase_orders', 'note', "TEXT NOT NULL DEFAULT ''"),
        ('purchase_orders', 'request_key', 'TEXT'),
        ('purchase_items', 'received_quantity', 'INTEGER NOT NULL DEFAULT 0'),
        ('inventory_movements', 'reserved_balance', 'INTEGER'),
        ('inventory_movements', 'available_before', 'INTEGER'),
        ('inventory_movements', 'available_after', 'INTEGER'),
        ('inventory_policy', 'source', "TEXT NOT NULL DEFAULT 'manual'"),
    ]:
        columns = table_columns(c, table)
        if columns and column not in columns:
            c.execute(f'ALTER TABLE {table} ADD COLUMN {column} {declaration}')
            if column == 'received_quantity':
                c.execute("UPDATE purchase_items SET received_quantity=quantity WHERE purchase_order_id IN (SELECT id FROM purchase_orders WHERE status='recibida')")
    c.executescript('''
    CREATE TABLE IF NOT EXISTS inventory_policy(
      product_id INTEGER PRIMARY KEY REFERENCES products(id), location TEXT NOT NULL DEFAULT '',
      maximum INTEGER NOT NULL CHECK(maximum>=0), lead_days INTEGER NOT NULL DEFAULT 7 CHECK(lead_days>=0),
      pack_size INTEGER NOT NULL DEFAULT 1 CHECK(pack_size>0), supplier_id INTEGER REFERENCES suppliers(id),
      updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS purchase_receipts(
      id INTEGER PRIMARY KEY, purchase_order_id INTEGER NOT NULL REFERENCES purchase_orders(id),
      request_key TEXT NOT NULL UNIQUE, note TEXT NOT NULL, user_id INTEGER REFERENCES users(id), created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS purchase_receipt_items(
      id INTEGER PRIMARY KEY, receipt_id INTEGER NOT NULL REFERENCES purchase_receipts(id),
      purchase_item_id INTEGER NOT NULL REFERENCES purchase_items(id), quantity INTEGER NOT NULL CHECK(quantity>0));
    CREATE TABLE IF NOT EXISTS inventory_counts(
      id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
      expected INTEGER NOT NULL, counted INTEGER NOT NULL CHECK(counted>=0), difference INTEGER NOT NULL,
      reason TEXT NOT NULL, user_id INTEGER REFERENCES users(id), created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS product_price_history(
      id INTEGER PRIMARY KEY,product_id INTEGER NOT NULL REFERENCES products(id),
      old_price_cents INTEGER NOT NULL,new_price_cents INTEGER NOT NULL,old_cost_cents INTEGER NOT NULL,new_cost_cents INTEGER NOT NULL,
      reason TEXT NOT NULL,user_id INTEGER REFERENCES users(id),created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS shipments(
      order_id INTEGER PRIMARY KEY REFERENCES orders(id), carrier TEXT NOT NULL DEFAULT '', tracking TEXT NOT NULL DEFAULT '',
      expected_at TEXT NOT NULL DEFAULT '', recipient TEXT NOT NULL DEFAULT '', incident TEXT NOT NULL DEFAULT '',
      updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS stock_observations(
      product_id INTEGER NOT NULL REFERENCES products(id), date TEXT NOT NULL,
      stock INTEGER NOT NULL, reserved INTEGER NOT NULL, available INTEGER NOT NULL, incoming INTEGER NOT NULL,
      price_cents INTEGER NOT NULL, cost_cents INTEGER NOT NULL, minimum INTEGER NOT NULL,
      captured_at TEXT NOT NULL, source TEXT NOT NULL DEFAULT 'operacion_demo',
      PRIMARY KEY(product_id,date));
    CREATE INDEX IF NOT EXISTS idx_purchase_items_product ON purchase_items(product_id,purchase_order_id);
    CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id,order_id);
    CREATE INDEX IF NOT EXISTS idx_audit_date ON audit(created_at);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_purchase_request ON purchase_orders(request_key) WHERE request_key IS NOT NULL;
    CREATE TABLE IF NOT EXISTS catalog_quality(
      product_id INTEGER PRIMARY KEY REFERENCES products(id), source TEXT NOT NULL DEFAULT 'manual',
      presentation_source TEXT NOT NULL DEFAULT 'pendiente', compatibility_source TEXT NOT NULL DEFAULT 'pendiente',
      image_kind TEXT NOT NULL DEFAULT 'pendiente', manufacturer_reference TEXT NOT NULL DEFAULT '',
      rules_version TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL);
    ''')
    if 'source' not in table_columns(c, 'inventory_policy'):
        c.execute("ALTER TABLE inventory_policy ADD COLUMN source TEXT NOT NULL DEFAULT 'manual'")
