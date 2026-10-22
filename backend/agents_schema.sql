CREATE TABLE IF NOT EXISTS supplier_offers (
 id INTEGER PRIMARY KEY, product_id INTEGER NOT NULL REFERENCES products(id),
 supplier_id INTEGER NOT NULL REFERENCES suppliers(id), cost_cents INTEGER NOT NULL CHECK(cost_cents>0),
 lead_days INTEGER NOT NULL CHECK(lead_days BETWEEN 1 AND 365),
 pack_size INTEGER NOT NULL CHECK(pack_size>0), minimum_quantity INTEGER NOT NULL CHECK(minimum_quantity>0),
 valid_until TEXT NOT NULL, source TEXT NOT NULL CHECK(source IN ('manual','referencia_catalogo')),
 active INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL, user_id INTEGER REFERENCES users(id),
 UNIQUE(product_id,supplier_id));
CREATE TABLE IF NOT EXISTS agent_runs (
 id INTEGER PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'en_cola',
 request_key TEXT NOT NULL UNIQUE, user_id INTEGER NOT NULL REFERENCES users(id),
 budget_cents INTEGER NOT NULL, product_limit INTEGER NOT NULL, strategy TEXT NOT NULL DEFAULT 'costo',
 created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, lease_until TEXT,
 result TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
 model TEXT NOT NULL, calls INTEGER NOT NULL DEFAULT 0, tokens INTEGER NOT NULL DEFAULT 0,
 approved_by INTEGER REFERENCES users(id), approved_at TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_single_worker ON agent_runs(status) WHERE status='en_curso';
CREATE INDEX IF NOT EXISTS idx_agent_runs_status ON agent_runs(status,id);
CREATE TABLE IF NOT EXISTS agent_steps (
 id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL REFERENCES agent_runs(id),
 agent TEXT NOT NULL, kind TEXT NOT NULL, target TEXT NOT NULL DEFAULT '',
 message TEXT NOT NULL, data TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_agent_steps_run ON agent_steps(run_id,id);
CREATE TABLE IF NOT EXISTS agent_schedules (
 id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL DEFAULT 0,
 kind TEXT NOT NULL, at_time TEXT NOT NULL, budget_cents INTEGER NOT NULL,
 product_limit INTEGER NOT NULL, user_id INTEGER NOT NULL REFERENCES users(id),
 updated_at TEXT NOT NULL, last_date TEXT NOT NULL DEFAULT '',
 last_run_id INTEGER REFERENCES agent_runs(id), last_message TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS agent_case_checks (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id),
 result TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS agent_presentations (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), request_key TEXT NOT NULL UNIQUE,
 status TEXT NOT NULL DEFAULT 'en_cola', result TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, lease_until TEXT);
CREATE UNIQUE INDEX IF NOT EXISTS idx_presentation_worker ON agent_presentations(status) WHERE status='en_curso';
