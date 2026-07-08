// SPDX-License-Identifier: Apache-2.0
import Database from 'better-sqlite3';
import type { Database as DatabaseType } from 'better-sqlite3';
import type { LoadedPack, PackIndexEntry, ScenarioIndexEntry } from './types.js';

const DDL = `
CREATE TABLE IF NOT EXISTS installed_packs (
  pack_id          TEXT PRIMARY KEY,
  name             TEXT NOT NULL,
  version          TEXT NOT NULL,
  content_rating   TEXT NOT NULL,
  author           TEXT NOT NULL,
  license          TEXT NOT NULL,
  description      TEXT NOT NULL,
  pack_root        TEXT NOT NULL,
  pack_root_kind   TEXT NOT NULL,
  supported_languages TEXT NOT NULL,
  tags             TEXT NOT NULL,
  requirements     TEXT,
  scenario_count   INTEGER NOT NULL DEFAULT 0,
  entry_scenarios  TEXT NOT NULL,
  installed_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS indexed_scenarios (
  scenario_id            TEXT NOT NULL,
  pack_id                TEXT NOT NULL REFERENCES installed_packs(pack_id) ON DELETE CASCADE,
  title                  TEXT NOT NULL,
  summary                TEXT NOT NULL,
  player_role_label      TEXT NOT NULL,
  difficulty_default     TEXT,
  max_turns              INTEGER NOT NULL,
  soft_time_limit_minutes INTEGER,
  rel_path               TEXT NOT NULL,
  PRIMARY KEY (pack_id, scenario_id)
);

CREATE INDEX IF NOT EXISTS idx_scenarios_pack_id ON indexed_scenarios(pack_id);
`;

/**
 * SQLite-backed index of installed scenario packs.
 *
 * Operations are synchronous (better-sqlite3). Open with PackIndex.open() to
 * ensure the schema is initialised before use.
 */
export class PackIndex {
  private readonly db: DatabaseType;

  private constructor(dbPath: string) {
    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('foreign_keys = ON');
    this.db.exec(DDL);
  }

  static open(dbPath: string): PackIndex {
    return new PackIndex(dbPath);
  }

  /** Import (or replace) a pack in the index, atomically updating its scenarios. */
  importPack(pack: LoadedPack): void {
    const now = Math.floor(Date.now() / 1000);
    const m = pack.manifest;

    const upsertPack = this.db.prepare(`
      INSERT INTO installed_packs
        (pack_id, name, version, content_rating, author, license, description,
         pack_root, pack_root_kind, supported_languages, tags, requirements,
         scenario_count, entry_scenarios, installed_at)
      VALUES
        (@pack_id, @name, @version, @content_rating, @author, @license, @description,
         @pack_root, @pack_root_kind, @supported_languages, @tags, @requirements,
         @scenario_count, @entry_scenarios, @installed_at)
      ON CONFLICT(pack_id) DO UPDATE SET
        name               = excluded.name,
        version            = excluded.version,
        content_rating     = excluded.content_rating,
        author             = excluded.author,
        license            = excluded.license,
        description        = excluded.description,
        pack_root          = excluded.pack_root,
        pack_root_kind     = excluded.pack_root_kind,
        supported_languages = excluded.supported_languages,
        tags               = excluded.tags,
        requirements       = excluded.requirements,
        scenario_count     = excluded.scenario_count,
        entry_scenarios    = excluded.entry_scenarios,
        installed_at       = excluded.installed_at
    `);

    const deleteScenarios = this.db.prepare(
      'DELETE FROM indexed_scenarios WHERE pack_id = ?',
    );

    const insertScenario = this.db.prepare(`
      INSERT INTO indexed_scenarios
        (scenario_id, pack_id, title, summary, player_role_label,
         difficulty_default, max_turns, soft_time_limit_minutes, rel_path)
      VALUES
        (@scenario_id, @pack_id, @title, @summary, @player_role_label,
         @difficulty_default, @max_turns, @soft_time_limit_minutes, @rel_path)
    `);

    this.db.transaction(() => {
      upsertPack.run({
        pack_id: m.pack_id,
        name: m.name,
        version: m.version,
        content_rating: m.content_rating,
        author: m.author,
        license: m.license,
        description: m.description,
        pack_root: pack.packRoot,
        pack_root_kind: pack.packRootKind,
        supported_languages: JSON.stringify(m.supported_languages ?? []),
        tags: JSON.stringify(m.tags ?? []),
        requirements: m.requirements ? JSON.stringify(m.requirements) : null,
        scenario_count: pack.scenarios.length,
        entry_scenarios: JSON.stringify(m.entry_scenarios ?? []),
        installed_at: now,
      });

      deleteScenarios.run(m.pack_id);

      for (const s of pack.scenarios) {
        insertScenario.run({
          scenario_id: s.data.scenario_id,
          pack_id: m.pack_id,
          title: s.data.title,
          summary: s.data.summary,
          player_role_label: s.data.player_role.label,
          difficulty_default: s.data.difficulty?.default ?? null,
          max_turns: s.data.duration.max_turns,
          soft_time_limit_minutes: s.data.duration.soft_time_limit_minutes ?? null,
          rel_path: s.relPath,
        });
      }
    })();
  }

  /** Remove a pack and all its scenarios from the index. */
  removePack(packId: string): void {
    this.db.prepare('DELETE FROM installed_packs WHERE pack_id = ?').run(packId);
  }

  /** List all indexed packs. */
  listPacks(): PackIndexEntry[] {
    const rows = this.db
      .prepare('SELECT * FROM installed_packs ORDER BY name')
      .all() as Array<Record<string, unknown>>;
    return rows.map(deserializePack);
  }

  /** List indexed scenarios, optionally filtered to a single pack. */
  listScenarios(packId?: string): ScenarioIndexEntry[] {
    if (packId !== undefined) {
      return this.db
        .prepare(
          'SELECT * FROM indexed_scenarios WHERE pack_id = ? ORDER BY title',
        )
        .all(packId) as ScenarioIndexEntry[];
    }
    return this.db
      .prepare('SELECT * FROM indexed_scenarios ORDER BY title')
      .all() as ScenarioIndexEntry[];
  }

  /** Look up a single pack by id. Returns undefined if not found. */
  getPack(packId: string): PackIndexEntry | undefined {
    const row = this.db
      .prepare('SELECT * FROM installed_packs WHERE pack_id = ?')
      .get(packId) as Record<string, unknown> | undefined;
    return row ? deserializePack(row) : undefined;
  }

  close(): void {
    this.db.close();
  }
}

function deserializePack(row: Record<string, unknown>): PackIndexEntry {
  return {
    pack_id: row['pack_id'] as string,
    name: row['name'] as string,
    version: row['version'] as string,
    content_rating: row['content_rating'] as string,
    author: row['author'] as string,
    license: row['license'] as string,
    description: row['description'] as string,
    pack_root: row['pack_root'] as string,
    pack_root_kind: row['pack_root_kind'] as string,
    supported_languages: JSON.parse(row['supported_languages'] as string) as string[],
    tags: JSON.parse(row['tags'] as string) as string[],
    requirements: row['requirements']
      ? (JSON.parse(row['requirements'] as string) as {
          min_app_version?: string;
          recommended_llm?: string[];
        })
      : null,
    scenario_count: row['scenario_count'] as number,
    entry_scenarios: JSON.parse(row['entry_scenarios'] as string) as string[],
    installed_at: row['installed_at'] as number,
  };
}
