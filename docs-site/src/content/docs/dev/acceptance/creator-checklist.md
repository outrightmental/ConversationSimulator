---
title: "Creator checklist"
description: "Acceptance checklist for the creator journey: copy, edit, validate, play, export, and share a scenario pack before an MVP release."
sidebar:
  order: 3
---

**Owner:** Content team
**Scope:** Every MVP release candidate must pass or document exceptions.

The creator journey covers: copy a pack → edit persona / goals / rubric → validate → play → export → share → understand content rules.

---

## Automated checks (run in CI)

```bash
# From repo root:
python -m pytest tests/acceptance/test_creator_flow.py -v
```

| Test class | What it verifies | CI label |
|---|---|---|
| `TestListPacks` | Workbench lists official (non-editable) and local-dev (editable) packs | `[workbench]` |
| `TestReadPackContent` | Pack card has pack_id and name; manifest YAML accessible via API | `[workbench]` |
| `TestPackValidation` | Valid pack passes `validate_pack_dir`; workbench `/validate` returns `valid: true` | `[pack-valid]` |
| `TestPackValidationErrors` | Missing or malformed manifest produces non-empty error list | `[pack-valid]` |
| `TestPackExport` | Export produces a zip with a manifest; filename ends in `.zip` | `[workbench]` |
| `TestPackImportRoundTrip` | Import succeeds; round-trip export preserves pack_id in filename | `[workbench]` |

All automated checks must pass before any manual step begins.

---

## Manual checks (sign-off required)

Run in the browser creator workbench or via the CLI. A local dev server must be running.

### C-M1 — Copy an official pack

```bash
# Option A — workbench UI: Settings → Creator Workbench → Duplicate Pack
# Option B — CLI
cp -r packs/official/job-interview-basic packs/local-dev/my-interview-pack
# edit packs/local-dev/my-interview-pack/manifest.yaml: change pack_id and name
```

- [ ] Local-dev pack appears in the workbench pack list
- [ ] Pack is marked editable

### C-M2 — Edit persona, goals, and rubric

Open `manifest.yaml`, scenario YAML, NPC YAML, and rubric YAML in an editor or the workbench file editor.

- [ ] Can modify NPC `display_name`, `speaking_style`, and `demeanor`
- [ ] Can change scenario `goals.player_visible` list
- [ ] Can add or rename a rubric dimension
- [ ] YAML files save without data loss

### C-M3 — Validate the edited pack

```bash
node packages/scenario-schema/tests/validate-packs.js packs/local-dev/my-interview-pack
```

Or via workbench: **Validate Pack** button.

- [ ] Valid pack exits 0 / shows all green
- [ ] Intentionally broken field produces a clear, actionable error message

### C-M4 — Play the scenario

Start a session using the edited pack.

- [ ] Custom NPC name appears in the conversation
- [ ] Custom goals appear in the player brief
- [ ] Session plays to completion with fake runtime

### C-M5 — Export and share

```bash
# Via API or workbench "Export" button
```

- [ ] Exported zip contains `manifest.yaml` (or `pack.json`) and scenario files
- [ ] Zip can be imported on a fresh install via `Settings → Import Pack`

### C-M6 — Understand content rules

Review the [safety policy](/trust/safety-policy/) and the [official pack quality bar](/create/quality-bar/).

- [ ] Creator can articulate the PG-13 content cap rule
- [ ] Creator can describe what `nsfw_sexual: block` means in the safety policy
- [ ] Creator knows that `fictional: true` is required on all NPC definitions

---

## Sign-off

| Item | Result | Tester | Date | Notes |
|---|---|---|---|---|
| Automated suite | PASS / FAIL | | | |
| C-M1 Copy pack | PASS / FAIL / SKIP | | | |
| C-M2 Edit persona/goals/rubric | PASS / FAIL / SKIP | | | |
| C-M3 Validate | PASS / FAIL / SKIP | | | |
| C-M4 Play scenario | PASS / FAIL / SKIP | | | |
| C-M5 Export + share | PASS / FAIL / SKIP | | | |
| C-M6 Content rules | PASS / FAIL / SKIP | | | |

**Release decision:** All automated checks PASS + manual checks C-M1 through C-M6 PASS (or documented SKIP) required before MVP tag.
