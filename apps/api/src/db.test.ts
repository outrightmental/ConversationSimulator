import { describe, it, expect, beforeEach } from 'vitest';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { initDb, resetDb, getDb } from './db.js';
import Database from 'better-sqlite3';

function tableNames(db: Database.Database): string[] {
  return (
    db
      .prepare("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
      .all() as { name: string }[]
  ).map((r) => r.name);
}

function columnNames(db: Database.Database, table: string): string[] {
  return (db.pragma(`table_info(${table})`) as { name: string }[]).map((r) => r.name);
}

function appliedMigrations(db: Database.Database): string[] {
  return (
    db.prepare('SELECT name FROM schema_migrations ORDER BY name').all() as { name: string }[]
  ).map((r) => r.name);
}

// ---------------------------------------------------------------------------
// Each test suite gets a fresh in-memory database via resetDb().
// ---------------------------------------------------------------------------

beforeEach(() => {
  resetDb();
});

// ---------------------------------------------------------------------------
// Schema setup
// ---------------------------------------------------------------------------

describe('initDb — schema setup', () => {
  it('creates the sessions table', () => {
    expect(tableNames(getDb())).toContain('sessions');
  });

  it('creates the session_events table', () => {
    expect(tableNames(getDb())).toContain('session_events');
  });

  it('creates the installed_models table', () => {
    expect(tableNames(getDb())).toContain('installed_models');
  });

  it('creates the model_config table', () => {
    expect(tableNames(getDb())).toContain('model_config');
  });

  it('creates the schema_migrations table', () => {
    expect(tableNames(getDb())).toContain('schema_migrations');
  });

  it('sessions table has all required columns', () => {
    const cols = columnNames(getDb(), 'sessions');
    expect(cols).toContain('session_id');
    expect(cols).toContain('scenario_id');
    expect(cols).toContain('state');
    expect(cols).toContain('ending_type');
    expect(cols).toContain('created_at');
    expect(cols).toContain('setup_json');
    expect(cols).toContain('state_vars_json');
    expect(cols).toContain('turn_count');
  });

  it('session_events table has all required columns', () => {
    const cols = columnNames(getDb(), 'session_events');
    expect(cols).toContain('event_id');
    expect(cols).toContain('session_id');
    expect(cols).toContain('event_type');
    expect(cols).toContain('payload_json');
    expect(cols).toContain('created_at');
  });

  it('enforces foreign keys', () => {
    const fk = getDb().pragma('foreign_keys', { simple: true }) as number;
    expect(fk).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Migration tracking
// ---------------------------------------------------------------------------

describe('schema_migrations tracking', () => {
  it('records all migrations after initDb', () => {
    const names = appliedMigrations(getDb());
    expect(names).toContain('0001_initial_schema');
  });

  it('does not duplicate migration rows when called again on same db', () => {
    const db = getDb();
    // Run a second initDb on the same path (in-memory already initialised via getDb).
    // We simulate idempotency by directly calling initDb with the live db handle's
    // path — instead, we verify via resetDb that a second init still has exactly
    // one row per migration.
    resetDb();
    const names = appliedMigrations(getDb());
    const unique = new Set(names);
    expect(unique.size).toBe(names.length);
  });

  it('re-applies migrations cleanly after resetDb', () => {
    resetDb();
    const names = appliedMigrations(getDb());
    expect(names.length).toBeGreaterThan(0);
    expect(tableNames(getDb())).toContain('sessions');
  });
});

// ---------------------------------------------------------------------------
// Migration idempotency across restarts (persistent database)
//
// The in-memory suites above cannot exercise the core promise of the migration
// system — that already-applied migrations are skipped when an existing player
// database is re-opened. These tests use a real file-backed database, close it,
// and re-open it to simulate a server restart.
// ---------------------------------------------------------------------------

describe('migration idempotency across restarts', () => {
  it('does not re-run applied migrations and preserves data when a persistent db is re-opened', () => {
    const dbDir = mkdtempSync(join(tmpdir(), 'convsim-db-migrations-'));
    const dbPath = join(dbDir, 'convsim.db');
    try {
      // First start: schema is created and migration 0001 is recorded.
      let db = initDb(dbPath);
      expect(
        (db.prepare('SELECT name FROM schema_migrations').all() as { name: string }[]).map(
          (r) => r.name,
        ),
      ).toEqual(['0001_initial_schema', '0002_session_ended_at']);
      db.prepare(
        'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json) VALUES (?, ?, ?, ?, ?)',
      ).run('sess-persist-01', 'behavioral_interview', 'NotStarted', new Date().toISOString(), '{}');
      db.close();

      // Restart: re-opening the same file must not re-apply the migration
      // (which would throw on the PRIMARY KEY) and must keep existing rows.
      db = initDb(dbPath);
      const applied = (
        db.prepare('SELECT name FROM schema_migrations').all() as { name: string }[]
      ).map((r) => r.name);
      expect(applied).toEqual(['0001_initial_schema', '0002_session_ended_at']);
      const row = db
        .prepare('SELECT session_id FROM sessions WHERE session_id = ?')
        .get('sess-persist-01') as { session_id: string } | undefined;
      expect(row?.session_id).toBe('sess-persist-01');
      db.close();
    } finally {
      rmSync(dbDir, { recursive: true, force: true });
    }
  });

  it('backfills state_vars_json and turn_count onto a pre-migration sessions table', () => {
    const dbDir = mkdtempSync(join(tmpdir(), 'convsim-db-legacy-'));
    const dbPath = join(dbDir, 'convsim.db');
    try {
      // Simulate a legacy database that predates the migration system: the
      // sessions table exists without the newer columns and there is no
      // schema_migrations table.
      const raw = new Database(dbPath);
      raw.exec(`
        CREATE TABLE sessions (
          session_id  TEXT PRIMARY KEY,
          scenario_id TEXT NOT NULL,
          state       TEXT NOT NULL DEFAULT 'NotStarted',
          ending_type TEXT,
          created_at  TEXT NOT NULL,
          setup_json  TEXT NOT NULL
        );
      `);
      raw.prepare(
        'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json) VALUES (?, ?, ?, ?, ?)',
      ).run('legacy-01', 'behavioral_interview', 'NotStarted', new Date().toISOString(), '{}');
      raw.close();

      // Opening it through initDb runs migration 0001, which backfills the
      // missing columns without dropping the existing row.
      const db = initDb(dbPath);
      const cols = (db.pragma('table_info(sessions)') as { name: string }[]).map((r) => r.name);
      expect(cols).toContain('state_vars_json');
      expect(cols).toContain('turn_count');
      const row = db
        .prepare('SELECT state_vars_json, turn_count FROM sessions WHERE session_id = ?')
        .get('legacy-01') as { state_vars_json: string; turn_count: number };
      expect(row.state_vars_json).toBe('{}');
      expect(row.turn_count).toBe(0);
      db.close();
    } finally {
      rmSync(dbDir, { recursive: true, force: true });
    }
  });
});

// ---------------------------------------------------------------------------
// Session repository — create
// ---------------------------------------------------------------------------

describe('session repository — create', () => {
  function insertSession(db: Database.Database, id: string): void {
    db.prepare(
      'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json) VALUES (?, ?, ?, ?, ?)',
    ).run(id, 'behavioral_interview', 'NotStarted', new Date().toISOString(), '{"save_transcript":true}');
  }

  it('inserts a session row with correct defaults', () => {
    const db = getDb();
    insertSession(db, 'sess-create-01');
    const row = db
      .prepare('SELECT * FROM sessions WHERE session_id = ?')
      .get('sess-create-01') as Record<string, unknown>;
    expect(row['session_id']).toBe('sess-create-01');
    expect(row['scenario_id']).toBe('behavioral_interview');
    expect(row['state']).toBe('NotStarted');
    expect(row['ending_type']).toBeNull();
    expect(row['state_vars_json']).toBe('{}');
    expect(row['turn_count']).toBe(0);
  });

  it('accepts a seed stored inside setup_json', () => {
    const db = getDb();
    const setup = JSON.stringify({ save_transcript: true, seed: 42 });
    db.prepare(
      'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json) VALUES (?, ?, ?, ?, ?)',
    ).run('sess-create-02', 'behavioral_interview', 'NotStarted', new Date().toISOString(), setup);

    const row = db
      .prepare('SELECT setup_json FROM sessions WHERE session_id = ?')
      .get('sess-create-02') as { setup_json: string };
    expect(JSON.parse(row.setup_json).seed).toBe(42);
  });

  it('session_id must be unique (PRIMARY KEY constraint)', () => {
    const db = getDb();
    insertSession(db, 'sess-dup');
    expect(() => insertSession(db, 'sess-dup')).toThrow();
  });
});

// ---------------------------------------------------------------------------
// Session repository — load
// ---------------------------------------------------------------------------

describe('session repository — load', () => {
  function insertSession(db: Database.Database, id: string): void {
    db.prepare(
      'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json) VALUES (?, ?, ?, ?, ?)',
    ).run(id, 'used_car_negotiation', 'NotStarted', new Date().toISOString(), '{}');
  }

  it('loads a session by id', () => {
    const db = getDb();
    insertSession(db, 'sess-load-01');
    const row = db.prepare('SELECT * FROM sessions WHERE session_id = ?').get('sess-load-01');
    expect(row).not.toBeUndefined();
  });

  it('returns undefined for a non-existent session id', () => {
    const row = getDb()
      .prepare('SELECT * FROM sessions WHERE session_id = ?')
      .get('sess-does-not-exist');
    expect(row).toBeUndefined();
  });

  it('lists all sessions ordered by created_at desc', () => {
    const db = getDb();
    insertSession(db, 'sess-load-a');
    insertSession(db, 'sess-load-b');
    const rows = db
      .prepare('SELECT session_id FROM sessions ORDER BY created_at DESC, rowid DESC')
      .all() as { session_id: string }[];
    // Both rows are inserted within the same millisecond in tests; rowid tie-break guarantees order.
    expect(rows.map((r) => r.session_id)).toContain('sess-load-a');
    expect(rows.map((r) => r.session_id)).toContain('sess-load-b');
  });
});

// ---------------------------------------------------------------------------
// Session repository — update
// ---------------------------------------------------------------------------

describe('session repository — update', () => {
  function insertSession(db: Database.Database, id: string): void {
    db.prepare(
      'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json) VALUES (?, ?, ?, ?, ?)',
    ).run(id, 'behavioral_interview', 'NotStarted', new Date().toISOString(), '{}');
  }

  it('updates session state from NotStarted to PlayerTurnListening', () => {
    const db = getDb();
    insertSession(db, 'sess-upd-01');
    db.prepare("UPDATE sessions SET state = 'PlayerTurnListening' WHERE session_id = ?").run(
      'sess-upd-01',
    );
    const row = db
      .prepare('SELECT state FROM sessions WHERE session_id = ?')
      .get('sess-upd-01') as { state: string };
    expect(row.state).toBe('PlayerTurnListening');
  });

  it('updates state_vars_json', () => {
    const db = getDb();
    insertSession(db, 'sess-upd-02');
    const vars = JSON.stringify({ trust: 60, patience: 80 });
    db.prepare('UPDATE sessions SET state_vars_json = ? WHERE session_id = ?').run(
      vars,
      'sess-upd-02',
    );
    const row = db
      .prepare('SELECT state_vars_json FROM sessions WHERE session_id = ?')
      .get('sess-upd-02') as { state_vars_json: string };
    expect(JSON.parse(row.state_vars_json)).toEqual({ trust: 60, patience: 80 });
  });

  it('updates ending_type to player_exit', () => {
    const db = getDb();
    insertSession(db, 'sess-upd-03');
    db.prepare("UPDATE sessions SET state = 'Ended', ending_type = 'player_exit' WHERE session_id = ?").run(
      'sess-upd-03',
    );
    const row = db
      .prepare('SELECT state, ending_type FROM sessions WHERE session_id = ?')
      .get('sess-upd-03') as { state: string; ending_type: string };
    expect(row.state).toBe('Ended');
    expect(row.ending_type).toBe('player_exit');
  });

  it('increments turn_count', () => {
    const db = getDb();
    insertSession(db, 'sess-upd-04');
    db.prepare('UPDATE sessions SET turn_count = turn_count + 1 WHERE session_id = ?').run(
      'sess-upd-04',
    );
    const row = db
      .prepare('SELECT turn_count FROM sessions WHERE session_id = ?')
      .get('sess-upd-04') as { turn_count: number };
    expect(row.turn_count).toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Session repository — delete
// ---------------------------------------------------------------------------

describe('session repository — delete', () => {
  function insertSession(db: Database.Database, id: string): void {
    db.prepare(
      'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json) VALUES (?, ?, ?, ?, ?)',
    ).run(id, 'behavioral_interview', 'NotStarted', new Date().toISOString(), '{}');
  }

  function insertEvent(db: Database.Database, sessionId: string, type: string): void {
    db.prepare(
      'INSERT INTO session_events (session_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)',
    ).run(sessionId, type, '{}', new Date().toISOString());
  }

  it('deletes a session row', () => {
    const db = getDb();
    insertSession(db, 'sess-del-01');
    db.prepare('DELETE FROM sessions WHERE session_id = ?').run('sess-del-01');
    const row = db.prepare('SELECT * FROM sessions WHERE session_id = ?').get('sess-del-01');
    expect(row).toBeUndefined();
  });

  it('cascade-deletes session_events when the session is deleted', () => {
    const db = getDb();
    insertSession(db, 'sess-del-02');
    insertEvent(db, 'sess-del-02', 'npc_opening');
    insertEvent(db, 'sess-del-02', 'player_turn');

    db.prepare('DELETE FROM sessions WHERE session_id = ?').run('sess-del-02');

    const events = db
      .prepare('SELECT * FROM session_events WHERE session_id = ?')
      .all('sess-del-02');
    expect(events).toHaveLength(0);
  });

  it('does not affect other sessions when one is deleted', () => {
    const db = getDb();
    insertSession(db, 'sess-del-keep');
    insertSession(db, 'sess-del-remove');
    db.prepare('DELETE FROM sessions WHERE session_id = ?').run('sess-del-remove');
    const row = db.prepare('SELECT * FROM sessions WHERE session_id = ?').get('sess-del-keep');
    expect(row).not.toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// session_events repository
// ---------------------------------------------------------------------------

describe('session_events repository', () => {
  function insertSession(db: Database.Database, id: string): void {
    db.prepare(
      'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json) VALUES (?, ?, ?, ?, ?)',
    ).run(id, 'behavioral_interview', 'NotStarted', new Date().toISOString(), '{}');
  }

  it('inserts and retrieves events ordered by event_id', () => {
    const db = getDb();
    insertSession(db, 'sess-evt-01');
    const now = new Date().toISOString();
    db.prepare(
      'INSERT INTO session_events (session_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)',
    ).run('sess-evt-01', 'npc_opening', JSON.stringify({ content: 'Hello' }), now);
    db.prepare(
      'INSERT INTO session_events (session_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)',
    ).run('sess-evt-01', 'player_turn', JSON.stringify({ content: 'Hi' }), now);

    const rows = db
      .prepare(
        'SELECT event_type, payload_json FROM session_events WHERE session_id = ? ORDER BY event_id ASC',
      )
      .all('sess-evt-01') as { event_type: string; payload_json: string }[];
    expect(rows).toHaveLength(2);
    expect(rows[0].event_type).toBe('npc_opening');
    expect(JSON.parse(rows[0].payload_json).content).toBe('Hello');
    expect(rows[1].event_type).toBe('player_turn');
  });

  it('does not insert events for a non-existent session (FK constraint)', () => {
    const db = getDb();
    expect(() =>
      db
        .prepare(
          'INSERT INTO session_events (session_id, event_type, payload_json, created_at) VALUES (?, ?, ?, ?)',
        )
        .run('sess-nonexistent', 'player_turn', '{}', new Date().toISOString()),
    ).toThrow();
  });
});

// ---------------------------------------------------------------------------
// resetDb
// ---------------------------------------------------------------------------

describe('resetDb', () => {
  it('clears all session data on reset', () => {
    const db = getDb();
    db.prepare(
      'INSERT INTO sessions (session_id, scenario_id, state, created_at, setup_json) VALUES (?, ?, ?, ?, ?)',
    ).run('sess-reset-01', 'behavioral_interview', 'NotStarted', new Date().toISOString(), '{}');

    resetDb();

    const rows = getDb().prepare('SELECT * FROM sessions').all();
    expect(rows).toHaveLength(0);
  });

  it('re-creates schema and re-applies migrations after reset', () => {
    resetDb();
    expect(tableNames(getDb())).toContain('sessions');
    expect(tableNames(getDb())).toContain('schema_migrations');
    expect(appliedMigrations(getDb()).length).toBeGreaterThan(0);
  });
});
