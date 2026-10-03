export type ScenarioDifficulty = 'warm' | 'standard' | 'hard' | 'adversarial';

export type LadderPosition = 'intro' | 'practice' | 'stretch';

export interface DifficultyOption {
  patience?: number;
  volatility?: number;
  disclosure?: number;
  time_pressure?: number;
  label?: string;
  description?: string;
}

export interface ScenarioDifficultyConfig {
  default: ScenarioDifficulty;
  options: Partial<Record<ScenarioDifficulty, DifficultyOption>>;
}

export interface PlayerRole {
  label: string;
  brief: string;
}

export interface ScenarioDuration {
  max_turns: number;
  soft_time_limit_minutes: number;
}

export interface StateVariable {
  type: 'integer';
  min: number;
  max: number;
  default: number;
  visible?: boolean;
}

export interface ScenarioStateConfig {
  variables: Record<string, StateVariable | number>;
  visible_to_player?: string[];
}

export interface ScenarioInfo {
  scenario_id: string;
  title: string;
  summary: string;
  content_rating: string;
  pack_id: string;
  pack_name: string;
  player_role: PlayerRole;
  difficulty: ScenarioDifficultyConfig;
  supported_languages: string[];
  duration: ScenarioDuration;
  state_meters_permitted: boolean;
  voice_supported: boolean;
  safety_summary: string;
  estimated_length_label: string;
  tags?: string[];
  recommended_model?: string[];
  ladder_position?: LadderPosition;
  taught_dimensions?: string[];
  tested_dimensions?: string[];
  /**
   * What the player is trying to achieve — the scenario's
   * `goals.player_visible`, which the Conversation Brief shows as the mission
   * objective (issue #500). Optional: the scenario list endpoint carries the
   * card fields only, a pack need not declare goals, and an older engine may
   * not send the field at all.
   *
   * `goals.hidden` is the NPC's covert agenda and is deliberately absent from
   * this contract — nothing here may be rendered from it. The engine withholds
   * it from the scenario response altogether unless dev mode is active and the
   * caller asks for it explicitly.
   */
  player_visible_goals?: string[];
}

export interface PackValidationError {
  rule_id?: string;
  file_path?: string;
  message: string;
}

export interface PackValidationResult {
  pack_id: string;
  valid: boolean;
  errors: PackValidationError[];
}
