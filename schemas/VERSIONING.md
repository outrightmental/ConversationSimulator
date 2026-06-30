<!-- SPDX-License-Identifier: Apache-2.0 -->
# Schema versioning rules

## Overview

Every schema-validated file in a ConvSim scenario pack declares its contract version with:

```yaml
schema_version: "0.1"
```

The value is a string (not a number) to preserve leading-zero minor versions and to make future multi-part versions unambiguous.

## Stable IDs

Every entity that crosses a package boundary must have a stable, unique identifier:

| Entity      | ID field      | Convention                                      | Example                         |
| ----------- | ------------- | ----------------------------------------------- | ------------------------------- |
| Pack        | `pack_id`     | `<namespace>.<slug>` in reverse-domain style    | `official.job_interview_basic`  |
| Scenario    | `scenario_id` | Snake-case slug, unique within a pack           | `behavioral_interview`          |
| NPC         | `npc_id`      | Snake-case slug, unique within a pack           | `hiring_manager`                |
| Rubric      | `rubric_id`   | Snake-case slug, unique within a pack           | `interview_rubric`              |
| Safety policy | `policy_id` | Snake-case slug, unique within a pack           | `default_safe_conversation`     |
| Session     | `session_id`  | UUID v4, assigned at runtime                    | `550e8400-e29b-41d4-a716-...`  |

IDs must match the pattern `^[a-z0-9_]+(\.[a-z0-9_]+)*$` (lowercase letters, digits, underscores; dots only for namespaced pack IDs).

Once published in a released pack, IDs must not be renamed. If an entity is superseded, deprecate it and introduce a new ID.

## Versioning rules

### schema_version

`schema_version` identifies the **schema contract version** that a file was authored against, not the version of the entity itself.

| When to change | How to change |
| --- | --- |
| Adding a new required field | Bump `schema_version` (e.g. `"0.1"` → `"0.2"`) |
| Removing or renaming a field | Bump `schema_version` |
| Changing the meaning of a field | Bump `schema_version` |
| Adding a new **optional** field with a backward-compatible default | May keep `schema_version` unchanged if the validator allows unknown optional properties. Prefer bumping anyway if the field is load-bearing. |
| Typo fix or documentation change | No change needed |

The validator must reject files whose `schema_version` it does not recognise. Supported versions are listed in the schema `enum`.

**Exception: `turn-output.schema.json`** — Turn output is a runtime LLM response format, not a pack-authored file. Pack authors never write turn output documents directly; the model generates them during a session. `turn-output.schema.json` therefore does not define a `schema_version` field. Changes to the turn output format are tracked by the overall project version (see `$id`) and require corresponding backend changes.

### Breaking vs non-breaking changes

| Change type | Classification | Action |
| --- | --- | --- |
| Add required field | Breaking | Bump version, update docs |
| Remove field | Breaking | Bump version, provide migration guide |
| Rename field | Breaking | Bump version |
| Change field type | Breaking | Bump version |
| Add optional field | Non-breaking (usually) | Update schema, keep version or bump |
| Add new enum value | Non-breaking | Update schema |
| Remove enum value | Breaking | Bump version |

### Review process

Schema changes must be reviewed before merging:

1. Open a pull request that modifies `schemas/*.schema.json`.
2. The PR description must include:
   - Which entities are affected.
   - Whether the change is breaking.
   - The new `schema_version` value if bumped.
   - A migration note for pack authors if breaking.
3. All existing schema tests must pass.
4. At least one maintainer must approve schema-breaking changes.

### Future versioning

When the project reaches stable (1.x), the `$id` of each schema will include the version:

```
https://schemas.convsim.dev/v1.0/pack.schema.json
```

Pre-1.0 schemas use `v0.1`, `v0.2`, etc. and make no backward-compatibility guarantees between minor versions.

## No executable code in packs

Schema files must not define fields that accept executable code. Specifically:

- No `scripts` object at any nesting level in pack manifests.
- No `eval`, `exec`, or `code` fields.
- No URLs that are loaded at runtime without user action.
- If a pack manifest's `assets` block includes an `allow_external_urls` field, the value must be `false` (enforced via `const: false` in `pack.schema.json`). Packs that omit `allow_external_urls` or the entire `assets` block are not constrained at the schema level; URL policy for those packs is enforced by the pack-loader at runtime.

Violations are treated as security issues. Report them via `SECURITY.md`.
