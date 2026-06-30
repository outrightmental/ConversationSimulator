// SPDX-License-Identifier: Apache-2.0
// Validates all YAML files in packs/official/ against their corresponding JSON schemas.
// Run with: node packages/scenario-schema/tests/validate-packs.js [packs-root]
// Exits 0 if all files pass, 1 if any fail.

import Ajv from "ajv";
import { readFileSync, readdirSync, statSync } from "fs";
import { resolve, dirname, basename, join } from "path";
import { fileURLToPath } from "url";
import { load as yamlLoad } from "js-yaml";

const _dir = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(_dir, "..", "..", "..");
const schemasDir = resolve(repoRoot, "schemas");

const packsRoot = process.argv[2]
  ? resolve(process.argv[2])
  : resolve(repoRoot, "packs", "official");

const ajv = new Ajv({ strict: false, validateSchema: false, allErrors: true });

function loadSchema(name) {
  return JSON.parse(readFileSync(resolve(schemasDir, name), "utf8"));
}

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

function schemaKeyForPath(filePath) {
  const dir = basename(dirname(filePath));
  const file = basename(filePath);
  if (file === "manifest.yaml") return "pack";
  if (dir === "scenarios") return "scenario";
  if (dir === "npcs") return "npc";
  if (dir === "rubrics") return "rubric";
  if (dir === "safety") return "safety";
  if (dir === "scenes") return "scene";
  if (dir === "tests") return "packTest";
  if (file.endsWith(".meta.json")) return "asset";
  return null;
}

function collectYamlFiles(dir) {
  const results = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      results.push(...collectYamlFiles(full));
    } else if (entry.endsWith(".yaml") || entry.endsWith(".yml")) {
      results.push(full);
    }
  }
  return results;
}

let passed = 0;
let failed = 0;

const files = collectYamlFiles(packsRoot);

for (const filePath of files) {
  const rel = filePath.startsWith(repoRoot)
    ? filePath.slice(repoRoot.length + 1)
    : filePath;
  const schemaKey = schemaKeyForPath(filePath);

  if (!schemaKey) {
    console.log(`  SKIP  ${rel}  (no schema mapped for this path)`);
    continue;
  }

  let data;
  try {
    data = yamlLoad(readFileSync(filePath, "utf8"));
  } catch (err) {
    console.error(`  FAIL  ${rel}`);
    console.error(`        YAML parse error: ${err.message}`);
    failed++;
    continue;
  }

  const validate = validators[schemaKey];
  const ok = validate(data);

  if (ok) {
    console.log(`  pass  ${rel}`);
    passed++;
  } else {
    console.error(`  FAIL  ${rel}`);
    for (const error of validate.errors) {
      const loc = error.instancePath || "(root)";
      console.error(`        ${loc}: ${error.message}`);
      if (error.params && Object.keys(error.params).length > 0) {
        console.error(`        params: ${JSON.stringify(error.params)}`);
      }
    }
    failed++;
  }
}

console.log(
  `\n${passed + failed} file(s) checked — ${passed} passed, ${failed} failed.`
);

if (failed > 0) {
  process.exit(1);
}
