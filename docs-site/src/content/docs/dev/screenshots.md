---
title: "Screenshots & demo assets"
description: "What the placeholder visual assets in docs/assets/ show, how they are licensed, and how to replace them with real screenshots at Milestone 1."
sidebar:
  order: 13
---

This document describes the visual assets in [`docs/assets/`](https://github.com/outrightmental/ConversationSimulator/tree/main/docs/assets) — what they show, where they
live, how they are licensed, and what to replace them with when the Milestone 1 UI ships.

---

## Demo asset (README hero)

| File | `docs/assets/demo-placeholder.svg` |
|------|-------------------------------------|
| Used in | [`README.md`](https://github.com/outrightmental/ConversationSimulator) |
| License | CC0-1.0 |
| Shows | Mid-session conversation: player turn → NPC challenge → state-variable meters → scenario event banner (`grudging_respect` triggered) — the full simulator loop in one frame |
| Fictional content | NPC "Victor Hargrove" (hostile executive, job-interview scenario) — no real person |
| Replace with | Animated GIF or short video (≤ 5 MB) recorded from the live app at Milestone 1 launch |

**Alt text used in README:**
> Conversation Simulator demo — a mid-session conversation with NPC Victor Hargrove. The player answers a technical question; the NPC challenges the trade-off. State meters below the transcript show credibility at 58, composure at 66, and pressure_level at 5 of 10. An amber banner reads "Scenario event: grudging_respect triggered · Turn 4".

---

## Screenshots (docs/assets/screenshots/)

All six files are SVG placeholder images, browsable at
[`docs/assets/screenshots/`](https://github.com/outrightmental/ConversationSimulator/tree/main/docs/assets/screenshots).
License: **CC0-1.0** (public domain).
Content: fictional NPCs and scenario data only — no real people, voices, or private data.

Replace each file with a real screenshot taken from the live app. Keep the filename so
README and docs links continue to work.

### 01-home.svg — Home screen

**What it shows:** Home screen with all services ready. Status panel lists Local runtime
(Ready), LLM (Qwen3 8B Instruct Q4_K_M), STT (Ready), TTS (Ready), network not required,
and 4 packs installed — all green.

**Alt text:**
> Conversation Simulator home screen showing the primary navigation links (Start a scenario,
> Create / edit a scenario, Install model, Import pack, Read docs) and a system-readiness
> Status panel with all services showing green "Ready" badges and "4 installed" for packs.

---

### 02-scenario-library.svg — Scenario Library

**What it shows:** The Scenario Library with the Job Interview Basics pack expanded. The
Executive Gauntlet scenario card shows a description, metadata chips (PG, Role: Job
Applicant, 12–15 min, Hard, EN, interview, negotiation), and a Launch button.

**Alt text:**
> Scenario Library listing four packs. The Job Interview Basics pack is expanded, showing
> The Executive Gauntlet scenario card with difficulty, content rating, language, and tag
> chips alongside a blue Launch button.

---

### 03-conversation.svg — Conversation (mid-session with state meters)

**What it shows:** An active conversation session. NPC panel shows Victor Hargrove (skeptical
emotion, currently Listening). An amber event banner reports "grudging_respect triggered ·
Turn 4". The transcript shows turns 2–5 (NPC turn in dark green, player turn in deep
purple, NPC streaming response faded). Below the transcript, the NPC state variables panel
shows three meters (matching the scenario's own state variables): credibility 58 / 100
(green), composure 66 / 100 (green), pressure_level 5 / 10 (orange).

**Alt text:**
> Conversation screen mid-session. NPC Victor Hargrove is shown as "skeptical" and "Listening".
> An amber banner announces "Scenario event: grudging_respect triggered · Turn 4". The
> transcript shows the player explaining an event-driven pipeline; the NPC's streaming
> response is partially visible. Below, NPC state variable meters show credibility, composure,
> and pressure_level as numeric gauges with colour-coded progress bars — green for higher
> values, orange for lower.

---

### 04-debrief.svg — Session Debrief

**What it shows:** Post-session debrief for The Executive Gauntlet. Overall score 74/100
with a green "Success" outcome badge. A scorecard shows three dimensions: clarity (82),
evidence quality (71), composure under pressure (65). Strengths listed in green, key
moments show two turning points — one positive (#4, architect insight) and one negative
(#7, verbose scale answer).

**Alt text:**
> Session Debrief page showing a score of 74 out of 100 with a green Success badge. A
> Scorecard section has three labelled bars: clarity at 82 (green), evidence quality at 71
> (green), and composure under pressure at 65 (orange). The Strengths section lists three
> bullet points in green. The Key moments section shows two turning points — one positive
> at turn 4 and one negative at turn 7.

---

### 05-creator-workbench.svg — Creator Workbench

**What it shows:** The three-panel Creator Workbench. Left panel lists official packs and a
local-dev pack "my-custom-pack" (selected). Middle panel shows the file tree for the
selected pack (manifest.yaml, scenarios/, npcs/, rubrics/, safety/, scenes/). Right panel
shows a YAML editor with `my_scenario.yaml` open — schema_version, scenario_id, player
role, and state variables visible. A green validation banner at the bottom confirms the
pack is valid.

**Alt text:**
> Creator Workbench with three panels. The left panel lists official scenario packs and one
> local-dev pack named "my-custom-pack" (highlighted in blue). The centre panel shows the
> pack's file tree: manifest.yaml, a scenarios folder with my_scenario.yaml selected, npcs,
> rubrics, safety, and scenes folders. The right panel contains a YAML editor open on
> my_scenario.yaml, showing schema_version, scenario_id, player_role, and a rapport state
> variable. A green banner at the bottom reads "Pack is valid — no issues found."

---

### 06-model-manager.svg — Model Manager

**What it shows:** The Model Manager during an active download. An installed model card
(Qwen3 8B Instruct Q4_K_M, green "Loaded" badge, Apache-2.0 licence, 5 GB, SHA-256 shown)
sits at the top. The registry lists three models: Qwen3 4B (Download button), Qwen3 14B
(actively downloading — amber progress bar at 3.2 GB / 9.0 GB), and Mistral Small 24B
(Download button). A "load own GGUF" path field appears at the bottom.

**Alt text:**
> Model Manager screen. An installed model card shows Qwen3 8B Instruct Q4_K_M with a
> green "Loaded" badge, Apache-2.0 licence, 5 GB size, and a SHA-256 checksum. Below,
> three registry entries are listed. Qwen3 14B is actively downloading with an amber
> progress bar at 3.2 of 9.0 GB. Qwen3 4B and Mistral Small 24B show Download buttons.
> A text field at the bottom lets users load any local GGUF file by path.

---

## Replacement checklist

When recording real screenshots or a GIF at Milestone 1:

- [ ] Record from a development build at `http://127.0.0.1:7354` with fictional NPC data
      and a local Qwen3 model — no real-person images, audio, or data.
- [ ] Export PNG screenshots at 2× (1800 × 1080 or similar), save as lossy-optimised PNG.
- [ ] Export the demo GIF at ≤ 5 MB (use `gifski` or `ffmpeg` with palette optimisation).
- [ ] Place files in `docs/assets/screenshots/` using the same filenames.
- [ ] Replace `docs/assets/demo-placeholder.svg` with the GIF or an MP4 fallback.
- [ ] Update `README.md` `<img>` tags with the real filenames and correct `alt` text.
- [ ] Run a manual content and safety review: no real faces, no sensitive data, no
      identifiable voices, no content above PG-13.
- [ ] Verify file sizes are acceptable for GitHub rendering (< 10 MB per image).
- [ ] Add or update the NOTICE file if new third-party assets are introduced.

---

## Licence summary

| Asset | Licence | Notes |
|-------|---------|-------|
| `docs/assets/demo-placeholder.svg` | CC0-1.0 | Placeholder; replace at launch |
| `docs/assets/screenshots/*.svg` | CC0-1.0 | Placeholder; replace with real screenshots |
| Future real screenshots | CC0-1.0 | Keep the same licence when replacing |
| Future GIF / video recording | CC0-1.0 | Record from the app using fictional NPCs only |
