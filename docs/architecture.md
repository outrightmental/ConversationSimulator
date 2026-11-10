<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Architecture

This document gives a developer-level overview of the Conversation Simulator system.
It covers the service topology, turn pipeline, session state machine, WebSocket event
contract, and the pack-loading security boundary.

For runtime adapter details see [runtime-adapters.md](runtime-adapters.md).
For the full technical specification see [SPEC.md](SPEC.md).

---

## Service topology

All services bind to `127.0.0.1` only. No traffic leaves the machine unless the
user explicitly enables LAN access (`CONVSIM_LAN_ACCESS_ENABLED=true`).

```
┌──────────────────────────────────────────────────────────────────┐
│                        Developer machine                         │
│                                                                  │
│  ┌──────────────────────┐                                        │
│  │  Browser             │  React/TypeScript/Vite                 │
│  │  convsim-ui :7354    │                                        │
│  └──────────┬───────────┘                                        │
│             │  HTTP REST + WebSocket (localhost)                 │
│             ▼                                                    │
│  ┌──────────────────────┐   SQLite                              │
│  │  convsim-core :7355  │◄──────────────────┐                   │
│  │  Python / FastAPI    │                   │                   │
│  └──────────┬───────────┘          ~/.convsim/db/               │
│             │                       convsim.sqlite              │
│    ┌────────┼─────────────────┐                                 │
│    ▼        ▼                 ▼                                 │
│  :7356    :7357             :7358                               │
│  LLM      STT               TTS                                 │
│  llama-   whisper.cpp       Kokoro /                            │
│  server   worker            sherpa-onnx                         │
└──────────────────────────────────────────────────────────────────┘
```

### Service ports

| Service       | Port  | Responsibility                          |
|---------------|-------|-----------------------------------------|
| convsim-ui    | 7354  | Browser UI (Vite dev server)            |
| convsim-core  | 7355  | Main API, scenario engine, WebSocket    |
| convsim-llm   | 7356  | Local LLM server (llama-server)         |
| convsim-stt   | 7357  | Speech-to-text worker (whisper.cpp)     |
| convsim-tts   | 7358  | Text-to-speech worker (Kokoro/sherpa)   |

### Key directories

| Path                         | Contents                              |
|------------------------------|---------------------------------------|
| `services/convsim-core/`     | Python FastAPI backend                |
| `apps/web/`                  | React frontend                        |
| `apps/api/`                  | TypeScript/Fastify API proxy layer    |
| `packages/`                  | Shared TS packages (types, UI, CLI)   |
| `runtimes/`                  | LLM/STT binary integration helpers   |
| `packs/`                     | Official first-party scenario packs   |
| `schemas/`                   | JSON Schema definitions               |
| `~/.convsim/`                | Runtime data root (db, packs, logs)   |

---

## Design principles

- **Provider abstraction.** The scenario engine calls `ChatRuntime`, never a
  specific LLM library. New runtimes (Ollama, llama.cpp, future providers)
  implement the same interface without touching engine code.

