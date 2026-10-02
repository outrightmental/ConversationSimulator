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
  flytingCalibration: ajv.compile(loadSchema("flyting-calibration.schema.json")),
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
  ["flytingCalibration", "flyting-calibration.example.json"],
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
}, "safety with unknown category in content_categories (additionalProperties: false)");

mustReject("safety", () => {
  const d = loadExample("safety.example.json");
  d.content_categories.self_harm_crisis = "redirect";
  return d;
}, "safety self_harm_crisis set to invalid action 'redirect' (only stop_with_resource_message allowed)");

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

// ─── Flyting: mode, flyting block, attack surface, calibration ───────────────

function mustAccept(schemaKey, getData, label) {
  test(`valid: accepts ${label}`, () => {
    const validate = validators[schemaKey];
    const data = getData();
    const ok = validate(data);
    if (!ok) {
      assert.fail(
        `Unexpected validation failure for ${label}:\n${JSON.stringify(validate.errors, null, 2)}`
      );
    }
  });
}

function flytingScenario() {
  const d = loadExample("scenario.example.json");
  d.mode = "flyting";
  d.flyting = {
    formats: ["bout", "batting_practice"],
    bout: { rounds: 8, momentum_win: 85, momentum_k: 1, riposte_bonus: 15, npc_tier: "wildean" },
    batting_practice: { shot_clock_s: 20, formats: ["timed_90", "set_10", "endless"] },
    difficulty_multiplier: 1.2,
    lexicon: { encouraged: ["blackguard"], anachronism_policy: "penalize" },
    register: { require_surface_politeness: false },
    verse: { required: false },
    judge_flavor: "A retired music-hall chairman. Cockney. Unimpressable.",
  };
  return d;
}

mustAccept("scenario", flytingScenario, "a flyting scenario with mode and flyting block");

mustAccept("scenario", () => {
  // Conversation-mode scenarios never mention flyting; the default must hold.
  const d = loadExample("scenario.example.json");
  assert.strictEqual(d.mode, undefined, "example scenario should not declare a mode");
  return d;
}, "a scenario that omits mode entirely (defaults to conversation)");

mustReject("scenario", () => {
  const d = loadExample("scenario.example.json");
  d.mode = "flyting";
  return d;
}, "mode: flyting with no flyting block");

mustReject("scenario", () => {
  const d = flytingScenario();
  delete d.mode;
  return d;
}, "a flyting block with no mode: flyting");

mustReject("scenario", () => {
  const d = flytingScenario();
  d.flyting.formats = [];
  return d;
}, "flyting with an empty formats array");

mustReject("scenario", () => {
  const d = flytingScenario();
  d.flyting.formats = ["freestyle"];
  return d;
}, "flyting with an unknown format");

mustReject("scenario", () => {
  const d = flytingScenario();
  d.flyting.difficulty_multiplier = 3;
  return d;
}, "flyting difficulty_multiplier above the 1.5 cap");

mustReject("scenario", () => {
  const d = flytingScenario();
  d.flyting.taunt_script = "not a declared field";
  return d;
}, "flyting with an undeclared field (additionalProperties: false)");

mustAccept("npc", () => {
  const d = loadExample("npc.example.json");
  d.attack_surface = [
    { id: "vanity", brief: "Convinced he is Adonis.", visibility: "visible" },
    { id: "new_money", brief: "The family crest is eleven years old.", visibility: "discoverable", themes: ["lineage"] },
  ];
  return d;
}, "an NPC with an attack surface");

mustReject("npc", () => {
  const d = loadExample("npc.example.json");
  d.attack_surface = [{ id: "Vanity", brief: "Uppercase id." }];
  return d;
}, "attack_surface trait id with uppercase (pattern violation)");

mustReject("npc", () => {
  const d = loadExample("npc.example.json");
  d.attack_surface = [{ id: "vanity" }];
  return d;
}, "attack_surface trait with no brief");

mustReject("npc", () => {
  const d = loadExample("npc.example.json");
  d.attack_surface = [{ id: "vanity", brief: "No such visibility.", visibility: "secret" }];
  return d;
}, "attack_surface trait with an unknown visibility");

mustAccept("rubric", () => {
  const d = loadExample("rubric.example.json");
  d.volley_judge = {
    weights: { sting: 0.35, wit: 0.25, craft: 0.2, fidelity: 0.2 },
    anchors: [{ dimension: "sting", score: 9, example: "A line that lands on this target alone.", why: "Aimed." }],
    hook_bonus: [0.15, 0.12, 0.08, 0.05],
    theme_decay: 0.75,
  };
  return d;
}, "a rubric with a volley_judge block");

mustReject("rubric", () => {
  const d = loadExample("rubric.example.json");
  d.volley_judge = { weights: { sting: 0.5, wit: 0.5 } };
  return d;
}, "volley_judge weights missing two of the four dimensions");

mustReject("rubric", () => {
  const d = loadExample("rubric.example.json");
  d.volley_judge = { anchors: [{ dimension: "charm", score: 5, example: "Not a judged dimension." }] };
  return d;
}, "volley_judge anchor naming an unknown dimension");

mustAccept("scene", () => {
  const d = loadExample("scene.example.json");
  d.audience = {
    label: "the fishwives",
    reactions: [
      { min_score: 0, line: "A few of them look away." },
      { min_score: 150, line: "The fishwives shriek with laughter.", event_id: "fishwives_shriek" },
    ],
  };
  return d;
}, "a scene with an audience block");

mustReject("scene", () => {
  const d = loadExample("scene.example.json");
  d.audience = { label: "the benches" };
  return d;
}, "a scene audience with no reactions");

mustReject("scene", () => {
  const d = loadExample("scene.example.json");
  d.audience = { reactions: [{ line: "No threshold given." }] };
  return d;
}, "a scene audience reaction with no min_score");

mustReject("flytingCalibration", () => {
  const d = loadExample("flyting-calibration.example.json");
  d.volleys = [];
  return d;
}, "a calibration suite with no volleys");

mustReject("flytingCalibration", () => {
  const d = loadExample("flyting-calibration.example.json");
  delete d.scenario_id;
  return d;
}, "a calibration suite with no scenario_id");

mustReject("flytingCalibration", () => {
  const d = loadExample("flyting-calibration.example.json");
  d.volleys[0].expect.band = "incandescent";
  return d;
}, "a calibration expectation naming an unknown band");

mustReject("flytingCalibration", () => {
  const d = loadExample("flyting-calibration.example.json");
  d.volleys[0].text = "x".repeat(501);
  return d;
}, "a calibration volley past the 500-character hard cap");
