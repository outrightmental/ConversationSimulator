---
title: "Offline smoke tests"
description: "How to run the offline smoke test harness that verifies no cloud service is contacted during play, in CI, locally, and with real models."
sidebar:
  order: 11
---

Conversation Simulator is designed to run entirely on-device during play.
The offline smoke test harness verifies this promise: it installs a network
guard that intercepts all outbound TCP connections and confirms that no cloud
service (LLM inference, STT, TTS, telemetry, CDN) is contacted while a
scripted session runs.

---

## CI path (automatic — mock runtime, no model required)

Every pull request runs several explicit CI steps:

| CI step | What it covers |
|---|---|
| **Run offline smoke tests (mock runtime)** | Loads all four official packs, plays scripted turns with the fake runtime, confirms no network violations (TypeScript/TCP guard). Also validates all golden transcript fixtures. |
| **Run CLI unit tests** | CLI argument parsing and command dispatch. |
| **Run acceptance tests** | Full player text-path journey including `TestNoCloudInference` (LOCAL_MODE=True guard). |
| **Run network guard acceptance tests** | Six explicit guard scenarios under a socket-level guard + `LOCAL_MODE`: text-only gameplay+debrief+export (G-1), STT-enabled audio upload (G-2), TTS-enabled synthesis (G-3), pack import and play (G-4), explicit-download always permitted (G-5), and a socket-guard self-test (G-6). |

These run automatically on every PR and merge to `main`.  No hardware or model
downloads are needed.

---

## Local path (mock runtime — no model required)

Run from the repo root after installing dependencies:

```bash
pnpm install --frozen-lockfile
pnpm --filter @convsim/shared-types build
pnpm --filter @convsim/scenario-schema build

# All offline smoke tests + golden transcript tests (TypeScript, TCP-level guard):
pnpm --filter @convsim/cli exec vitest run tests/offline-smoke-test.test.ts tests/runner.test.ts

# Or run everything in the CLI package:
pnpm --filter @convsim/cli test
```

A pass produces output like:

```
✓ offline-smoke-test — official packs > passes for the first official pack (job-interview-basic)
✓ offline-smoke-test — official packs > passes for the difficult-conversations pack
✓ offline-smoke-test — official packs > passes for the everyday-negotiation pack
✓ offline-smoke-test — official packs > passes for the language-cafe pack
✓ golden — job-interview-basic smoke test > passes all fixtures with the fake runtime
...
```

### Python acceptance tests (multi-path guard)

Run the network guard acceptance tests to verify STT, TTS, debrief, and pack-import
paths all complete without outbound calls.  Each guarded scenario runs under a
socket-level guard (patches `socket.socket.connect`/`connect_ex`) **and**
`LOCAL_MODE = True`, so any outbound connection to a non-loopback host is both
recorded and blocked:

```bash
pip install -e "packages/prompt-composer[dev]"
pip install -e "services/convsim-core[dev]"

# All acceptance tests (includes G-1 through G-6 guard scenarios):
python -m pytest tests/acceptance/ -v

# Network guard tests only:
python -m pytest tests/acceptance/test_network_guard.py -v
```

| Guard scenario | What is tested |
|---|---|
| **G-1** Text-only | create → start → turn → end → debrief → transcript export |
| **G-2** STT-enabled | health check → audio upload → turn submitted as text → end |
| **G-3** TTS-enabled | turn → NPC utterance synthesised to local WAV → debrief |
| **G-4** Pack import | zip import → scenario listed → session created and played |
| **G-5** Explicit-download | `NetworkMode.EXPLICIT_DOWNLOAD` always passes through LOCAL_MODE |
| **G-6** Guard self-test | socket guard actually blocks + records a non-loopback connection, permits loopback, and restores cleanly |

---

## CLI path (real pack directory)

After building the CLI (`pnpm --filter @convsim/cli build`):

```bash
# Run against a single pack directory:
node packages/convsim-cli/dist/index.js offline-smoke-test packs/official/job-interview-basic

# Machine-readable JSON output (useful for attaching to a report):
node packages/convsim-cli/dist/index.js offline-smoke-test --json packs/official/job-interview-basic
```

Successful output (human):

```
✓ Offline smoke test passed
  Pack:     official.job_interview_basic
  Scenario: behavioral_interview
  Turns:    3
  Debrief:  generated
  Network:  no outbound calls detected
```

