<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Pack validation

This document describes what `convsim validate-pack` and `convsim test-pack`
check, how to run them in CI, and how to fix common errors.

For the scenario authoring guide, see
[`docs/scenario-authoring.md`](scenario-authoring.md).  
For the official quality bar and contribution checklist, see
[`docs/official-pack-quality-bar.md`](official-pack-quality-bar.md).

---

## What convsim validate-pack checks

Run schema validation and structural checks with:

```sh
convsim validate-pack <pack-dir>
```

Exit codes:

| Code | Meaning |
|------|---------|
| `0`  | Pack is valid. |
| `1`  | Pack is invalid. Error details are printed to stderr. |
| `3`  | Unexpected system error (out of memory, OS error, etc.). |

Use `--json` to get machine-readable output:

```sh
convsim validate-pack my-pack/ --json
```

### Checks performed

**Schema validation**

Every file is validated against its corresponding JSON Schema:

| File type | Schema |
|-----------|--------|
| `manifest.yaml` | `schemas/pack.schema.json` |
| `scenarios/*.yaml` | `schemas/scenario.schema.json` |
| `npcs/*.yaml` | `schemas/npc.schema.json` |
| `rubrics/*.yaml` | `schemas/rubric.schema.json` |
| `safety/*.yaml` | `schemas/safety.schema.json` |
| `scenes/*.yaml` | `schemas/scene.schema.json` |
| `tests/*.yaml` | `schemas/pack-test.schema.json` |

A file that fails its schema check produces an error with the file path and
the schema field that failed.

**Cross-file reference resolution**

- All paths in `manifest.yaml → entry_scenarios` must resolve to existing
  scenario files.
- All `npc.ref` paths in scenario files must resolve to existing NPC files.
- All `rubric.ref` paths in scenario files must resolve to existing rubric
  files.
- All `scene.ref` paths in scenario files must resolve to existing scene
  files (if set).
- The `safety.policy` path in `manifest.yaml` must resolve to an existing
  file.

**NPC consistency checks**

- Every NPC must have `fictional: true`. Any NPC without this field, or with
  `fictional: false`, fails validation.
- Every NPC must have `age_band: adult`. The schema enforces this via `enum`.

**Safety policy validation**

- The safety policy file must parse as valid YAML and pass schema validation.
- The `content_rating_cap` field must match the `content_rating` declared in
  `manifest.yaml` or be stricter.

**Injection scan**

Pack files are scanned for template injection patterns. Any file that appears
to embed executable directives is rejected with error code
`INJECTION_PATTERN_DETECTED`. Packs are data, not code.

**No-scripts enforcement**

`manifest.yaml` must not declare a `scripts` field. The schema enforces this
with a `not: { required: ["scripts"] }` constraint.

---

## JSON Schema validation for pack files

The full schema suite is in `schemas/`. Schema files use JSON Schema draft
2020-12 and are versioned via `$id` URIs:

```
https://schemas.convsim.dev/v0.1/pack.schema.json
https://schemas.convsim.dev/v0.1/scenario.schema.json
https://schemas.convsim.dev/v0.1/npc.schema.json
https://schemas.convsim.dev/v0.1/rubric.schema.json
https://schemas.convsim.dev/v0.1/safety.schema.json
https://schemas.convsim.dev/v0.1/scene.schema.json
https://schemas.convsim.dev/v0.1/pack-test.schema.json
```

For worked examples, see `schemas/examples/`.

Schema versioning policy: see [`schemas/VERSIONING.md`](../schemas/VERSIONING.md).

---

## What convsim test-pack checks

Run the pack's smoke tests with:

```sh
convsim test-pack <pack-dir>
```

This runs every `tests/*.yaml` fixture file against the fake runtime and
checks that assertions pass. The fake runtime uses a deterministic
pseudo-random sequence seeded from each fixture's `seed` field.

### Fixture structure

Fixture files contain:

- **`turns`** — a sequence of player inputs and expected outcomes for each turn.
- **`static_assertions`** — structural checks against resolved pack fields
  (opening lines, NPC properties, safety categories, etc.).

#### Turn-level checks

For each turn, the test runner checks:

