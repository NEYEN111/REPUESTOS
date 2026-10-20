CREATE TABLE IF NOT EXISTS ml_daily (
 product_id INTEGER NOT NULL REFERENCES products(id), date TEXT NOT NULL,
 payload TEXT NOT NULL, first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
 complete INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(product_id,date));
CREATE TABLE IF NOT EXISTS ml_samples (
 product_id INTEGER NOT NULL REFERENCES products(id), date TEXT NOT NULL, slot INTEGER NOT NULL,
 available INTEGER NOT NULL, captured_at TEXT NOT NULL, PRIMARY KEY(product_id,date,slot));
CREATE TABLE IF NOT EXISTS ml_runs (
 id INTEGER PRIMARY KEY, source TEXT NOT NULL CHECK(source IN ('referencia','operacion')),
 cutoff TEXT NOT NULL, model_hash TEXT NOT NULL, created_at TEXT NOT NULL,
 user_id INTEGER REFERENCES users(id), actor TEXT NOT NULL DEFAULT 'usuario',
 count INTEGER NOT NULL, summary TEXT NOT NULL,
 UNIQUE(source,cutoff,model_hash));
CREATE TABLE IF NOT EXISTS ml_predictions (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES ml_runs(id),
 product_id INTEGER NOT NULL REFERENCES products(id), sku TEXT NOT NULL,
 prediction REAL NOT NULL, lower_bound REAL NOT NULL, upper_bound REAL NOT NULL,
 available INTEGER NOT NULL, rotation TEXT NOT NULL, review INTEGER NOT NULL,
 coverage TEXT NOT NULL, reasons TEXT NOT NULL, features TEXT NOT NULL,
 history TEXT NOT NULL, actual INTEGER, evaluated_at TEXT, UNIQUE(run_id,sku));
CREATE INDEX IF NOT EXISTS idx_ml_daily_date ON ml_daily(date,complete);
CREATE INDEX IF NOT EXISTS idx_ml_predictions_run ON ml_predictions(run_id,product_id);
