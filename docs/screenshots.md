<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Screenshots and demo assets

Every image in `docs/assets/` is a capture of the app running a real session against a
real local model. Nothing here is a mockup, a composite, or a retouched frame. This
document records what each asset shows, the alt text that must travel with it, the
machine it was captured on, and the single command that remakes the whole set.

---

## Capture environment

Recorded 2 October 2026 from the development build.

| | |
|---|---|
| Hardware | Apple M1 Pro, 16 GB unified memory, macOS 14.8.2 |
| Model | Qwen3 4B Instruct Q4_K_M (Apache-2.0), 2.3 GB on disk, loaded as a local GGUF |
| Engine | llama.cpp `b9415` `llama-server`, `--ctx-size 8192 --n-gpu-layers 99` |
| App | `./scripts/dev.sh` — UI on `http://127.0.0.1:7354`, core on `http://127.0.0.1:7355` |
| Profile | a throwaway `CONVSIM_DATA_ROOT` with the six official packs seeded and no personal data |
| Scenario | **Making the Case** (Job Interview Basics), standard difficulty, seed `455`, text input, NPC state meters enabled |
| Browser | Chromium (Playwright), 1280 CSS px wide at `devicePixelRatio` 2 |

Two things visible in the captures are the app reporting on **this machine**, not on the
product, and are kept rather than staged away:

- **The amber performance advisories.** The app raises two, and both are in frame here:
  "NPC response is slow" on `03-conversation.png`, where the first token took 9.6 s, and
  "Full NPC response is very slow" at the end of the hero recording, where the whole
  reply took 14.0 s. The product budgets 2.5 s to first token and 10 s to a full response
  on the recommended tier ([`packages/shared/src/types/metrics.ts`](../packages/shared/src/types/metrics.ts)); a 2021
  laptop running a 4B model at a ~1,500-token prompt lands well past both and the app
  says so. Capturing on faster hardware removes the banners; editing them out would be a
  lie about the thing the README is selling.
- **STT and TTS reading "Not installed"** on the home screen. Voice needs whisper.cpp and
  a local Kokoro server, which are optional runtimes a text-only install does not have
  (see [`docs/install.md`](install.md)). The app runs fully in text mode without them.

No real people, faces, voices, or private data appear in any asset. Every NPC, company
and transcript line is fictional scenario content or model output responding to it.

---

## Re-capturing

```sh
# 1. a local model installed and selected, engine up, dev services running
./scripts/dev.sh

# 2. Playwright + Chromium (not a repo dependency — only needed to re-capture)
npm install playwright && npx playwright install chromium

# 3. drive a real playthrough and write every asset
NODE_PATH="$PWD/node_modules" node scripts/capture-screenshots.mjs
```

[`scripts/capture-screenshots.mjs`](../scripts/capture-screenshots.mjs) plays the
scenario through the real UI — library search, scenario setup, four typed turns, end
session, debrief — then captures the Creator Workbench and Model Manager, and encodes
the hero recording from the last exchange with `ffmpeg`. It **refuses to run** when the
active runtime is `fake` or `scripted`, so a capture can never quietly ship canned text
as gameplay.

Useful flags: `--skip-hero` (screenshots only, no recording) and `--only=03,06` (still
plays the session, but writes only the named screens). The scenario, player turns and
seed are constants at the top of the file.

---

## Demo asset (README hero)

| File | `docs/assets/demo.gif` (3.1 MB) · `docs/assets/demo.mp4` (0.6 MB fallback) |
|------|-----------------------------------------------------------------------------|
| Used in | `README.md` |
| License | CC0-1.0 |
| Shows | 25 s of one real turn: the player types a reply, the local model answers as the NPC, and the state meters under the transcript move as the turn resolves |
| Fictional content | NPC "Elena Vasquez" (Head of Product, stretch-hire interview) — no real person |

**Alt text used in README:**

> One turn of "Making the Case" in Conversation Simulator: the player types a reply into
> the composer, the local model answers as the NPC with event flags beneath it, and the
> NPC state meters below the transcript — trust, patience, rapport, openness,
> objective_progress, conviction, preparation_score — update as the turn resolves. An
> amber advisory above the transcript reports that the full response took 14.0 seconds on
> this machine.

---

## Screenshots (docs/assets/screenshots/)

Six PNGs, 2560 px wide (1280 CSS px at 2×), heights fitted to each screen.
License: **CC0-1.0** (public domain).

### 01-home.png — Home screen

