---
title: "Architecture"
description: "Developer-level overview of the Conversation Simulator system: service topology, turn pipeline, session state machine, WebSocket event contract, and pack security."
sidebar:
  order: 1
---

This document gives a developer-level overview of the Conversation Simulator system.
It covers the service topology, turn pipeline, session state machine, WebSocket event
contract, and the pack-loading security boundary.

For runtime adapter details see [runtime-adapters.md](/reference/runtime-adapters/).
For the full technical specification see [SPEC.md](/reference/spec/).

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

These paths are relative to the [repository root](https://github.com/outrightmental/ConversationSimulator).

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
        ▼ 3. Build prompt  (convsim_prompt.compose_turn_prompt)
        │     scenario context, NPC persona, state variables,
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
        │     reject unknown keys, clamp per-turn delta, clamp to [min,max]
        │
        ▼ 7. Evaluate event triggers & ending conditions
        │     (scenario_state.evaluate_event_triggers / evaluate_ending_condition)
        │     variable_above / variable_below / max_turns / flag conditions
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

---

## REST API summary

Base URL: `http://127.0.0.1:7355`

### Sessions

| Method | Path                              | Description                              |
|--------|-----------------------------------|------------------------------------------|
| POST   | `/api/sessions`                   | Create a session (`NotStarted`)          |
| GET    | `/api/sessions/{id}`              | Get current state                        |
| POST   | `/api/sessions/{id}/start`        | Deliver NPC opening; → `PlayerTurnListening` |
| POST   | `/api/sessions/{id}/turn`         | Submit player turn; runs full pipeline   |
| POST   | `/api/sessions/{id}/end`          | End session; → `Ended`                   |
| POST   | `/api/sessions/{id}/debrief`      | Generate debrief; → `DebriefReady`       |
| GET    | `/api/sessions/{id}/transcript`   | Retrieve full transcript                 |
| GET    | `/api/sessions/{id}/export`       | Export session JSON (turns + events + debrief) |
| DELETE | `/api/sessions/{id}`              | Delete session and transcript            |

**Idempotency note.** `POST /turn` is not idempotent. Before retrying after
a network failure, call `GET /api/sessions/{id}` to check whether the turn
was already recorded.

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
the API layer (`apps/api`). On connect the server always sends the current
`session.state` so a reconnecting client can resync.

Pass `?after_seq=0` to also replay the durable events for the session in
chronological order (NPC opening, NPC turns, and the ending, capped at the
first 50 by `event_id`). Per-`seq` resume —
passing the last received `seq` to receive only events after it — is **not yet
implemented**; any non-zero `after_seq` value is silently ignored because the
persisted events are keyed by `event_id`, a different number space from the WS
`seq`. Until seq-mapped replay lands, a client that detects a gap should
re-fetch full state via `GET /api/sessions/{id}`.

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
| `session.state`         | Any state transition                                | `state`, `state_vars?`, `ending_type?`           |
| `npc.token`             | Each streamed LLM token                             | `text`                                           |
| `npc.final`             | NPC response complete                               | `content`, `emotion`, `state_delta`, `event_flags` |
| `scenario.state_delta`  | State variables updated after a turn                | `delta`, `state_vars`                            |
| `scenario.event`        | A scenario narrative event fired                    | `flags`                                          |
| `safety.redirect`       | Input safety redirected the conversation            | `reason`                                         |
| `error`                 | Processing error (may or may not be fatal)          | `code`, `message`, `details?`                    |

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
3. Compute weighted per-dimension and overall scores (baseline 50, range 0–100).
4. Identify turning points: significant state changes, event flags, safety events.
5. Build a debrief prompt (scenario context + full transcript + rubric scores).
6. Call `ChatRuntime.chat_stream` with the debrief JSON schema.
7. Persist and return the debrief document.

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
| `turn_session_events`  | Per-turn events (state_delta, scenario_event, etc.)  |
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
