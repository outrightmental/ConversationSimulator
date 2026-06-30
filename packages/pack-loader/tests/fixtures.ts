// SPDX-License-Identifier: Apache-2.0
import { mkdirSync, writeFileSync, mkdtempSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { tmpdir } from 'node:os';

// ---------------------------------------------------------------------------
// Minimal valid YAML strings (schema_version "0.1")
// ---------------------------------------------------------------------------

export const VALID_MANIFEST_YAML = `schema_version: "0.1"
pack_id: test.minimal_pack
name: Minimal Test Pack
version: 0.1.0
description: A minimal pack for testing the pack loader.
author: Test Suite
license: MIT
content_rating: PG
safety:
  policy: safety/policy.yaml
`;

export const VALID_SAFETY_YAML = `schema_version: "0.1"
policy_id: test_safety
content_rating_cap: PG
content_categories:
  nsfw_sexual: block
  real_person_impersonation: block
  instructional_criminal: block
  crisis_content: redirect
redirect_message: "This content is not appropriate for this scenario."
`;

export const VALID_NPC_YAML = `schema_version: "0.1"
npc_id: test_npc
display_name: Test NPC
archetype: test_archetype
fictional: true
age_band: adult
public_persona:
  occupation: A test NPC for unit testing the pack loader
  speaking_style: Direct and clear
  demeanor: Neutral and cooperative
private_persona: {}
`;

export const VALID_RUBRIC_YAML = `schema_version: "0.1"
rubric_id: test_rubric
title: Test Rubric
dimensions:
  - id: accuracy
    name: Accuracy
    description: How accurately the tester completed the task
    scoring:
      low: Failed to complete basic tasks
      medium: Completed most tasks with minor errors
      high: Completed all tasks accurately
`;

export const VALID_SCENE_YAML = `schema_version: "0.1"
scene_id: test_scene
display_name: Test Room
description: A neutral test room used for unit testing the pack loader.
`;

export const VALID_SCENARIO_YAML = `schema_version: "0.1"
scenario_id: test_scenario
title: Test Scenario
summary: A minimal test scenario for unit testing the pack loader.
player_role:
  label: Tester
  brief: You are testing the pack loader.
npc:
  ref: ../npcs/test_npc.yaml
rubric:
  ref: ../rubrics/test_rubric.yaml
duration:
  max_turns: 5
opening:
  npc_says: "Hello! Let's begin the test."
goals:
  player_visible:
    - Test the pack loader correctly
`;

export const VALID_SCENARIO_WITH_SCENE_YAML = `schema_version: "0.1"
scenario_id: test_scenario_scene
title: Test Scenario With Scene
summary: A test scenario that includes a scene reference.
player_role:
  label: Tester
  brief: You are testing scene resolution.
npc:
  ref: ../npcs/test_npc.yaml
rubric:
  ref: ../rubrics/test_rubric.yaml
scene:
  ref: ../scenes/test_scene.yaml
duration:
  max_turns: 5
opening:
  npc_says: "Welcome to the test room."
goals:
  player_visible:
    - Verify that scene references resolve correctly
`;

// ---------------------------------------------------------------------------
// Temp directory helpers
// ---------------------------------------------------------------------------

export interface PackDirOptions {
  manifestYaml?: string;
  safetyYaml?: string;
  npcYaml?: string;
  rubricYaml?: string;
  sceneYaml?: string;
  scenarioYamls?: Record<string, string>;
  extraFiles?: Record<string, string>;
}

function populatePackDir(root: string, options: PackDirOptions): void {
  const {
    manifestYaml = VALID_MANIFEST_YAML,
    safetyYaml = VALID_SAFETY_YAML,
    npcYaml = VALID_NPC_YAML,
    rubricYaml = VALID_RUBRIC_YAML,
    sceneYaml,
    scenarioYamls = { 'test_scenario.yaml': VALID_SCENARIO_YAML },
    extraFiles = {},
  } = options;

  for (const sub of ['scenarios', 'npcs', 'rubrics', 'safety', 'scenes']) {
    mkdirSync(join(root, sub), { recursive: true });
  }

  writeFileSync(join(root, 'manifest.yaml'), manifestYaml, 'utf8');
  writeFileSync(join(root, 'safety', 'policy.yaml'), safetyYaml, 'utf8');
  writeFileSync(join(root, 'npcs', 'test_npc.yaml'), npcYaml, 'utf8');
  writeFileSync(join(root, 'rubrics', 'test_rubric.yaml'), rubricYaml, 'utf8');

  if (sceneYaml) {
    writeFileSync(join(root, 'scenes', 'test_scene.yaml'), sceneYaml, 'utf8');
  }

  for (const [filename, yaml] of Object.entries(scenarioYamls)) {
    writeFileSync(join(root, 'scenarios', filename), yaml, 'utf8');
  }

  for (const [relPath, content] of Object.entries(extraFiles)) {
    const abs = resolve(root, relPath);
    mkdirSync(resolve(abs, '..'), { recursive: true });
    writeFileSync(abs, content, 'utf8');
  }
}

/**
 * Create a temporary pack directory with the supplied file contents.
 * Returns the absolute path to the pack root.
 */
export function makeTempPackDir(options: PackDirOptions = {}): string {
  const root = mkdtempSync(join(tmpdir(), 'convsim-pack-loader-test-'));
  populatePackDir(root, options);
  return root;
}

/**
 * Create a pack directory as a named subdirectory of `parentDir`.
 * Useful for testing `loadPacksFromRoots` where packs must live inside a root.
 * Returns the absolute path to the pack directory.
 */
export function makePackInDir(
  parentDir: string,
  packName: string,
  options: PackDirOptions = {},
): string {
  const root = join(parentDir, packName);
  mkdirSync(root, { recursive: true });
  populatePackDir(root, options);
  return root;
}
