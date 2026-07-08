<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Privacy and data handling

Conversation Simulator is designed so that **nothing leaves your computer
during play**. This document explains exactly what data exists, where it is
stored, and how to delete it.

For network-level enforcement of this guarantee, see
[`network-security.md`](network-security.md).  
For content safety policy, see [`safety-policy.md`](safety-policy.md).

---

## The local-first promise

> Conversation Simulator does not send your conversations, audio, prompts,
> transcripts, or model outputs to any server during play. Model and pack
> downloads happen only when you explicitly request them.

This is backed by the code, not just by policy:

- All services bind to `127.0.0.1` by default. No ports are reachable from
  other machines. This is the primary runtime guarantee.
- Play-mode network calls (LLM, TTS, STT) route through a central gate,
  `require_network(NetworkMode.PLAY)` in `convsim_core.network_policy`. When
  local-only mode is enabled (`LOCAL_MODE = True`) the gate raises
  `NetworkBlockedError` on any play-mode outbound attempt. Local-only mode is
  what the offline smoke test and CI run under, so an accidental outbound call
  is caught before it can ship.
- The offline smoke test (see [Verifying local-only operation](#verifying-local-only-operation))
  runs an end-to-end session with a blocked network and confirms that nothing
  reaches out.

---

## What data exists and where it lives

### Conversation transcripts

**Default:** saved locally (on your machine only). You can turn this off.

Transcripts are stored in a local SQLite database (`~/.convsim/db/sessions.db`).
Saving is **on by default** so you can review, export, and search past sessions.
You can disable it under **Settings → Transcript → Save transcripts locally**;
when saving is off, no conversation text is written to disk after the session ends.

Whether saving is on or off, transcripts are never transmitted anywhere:

- The database contains the session metadata, turn-by-turn exchange text, and
  structured debrief results.
- All data stays on your machine under `~/.convsim/`.
- Nothing in the transcript is transmitted to any server.

To clear all saved transcripts: use **Clear all local data** in **Settings**,
or call `POST /api/privacy/clear` on the local API.

### Raw audio

**Default:** never saved.

The microphone stream is processed in memory by the local speech-to-text
(Whisper) runtime. Raw audio is not written to disk at any point in the default
configuration. Only the transcribed text is passed to the scenario engine.

If you enable the `convsim.privacy.saveRawAudio` developer setting, audio
is written to a local temporary directory for debugging purposes only. This
setting is off by default and should not be enabled in normal use.

### TTS cache

Text-to-speech synthesis is computationally expensive. The app caches
synthesized audio clips locally at `~/.convsim/tts-cache/` to avoid
re-generating the same phrase twice.

- The TTS cache is local only. No audio is sent to external servers.
- Cache files contain synthesized voice output for short NPC phrases.
  They do not contain your voice or any player input.
- To clear the TTS cache, delete the cache directory: `rm -rf ~/.convsim/tts-cache/`.

### Runtime logs

Log files are written to `~/.convsim/logs/` (configurable with the
`CONVSIM_LOG_DIR` environment variable).

What **is** logged:

- Safety events (matched category and action, but **not** the raw player text).
- Session lifecycle events (start, end, ending type).
- Service startup, shutdown, and error events.
- Model inference timing (duration only, no prompts or outputs).

What **is not** logged:

- Raw player text or voice input.
- NPC responses or model outputs.
- The full conversation transcript.
- Any personally identifying information.

Log files are rotated and stored locally only. They are never transmitted.

### Telemetry

**Telemetry is absent from the MVP.**

No usage analytics, session counts, feature-use events, or performance
metrics are sent to any server. There are no background pings and no anonymous
reporting. The settings model carries a `telemetry_enabled` flag that defaults
to off (surfaced read-only under the `privacy` object of the `/api/health`
response), but the MVP ships no telemetry subsystem to act on it — nothing is
transmitted regardless of the flag.

If telemetry is ever added in a future release, it will:

- Require explicit opt-in from the user.
- Be documented here in advance of the release.
- Default to off.

### Crash reports

**No crash reports are transmitted in the MVP.**

If the app crashes, error output is written to the local log at
`~/.convsim/logs/`. Nothing is sent to Sentry, Bugsnag, or any third-party
crash reporting service in the MVP release.

To report a crash, copy the relevant portion of the local log and open a
GitHub issue manually.

### Exports

You can export a single session's transcript and events to a local JSON file
via the UI (**Session → Export**) or via the API:

```
GET /api/sessions/<session_id>/export
```

The export contains:

- Session metadata (scenario ID, start time, ending type, turn count).
- Full turn-by-turn exchange (player input as transcribed text, NPC response).
- Structured debrief results.

Exports are written to wherever you choose to save them. The app does not
transmit exports anywhere.

### Model files

Model weights are stored at `~/.convsim/models/` after you download them
through the in-app model manager. Model files are never uploaded or
synchronized. The model manager only downloads files when you explicitly
request a model.

### Pack files

Installed packs are stored at `~/.convsim/packs/` (for user-installed packs)
or in the repository's `packs/official/` directory. Pack files are never
uploaded or synchronized.

---

## Deletion

### Delete all conversation data

Use the **Clear all local data** button in **Settings**  
or  
```
POST /api/privacy/clear
```

This deletes all rows from the `sessions` and `session_events` tables in
the local SQLite database. It cannot be undone.

### Delete TTS cache

```
rm -rf ~/.convsim/tts-cache/
```

### Delete all local data

To remove everything Conversation Simulator has stored:

```bash
rm -rf ~/.convsim/
```

This removes all transcripts, model files, packs, logs, and cache. After
this, the app will prompt you to reinstall a model on next launch.

---

## Verifying local-only operation

You can confirm that a play session makes no outbound connections using the
built-in offline smoke test:

```bash
# Run against an official pack (no model download needed)
npx convsim offline-smoke-test packs/official/job-interview-basic

# Machine-readable output for CI
npx convsim offline-smoke-test --json packs/official/job-interview-basic
```

**What the test does:**

1. Loads the first scenario from the pack.
2. Runs a scripted conversation with a local fake runtime (no real model
   inference needed).
3. Generates a local debrief.
4. Asserts that no outbound TCP connection was attempted during play.

**Expected output (success):**

```
✓ Offline smoke test passed
  Pack:     job-interview-basic
  Scenario: behavioral-q1
  Turns:    3
  Debrief:  generated
  Network:  no outbound calls detected
```

**Expected output (failure):**

```
✗ Offline smoke test FAILED: outbound network detected during play (1 violation)
  Subsystem: tts
  URL: https://api.example.com/synthesize
  Install a local runtime or check for background telemetry.
```

The command exits nonzero on failure, making it suitable as a CI gate.

The same end-to-end verification runs on every CI build in
`packages/convsim-cli/tests/offline-smoke-test.test.ts`, and the underlying
network-policy guard is unit-tested in
`services/convsim-core/tests/test_network_policy.py`.

---

## Privacy preferences reference

The following preferences are available in **Settings**:

| Preference | Default | Effect |
|---|---|---|
| Save transcripts | On | When on, conversation text is written to the local SQLite database. Turn off to keep nothing after a session ends. |
| Save raw audio | Off | When on (dev setting only), microphone audio is written to a local temp directory. |
| Save TTS cache | On | When off, synthesized audio clips are discarded after each session. |

All preferences are stored locally in the browser's `localStorage` under
the `convsim.privacy.*` namespace. They are never transmitted.

---

## Questions and concerns

If you have a privacy question or believe a data boundary has been violated,
open a GitHub issue with the `privacy` label. If you believe you have found
a security vulnerability, follow the responsible disclosure process described
in [`SECURITY.md`](../SECURITY.md).
