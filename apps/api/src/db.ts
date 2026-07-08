import Database from 'better-sqlite3';

// Scenario id used for temporary workbench test sessions. These sessions are
// created with save_transcript: false and must never appear in the normal
// player session history (GET /api/sessions).
export const WORKBENCH_TEST_SCENARIO_ID = 'workbench_test';

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

    CREATE TABLE IF NOT EXISTS installed_models (
      id              INTEGER PRIMARY KEY AUTOINCREMENT,
      registry_id     TEXT,
      filename        TEXT NOT NULL,
      file_path       TEXT NOT NULL DEFAULT '',
      size_bytes      INTEGER,
      install_status  TEXT NOT NULL DEFAULT 'pending',
      progress_bytes  INTEGER NOT NULL DEFAULT 0,
      error_message   TEXT,
      verified_sha256 TEXT,
      installed_at    TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS model_config (
      key   TEXT PRIMARY KEY,
      value TEXT NOT NULL
    );
  `);
  // Migrate existing databases: CREATE TABLE IF NOT EXISTS is a no-op when
  // the table already exists, so new columns must be added explicitly.
  for (const [col, def] of [
    ['state_vars_json', "TEXT NOT NULL DEFAULT '{}'"],
    ['turn_count', 'INTEGER NOT NULL DEFAULT 0'],
  ] as const) {
    const exists = (
      db.pragma(`table_info(sessions)`) as { name: string }[]
    ).some((r) => r.name === col);
    if (!exists) {
      db.exec(`ALTER TABLE sessions ADD COLUMN ${col} ${def}`);
    }
  }

  // On startup, any download that was 'pending' or 'downloading' when the
  // server last shut down cannot resume. Mark them failed so the UI doesn't
  // show a phantom in-progress bar.
  db.exec(`
    UPDATE installed_models
    SET install_status = 'failed',
        error_message  = 'Download interrupted — server restarted. Please retry.'
    WHERE install_status IN ('pending', 'downloading')
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
