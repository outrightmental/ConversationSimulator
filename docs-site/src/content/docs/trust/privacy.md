---
title: "Privacy & your data"
description: "What data Conversation Simulator stores, where it lives on your machine, and how to delete it."
sidebar:
  order: 1
---

Conversation Simulator is designed so that **nothing leaves your computer
during play**. This document explains exactly what data exists, where it is
stored, and how to delete it.

The app sends nothing. The two websites, conversationsimulator.com and
docs.conversationsimulator.com, are a different matter: both count how far
their pages are read, without cookies, and remember a visitor only after a
yes, and conversationsimulator.com also runs Google Analytics, which does
use cookies. [These websites](#these-websites) says exactly what they
collect.

For network-level enforcement of this guarantee, see
[`network-security.md`](/trust/network-security/).  
For content safety policy, see [`safety-policy.md`](/trust/safety-policy/).

---

## The local-first promise

> Conversation Simulator does not send your conversations, audio, prompts,
> transcripts, or model outputs to any server during play. Model and pack
> downloads happen only when you explicitly request them.

This is backed by the code, not just by policy:

- All services bind to `127.0.0.1` by default. No ports are reachable from
  other machines. This is the primary runtime guarantee.
- `convsim_core.network_policy` provides a central guard,
  `require_network(NetworkMode.PLAY)`, that outbound-capable play-mode code
  (LLM, TTS, STT) is required to clear before opening a connection. Setting
  `LOCAL_MODE = True` makes any play-mode attempt raise `NetworkBlockedError`.
  This contract is enforced by the unit tests in
  [`services/convsim-core/tests/test_network_policy.py`](https://github.com/outrightmental/ConversationSimulator/blob/main/services/convsim-core/tests/test_network_policy.py), which run in CI.
- The offline smoke test (see [Verifying local-only operation](#verifying-local-only-operation))
  is the end-to-end check. It installs a socket-level network guard that blocks
  any non-localhost connection during a scripted session and records a violation
  if anything reaches out — so an accidental outbound call fails the test before
  it can ship.

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

### Turn timing

**Default:** recorded locally with the session; deleted with it.

Beside each NPC turn the app keeps one record of what that turn cost: how long
the engine spent reading the prompt and writing the reply, when the first
token arrived, token counts (prompt, reused from cache, written), the engine's
reading and writing speeds, whether a repair call was made, how long speech
synthesis took when voice is on, and which runtime and model produced it. The
model is named by the id the engine was asked for and, when the selected model
served the turn, by the registry id of a model the app installed or the file
name of a model file you supplied yourself. A file path is never stored, so
the record does not say where on your computer a model lives. It contains
**no text** — no prompt, no reply, no player input — only durations and
counts.

The record is stored as a `turn_timing` event in the same local database as
the transcript, so it is deleted with the session, by **Clear all local
data**, and is included in a session export. `GET /api/performance/rolling`
reads the recent records to say how fast replies have been on this machine.
Nothing about it is transmitted anywhere.

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
reporting from the app. (The websites are measured; see
[These websites](#these-websites).) The settings model carries a
`telemetry_enabled` flag that defaults to off (surfaced read-only under the
`privacy` object of the `/api/health` response), but the MVP ships no telemetry subsystem to act on it — nothing is
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
- Every per-turn event, including each NPC turn's timing record (durations
  and token counts only — see [Turn timing](#turn-timing)).

Exports are written to wherever you choose to save them. The app does not
transmit exports anywhere.

### Model files

Model weights are stored at `~/.convsim/models/` after you download them
through the in-app model manager. Model files are never uploaded or
synchronized. The model manager only downloads files when you explicitly
request a model.

### Pack files

Installed packs are stored at `~/.convsim/packs/` (for user-installed packs)
or in the repository's [`packs/official/`](https://github.com/outrightmental/ConversationSimulator/tree/main/packs/official/) directory. Pack files are never
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
[`packages/convsim-cli/tests/offline-smoke-test.test.ts`](https://github.com/outrightmental/ConversationSimulator/blob/main/packages/convsim-cli/tests/offline-smoke-test.test.ts),
and the underlying network-policy guard is unit-tested in
[`services/convsim-core/tests/test_network_policy.py`](https://github.com/outrightmental/ConversationSimulator/blob/main/services/convsim-core/tests/test_network_policy.py).

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

## These websites

Everything above is about the app, which sends nothing. This section is
about the two websites: **conversationsimulator.com** and
**docs.conversationsimulator.com**. Nothing they collect comes from, or
reaches, the app.

Both sites are measured with **Signal**, Outright Mental's own analytics,
which Outright Mental runs itself (`in.signal.outright.io`), with no
analytics company in between. It keeps counts, not records of you.

### How far each page is read, for every visitor

Each page carries a column of tiny invisible images, one every 200 pixels
down the page and one at its foot. Your browser fetches each one from Signal
as you scroll near it, with or without JavaScript. Each request carries the
site, the page's address and how far down the page it sits, and nothing
else: **no cookie, no identifier, nothing stored on your device**. Signal
adds one to a count for that page and that day and keeps nothing else about
the request. It cannot tell one visitor from another.

### Journeys, only if you say yes

On your first visit a small box asks whether this site may remember your
browser, so Outright Mental can see how people find their way between its
sites and games: these two sites, outrightmental.com, nickcharneykaye.com,
and the sites of the studio's other games and products (such as
fevertilt.com, starharvester.com, xjmusic.com and ascendinglark.com).
[Outright Mental's privacy policy](https://outrightmental.com/privacy/)
lists them all.

- **If you say no, or don't answer, nothing more is collected** than the
  page counts above. A browser that sends
  [Global Privacy Control](https://globalprivacycontrol.org/) is treated as
  a no, and is not asked.
- **If you say yes**, the site keeps a random id in its own browser storage
  (`localStorage`, not a cookie) and sends each page view with it. A link
  you follow to another Outright Mental site carries that id in the part of
  the address after `#`, which no server sees, so the next site can join the
  two visits once you say yes there too.
- Nothing that could recognise you is kept as itself: the id is hashed
  with a secret key held only on Signal's servers. Journeys are used to
  learn how people find Outright Mental's work and for nothing else: not
  sold, not shared, not used for advertising. A journey is kept for up to
  760 days after you were last seen, each page view in it for 395 days.
- **Changing your answer to no erases you**, on every Outright Mental site at
  once. Each site keeps its own answer: use **Privacy choices** in the
  footer of conversationsimulator.com, and
  this button for the docs site:
  <button type="button" onclick="if (window.Signal) window.Signal.choices()">Privacy choices for the docs site</button>
- To ask what Signal holds about you, or to have it erased, write to
  [legal@outrightmental.com](mailto:legal@outrightmental.com).

Neither site has a sign-up or mailing-list form today.

### Google Analytics on conversationsimulator.com

The marketing site (not the docs site) also runs Google Analytics 4, which
sets cookies (`_ga`) to tell visits apart and sends page views to Google.
It runs whatever you answer in the box above. Google's
[opt-out browser add-on](https://tools.google.com/dlpage/gaoptout) turns it
off.

---

## Questions and concerns

If you have a privacy question or believe a data boundary has been violated,
open a GitHub issue with the `area:safety` label. If you believe you have found
a security vulnerability, follow the responsible disclosure process described
in [`SECURITY.md`](/project/security/).
