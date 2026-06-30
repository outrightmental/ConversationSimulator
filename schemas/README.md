<!-- SPDX-License-Identifier: Apache-2.0 -->
# schemas/

JSON Schema definitions for all scenario pack file types.

**Status:** Placeholder. Schemas will be added in Milestone 2 (scenario pack system).

## Planned schema files

| File                  | Validates                                            |
| --------------------- | ---------------------------------------------------- |
| `pack.schema.json`    | Pack `manifest.yaml`                                 |
| `scenario.schema.json`| Individual scenario YAML files                       |
| `npc.schema.json`     | NPC definition files                                 |
| `rubric.schema.json`  | Rubric definition files                              |
| `safety.schema.json`  | Safety policy files                                  |
| `turn-output.schema.json` | Structured JSON output from the LLM per turn     |
| `debrief.schema.json` | Debrief output structure                             |

These schemas are used by:
- `convsim validate-pack` (CLI tool)
- `packages/scenario-schema` (TypeScript types for the frontend)
- The creator workbench validator panel