| Assertion field | What it checks |
|-----------------|----------------|
| `state_delta_contains` | Listed state variables changed value during the turn |
| `session_control` | `continue_session` or `end_session` |
| `safety_status` | `ok`, `redirect`, `refuse`, or `stop` |
| `npc_emotion_not` | NPC emotional state does not include the listed value |

#### Static assertions

Static assertions use `path` (dot notation with optional `[id=...]` filters)
and `check` expressions:

| Check | Example |
|-------|---------|
| `non_empty_string` | `check: non_empty_string` |
| `equals <value>` | `check: "equals true"` |
| `min_length_<n>` | `check: min_length_1` |
| `contains <value>` | `check: "contains scenarios/my_scenario.yaml"` |
| Compound (`AND`) | `check: "type=variable_above AND variable=impression"` |

---

## Running the validator in CI

The CI pipeline runs both validation commands on every pull request:

```sh
convsim validate-pack packs/official/my-pack/
convsim test-pack packs/official/my-pack/
```

Both commands must exit with code `0` for the PR to pass the pack quality
gate.

To reproduce the CI check locally before pushing:

```sh
# Validate all official packs
for pack in packs/official/*/; do
  convsim validate-pack "$pack"
done

# Test all official packs
for pack in packs/official/*/; do
  convsim test-pack "$pack"
done
```

---

## Common validation errors and how to fix them

### MANIFEST_NOT_FOUND

```
✗ Pack validation failed: MANIFEST_NOT_FOUND
  manifest.yaml not found at: my-pack/manifest.yaml
```

The pack directory does not contain a `manifest.yaml`. Check the path you
passed to `validate-pack` and ensure the file exists.

### SCHEMA_INVALID

```
✗ Pack validation failed: SCHEMA_INVALID
  File: my-pack/manifest.yaml
  Validation error at /content_rating: must be one of ["G", "PG", "PG-13"]
```

A file failed JSON Schema validation. The error message includes the file
path and the failing field. Check the value against the allowed options in the
corresponding schema file.

### NPC_NOT_FICTIONAL

```
✗ Pack validation failed: NPC_NOT_FICTIONAL
  File: my-pack/npcs/my_npc.yaml
  NPC must have fictional: true
```

Every NPC must set `fictional: true`. Real-person impersonation is not
permitted. Add or correct the `fictional` field.

### MISSING_SAFETY_POLICY

```
✗ Pack validation failed: MISSING_SAFETY_POLICY
  File: my-pack/safety/my_policy.yaml not found
  Referenced from: manifest.yaml → safety.policy
```

The safety policy file referenced in `manifest.yaml` does not exist. Create
the file or correct the path.

### UNRESOLVED_REF

```
✗ Pack validation failed: UNRESOLVED_REF
  File: my-pack/scenarios/my_scenario.yaml
  npc.ref resolves to a file that does not exist: my-pack/npcs/missing_npc.yaml
```

A `ref` field in a scenario points to a file that does not exist. Check the
relative path and create or rename the file.

### INJECTION_PATTERN_DETECTED

```
✗ Pack validation failed: INJECTION_PATTERN_DETECTED
  File: my-pack/npcs/my_npc.yaml
  Executable directive pattern detected in field: public_persona.speaking_style
```

A pack file contains a pattern that looks like template injection or an
embedded executable directive. Packs are data, not code. Remove any
`{{...}}`, `{% %}`, or similar template syntax from the file.

### CONTENT_RATING_MISMATCH

```
✗ Pack validation failed: CONTENT_RATING_MISMATCH
  manifest.yaml declares content_rating: G but safety policy declares content_rating_cap: PG
```

The `content_rating_cap` in the safety policy must match or be stricter than
the `content_rating` in `manifest.yaml`. Update one of the values to be
consistent.

### TEST_FIXTURE_FAILED

```
✗ Test failed: smoke_my_scenario
  Turn 1 assertion failed: session_control expected continue_session, got end_session
```

A smoke test turn assertion failed. Check the fixture's `player_input` for
that turn — it may be triggering an unexpected session end (safety stop or
ending condition). Adjust the input or check the scenario's ending thresholds.
