import Database from 'better-sqlite3';

// Scenario id used for temporary workbench test sessions. These sessions are
// created with save_transcript: false and must never appear in the normal
// player session history (GET /api/sessions).
export const WORKBENCH_TEST_SCENARIO_ID = 'workbench_test';

let _db: Database.Database | null = null;

// ---------------------------------------------------------------------------
// Versioned migration definitions
// Each migration runs exactly once per database, tracked in schema_migrations.
// All DDL uses CREATE TABLE IF NOT EXISTS so migrations are safe to apply to
// both fresh and existing databases.
// ---------------------------------------------------------------------------

type Migration = { name: string; up: (db: Database.Database) => void };

const MIGRATIONS: Migration[] = [
  {
    name: '0001_initial_schema',
    up: (db) => {
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

      // Backwards compat: add columns to databases that predate this migration
      // system. CREATE TABLE IF NOT EXISTS on new installs already includes
      // these columns, so the check-and-add is a no-op there.
      for (const [col, def] of [
        ['state_vars_json', "TEXT NOT NULL DEFAULT '{}'"],
        ['turn_count', 'INTEGER NOT NULL DEFAULT 0'],
      ] as const) {
        const cols = (db.pragma('table_info(sessions)') as { name: string }[]).map((r) => r.name);
        if (!cols.includes(col)) {
          db.exec(`ALTER TABLE sessions ADD COLUMN ${col} ${def}`);
        }
      }
    },
  },
  {
    name: '0002_session_ended_at',
    up: (db) => {
      const cols = (db.pragma('table_info(sessions)') as { name: string }[]).map((r) => r.name);
      if (!cols.includes('ended_at')) {
        db.exec('ALTER TABLE sessions ADD COLUMN ended_at TEXT');
      }
    },
  },
];

function runMigrations(db: Database.Database): void {
  db.exec(`
    CREATE TABLE IF NOT EXISTS schema_migrations (
      name       TEXT PRIMARY KEY,
      applied_at TEXT NOT NULL
    )
  `);

  const applied = new Set(
    (db.prepare('SELECT name FROM schema_migrations').all() as { name: string }[]).map((r) => r.name),
  );

  for (const migration of MIGRATIONS) {
    if (applied.has(migration.name)) continue;
    db.transaction(() => {
      migration.up(db);
      db.prepare('INSERT INTO schema_migrations (name, applied_at) VALUES (?, ?)').run(
        migration.name,
        new Date().toISOString(),
      );
    })();
  }
}

export function initDb(path = ':memory:'): Database.Database {
  const db = new Database(path);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');

  runMigrations(db);

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