Successful output (JSON):

```json
{
  "status": "ok",
  "pack_id": "official.job_interview_basic",
  "scenario_id": "behavioral_interview",
  "turns_played": 3,
  "debrief_generated": true,
  "network_violations": []
}
```

Exit codes: `0` = pass, `1` = network violation or pack error, `3` = unexpected error.

---

## Local path (real model verification — optional)

To verify that the installed llama.cpp or Ollama runtime makes no *unexpected*
outbound calls, run the smoke test while the real runtime is active.

### 1. Start the local runtime

```bash
# llama.cpp sidecar (see docs/runtime-adapters.md for setup):
./scripts/dev.sh

# Or Ollama:
ollama serve
```

### 2. Run the offline smoke test against the live server

The CLI smoke test uses the fake runtime internally (it does not contact your
running server), so it is still valid as a no-network check.  To verify that
the *server* makes no outbound calls during a real session, use the Python
acceptance test with `LOCAL_MODE=True`:

```bash
# From repo root, with both packages installed:
pip install -e "packages/prompt-composer[dev]"
pip install -e "services/convsim-core[dev]"

python -m pytest tests/acceptance/test_player_text_path.py::TestNoCloudInference -v
```

This starts the FastAPI app with the fake runtime, enables `LOCAL_MODE`, runs a
full session (start → two turns → end), and asserts that no `NetworkBlockedError`
was raised.

---

## Beta tester guide: running and attaching sanitized results

### Prerequisites

- Node.js 20 and pnpm 9 installed
- Repo cloned and dependencies installed (`pnpm install --frozen-lockfile`)
- Packages built (`pnpm --filter @convsim/shared-types build && pnpm --filter @convsim/scenario-schema build && pnpm --filter @convsim/cli build`)

### Step 1 — Run the smoke test for all official packs

```bash
for pack in packs/official/*/; do
  echo "--- $pack ---"
  node packages/convsim-cli/dist/index.js offline-smoke-test --json "$pack"
done
```

### Step 2 — Capture output to a file

```bash
for pack in packs/official/*/; do
  pack_name=$(basename "$pack")
  node packages/convsim-cli/dist/index.js offline-smoke-test --json "$pack" \
    > "/tmp/smoke-${pack_name}.json" 2>&1
  echo "$pack_name: exit $?"
done
```

This writes one JSON file per pack to `/tmp/`.

### Step 3 — Sanitize results before sharing

The JSON output contains only:

- `status` — `ok`, `network_violation`, or `error`
- `pack_id` — the pack identifier (e.g. `official.job_interview_basic`)
- `scenario_id` — the first scenario in the pack
- `turns_played` — number of scripted turns completed
- `debrief_generated` — boolean
- `network_violations` — array of `{ url, subsystem }` objects (empty when `status` is `ok`)

No conversation content, player text, session IDs, or personal information is
included.  The output is safe to share as-is.

If a `network_violation` is reported, the `url` field contains the intercepted
address.  Review it before sharing in case it contains a locally-configured
hostname that you do not want public.

### Step 4 — Attach to the beta feedback issue

Attach the `/tmp/smoke-*.json` files to the relevant GitHub issue or email them
to the beta coordinator.  Include your platform (`uname -a` output or OS version)
and Node.js version (`node --version`).

### Expected result for a correctly installed build

All four official packs should report `"status": "ok"` with `"network_violations": []`.
Any `network_violation` result is a regression and should be reported immediately.

---

## How the network guard works

### TypeScript / Node.js (CLI guard)

The guard patches `net.Socket.prototype.connect` — the lowest-level hook in
Node.js's network stack.  Every HTTP, HTTPS, and `fetch()` call eventually calls
this function to open a TCP connection.  The patch checks whether the target host
is `localhost` / `127.0.0.1` / `::1` and, if not, records a violation and emits
an error on the socket instead of connecting.

This approach catches:
- Direct `http` / `https` requests
- Node's built-in `fetch` (undici)
- Any third-party HTTP client that uses `net.Socket`

It does **not** prevent connections to other local processes (e.g. the llama.cpp
sidecar listening on `127.0.0.1:8080`), which are intentional during real play.

### Python / FastAPI (socket guard + policy gate)

