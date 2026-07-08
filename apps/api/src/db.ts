import Database from 'better-sqlite3';

let _db: Database.Database | null = null;

export function initDb(path = ':memory:'): Database.Database {
  const db = new Database(path);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  db.exec(`
    CREATE TABLE IF NOT EXISTS sessions (
      session_id      TEXT PRIMARY KEY,
      scenario_id     TEXT NOT NULL,
      state           TEXT NOT NULL DEFAULT 'NotStarted',
      ending_type     TEXT,
      created_at      TEXT NOT NULL,
      setup_json      TEXT NOT NULL,
      state_vars_json TEXT NOT NULL DEFAULT '{}',
      turn_count      INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS session_events (
      event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
      session_id   TEXT NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
      event_type   TEXT NOT NULL,
      payload_json TEXT NOT NULL DEFAULT '{}',
      created_at   TEXT NOT NULL
    );
  `);
  _db = db;
  return db;
}

export function getDb(): Database.Database {
  if (!_db) initDb(':memory:');
  return _db!;
}

export function resetDb(): void {
  if (_db) {
    try {
      _db.close();
    } catch {
      // ignore
    }
  }
  _db = null;
  initDb(':memory:');
}
