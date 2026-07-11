---
title: "Pack validation"
description: "What convsim validate-pack and test-pack check, how to run them in CI, and how to fix common validation errors."
sidebar:
  order: 3
---

This document describes what `convsim validate-pack` and `convsim test-pack`
check, how to run them in CI, and how to fix common errors.

For the scenario authoring guide, see
[`docs/scenario-authoring.md`](/create/scenario-authoring/).  
For the official quality bar and contribution checklist, see
[`docs/official-pack-quality-bar.md`](/create/quality-bar/).

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

- The safety policy file must parse as valid YAML and pass schema validation
  against `schemas/safety.schema.json` — this includes the required
  `content_rating_cap` field and the allowed action for each declared category.

> Keeping `content_rating_cap` consistent with the manifest's `content_rating`
> is a **manual** review item; the validator does not currently compare the two.

**Executable-content scan**

Before any YAML is parsed, the loader scans the pack directory and rejects it
if it finds an executable or script file — matched by extension (`.sh`, `.py`,
`.js`, `.exe`, …), by executable magic-byte signature (a disguised binary given
a data extension), or a symlink (which could escape the pack root). Violations
fail with `FORBIDDEN_FILE` or `FORBIDDEN_BINARY`. Packs are data, not code.

**No-scripts enforcement**

`manifest.yaml` must not declare a `scripts` field. The schema enforces this
with a `not: { required: ["scripts"] }` constraint.

---

## JSON Schema validation for pack files

