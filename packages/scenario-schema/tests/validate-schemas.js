// SPDX-License-Identifier: Apache-2.0
// Schema validation tests: verifies example instances pass and targeted invalid instances fail.
// Run with: node packages/scenario-schema/tests/validate-schemas.js (requires pnpm install first)

import Ajv from "ajv";
import { readFileSync } from "fs";
import { resolve, dirname } from "path";
import { fileURLToPath } from "url";
import { test } from "node:test";
import assert from "node:assert/strict";

const _dir = dirname(fileURLToPath(import.meta.url));
const schemasDir = resolve(_dir, "..", "..", "..", "schemas");
const examplesDir = resolve(schemasDir, "examples");

// strict:false and validateSchema:false allow the 2020-12 $schema declaration without
// requiring a separate 2020-12 AJV instance; all constraints used are Draft-07 compatible.
const ajv = new Ajv({ strict: false, validateSchema: false, allErrors: true });

function loadJSON(filePath) {
  return JSON.parse(readFileSync(filePath, "utf8"));
}

function loadSchema(name) {
  return loadJSON(resolve(schemasDir, name));
}

function loadExample(name) {
  return loadJSON(resolve(examplesDir, name));
}

// Pre-compile validators for all pack-authored schemas.
const validators = {
  pack: ajv.compile(loadSchema("pack.schema.json")),
  scenario: ajv.compile(loadSchema("scenario.schema.json")),
  npc: ajv.compile(loadSchema("npc.schema.json")),
  rubric: ajv.compile(loadSchema("rubric.schema.json")),
  safety: ajv.compile(loadSchema("safety.schema.json")),
  scene: ajv.compile(loadSchema("scene.schema.json")),
  packTest: ajv.compile(loadSchema("pack-test.schema.json")),
  asset: ajv.compile(loadSchema("asset.schema.json")),
};

// ─── Valid example tests ──────────────────────────────────────────────────────

const VALID_PAIRS = [
  ["pack", "pack.example.json"],
  ["scenario", "scenario.example.json"],
  ["npc", "npc.example.json"],
  ["rubric", "rubric.example.json"],
  ["safety", "safety.example.json"],
  ["scene", "scene.example.json"],
  ["packTest", "pack-test.example.json"],
  ["asset", "asset.example.json"],
];

for (const [schemaKey, exampleFile] of VALID_PAIRS) {
  test(`valid: ${exampleFile} passes ${schemaKey}.schema.json`, () => {
    const validate = validators[schemaKey];
    const data = loadExample(exampleFile);
    const ok = validate(data);
    if (!ok) {
      assert.fail(
        `Unexpected validation failure in ${exampleFile}:\n${JSON.stringify(validate.errors, null, 2)}`
      );
    }
  });
}

// ─── Invalid instance rejection tests ────────────────────────────────────────

function mustReject(schemaKey, getData, label) {
  test(`invalid: rejects ${label}`, () => {
    const validate = validators[schemaKey];
    const data = getData();
    const ok = validate(data);
    assert.ok(!ok, `Expected validation to fail for: ${label}`);
  });
}

// Pack: required top-level fields
mustReject("pack", () => {
  const d = loadExample("pack.example.json");
  delete d.license;
  return d;
}, "pack missing license");

mustReject("pack", () => {
  const d = loadExample("pack.example.json");
  delete d.content_rating;
  return d;
}, "pack missing content_rating");

mustReject("pack", () => {
  const d = loadExample("pack.example.json");
  delete d.safety;
  return d;
}, "pack missing safety block");

mustReject("pack", () => {
  const d = loadExample("pack.example.json");
  d.safety = {};
  return d;
}, "pack safety block missing policy path");

mustReject("pack", () => {
  return { ...loadExample("pack.example.json"), scripts: { postinstall: "rm -rf /" } };
}, "pack with scripts field (executable code forbidden)");

