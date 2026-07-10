// SPDX-License-Identifier: Apache-2.0

/** Difficulty level options a scenario can expose to the player. */
export type DifficultyLevel = "warm" | "standard" | "hard" | "adversarial";

/** Lightweight scenario card returned by the scenario-listing API endpoint. */
export interface ScenarioSummary {
  /** Scenario identifier, unique within its pack. */
  scenario_id: string;
  /** Pack the scenario belongs to. */
  pack_id: string;
  /** Display title. */
  title: string;
  /** One-paragraph description shown on the scenario card. */
  summary: string;
  /** Supported difficulty levels. */
  difficulty_options: DifficultyLevel[];
  /** What the player is called in this scenario. */
  player_role_label: string;
  /** Supported language codes. */
  supported_languages: string[];
  /** Maximum number of conversation turns. */
  max_turns: number;
  /** Relative path from the pack root (used to load the full scenario). */
  file_path: string;
}

/** Lightweight pack card returned by the pack-listing API endpoint. */
export interface PackSummary {
  pack_id: string;
  name: string;
  description: string;
  author: string;
  license: string;
  version: string;
  content_rating: "G" | "PG" | "PG-13";
  tags: string[];
  supported_languages: string[];
  scenario_count: number;
}
