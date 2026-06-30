// SPDX-License-Identifier: Apache-2.0
// Verifies that every schema placeholder can be read and parsed as valid JSON.
// Run with: node tests/load-schemas.js (requires Node >= 18)

import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { test } from "node:test";
import assert from "node:assert/strict";

const _dir = dirname(fileURLToPath(import.meta.url));
// Navigate from tests/ -> scenario-schema/ -> packages/ -> repo root -> schemas/
const schemasDir = resolve(_dir, "..", "..", "..", "schemas");

const SCHEMA_NAMES = [
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
];

for (const name of SCHEMA_NAMES) {
  test(`load ${name}`, () => {
    const schemaPath = resolve(schemasDir, name);
    let content;
    try {
      content = readFileSync(schemaPath, "utf8");
    } catch (err) {
      assert.fail(`Could not read schema file at ${schemaPath}: ${err.message}`);
    }

    let schema;
    try {
      schema = JSON.parse(content);
    } catch (err) {
      assert.fail(`Schema file ${name} is not valid JSON: ${err.message}`);
    }

    assert.ok(schema.$schema, `${name} must have a $schema field`);
    assert.ok(schema.$id, `${name} must have a $id field`);
    assert.strictEqual(schema.type, "object", `${name} must describe an object`);
  });
}

test("no schema has a scripts field (no executable code)", () => {
  for (const name of SCHEMA_NAMES) {
    const schemaPath = resolve(schemasDir, name);
    const schema = JSON.parse(readFileSync(schemaPath, "utf8"));
    const raw = JSON.stringify(schema);
    assert.ok(
      !raw.includes('"scripts"') || name === "pack.schema.json",
      `${name} must not define a 'scripts' property (pack.schema.json blocks it via 'not')`
    );
    if (name === "pack.schema.json") {
      assert.ok(
        schema.not && schema.not.required && schema.not.required.includes("scripts"),
        "pack.schema.json must use 'not' to prohibit a top-level 'scripts' field"
      );
    }
  }
});
