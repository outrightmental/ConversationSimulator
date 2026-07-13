---
title: "Player checklist"
description: "Automated and manual acceptance checks covering the full player journey that every MVP release candidate must pass."
sidebar:
  order: 2
---

**Owner:** Platform team
**Scope:** Every MVP release candidate must pass or document exceptions.

The player journey covers: clone → install → select model or fake demo → select scenario → speak/type → NPC responds → state evolves → finish → debrief → replay → confirm no cloud inference.

---

## Automated checks (run in CI)

Run with the fake runtime — no model download required.

```bash
# From repo root (requires convsim-core and prompt-composer installed):
python -m pytest tests/acceptance/test_player_text_path.py -v
```

| Test class | What it verifies | CI label |
|---|---|---|
| `TestScenarioSelection` | Scenario library returns at least one scenario; behavioral_interview is listed with title, summary, difficulty | `[scenario-lib]` |
| `TestSessionStart` | Session creation returns `sess-` ID; starting delivers NPC opening event with non-empty content | `[text-session]` |
| `TestPlayerTurn` | Text turn returns player_turn + npc_turn events; NPC has a valid emotion; two turns both succeed | `[text-session]` |
| `TestStateEvolution` | `state_delta` is present in NPC event; applied delta is returned; state carries into next turn | `[text-session]` |
| `TestSessionEnd` | Explicit end returns `Ended` + `player_exit`; further turns are rejected 409 | `[text-session]` |
| `TestDebrief` | Debrief generated after session ends; debrief on active session rejected 409; idempotent | `[debrief]` |
| `TestSessionRetrieval` | Completed session retrievable by ID; two sessions both retrievable; export available after debrief | `[text-session]` |
| `TestNoCloudInference` | Full session with `LOCAL_MODE=True` completes without `NetworkBlockedError`; fake runtime in use | `[offline]` |

All automated checks must pass before any manual step begins.

---

## Manual checks (sign-off required)

Run on a **clean profile** (`~/.convsim/` freshly created or deleted).

### P-M1 — Clone and install

```bash
git clone https://github.com/outrightmental/ConversationSimulator.git
cd ConversationSimulator
./scripts/setup.sh
```

- [ ] Setup completes without errors
- [ ] Python venv present at `services/convsim-core/.venv/`
- [ ] `node_modules` installed at repo root and workspaces

### P-M2 — First run with fake demo (no model)

```bash
./scripts/dev.sh   # keep running
# open http://127.0.0.1:7354
```

- [ ] Home screen loads; no console errors; no "Failed to fetch" in network tab
- [ ] Service status indicators show correct state (fake runtime expected on fresh install)
- [ ] Model manager screen shows no automatic download

### P-M3 — Install or select real model (optional — requires adequate hardware)

Navigate to **Settings**, find the **Runtime** section, and click **Open model manager**.

- [ ] License acceptance dialog appears before download activates
- [ ] Download completes with SHA-256 checksum verification
- [ ] Model status changes to `"loaded"`
- [ ] Record model filename and size in the smoke log

### P-M4 — Select scenario

Navigate to **Scenarios**.

- [ ] At least one official pack is listed
- [ ] Expanding pack shows scenarios with title, description, difficulty tag
- [ ] Player can select **Job Interview Basics → Behavioral Interview**

### P-M5 — Speak or type

Start the selected scenario.

- [ ] NPC opening line delivered within 10 seconds
- [ ] Typing a player turn and submitting returns NPC response within 30 s (fake) / 60 s (real CPU)
- [ ] Transcript updates after each turn

### P-M6 — State meters (optional)

Enable **Show state meters** in session settings.

- [ ] State variables visible during conversation
- [ ] Values change after turns that trigger state deltas

### P-M7 — Finish and debrief

End the session.

- [ ] End session button works and confirms session closed
- [ ] Debrief screen loads with rubric scores and (if session long enough) narrative
- [ ] Export / Download debrief option is present

### P-M8 — Replay

Return to the scenario library.

- [ ] Session history or past sessions accessible
- [ ] Previously played sessions retrievable by ID

### P-M9 — No cloud inference confirmation

During or after a full session:

- [ ] No outbound requests in browser network tab to external LLM APIs
- [ ] `LOCAL_MODE` test passes in CI (automated gate above)

---

## Sign-off

| Item | Result | Tester | Date | Notes |
|---|---|---|---|---|
| Automated suite | PASS / FAIL | | | |
| P-M1 Clone + install | PASS / FAIL / SKIP | | | |
| P-M2 Fake demo | PASS / FAIL / SKIP | | | |
| P-M3 Real model | PASS / FAIL / SKIP | | | optional |
| P-M4 Scenario select | PASS / FAIL / SKIP | | | |
| P-M5 Speak/type | PASS / FAIL / SKIP | | | |
| P-M6 State meters | PASS / FAIL / SKIP | | | optional |
| P-M7 Debrief | PASS / FAIL / SKIP | | | |
| P-M8 Replay | PASS / FAIL / SKIP | | | |
| P-M9 No cloud | PASS / FAIL / SKIP | | | |

**Release decision:** All automated checks PASS + manual checks P-M1 through P-M9 PASS (or documented SKIP with justification) required before MVP tag.