// NPC: fictional flag and age constraints
mustReject("npc", () => {
  return { ...loadExample("npc.example.json"), fictional: false };
}, "npc fictional: false");

mustReject("npc", () => {
  const d = loadExample("npc.example.json");
  delete d.fictional;
  return d;
}, "npc missing fictional flag");

mustReject("npc", () => {
  const d = loadExample("npc.example.json");
  delete d.age_band;
  return d;
}, "npc missing age_band (ambiguous age rejected)");

mustReject("npc", () => {
  return { ...loadExample("npc.example.json"), licensed_persona: { real_name: "John Doe" } };
}, "npc licensed_persona reserved namespace (blocked in MVP)");

// Safety: mandatory fields
mustReject("safety", () => {
  const d = loadExample("safety.example.json");
  delete d.content_rating_cap;
  return d;
}, "safety missing content_rating_cap");

mustReject("safety", () => {
  const d = loadExample("safety.example.json");
  delete d.content_categories;
  return d;
}, "safety missing content_categories");

mustReject("safety", () => {
  const d = loadExample("safety.example.json");
  delete d.schema_version;
  return d;
}, "safety missing schema_version");

mustReject("safety", () => {
  const d = loadExample("safety.example.json");
  delete d.policy_id;
  return d;
}, "safety missing policy_id");

mustReject("safety", () => {
  return { ...loadExample("safety.example.json"), unknown_top_level_field: true };
}, "safety with unknown top-level field (additionalProperties: false)");

mustReject("safety", () => {
  const d = loadExample("safety.example.json");
  d.content_categories.nsfw_sexual_content = "block";
  return d;
}, "safety nsfw_sexual_content set to invalid action 'block'");

mustReject("safety", () => {
  const d = loadExample("safety.example.json");
  d.content_categories.made_up_category = "stop";
  return d;
}, "safety missing required instructional_criminal category");

mustReject("safety", () => {
  const d = loadExample("safety.example.json");
  delete d.content_categories.crisis_content;
  return d;
}, "safety missing required crisis_content category");

// Rubric: stable dimension ids and required fields
mustReject("rubric", () => {
  const d = loadExample("rubric.example.json");
  delete d.rubric_id;
  return d;
}, "rubric missing rubric_id");

mustReject("rubric", () => {
  const d = loadExample("rubric.example.json");
  d.dimensions = [];
  return d;
}, "rubric with empty dimensions array");

mustReject("rubric", () => {
  const d = loadExample("rubric.example.json");
  delete d.dimensions[0].id;
  return d;
}, "rubric dimension missing stable id");

mustReject("rubric", () => {
  const d = loadExample("rubric.example.json");
  delete d.dimensions[0].scoring;
  return d;
}, "rubric dimension missing scoring descriptions");

mustReject("rubric", () => {
  const d = loadExample("rubric.example.json");
  d.dimensions[0].id = "InvalidID";
  return d;
}, "rubric dimension id with uppercase (pattern violation)");

// Scenario: required fields
mustReject("scenario", () => {
  const d = loadExample("scenario.example.json");
  delete d.scenario_id;
  return d;
}, "scenario missing scenario_id");

mustReject("scenario", () => {
  const d = loadExample("scenario.example.json");
  delete d.npc;
  return d;
}, "scenario missing npc reference");

mustReject("scenario", () => {
  const d = loadExample("scenario.example.json");
  delete d.rubric;
  return d;
}, "scenario missing rubric reference");

// Pack-test: required fields
mustReject("packTest", () => {
  const d = loadExample("pack-test.example.json");
  d.turns = [];
  return d;
}, "pack-test with empty turns array");

mustReject("packTest", () => {
  const d = loadExample("pack-test.example.json");
  delete d.fixture_id;
  return d;
}, "pack-test missing fixture_id");

// Asset: executable field prohibition
mustReject("asset", () => {
  return { ...loadExample("asset.example.json"), runtime_url: "https://example.com/file.png" };
}, "asset with runtime_url field (executable field forbidden)");
