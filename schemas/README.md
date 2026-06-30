<!-- SPDX-License-Identifier: Apache-2.0 -->
# schemas/

JSON Schema (Draft 2020-12) definitions for all ConvSim scenario pack file types.

## Schema files

| File | Validates |
|------|-----------|
| `pack.schema.json` | Pack `manifest.yaml` — manifest fields, license, content rating, safety policy reference |
| `scenario.schema.json` | Individual scenario YAML files — roles, goals, state variables, events, endings |
| `npc.schema.json` | NPC definition files — persona, fictional flag, age band, private agenda |
| `rubric.schema.json` | Rubric files — scoring dimensions with stable IDs and weight |
| `safety.schema.json` | Safety policy files — prohibited categories, redirects, content rating cap |
| `scene.schema.json` | Scene descriptor files — visual and ambient context |
| `pack-test.schema.json` | Pack test fixture files — scripted turn sequences and static assertions |
| `asset.schema.json` | Asset metadata sidecar files — license, provenance, and dimensions |
| `turn-output.schema.json` | Structured JSON output the LLM produces per turn (runtime, not pack-authored) |
| `debrief.schema.json` | Debrief report generated after a completed session (runtime output) |

## Examples

`examples/` contains one valid JSON example per pack-authored schema. These serve as both documentation and test fixtures for `packages/scenario-schema/tests/validate-schemas.js`.

## Enforcement

Every pack-authored file must declare:

```yaml
schema_version: "0.1"
```

Schemas are used by:
- `packages/scenario-schema/tests/` — load and validation tests (CI)
- `packages/scenario-schema/src/` — TypeScript `SCHEMA_NAMES` constant for the frontend
- `convsim validate-pack` — CLI validator (planned)

See `VERSIONING.md` for schema versioning rules and the breaking-change review process.
