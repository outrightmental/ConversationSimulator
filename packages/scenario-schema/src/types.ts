/** Discriminates which kind of pack file is being edited. */
export type PackFileType = 'manifest' | 'scenario' | 'npc' | 'rubric';

// ---------------------------------------------------------------------------
// Pack Manifest
// ---------------------------------------------------------------------------

export interface PackManifest {
  schema_version: '1.0';
  fictional: true;
  id: string;
  name: string;
  version: string;
  description: string;
  author: string;
  license: string;
  tags?: string[];
  scenarios?: string[];
  npcs?: string[];
  rubrics?: string[];
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Scenario
// ---------------------------------------------------------------------------

export interface StateDefaults {
  trust: number;
  patience: number;
  pressure: number;
  rapport: number;
  openness: number;
  objective_progress: number;
}

export interface ScenarioEnding {
  id: string;
  label: string;
  condition: string;
  npc_reaction: string;
}

export interface ScenarioFile {
  schema_version: '1.0';
  id: string;
  title: string;
  description: string;
  player_role: string;
  goals: string[];
  difficulty: 'easy' | 'medium' | 'hard';
  duration_minutes: number;
  npc_ref: string;
  rubric_ref?: string;
  opening_context: string;
  state_defaults: StateDefaults;
  endings: ScenarioEnding[];
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// NPC
// ---------------------------------------------------------------------------

export interface NpcPersona {
  background: string;
  speaking_style: string;
  personality_traits: string[];
  [key: string]: unknown;
}

export interface NpcVoice {
  tone: 'casual' | 'professional' | 'formal';
  pace: 'slow' | 'moderate' | 'fast';
  formality: string;
  [key: string]: unknown;
}

export interface NpcFile {
  schema_version: '1.0';
  id: string;
  name: string;
  role: string;
  persona: NpcPersona;
  voice: NpcVoice;
  boundaries: string[];
  hidden_agenda?: string;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Rubric
// ---------------------------------------------------------------------------

export interface RubricDimension {
  id: string;
  label: string;
  description: string;
  weight: number;
  max_score: number;
}

export interface RubricFile {
  schema_version: '1.0';
  id: string;
  title: string;
  dimensions: RubricDimension[];
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// Validation result
// ---------------------------------------------------------------------------

export interface FieldError {
  /** Dot-separated path to the invalid field, e.g. "state_defaults.trust". */
  path: string;
  /** Human-readable message suitable for display in a form. */
  message: string;
}

export type ParseResult<T> =
  | { ok: true; data: T; errors: [] }
  | { ok: false; data: null; errors: FieldError[] };