**What it shows:** The home screen on a ready text-only install. Navigation links, the
"Your training" card summarising the three sessions played in this capture profile
(streak, strongest and weakest rubric dimension, last session's delta), a three-scenario
training plan, and the Status panel: Local runtime ready, the loaded model named, voice
runtimes not installed, no network required, six packs installed.

**Alt text:**
> Conversation Simulator home screen. Links run down the page — Start a scenario,
> Create / edit a scenario, Install model, Import pack, Creator workbench guide, Read
> docs — above a "Your training" card summarising the three sessions played in this
> profile, and a three-scenario training plan. The Status panel reports Local runtime:
> Ready, LLM: Qwen3 4B Instruct Q4_K_M, STT and TTS: Not installed, Network required to
> play: No, and Packs: 6 installed.

---

### 02-scenario-library.png — Scenario Library

**What it shows:** The library with the live search box filtered to `interview`, the
rating, language, difficulty and tag filters beside it, and the Job Interview Basics pack
expanded to its four scenario cards with metadata chips and Launch buttons.

**Alt text:**
> Scenario Library filtered by the search word "interview": four scenarios in one pack.
> The Job Interview Basics pack lists Making the Case, The Behavioral Interview, The
> Executive Gauntlet and The Foreman's Interview. Each card carries a summary, chips for
> content rating, player role, length, language, difficulty and tags, and a blue Launch
> button.

---

### 03-conversation.png — Conversation (mid-session with state meters)

**What it shows:** Turn 10 of the session. NPC panel (emotion "Impressed", status
"Listening"), the scene card, the performance advisory this machine earned, four turns of
transcript with per-turn event flags, the NPC state variable meters — the five baseline
variables plus the scenario's own `conviction` and `preparation_score` — the accumulated
event-flag strip, and the text composer.

**Alt text:**
> The conversation screen mid-session in "Making the Case". The NPC panel reads Impressed
> and Listening beside a scene card describing the stretch-hire interview, and an amber
> advisory notes that the first token took 9.6 seconds on this machine. The transcript
> alternates the player's turns in violet with the NPC's replies in green, each NPC turn
> tagged with event flags such as honesty_demonstrated. Below the transcript, NPC state
> variable meters read trust 95, patience 75, rapport 50, openness 80, objective_progress
> 0, conviction 35 and preparation_score 55.

---

### 04-debrief.png — Session Debrief

**What it shows:** The debrief generated for that session: overall score and outcome
badge, a model-written summary, the rubric scorecard, the telemetry panel with
conversation metrics and a sparkline per state variable, then strengths — each citing the
turn it came from — and areas for improvement. The frame ends at the improvements
section; key moments, replay suggestions and the transcript continue below.

**Alt text:**
> Session Debrief scoring the session 53 out of 100 with a "Player Exit" outcome badge
> and four turns. A written summary is followed by a six-dimension scorecard — Experience
> Gap Acknowledged 59, Transferable Skills Demonstrated 52, Learning Velocity
> Demonstrated 52, Specific Evidence Transferable Skills 52, Honesty About Experience Gap
> 51, Transferable Evidence 52 — then a Telemetry panel showing talk ratio, words per
> turn, question counts, response latency and a sparkline for each state meter. Strengths
> are listed in green, each citing the turn it came from, and areas for improvement in
> amber.

---

### 05-creator-workbench.png — Creator Workbench

**What it shows:** The workbench after using "Create local copy to edit" on an official
pack: the green validation banner, the pack list with six read-only official packs and
one editable local-dev copy, that copy's file tree, and the YAML editor open on a
scenario file with the YAML/Form toggle, Save, and Export .zip.

**Alt text:**
> Creator Workbench. A green "Pack is valid" banner sits above a three-column layout: the
> pack list with six official packs and one editable local-dev copy of Job Interview
> Basics, that copy's file tree with scenarios/stretch_role_interview.yaml selected, and
> a YAML editor showing the file — schema_version, scenario_id, title, summary,
> player_role, and the npc, scene and rubric references — with YAML and Form editor
> toggles, a Save button and an Export .zip button.

---

### 06-model-manager.png — Model Manager

**What it shows:** The model surface as it actually ships: three ways to get an engine
running — install the recommended registry model, pick one from a local Ollama, or point
at a GGUF file already on disk — with size, licence, VRAM requirement and an expected
speed class on the recommended card.

**Alt text:**
> Model Manager. "Set up your model" offers three cards: install the recommended Qwen3 4B
> Instruct Q4_K_M (2.5 GB, Apache-2.0, requires 4 GB VRAM, tagged Fast with an expected
> 0.8 to 2.4 second time to first token), use a model already installed in local Ollama,
> or point the app at a GGUF file already on the machine.

---

## Capture checklist

Completed for the current set; re-run it whenever the assets are replaced.

- [x] Recorded from a development build at `http://127.0.0.1:7354` with fictional NPC
      data and a local Qwen3 model — no real-person images, audio, or data.
- [x] PNG screenshots exported at 2× (2560 px wide), heights fitted per screen.
- [x] Hero recording exported under 5 MB (`ffmpeg` palette optimisation), with an MP4
      fallback alongside it.
- [x] Files placed in `docs/assets/screenshots/`, and derived web copies placed in
      `website/static/images/screenshots/` and `docs-site/public/images/screenshots/`:
      `magick <png> -resize 1280x -colors 256 -strip <dest>` (about a fifth the bytes,
      still sharp at the sizes those pages render).
- [x] The old hero SVG and the six mockup SVGs are gone from the tree; `demo.gif`
      and the six PNGs take their place.
- [x] `README.md` image tags updated with the real filenames and the alt text above.
- [x] Manual content and safety review: no real faces, no sensitive data, no identifiable
      voices, nothing above PG-13.
- [x] File sizes verified for GitHub rendering (largest screenshot 0.5 MB, hero 3.1 MB).
- [x] `NOTICE` updated for the captured assets (CC0-1.0).

---

## Licence summary

| Asset | Licence | Notes |
|-------|---------|-------|
| `docs/assets/demo.gif`, `docs/assets/demo.mp4` | CC0-1.0 | Captured from a real session; fictional NPCs only |
| `docs/assets/screenshots/*.png` | CC0-1.0 | Captured from a real session; fictional NPCs only |
| Site copies under `website/static/images/` and `docs-site/public/images/` | CC0-1.0 | The same captures at 1×, 256 colours, for page weight |
| Future re-captures | CC0-1.0 | Keep the same licence, and re-run the checklist above |
