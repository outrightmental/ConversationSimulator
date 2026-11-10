<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Screenshots and demo assets

Every image in `docs/assets/` is a capture of the app running a real session against a
real local model. Nothing here is a mockup, a composite, or a retouched frame. The one
edit is the hero recording's playback speed, and every frame of it says so (see
[Demo asset](#demo-asset-readme-hero)). This document records what each asset shows,
the alt text that must travel with it, the machine it was captured on, and the single
command that remakes the whole set.

---

## Capture environment

Recorded 10 November 2026 from the development build of the v0.4.0 release (#554).

| | |
|---|---|
| Hardware | Cloud VM: 4 vCPU Intel Xeon @ 2.10 GHz, 15 GB RAM, no GPU, Ubuntu 24.04 |
| Model | Qwen3 4B Instruct Q4_K_M (Apache-2.0), 2.5 GB, installed by the app's own one-click set-up: download, SHA-256 verify, warm-up |
| Engine | llama.cpp `b9415` `llama-server`, CPU only, launched by convsim-core with `--ctx-size 8192` and its one-conversation profile (#523) |
| Measured speed | about 63 tokens/s reading the prompt and 6.5 tokens/s writing, so a turn late in the session takes one to two minutes |
| App | `./scripts/dev.sh` — UI on `http://127.0.0.1:7354`, core on `http://127.0.0.1:7355` |
| Profile | a throwaway `CONVSIM_DATA_ROOT` with the official packs seeded, onboarding completed through the real welcome screen ("Set me up"), and no personal data |
| Scenario | **Making the Case** (Job Interview Basics), standard difficulty, seed `455`, text input, conversation meters on |
| Browser | Chromium (Playwright 1.63), 1280 CSS px wide at `devicePixelRatio` 2 |

This machine is slower than any the app recommends: it has no graphics card and four
cores. Two things in the captures are the app reporting on **this machine**, not on the
product, and are kept rather than staged away:

- **How long the turn takes.** The hero recording is played back at 6x, with the factor
  and the real length of the turn on every frame. In real time the player waits through
  the staged panel ("Elena Vasquez is thinking…", the reading bar) for most of a minute
  before the reply starts, and then watches it arrive a sentence at a time. On the
  reference hardware in the release checklist the same turn takes a few seconds.
- **Voice input and output reading "Not installed"** on the home screen. Voice needs
  whisper.cpp and a local Kokoro server, which are optional runtimes a text-only install
  does not have (see [`docs/install.md`](install.md)). The app runs fully in text mode
  without them.

The Status panel names the model by its file, `qwen3-4b-instruct-q4_k_m.gguf`, because
that is what the engine reports once the one-click set-up has installed it; shorter,
friendlier model names are #555.

No real people, faces, voices, or private data appear in any asset. Every NPC, company
and transcript line is fictional scenario content or model output responding to it.

---

## Re-capturing

```sh
# 1. a local model installed and selected, engine up, dev services running
./scripts/dev.sh

# 2. Playwright + Chromium (not a repo dependency — only needed to re-capture)
npm install playwright && npx playwright install chromium

# 2b. ffmpeg, for the hero recording (not needed with --skip-hero, or with
#     an --only list that leaves `hero` off)
brew install ffmpeg

# 3. drive a real playthrough and write every asset under docs/assets/
NODE_PATH="$PWD/node_modules" node scripts/capture-screenshots.mjs

# 4. remake the 1x web copies the two sites render (the script prints this
#    command itself whenever it rewrote a screenshot)
for f in docs/assets/screenshots/*.png; do
  for d in website/static/images/screenshots docs-site/public/images/screenshots; do
    magick "$f" -resize 1280x -colors 256 -strip "$d/$(basename "$f")"
  done
done
```

[`scripts/capture-screenshots.mjs`](../scripts/capture-screenshots.mjs) plays the
scenario through the real UI — library search, scenario setup, four typed turns, end
session, debrief — then captures the Creator Workbench and Model Manager, and encodes
the hero recording from the last exchange with `ffmpeg`. It **refuses to run** when the
active runtime is `fake` or `scripted`, so a capture can never quietly ship canned text
as gameplay.

Useful flags: `--skip-hero` (screenshots only, no recording) and `--only=03,06` (still
plays the session, but writes only the named outputs — a screen number, or `hero` for the
recording; anything left off the list keeps the file already committed). A name the
script does not write — or a pair of flags that cancel out, like `--skip-hero
--only=hero` — is rejected before the playthrough starts, so neither can cost a run. The
scenario, player turns and seed are constants at the top of the file.

`--hero-speed=N` (1 to 16, default 1) plays the hero recording back N times faster and
draws "Played at Nx speed — this turn took S s on the capture machine" on every frame.
Use it only where a real-time turn would make the recording minutes long; on the
recommended hardware the default real-time recording fits the GIF budget.

Two things that cost a run: `./scripts/dev.sh` serves convsim-core with `--reload`, so
editing anything under `services/convsim-core/` mid-capture restarts the core and its
engine and fails the turn in flight; and a run that stops mid-session leaves that session
open, so the next run's screens carry a "Conversation in progress" banner. End it first
(`POST /api/sessions/<id>/end`).

The demo app's Steam store screenshots are a separate set, made by
[`scripts/capture-store-screenshots.mjs`](../scripts/capture-store-screenshots.mjs)
against a demo-edition engine on a fresh profile; see
[`publishing/STEAM_NEXT_FEST_DEMO.md`](../publishing/STEAM_NEXT_FEST_DEMO.md) §4.2.

A run that loses a screen keeps going — the other outputs are worth more than the one
that failed — but it **exits non-zero** and names what it missed. Those files still hold
the previous capture, so check the exit status before committing: a partial run is
otherwise indistinguishable from a full one. If it is the hero encode that failed, the
raw `.webm` is left in its temp directory and the path printed, so the segment can be
re-encoded by hand instead of replayed.

---

## Demo asset (README hero)

| File | `docs/assets/demo.gif` (3.1 MB) · `docs/assets/demo.mp4` (0.6 MB fallback) |
|------|-----------------------------------------------------------------------------|
| Used in | `README.md` — the GIF. The MP4 is the same segment kept as a video source for the Steam trailer and store page (`publishing/STEAM_ASSETS_SPEC.md`); nothing embeds it today. |
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

The alt text recorded below is what `README.md` carries verbatim. The 1× web copies and
the authoring guide carry condensed variants of the same description — shorter, but a
subset of what is recorded here, never a different claim.

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
transcript with per-turn event flags, the NPC state variable meters — the five visible
baseline variables plus the two the scenario adds, `conviction` and `preparation_score` —
the accumulated event-flag strip, and the text composer. The hidden variables (baseline
`pressure`, the scenario's `stretch_potential` and `gap_acknowledged`) have no meter here;
they surface only in the debrief telemetry on `04-debrief.png`.

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
scenario file with the YAML/Form toggle, Save, and Export .zip. Both columns are
viewport-height panels that scroll on their own, so the frame shows the top of
the file tree and the top of the open file rather than all of either.

**Alt text:**
> Creator Workbench. A green "Pack is valid" banner sits above a two-column layout. On
> the left, the pack list — six official packs and one editable local-dev copy of Job
> Interview Basics — sits above that copy's file tree, with
> scenarios/stretch_role_interview.yaml selected. On the right, a YAML editor shows the
> file — schema_version, scenario_id, title, summary, player_role, and the npc, scene
> and rubric references — with YAML and Form editor toggles, a Save button and an
> Export .zip button.

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
      `magick <png> -resize 1280x -colors 256 -strip <dest>` (about a quarter the bytes,
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
