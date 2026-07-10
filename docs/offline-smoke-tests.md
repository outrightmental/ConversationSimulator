<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Offline smoke tests

Conversation Simulator is designed to run entirely on-device during play.
The offline smoke test harness verifies this promise: it installs a network
guard that intercepts all outbound TCP connections and confirms that no cloud
service (LLM inference, STT, TTS, telemetry, CDN) is contacted while a
scripted session runs.

---

## CI path (automatic — mock runtime, no model required)

Every pull request runs two explicit CI steps:

| CI step | What it covers |
|---|---|
| **Run offline smoke tests (mock runtime)** | Loads all four official packs, plays scripted turns with the fake runtime, confirms no network violations. Also validates all golden transcript fixtures. |
| **Run CLI unit tests** | CLI argument parsing and command dispatch. |

These run automatically on every PR and merge to `main`.  No hardware or model
downloads are needed.

---

## Local path (mock runtime — no model required)

Run from the repo root after installing dependencies:

```bash
pnpm install --frozen-lockfile
pnpm --filter @convsim/shared-types build
pnpm --filter @convsim/scenario-schema build

# All offline smoke tests + golden transcript tests:
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
