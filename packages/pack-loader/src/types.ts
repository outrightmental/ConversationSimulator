// SPDX-License-Identifier: Apache-2.0

export const SUPPORTED_SCHEMA_VERSION = '0.1';

export type PackRootKind = 'official' | 'community' | 'local-dev';

// ---------------------------------------------------------------------------
// Raw YAML shapes (schema_version "0.1")
// ---------------------------------------------------------------------------

export interface RawManifest {
  schema_version: string;
  pack_id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  license: string;
  content_rating: 'G' | 'PG' | 'PG-13';
  tags?: string[];
  supported_languages?: string[];
  requirements?: { min_app_version?: string; recommended_llm?: string[] };
  entry_scenarios?: string[];
  assets?: { allow_external_urls: false };
  safety: { policy: string };
  [key: string]: unknown;
}

export interface RawScenario {
  schema_version: string;
  scenario_id: string;
  title: string;
  summary: string;
  player_role: { label: string; brief: string };
  npc: { ref: string };
  rubric: { ref: string };
  scene?: { ref: string };
  duration: { max_turns: number; soft_time_limit_minutes?: number };
  opening: { npc_says: string };
  goals: { player_visible?: string[]; hidden?: string[] };
  difficulty?: { default?: string; options?: Record<string, unknown> };
  state?: unknown;
  events?: unknown[];
  ending_conditions?: unknown;
  [key: string]: unknown;
}

export interface RawNpc {
  schema_version: string;
  npc_id: string;
  display_name: string;
  archetype: string;
  fictional: true;
  age_band: 'adult';
  portrait?: string;
  public_persona: { occupation: string; speaking_style: string; demeanor: string };
  private_persona: Record<string, unknown>;
  [key: string]: unknown;
}

export interface RawRubric {
  schema_version: string;
  rubric_id: string;
  title: string;
  dimensions: Array<{
    id: string;
    name: string;
    description: string;
    scoring: { low: string; medium: string; high: string };
    weight?: number;
  }>;
  [key: string]: unknown;
}

export interface RawSafety {
  schema_version: string;
  policy_id: string;
  content_rating_cap: 'G' | 'PG' | 'PG-13';
  content_categories: Record<string, string>;
  redirect_message: string;
  [key: string]: unknown;
}

export interface RawScene {
  schema_version: string;
  scene_id: string;
  display_name: string;
  description: string;
  background?: string;
  ambient?: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Loader output types
// ---------------------------------------------------------------------------

export interface LoadedScenario {
  relPath: string;
  data: RawScenario;
}

/**
 * Non-fatal validation finding produced by content analysis.
 * Warnings do not block pack loading but must be surfaced to creators.
 */
export interface ValidationWarning {
  /** Stable code for programmatic handling. */
  code: 'EXTERNAL_URL' | 'PROMPT_INJECTION_RISK' | 'MISSING_ASSET';
  /** Human-readable explanation with enough detail to fix the issue. */
  message: string;
  /** Dot-path to the problematic field within the pack (e.g. "npcs/my_npc/private_persona/hidden_agenda[0]"). */
  field: string;
}

export interface LoadedPack {
  manifest: RawManifest;
  packRoot: string;
  packRootKind: PackRootKind;
  scenarios: LoadedScenario[];
  npcs: Map<string, RawNpc>;
  rubrics: Map<string, RawRubric>;
  scenes: Map<string, RawScene>;
  safety: RawSafety;
  /** Non-fatal warnings from content analysis. Empty for a clean pack. */
  warnings: ValidationWarning[];
}

export interface ResolvedBundle {
  scenarioId: string;
  packId: string;
  packRoot: string;
  scenario: RawScenario;
  npc: RawNpc;
  rubric: RawRubric;
  scene: RawScene | null;
  safety: RawSafety;
}

// ---------------------------------------------------------------------------
// SQLite index row types
// ---------------------------------------------------------------------------

export interface PackIndexEntry {
  pack_id: string;
  name: string;
  version: string;
  content_rating: string;
  author: string;
  license: string;
  description: string;
  pack_root: string;
  pack_root_kind: string;
  supported_languages: string[];
  tags: string[];
  requirements: { min_app_version?: string; recommended_llm?: string[] } | null;
  scenario_count: number;
  entry_scenarios: string[];
  installed_at: number;
}

export interface ScenarioIndexEntry {
  scenario_id: string;
  pack_id: string;
  title: string;
  summary: string;
  player_role_label: string;
  difficulty_default: string | null;
  max_turns: number;
  soft_time_limit_minutes: number | null;
  rel_path: string;
}

// ---------------------------------------------------------------------------
// Pack test fixture types
// ---------------------------------------------------------------------------

export interface RawFixtureTurnExpect {
  state_delta_contains?: string[];
  npc_emotion_not?: string;
  session_control?: 'continue_session' | 'end_session';
  safety_status?: 'ok' | 'redirect' | 'stop';
}

export interface RawFixtureTurn {
  turn: number;
  player_input: string;
  expect?: RawFixtureTurnExpect;
}

export interface RawStaticAssertion {
  description: string;
  path: string;
  check: string;
}

export interface RawFixture {
  schema_version: '0.1';
  fixture_id: string;
  scenario_id: string;
  description: string;
  seed?: number;
  input_mode?: 'text' | 'voice';
  difficulty?: 'easy' | 'normal' | 'hard';
  turns: RawFixtureTurn[];
  static_assertions?: RawStaticAssertion[];
}

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

export type PackLoaderErrorCode =
  | 'MISSING_FILE'
  | 'INVALID_YAML'
  | 'SCHEMA_VALIDATION'
  | 'PATH_TRAVERSAL'
  | 'DUPLICATE_ID'
  | 'UNSUPPORTED_VERSION'
  | 'FORBIDDEN_FILE'
  | 'FORBIDDEN_BINARY'
  | 'INVALID_SOURCE'
  | 'UNSAFE_ZIP';

export class PackLoaderError extends Error {
  readonly code: PackLoaderErrorCode;
  readonly filePath: string | undefined;

  constructor(code: PackLoaderErrorCode, message: string, filePath?: string) {
    super(message);
    this.name = 'PackLoaderError';
    this.code = code;
    this.filePath = filePath;
  }
}