- **Declarative packs.** Scenario content is YAML/JSON data, never executable
  code. The validator enforces this at import time (see [Pack security](#pack-security)).

- **Local-only inference.** No LLM, STT, or TTS call leaves the machine.
  SQLite holds all session state and transcripts.

- **Layered safety.** Deterministic keyword checks precede the LLM call;
  the LLM itself applies policy-scoped content rules; output validation
  can reject or fall back on malformed responses.

---

## Turn pipeline

A single player turn passes through nine ordered steps inside
`convsim_core/services/turn_pipeline.py`.

```
Player text (HTTP POST /api/sessions/{id}/turn)
        │
        ▼ 1. Normalize & validate
        │     strip whitespace, reject empty, reject > 2000 chars
        │
        ▼ 2. Input safety precheck  (turn_pipeline._safety_precheck)
        │     currently a placeholder no-op (accepts all input).
        │     The intended enforcement point is input_router.route_player_input,
        │     which classifies input against global non-overridable rules
        │     (minors, self-harm crisis) and policy-configurable rules
        │     (NSFW, criminal, etc.) into ok | redirect | refuse | stop |
        │     stop_with_resource_message. It is not yet wired into this pipeline.
        │
        ▼ 3. Evaluate event triggers, then build the prompt
        │     (scenario_state.evaluate_event_triggers, on the state the previous
        │     turn left; convsim_prompt.compose_turn_prompt)
        │     scenario context, NPC persona, the scenario's state variables
        │     with their meanings, the instructions of the events that fired,
        │     last 12 transcript turns, safety policy, player utterance
        │
        ▼ 4. Call ChatRuntime  (runtime.chat_stream)
        │     streams ChatToken chunks, receives ChatFinal
        │
        ▼ 5. Validate / repair / fallback  (convsim_prompt.parse_turn_output)
        │     JSON schema validation; fallback utterance on parse failure:
        │     "I'm not sure what to say right now. Could you repeat that?"
        │
        ▼ 6. Apply bounded state deltas  (scenario_state.apply_state_delta)
        │     reject unknown keys and any the session's schema does not name,
        │     clamp per-turn delta, clamp to [min,max]
        │
        ▼ 7. Evaluate ending conditions  (scenario_state.evaluate_ending_condition)
        │     variable_above / variable_below / max_turns conditions
        │     ending priority: safety_stop → player_exit → success → failure → timeout
        │
        ▼ 8. Persist atomically  (SQLite transaction)
        │     player turn row, NPC turn row, state_delta event,
        │     scenario_event rows, safety events, ending event,
        │     FTS entries (if save_transcript=true),
        │     update turn_sessions.state_vars_json / flow_state
        │
        ▼ 9. Return TurnPipelineResult
              → HTTP response with events array
```

**Error policy.** `TurnInputError` (raised in step 1) surfaces as HTTP 400.
Model errors (step 4) are absorbed; the safe fallback utterance is used
instead and `used_fallback=true` is set in the result.

---

## Session state machine

Sessions progress through a linear set of states stored in
`turn_sessions.flow_state`. The full set of valid states is defined in
`packages/shared/src/types/session.ts`.

```
NotStarted
    │  POST /api/sessions/{id}/start
    ▼
PlayerTurnListening   ◄──────────────────────────┐
    │  POST /api/sessions/{id}/turn               │
    ▼                                             │
 (turn pipeline runs)                             │
    │                                             │
    ├─── ending_type = null ──────────────────────┘  (session continues)
    │
    └─── ending_type set ──► Ended
                               │
                               │  POST /api/sessions/{id}/debrief
                               ▼
                         DebriefGenerating
                               │
                               ▼
                         DebriefReady
```

Additional states used by the frontend state machine (not persisted
in the DB, managed client-side):

| State              | Description                                      |
|--------------------|--------------------------------------------------|
| `LoadingModel`     | Waiting for the LLM runtime to become ready      |
| `LoadingScenario`  | Fetching scenario data from the API              |
| `Briefing`         | Showing the player role briefing before start    |
| `NpcOpening`       | Displaying the NPC opening line                  |
| `PlayerTurnReview` | Player has typed; confirming before submit       |
| `NpcThinking`      | Waiting for first NPC token                      |
| `NpcSpeaking`      | Streaming NPC tokens to the UI                   |
| `ScenarioEvent`    | A scenario narrative event is being displayed    |
| `Error`            | Unrecoverable error; debrief may still be tried  |

### Ending types

| Ending type    | Cause                                                 |
|----------------|-------------------------------------------------------|
| `success`      | Scenario success condition met                        |
| `failure`      | Scenario failure condition met                        |
| `timeout`      | `max_turns` reached without success or failure        |
| `safety_stop`  | Input safety precheck or NPC output triggered stop    |
| `player_exit`  | Player called `POST /api/sessions/{id}/end`           |

### What counts as a turn

**One turn is one player message plus the NPC's reply to it.** The two are
halves of a single turn, not two turns — the sense the term carries elsewhere
in the conversational-LLM world.

This is the unit everything server-side already counted, and it is now also the
unit the transcript labels:

- `turn_count` on `turn_sessions` increments once per exchange, so the turn
  pipeline numbers a turn `turn_count + 1`.
- `duration.max_turns` and the `max_turns` ending condition are measured in it,
  so a scenario with `max_turns: 16` allows sixteen exchanges — not eight.
- Debrief key moments point at it, so a debrief's "turn 3" and the transcript's
  "Turn 3" are the same moment.
- The NPC's opening line is part of no exchange. It is stored at turn number 0
  and labelled rather than numbered, so it does not consume turn 1.

Transcript rows are a finer grain than turns: the opening is stored at row 0,
and whole turn *n* occupies the player row `2n-1` and the NPC row `2n`.

---

## REST API summary

Base URL: `http://127.0.0.1:7355`

### Sessions

| Method | Path                              | Description                              |
|--------|-----------------------------------|------------------------------------------|
| POST   | `/api/sessions`                   | Create a session (`NotStarted`)          |
| GET    | `/api/sessions`                   | List this profile's sessions, newest first |
| GET    | `/api/sessions/{id}`              | Get current state                        |
| POST   | `/api/sessions/{id}/start`        | Deliver NPC opening; → `PlayerTurnListening` |
| POST   | `/api/sessions/{id}/turn`         | Submit player turn; runs full pipeline   |
| POST   | `/api/sessions/{id}/end`          | End session; → `Ended`                   |
| POST   | `/api/sessions/{id}/debrief`      | Generate debrief; → `DebriefReady`       |
| GET    | `/api/sessions/{id}/transcript`   | Retrieve full transcript                 |
| GET    | `/api/sessions/{id}/export`       | Export session JSON (turns + events + debrief) |
| DELETE | `/api/sessions/{id}`              | Delete session and transcript            |
| GET    | `/api/performance/rolling`        | This machine's recent turn speeds (medians over `turn_timing` records) |

**Idempotency note.** `POST /turn` is not idempotent. Before retrying after
a network failure, call `GET /api/sessions/{id}` to check whether the turn
was already recorded.

**Listing sessions.** `GET /api/sessions` takes two optional query parameters:

| Parameter | Values | Default | Meaning |
|-----------|--------|---------|---------|
| `status`  | `all`, `in_progress`, `ended` | `all` | `in_progress` is the *resumable* set — started and not ended |
| `limit`   | 1–500 | 50 | Out-of-range values are rejected with 400 |

Each row carries the session's `setup` (the request it was created with), its
`turn_count`, and its `ending_type` / `ended_at` when it has finished. `setup`
is what lets a resumed conversation rebuild the language, meter and voice
choices it was launched with after the UI has lost them to a navigation or a
relaunch. `status=in_progress` deliberately excludes `NotStarted`: nothing has
been said yet, so there is no conversation to pick back up.

`status=ended` covers every state a finished session can sit in, not just
`Ended`: generating the debrief moves the row to `DebriefGenerating` and then
`DebriefReady`, and a debrief that fails leaves `Error`. Together with
`in_progress` and `NotStarted` that accounts for every state, so the two
filters partition the sessions that were ever started.

The two state lists are also needed client-side — Settings lists every
unfinished conversation with its own Resume button, picking them out of a full
listing — so they live in `packages/shared` (`RESUMABLE_SESSION_STATES`,
`ENDED_SESSION_STATES`) for every TypeScript consumer, with a pytest guard
asserting they still match convsim-core's `RESUMABLE_FLOW_STATES` and
`ENDED_FLOW_STATES`.

Creator Workbench preview sessions are excluded from every `status`, including
`all`. They are written straight into `turn_sessions` under a dynamic
`__wbtest__<hex>` scenario id and nothing ever ends them, so one preview would
otherwise sit at the top of the resumable set permanently, pointing at a
scenario that was only ever registered in memory.

**Reading one session back.** `GET /api/sessions/{id}` returns the same shape
plus `visible_state`: the session's current meter values, filtered through the
scenario's own variable visibility so a hidden variable stays hidden, and,
for a scenario with state of its own, leaving out the variables it does not
play (see the state section below). Meter
values otherwise only ever arrive with a turn, so this is what lets a resumed
conversation draw its meters before the player sends another message.

### Other routes

| Prefix          | Description                           |
|-----------------|---------------------------------------|
| `/api/health`   | Liveness and runtime health check     |
| `/api/settings` | User settings (key-value)             |
| `/api/models`   | Model manager (list, install, status) |
| `/api/packs`    | Pack import, validation, browsing     |
| `/api/scenarios`| Scenario catalog and metadata         |
| `/api/stt`      | STT worker control                    |
| `/api/sidecar`  | llama-server sidecar control          |
| `/api/diag`     | Diagnostics and system info           |

---

## WebSocket events

The WebSocket endpoint is at `ws://127.0.0.1:7355/ws/session/{id}`, served by
`convsim-core` (`routers/session_ws.py`, issue #538). On connect the server
sends the current `session.state` so a reconnecting client can resync.

The socket is how the player sees a turn *while* it happens; the REST turn
response stays the commit and the source of truth, and with no socket connected
a turn behaves exactly as it does over REST alone. Events are not persisted and
there is no replay: `?after_seq` is accepted and ignored. A client that detects
a gap in `seq` re-fetches state via `GET /api/sessions/{id}` and the transcript.

**Origin.** CORS middleware does not cover socket upgrades, so the route checks
`Origin` itself against the same local list the REST API trusts (the packaged
webview's `tauri://localhost`, `http://tauri.localhost`,
`https://tauri.localhost`, plus the dev server at `127.0.0.1:7354` /
`localhost:7354`). Any other origin is answered with HTTP 403 before the
handshake. A request with no `Origin` header is not a browser page and is
accepted.

**One turn at a time.** `POST /api/sessions/{id}/turn` holds an in-memory lock
per session; a second submit while one is running answers 409
`TURN_IN_PROGRESS` and starts no generation. Nothing is persisted as "in
flight", so a crash can never leave a session unable to accept a turn.

Every message is a JSON object with these base fields:

```json
{
  "seq": 42,
  "session_id": "sess-abc123",
  "type": "npc.token",
  "ts": "2025-01-01T00:00:00.000Z",
  "payload": { ... }
}
```

`seq` is a monotonically increasing per-session counter assigned by the server
as each event is sent. Gaps in `seq` indicate missed events; the client should
re-fetch state via `GET /api/sessions/{id}`.

### Event types

| Type                    | When emitted                                        | Key payload fields                               |
|-------------------------|-----------------------------------------------------|--------------------------------------------------|
| `session.state`         | On connect, and at each turn's commit               | `state`, `state_vars?`, `ending_type?`           |
| `turn.progress`         | Each stage change of a running turn, and each prompt-reading progress report from the engine | `stage` (`waiting` · `reading` · `writing` · `finishing` · `checking` · `voice`), `prompt` (`{processed, total, cached}` or null), `output_tokens`, `elapsed_ms` |
| `npc.token`             | Each sentence of the NPC's line, once the line so far has passed the output check | `text` — an exact slice of the line; concatenating every `npc.token` of a turn reproduces the committed line |
| `npc.final`             | The spoken line is complete (the bookkeeping is still being written) | `content` only. `emotion`, `state_delta` and `event_flags` are not known yet; they arrive on `scenario.state_delta`. |
| `scenario.state_delta`  | The turn committed                                  | `delta`, `state_vars`, `turn_number`, `emotion`, `event_flags`, `triggered_scenario_events`, `ending_type`, `salvaged`, `timing` |
| `scenario.event`        | A scenario narrative event fired                    | `flags`                                          |
| `safety.redirect`       | The model's output was redirected for safety        | `reason`                                         |
| `error`                 | Processing error (may or may not be fatal)          | `code`, `message`, `details?`                    |

**Released text is committed text.** A sentence is sent as `npc.token` only
after the whole line so far, that sentence included, has passed the output
check, so nothing is shown and then withdrawn. If a later sentence fails the
check, generation stops and the turn is committed as the sentences already
released, with its bookkeeping defaulted and the turn marked `salvaged`. If
the JSON after the line is cut off, the released line stands and the fields
that completed before the cut are kept. The REST response always equals what
was streamed. A runtime that does not put the spoken line first releases
nothing, and the turn behaves as it did before streaming.

Reserved for future speech support (clients should accept and ignore):

| Type               | Planned purpose                              |
|--------------------|----------------------------------------------|
| `stt.partial`      | Interim speech-to-text transcript            |
| `stt.final`        | Final speech-to-text transcript              |
| `tts.audio_chunk`  | Base64-encoded audio chunk                   |

---

## Scenario state variables

Every session maintains a state dictionary of integer variables clamped
to `[min, max]`. Six baseline variables are present in every scenario:

| Variable            | Default | Visibility | Description                    |
|---------------------|---------|------------|--------------------------------|
| `trust`             | 50      | visible    | NPC trust in the player        |
| `patience`          | 75      | visible    | NPC tolerance for misbehavior  |
| `pressure`          | 25      | **hidden** | Situational pressure on NPC    |
| `rapport`           | 50      | visible    | Conversational warmth          |
| `openness`          | 50      | visible    | NPC willingness to share       |
| `objective_progress`| 0       | visible    | Progress toward scenario goal  |

Scenario packs can override baseline defaults or add custom variables via
the `state.variables` block in the scenario YAML. Each variable also carries
`max_delta_per_turn` (default 20) which caps how much the LLM can move it
per turn. Unknown variable names proposed by the LLM are rejected silently
and logged at WARNING.

A scenario that declares variables of its own plays exactly those, plus any
baseline its events or ending conditions read (`played_variable_names`).
The turn prompt's `STATE_VARIABLES` layer gives each its range, per-turn
limit and authored `description` (or, without one, what the scenario's
events on it say), and the turn output schema the runtime is sent makes
`state_delta` an object with each of them a required integer and no other
key; the engine clamps each to its `max_delta_per_turn`. A baseline nothing
in the scenario reads is left out of the prompt and cannot be moved, so it
has no meter either: every path that reports meters (the turn result, the
opening event, the session detail and export, the session socket's resync
and the debrief's state arc) shows only the visible variables the scenario
plays. A scenario that
configures no state (most of the hardcoded catalog) plays every baseline
with a free-form `state_delta`, and shows each visible one, as before.

Scenario events are evaluated at the start of a turn, on the state the
previous turn left; each one that fires puts its `npc_instruction` into that
turn's prompt (the `SCENARIO_EVENTS` layer) and is recorded on that turn.

---

## Pack security

Scenario packs are **untrusted data**. The validator and importer apply
multiple security layers before any pack content reaches the engine.

### What is enforced at import time

1. **No executable content.** Forbidden extensions include `.exe`, `.bat`,
   `.cmd`, `.sh`, `.ps1`, `.py`, `.js`, `.ts`, `.jar`, `.so`, `.dll`,
   `.dylib`, `.wasm`. Files are also inspected for magic bytes (ELF,
   Mach-O, PE, WebAssembly, shebangs) regardless of extension.

2. **No symlinks in zip archives.** `safe_extract_zip` rejects symlinks
   and any path that would escape the extraction directory (zip-slip
   protection).

3. **Size cap.** ZIP archives may not expand beyond 500 MB.

4. **Schema validation.** Every YAML file is validated against a
   corresponding JSON Schema (pack manifest, scenario, NPC, rubric,
   safety policy, scene). Validation errors block import.

5. **Prompt injection scanning.** Scenario text is scanned for patterns
   that attempt to override the system prompt, switch roles, or escape
   delimiters. Findings are reported as warnings or errors.

6. **Path escape check.** The computed install directory is verified to
   stay within `~/.convsim/packs/`.

7. **Conflict check.** Importing a pack whose `pack_id` is already
   installed is rejected (HTTP 409).

### What packs can and cannot do

| Packs can                                   | Packs cannot                            |
|---------------------------------------------|-----------------------------------------|
| Define NPC personas, goals, and tone        | Execute arbitrary code                  |
| Configure state variables and their limits  | Override global safety rules            |
| Add custom scenario events                  | Install files outside the pack dir      |
| Specify a content rating cap (G/PG/PG-13)   | Claim a content rating higher than PG-13|
| Define per-category safety policy actions   | Disable minors or self-harm rules       |
| Include images, audio, and text assets      | Embed external URLs in assets           |

### Runtime separation

System-level prompts (NPC persona framing, safety policy, output schema)
are composed by `convsim_prompt.compose_turn_prompt` from structured
fields, not from raw pack strings interpolated into the prompt verbatim.
Pack text that reaches the prompt is placed inside clearly delimited
content sections, reducing the blast radius of injection attempts.

---

## Debrief engine

After a session ends, `POST /api/sessions/{id}/debrief` calls
`services/debrief_engine.generate_debrief`:

1. Load all turns and raw LLM output from the database.
2. Aggregate rubric observations (score deltas per dimension from each turn).
   With a rubric, only observations under its dimensions count.
3. Identify turning points: significant state changes, event flags, safety events.
4. Build a debrief prompt: scenario context, the rubric's dimensions with
   their names, weights and low / medium / high bands, and the transcript,
   with every line and note labelled with whose it is.
5. Call `ChatRuntime.chat_stream` with the debrief JSON schema. With a rubric
   the schema also asks for each dimension's band (`dimension_bands`).
6. Score each dimension (0–100). A band sets the score (low 25, medium 55,
   high 85) and the turn deltas move it at most 12 points either way; a
   dimension with no band scores 50 plus its deltas, and one with neither is
   left off. The overall score weights the dimensions by the rubric's weights.
   A scenario with no rubric scores every observed id from 50 plus its
   deltas, and the overall score is their mean.
7. Persist and return the debrief document, with each dimension's rubric
   name (`dimension_names`) and band (`dimension_bands`).

The turn prompt names the same dimensions (its `RUBRIC` layer), and the turn
output schema the runtime is sent makes `rubric_observations[].rubric_id` an
enum of their ids, so the engine's grammar cannot write any other.

Language guardrails in the prompt prohibit clinical advice, performance
guarantees, and invented quotes. Evidence is cited by turn number only.

---

## Database schema (SQLite)

The database lives at `~/.convsim/db/convsim.sqlite` with WAL mode and
`PRAGMA foreign_keys = ON`.

| Table                  | Purpose                                              |
|------------------------|------------------------------------------------------|
| `packs`                | Installed pack metadata                              |
| `scenarios`            | Scenario catalog (one row per scenario)              |
| `scenario_versions`    | Versioned scenario JSON content                      |
| `turn_sessions`        | Active and completed sessions                        |
| `turn_session_turns`   | Individual player and NPC turns                      |
| `turn_session_events`  | Per-turn events (state_delta, scenario_event, turn_timing, etc.) |
| `session_debriefs`     | Generated debrief documents (JSON)                   |
| `installed_models`     | Downloaded model files and install status            |
| `model_registry`       | Curated model definitions with checksums             |
| `asset_index`          | Pack asset catalog                                   |
| `user_settings`        | Key-value user preferences                           |

Full-text search tables (FTS5): `session_transcript_fts`, `scenario_fts`,
`pack_readme_fts`.

---

## Future / non-MVP areas

The following areas are planned but not implemented in the current milestone:

- **Voice input/output (STT/TTS).** Ports 7357 and 7358 are reserved;
  the WebSocket `stt.*` and `tts.*` event types are defined but not
  yet emitted.
- **Godot / VR client.** The WebSocket protocol is designed to support
  non-browser clients; a Godot adapter is a planned future target.
- **Pack marketplace.** Import currently supports local folders and zip
  uploads. A curated marketplace with signed packs is planned.
- **Model classifier safety hook.** The `_safety_precheck` function in
  `turn_pipeline.py` is a no-op placeholder today. The deterministic
  `input_router.route_player_input` classifier plus a future local model
  classifier will be wired in as the real input-safety enforcement point.
- **LAN multiplayer.** `CONVSIM_LAN_ACCESS_ENABLED=true` unlocks LAN
  binding, but multi-user session management is not yet implemented.
