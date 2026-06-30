// SPDX-License-Identifier: Apache-2.0

export * from './types.js';
export * from './schemas.js';
export * from './yaml-sync.js';

/** Names of all schema files shipped in the root schemas/ directory. */
export const SCHEMA_NAMES = [
  "pack.schema.json",
  "scenario.schema.json",
  "npc.schema.json",
  "rubric.schema.json",
  "safety.schema.json",
  "scene.schema.json",
  "pack-test.schema.json",
  "asset.schema.json",
  "turn-output.schema.json",
  "debrief.schema.json",
] as const;

export type SchemaName = (typeof SCHEMA_NAMES)[number];

/**
 * The schemas/ directory is at the repository root:
 *   <repo-root>/schemas/<SchemaName>
 *
 * From a Node.js ESM context you can resolve a schema path with:
 *   import { fileURLToPath } from "url";
 *   import { dirname, resolve } from "path";
 *   const schemasDir = resolve(dirname(fileURLToPath(import.meta.url)), "../../..", "schemas");
 *   const packSchemaPath = resolve(schemasDir, "pack.schema.json");
 *
 * See packages/scenario-schema/tests/load-schemas.js for a concrete example.
 */
export const SCHEMAS_DIR_FROM_REPO_ROOT = "schemas" as const;