The full schema suite is in the repository's
[`schemas/`](https://github.com/outrightmental/ConversationSimulator/tree/main/schemas)
directory. Schema files use JSON Schema draft
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

For worked examples, see
[`schemas/examples/`](https://github.com/outrightmental/ConversationSimulator/tree/main/schemas/examples).

Schema versioning policy: see [`schemas/VERSIONING.md`](/reference/schema-versioning/).

---

## What convsim test-pack checks

Run the pack's test fixtures with:

```sh
convsim test-pack <pack-dir>
```

This runs every `tests/*.yaml` fixture file against the fake runtime and
checks that assertions pass. The fake runtime is fully deterministic: it
invokes no model and produces the same structural output every run. A fixture
may declare an optional `seed` field for forward compatibility, but the current
fake runtime does not consume it — it is reserved for reproducible results once
a real runtime is wired in.

### Smoke tests vs. golden transcript tests

Official packs contain two types of test fixture files in `tests/`:

| File naming convention | Purpose |
|------------------------|---------|
| `smoke_<scenario>.yaml` | **Structural smoke test.** Runs in CI against the fake runtime. Verifies that the pack loads, required fields are present, and a single realistic player turn does not produce an unexpected end or safety stop. Focuses on *structure*, not *behaviour*. |
| `golden_<scenario>.yaml` | **Behavioural property test.** Runs a multi-turn scripted conversation and asserts that state variables advance correctly, events fire at the right thresholds, and session endings are wired to the right variables. The fake runtime can check the structural properties (via `static_assertions`) but cannot verify that the state variables actually *change* in response to input — that requires a real runtime. |

Both fixture types use the same YAML schema (`schemas/pack-test.schema.json`)
and both run with `convsim test-pack`. The distinction is in purpose and depth,
not in a separate command.

**Every pack must include at minimum one smoke test per entry scenario.**
Golden tests are expected for all official packs and recommended for any pack
intended for wider sharing.

### Fixture structure

Fixture files contain:

- **`turns`** — a sequence of player inputs and expected outcomes per turn.
- **`static_assertions`** — structural checks against resolved pack fields
  (opening lines, NPC properties, safety categories, event wiring, etc.).

#### Turn-level checks

For each turn, the test runner checks:

| Assertion field | What it checks |
|-----------------|----------------|
| `state_delta_contains` | Listed variable names appear in the turn's `state_delta` output |
| `session_control` | Turn's `session_control` equals the expected `continue_session` or `end_session` |
| `safety_status` | Turn's `safety_status` equals the expected `ok`, `redirect`, or `stop` |
| `npc_emotion_not` | Reserved. Accepted in fixtures but not evaluated by the fake runtime (emotion is always `null`), so it trivially passes today. Will assert that the turn's `npc_emotion` does not equal the listed value once a real runtime is wired in. |

> **Fake-runtime limitation.** `test-pack` runs against a deterministic fake
> runtime that requires no model weights. It populates `state_delta` with every
> declared state variable at its **default** value (it does not simulate value
> changes), and always returns `session_control=continue_session`,
> `safety_status=ok`, and `npc_emotion=null`. In practice this means CI smoke
> tests verify structure — that a variable is declared and the session proceeds
> without an unexpected end — rather than dynamic behaviour. A turn assertion
> expecting `end_session` or `safety_status: redirect`/`stop` cannot pass under
> the fake runtime, and `npc_emotion_not` is accepted but not evaluated (it
> trivially passes); those assertions are reserved for when a real runtime is
> wired in. Assert `session_control: continue_session`
> and `safety_status: ok` in smoke tests.

#### Static assertions

Static assertions use `path` (dot notation with optional `[id=...]` filters)
and `check` expressions:

| Check | Example |
|-------|---------|
| `non_empty_string` | `check: non_empty_string` |
| `equals <value>` | `check: "equals true"` |
| `min_length_1` | `check: min_length_1` |
| `contains <value>` | `check: "contains scenarios/my_scenario.yaml"` |
| Compound (`AND`) | `check: "type=variable_above AND variable=impression"` |

---

## Golden transcript tests in detail

A golden transcript test asserts **behavioural properties** of a scenario by
scripting a multi-turn conversation and verifying structural invariants across
the whole scenario design. They complement smoke tests by covering the event
system, state variable wiring, difficulty settings, and ending conditions —
things that cannot be checked by loading a single turn.

### Anatomy of a golden test

```yaml
# SPDX-License-Identifier: CC-BY-4.0
schema_version: "0.1"
fixture_id: golden_my_scenario
scenario_id: my_scenario
description: >-
  Property test: verifies that a player who applies the winning strategy
  causes deal_progress to advance through the event sequence without
  triggering a safety stop.

seed: 42
input_mode: text
difficulty: standard

# Multi-turn scripted conversation — each turn represents an ideal player move
turns:
  - turn: 1
    player_input: >-
      [The opening move that should advance the key variable positively.]
    expect:
      state_delta_contains:
        - key_variable       # Assert the variable is tracked
      session_control: continue_session
      safety_status: ok

  - turn: 2
    player_input: >-
      [A follow-through move that continues advancing the scenario.]
    expect:
      state_delta_contains:
        - key_variable
        - secondary_variable
      session_control: continue_session
      safety_status: ok

# Structural property checks — verified at load time, not turn time
static_assertions:
  - description: Opening line is non-empty
    path: opening.npc_says
    check: non_empty_string

  - description: Event fires when variable crosses the threshold
    path: events[id=my_event].when
    check: "type=variable_above AND variable=key_variable AND threshold=60"

  - description: Event fires only once (repeat: false)
    path: events[id=my_event].repeat
    check: "equals false"

  - description: Success ending condition targets the right variable
    path: ending_conditions.success
    check: "type=variable_above AND variable=key_variable"

  - description: Visible variable is accessible to the player
    path: state.variables.key_variable.visibility
    check: "equals visible"

  - description: Hidden variable is not accessible to the player
    path: state.variables.internal_counter.visibility
    check: "equals hidden"

  - description: NPC is marked fictional
    path: npc.fictional
    check: "equals true"

  - description: Hard difficulty reduces NPC patience
    path: scenario.difficulty.options.hard.patience
    check: "lte 33"
```

### What to assert in a golden test

**State variable wiring:**
- Every state variable declared in the scenario appears in `state_delta_contains`
  for the turn where it should change.
- Visible variables are accessible to players; hidden variables are not.

**Event system:**
- Each named event has the correct `when` condition (type, variable, threshold).
- Single-fire events set `repeat: false`; recurring events set `repeat: true`.

**Ending conditions:**
- `success` and `failure` conditions target the right variable and threshold type.

**Difficulty settings:**
- `warm` raises `patience` and `disclosure`; `hard`/`adversarial` lower them.
- `volatility` and `time_pressure` climb as the preset gets harder.

**Safety:**
- Required safety categories are present and have the right actions.
- The non-overridable global rules are both declared.

**Manifest:**
- The scenario appears in `manifest.entry_scenarios` via a `contains` assertion.

### Golden tests and the fake runtime

Under the fake runtime, the `turns` section verifies structural correctness:
that the state variables are *declared*, the session format is *valid*, and no
safety stop fires for benign input. The fake runtime does not change variable
values in response to player input, so golden tests cannot assert that
`key_variable` reached a specific value after turn 3.

Once a real runtime is wired in, the same fixture will run against live
inference, and turn-level assertions like `state_delta_contains` will verify
*actual* behavioural changes. Write the scripted player inputs to represent a
realistic ideal strategy — the fake runtime ignores the content, but the real
runtime will use it.

### Example from an official pack

The `everyday-negotiation` pack's golden test for `used_car_negotiation`
scripts four turns representing an ideal negotiation strategy and uses
`static_assertions` to verify all event conditions and ending condition wiring.
See
[`packs/official/everyday-negotiation/tests/golden_used_car_negotiation.yaml`](https://github.com/outrightmental/ConversationSimulator/blob/main/packs/official/everyday-negotiation/tests/golden_used_car_negotiation.yaml)
for a reference implementation.

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

Each failure is reported with a stable error `code` (also surfaced in `--json`
mode) followed by a human-readable message. The codes below are the ones the
loader actually emits.

### MISSING_FILE

```
✗ Pack validation failed: MISSING_FILE
  File not found: my-pack/manifest.yaml
```

A required file is missing. This covers a missing `manifest.yaml`, a
`safety.policy` / `npc.ref` / `rubric.ref` / `scene.ref` that resolves to a
non-existent file, and an `entry_scenarios` path that does not match a
discovered scenario. Check the path you passed to `validate-pack` and confirm
every referenced file exists at the resolved relative path.

### SCHEMA_VALIDATION

```
✗ Pack validation failed: SCHEMA_VALIDATION
  Schema validation failed for my-pack/manifest.yaml: /content_rating: must be equal to one of the allowed values
```

A file failed JSON Schema validation. The message names the file path and the
failing field (JSON pointer). Common cases include an out-of-range
`content_rating`, a missing required field, and an NPC with `fictional: false`
or a missing `fictional` field (the schema requires `fictional: true`). Check
the value against the corresponding schema in `schemas/`.

### INVALID_YAML

```
✗ Pack validation failed: INVALID_YAML
  YAML parse error in my-pack/npcs/my_npc.yaml: bad indentation of a mapping entry
```

A file is not well-formed YAML, or its top level is not a mapping. Fix the
syntax reported in the message.

### FORBIDDEN_FILE / FORBIDDEN_BINARY

```
✗ Pack validation failed: FORBIDDEN_FILE
  Executable or script file not allowed in pack: 'scripts/setup.py'. MVP packs are data, not code.
```

The pack contains a script/executable file (by extension), a file whose bytes
match an executable format (`FORBIDDEN_BINARY`), or a symlink. Packs are data,
not code — remove the offending file and inline any needed content as data.

### DUPLICATE_ID

```
✗ Pack validation failed: DUPLICATE_ID
  Duplicate scenario_id "behavioral_interview" found in pack "official.my_pack"
```

Two scenarios share a `scenario_id`, or two NPCs share an `npc_id`. IDs must
be unique within a pack. Rename one of them.

### UNSUPPORTED_VERSION

```
✗ Pack validation failed: UNSUPPORTED_VERSION
  Unsupported schema_version "0.2" in my-pack/manifest.yaml. Expected "0.1".
```

A file declares a `schema_version` the loader does not support. MVP supports
`"0.1"` only. Set every file's `schema_version` to `"0.1"`.

### PATH_TRAVERSAL

```
✗ Pack validation failed: PATH_TRAVERSAL
  Ref "../../etc/passwd" escapes the pack root "my-pack"
```

A `ref` (or other referenced path) resolves outside the pack directory, or
contains a null byte. References must stay within the pack root — a ref that
escapes it fails with `PATH_TRAVERSAL` rather than `MISSING_FILE`. Keep all
paths relative to the pack and pointing at files inside it.

### Test fixture failure (`convsim test-pack`)

```
✗ 1 failed, 0 passed
  smoke_my_scenario: Turn 1: session_control expected "continue_session", got "end_session"
```

A smoke test turn assertion failed. Check the fixture's `player_input` for
that turn — it may be triggering an unexpected session end (safety stop or
ending condition). Adjust the input or check the scenario's ending thresholds.
`test-pack` exits `1` when any fixture fails and `0` when all pass.
