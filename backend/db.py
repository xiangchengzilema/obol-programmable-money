"""
Obol — SQLite storage layer.
One fresh connection per call → no cross-thread SQLite errors (the bug that
sank our last hackathon demo). Never share a connection across requests.
"""
import os
import sqlite3

DB_PATH = os.getenv("OBOL_DB_PATH", os.path.join(os.path.dirname(__file__), "obol.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS creators (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,
  payout_address  TEXT NOT NULL,
  created_at      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS articles (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  creator_id  INTEGER NOT NULL,
  title       TEXT NOT NULL,
  summary     TEXT,
  content     TEXT NOT NULL,
  price_usdc  REAL NOT NULL,
  tags        TEXT,
  created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_runs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  query        TEXT NOT NULL,
  budget_usdc  REAL NOT NULL,
  status       TEXT NOT NULL DEFAULT 'running',   -- running | done | error
  answer       TEXT,
  plan         TEXT,                              -- agent's stated strategy for the run
  policy_json  TEXT,                              -- immutable per-run spending controls
  stop_rule    TEXT,                              -- structured rule that ended the run
  stop_reason  TEXT,                              -- human-readable final audit event
  total_spent  REAL NOT NULL DEFAULT 0,
  coverage     REAL NOT NULL DEFAULT 0,           -- 0..1 share of query aspects covered
  created_at   REAL NOT NULL,
  finished_at  REAL
);
CREATE TABLE IF NOT EXISTS decisions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id      INTEGER NOT NULL,
  article_id  INTEGER NOT NULL,
  decision    TEXT NOT NULL,        -- buy | skip
  reason      TEXT,
  policy_rule TEXT,                 -- stable rule id behind the decision
  relevance   REAL,
  price_usdc  REAL,
  budget_before_usdc REAL,          -- unspent total balance before the action
  budget_after_usdc  REAL,          -- unspent total balance after the action
  created_at  REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS receipts (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id      INTEGER,                      -- NULL for external x402 purchases
  article_id  INTEGER NOT NULL,
  creator_id  INTEGER NOT NULL,
  amount_usdc REAL NOT NULL,
  tx_hash     TEXT,
  transaction_id TEXT,
  blockchain  TEXT,
  settlement_mode TEXT NOT NULL DEFAULT 'legacy', -- live | mock | legacy
  source      TEXT NOT NULL DEFAULT 'agent', -- agent | x402 | unlock
  buyer       TEXT,                          -- external buyer id/address (x402)
  created_at  REAL NOT NULL
);
"""

# Columns added after first release — applied to existing DBs idempotently.
_MIGRATIONS = [
    ("receipts", "source", "TEXT NOT NULL DEFAULT 'agent'"),
    ("receipts", "buyer", "TEXT"),
    ("receipts", "transaction_id", "TEXT"),
    ("receipts", "settlement_mode", "TEXT NOT NULL DEFAULT 'legacy'"),
    ("agent_runs", "plan", "TEXT"),
    ("agent_runs", "coverage", "REAL NOT NULL DEFAULT 0"),
    ("agent_runs", "policy_json", "TEXT"),
    ("agent_runs", "stop_rule", "TEXT"),
    ("agent_runs", "stop_reason", "TEXT"),
    ("decisions", "policy_rule", "TEXT"),
    ("decisions", "budget_before_usdc", "REAL"),
    ("decisions", "budget_after_usdc", "REAL"),
]


def _migrate(conn):
    for table, col, decl in _MIGRATIONS:
        cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
            except Exception:
                pass


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=10000")
    return conn


def init_db():
    conn = get_db()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    _migrate(conn)
    conn.commit()
    conn.close()


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_list(rows):
    return [dict(r) for r in rows]