The Python acceptance tests enforce the local-only promise with **two**
independent guards, both active for the entire guarded-client lifetime:

1. **Socket-level guard** — the acceptance-test fixture patches
   `socket.socket.connect` and `socket.socket.connect_ex` (the Python analogue
   of the TypeScript `net.Socket.prototype.connect` hook).  Any connection to a
   non-loopback host is recorded and blocked with `OutboundNetworkAttempt`,
   regardless of whether the calling code went through the policy gate.  This
   catches accidental cloud calls made by a stray `requests`/`httpx`/`urllib`
   dependency on any play, debrief, transcript, telemetry, or crash path.  The
   `G-6` self-test proves the guard is not a silent no-op.
2. **Policy gate** — `convsim_core.network_policy`.  Play-mode code that would
   contact a remote service must call `require_network(NetworkMode.PLAY)` before
   opening a connection.  With `LOCAL_MODE = True` that call raises
   `NetworkBlockedError` immediately, giving a labelled, defence-in-depth signal
   at the exact call site.

User-initiated downloads (model files, pack bundles) use
`require_network(NetworkMode.EXPLICIT_DOWNLOAD)`, which always passes through
regardless of `LOCAL_MODE`.  (The socket guard is only installed inside the
acceptance-test fixture, so it never interferes with real explicit downloads.)

---

## Known limitations

| Limitation | Why | Workaround |
|---|---|---|
| The TypeScript TCP guard cannot intercept Rust/C process syscalls. | The Tauri shell and llama.cpp sidecar are native processes — `net.Socket.prototype.connect` only covers the Node.js process. | Run `lsof -i` during a manual session to check sidecar outbound activity. |
| The Python socket guard cannot intercept native-process (Rust/C) syscalls. | Like the TypeScript guard, `socket.socket.connect` only covers the Python process — the Tauri shell and whisper.cpp / Kokoro sidecars are separate native processes. | Run `lsof -i` during a manual session; see "Manual verification with real voice workers" below. |
| The `LOCAL_MODE` policy gate only fires when call sites explicitly invoke `require_network(PLAY)`. | A call site that skips the gate produces no labelled `NetworkBlockedError`. | The socket-level guard still records and blocks the actual outbound connection, so the leak is caught regardless — the policy gate just adds a precise, labelled signal on top. |
| Fake workers (FakeSttWorker, FakeTtsWorker) are used in CI. | Real whisper.cpp and Kokoro binaries are not available in the CI environment. | See "Manual verification with real voice workers" below for how to test with real models. |
| Mic capture and VAD hardware cannot be tested at the API level. | Microphone input requires a physical device and browser permission. | Tested manually as part of the beta sign-off checklist. |
| WebSocket session paths are not covered by the acceptance tests. | FastAPI `TestClient` does not exercise the WebSocket session endpoint. | The WebSocket handler delegates to the same turn pipeline as the REST endpoint; REST coverage is sufficient for the network policy ratchet. |

---

## Manual verification with real voice workers

To verify the complete voice pipeline (whisper.cpp STT + Kokoro TTS) makes no
unexpected outbound network calls during a real session:

### 1. Install and start the voice workers

Follow the [runtime adapters guide](/reference/runtime-adapters/) to install whisper.cpp and Kokoro, then start
the full service stack:

```bash
./scripts/dev.sh
```

### 2. Run the Python network guard tests against the real workers

```bash
CONVSIM_STT_WORKER_ID=whisper_cpp CONVSIM_TTS_WORKER_ID=kokoro \
  python -m pytest tests/acceptance/test_network_guard.py -v
```

The guard test fixture wires `LOCAL_MODE = True` for the entire test client
lifetime.  Any attempt by whisper.cpp or Kokoro to contact a remote server
during a test session will raise `NetworkBlockedError` — but both are
expected to pass, since they process audio locally.

### 3. Record and report results

Capture output to a file:

```bash
CONVSIM_STT_WORKER_ID=whisper_cpp CONVSIM_TTS_WORKER_ID=kokoro \
  python -m pytest tests/acceptance/test_network_guard.py -v \
  > /tmp/network-guard-$(uname -m).txt 2>&1
echo "Exit: $?"
```

Attach `/tmp/network-guard-*.txt` to the beta feedback issue along with your
OS, Python version (`python --version`), and whisper.cpp / Kokoro versions.
