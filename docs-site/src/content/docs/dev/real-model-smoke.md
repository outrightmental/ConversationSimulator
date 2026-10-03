---
title: "Real-model smoke test (nightly)"
description: "The nightly CI job that plays a scripted conversation on a real local model end-to-end — registry download, llama.cpp, convsim-core, scored debrief — with classified failures and a documented runtime budget."
sidebar:
  order: 13
---

Every other CI job validates Conversation Simulator against the **fake** and
**scripted** runtimes — deterministic stand-ins that need no model download.
That keeps pull requests fast, but it means a whole class of regression is
invisible per-PR: a prompt a real model cannot satisfy, a JSON schema the
adapter mis-serialises, a debrief that generates prose but never a score.

The nightly real-model smoke closes that gap. It plays a scripted conversation
on a **real local model** end-to-end — registry download → llama.cpp →
`convsim-core` → scored debrief — and fails with a classified verdict.

| | |
|---|---|
| Workflow | [`.github/workflows/model-smoke-nightly.yml`](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/workflows/model-smoke-nightly.yml) |
| Harness | [`scripts/nightly-model-smoke.py`](https://github.com/outrightmental/ConversationSimulator/blob/main/scripts/nightly-model-smoke.py) |
| Unit tests (per-PR) | `tests/scripts/test_nightly_model_smoke.py` |
| Schedule | 04:00 UTC daily, plus **Run workflow** (`workflow_dispatch`) |
| Runner | GitHub-hosted `ubuntu-latest`, CPU-only inference |
| Model | registry role `starter` — Qwen3 4B Instruct Q4\_K\_M, ~2.5 GB, Apache-2.0 |
| Runtime budget | **< 30 min** (`timeout-minutes: 30`); the harness self-limits to 20 min |

> Nightly, not per-PR, on purpose: a 2.5 GB download plus ~11 min of CPU-only
> inference cannot sit in the PR path. The fake-runtime counterpart is the
> playthrough in `tests/e2e/test_scripted_playthrough.py` — run at release time
> by `scripts/release-smoke.sh`, not on pull requests — which uses the *same
> scripted player turns*, so the two cover the same conversation shape against
> different runtimes. What *does* run per-PR is this harness's own unit tests.

---

## What the nightly proves

1. The pinned starter model downloads and its bytes match the registry SHA-256.
2. `llama-server` loads the GGUF and `convsim-core` reports
   `runtime_id == "llama_cpp"` — the smoke refuses to run on a fake runtime.
3. A real model drives a multi-turn conversation on the built-in
   `behavioral_interview` scenario, producing NPC turns that satisfy
   `turn-output.schema.json`.
4. The session ends and produces a **scored** debrief: at least one rubric
   dimension scored, a numeric `overall_score` in `[0, 100]`, and a non-empty
   summary. The scores come from the rubric observations the model volunteered
   on each turn, so this asserts the scoring path; the debrief *narrative* is a
   separate model call, and a run where it fell back to the deterministic
   template still passes — with a warning that says so, because the scores are
   unaffected and one unlucky generation must not red the nightly. Recurring
   across nightlies is a regression in the debrief prompt or its schema.
5. End-to-end turn latency stays within the documented budget, scaled for CI
   hardware.

The NPC *opening* line is authored scenario text, not a generation — so the
scripted player turns, not the opening, are what prove the model is working.

If the NPC closes the conversation before the script runs out
(`session_control.continue_session`), the run still passes on the turns it did
play — that is the product working as designed — but it records
`scripted_turns_played` and warns in the step summary, so a green run on one
turn is not mistaken for a green run on three.

---

## Failure classification

A red nightly must be triageable from the job summary alone, so every failure is
attributed to exactly one class, with its own exit code, its own banner in the
log, and a remedy printed next to it:

| Exit | Class | Means | First thing to do |
|---|---|---|---|
| 1 | `budget` | Pipeline worked; latency regressed past the CI ceiling | Compare `measured_ms` in the report artifact against recent nightlies |
| 2 | `download` | Model could not be fetched — network, HTTP, or an empty cache | `python scripts/validate-registry.py --url-check`, then re-run |
| 3 | `checksum` | **SHA-256 drift**: on-disk bytes ≠ `model-registry/registry.yaml` | See [Checksum drift](#checksum-drift) — never relax the check |
| 4 | `runtime` | `llama-server` or `convsim-core` crashed, hung, or returned 5xx — or one of the two ports was already taken, so neither could be started | Read the child stderr tail printed above the banner. A port conflict started no child and so has no tail: the banner carries its own remedy instead, naming the port to free — see [Running it locally](#running-it-locally) |
| 5 | `pipeline` | Servers healthy, but an end-to-end assertion failed | Inspect per-turn `used_fallback` flags in the report artifact — except for an unscored debrief, see [Unscored debrief](#unscored-debrief) |
| 6 | `timeout` | Wall-clock budget exhausted; the failing phase is named | Check `phase_durations_s` before raising the budget |

The distinction that matters most in practice is **2/3 vs 4 vs 5**: a download or
checksum failure says nothing about the app, a runtime failure is a crash, and a
pipeline failure means the model ran and produced output the product rejected.

Anything the harness could not carry out — a `registry.yaml` that is malformed
or names no usable `starter` model, a bad command line, a disk that fills up
mid-run, a bug in the harness itself — is also reported as exit 5, with a
message and a remedy that say so, so that **exit 1 only ever means a latency
regression**. Nothing exits with an unclassified traceback, and nothing borrows
a class's exit code without correcting the advice printed beneath it: a broken
registry entry is *not* exit 2, because `download`'s remedy ends "re-run the
job" and no re-run will repair a file in the repository.

When more than one class could apply, the harness reports the strongest evidence
rather than the symptom the client happened to see:

1. **A crashed child wins.** A dead `convsim-core` reads as `runtime`, not as the
   connection reset it caused downstream.
2. **An exhausted wall clock beats a transport error.** Each request timeout is
   capped to the budget that remains, so the last call before the deadline dies
   client-side and *looks* like an unresponsive server. It is reported as
   `timeout`, whose remedy points at `phase_durations_s`.

Because `timeout` outranks `budget`, a *uniform* slowdown normally surfaces as
exit 6 rather than exit 1: three turns at the 240 s CI ceiling plus a debrief
allowed twice that very nearly fill the 20 min budget, so a ~2x regression
exhausts the clock before the budget phase runs. The class stays `timeout` — the
clock really did run out — but when the turns that *did* complete already have a
median past the ceiling, the verdict says so and names the measurement, so exit 6
is not mistaken for a hang. Exit 1 remains the verdict when the conversation
finishes inside the budget but too slowly.

Each run writes the verdict, failure class, remedy, measured latencies and
per-phase durations to the GitHub **step summary**, and uploads the full JSON
report as the `model-smoke-report` artifact (30-day retention).

### Unscored debrief {#unscored-debrief}

Exit 5 with *"Debrief has no rubric dimension scores"* is the one `pipeline`
failure whose cause is ambiguous from the class alone, so the harness resolves it
for you: each NPC turn's `rubric_observation_count` is recorded in the report
artifact, totalled as `rubric_observations_seen`, and the failure message names
which of the causes below applies.

The debrief's dimension scores are accumulated entirely from
`rubric_observations` that the model volunteers on each NPC turn. Nothing asks
it for them: the built-in `behavioral_interview` scenario defines no rubric, no
prompt layer names any rubric dimensions, and the only hint the model gets is
the bare `rubric_observations` array in the embedded output schema — whose empty
list the schema accepts. The fake runtime always returns `[]`, which is why the
release-time playthrough asserts only that `scores` *is* a dict.

That thin prompt coverage is the standing weakness that makes an unscored
debrief reachable at all. It is *not*, however, the expected outcome: in local
verification against the real starter model — Qwen3 4B Q4\_K\_M, the same pin
the nightly uses, under the turn-output schema — every one of six scripted turns
across two runs volunteered at least one observation, and the debrief scored
three to four dimensions with an `overall_score` near 50. Treat zero
observations as a signal, not as the resting state.

So an unscored debrief means one of three quite different things:

- **`rubric_observations_seen` is 0 — the model volunteered nothing.** Only the
  prompt's bare schema hint was ever asking, so this is reachable by design —
  but since the starter model does normally answer that hint, first check what
  changed about what reaches the model: the `OUTPUT_SCHEMA` prompt layer, the
  registry's `starter` pin, the adapter's JSON-schema constraint, sampling
  settings. Then fix the weakness itself in the product (give the turn prompt a
  rubric layer, or play a scenario that defines one), not by relaxing the
  assertion.
- **`rubric_observations_seen` is above 0 — a real regression.** The turns
  returned observations and the debrief scored none of them, so the model did
  its part. The debrief engine does not score the validated observations the
  turn pipeline handed it: `_parse_rubric_observations` in
  `services/convsim-core/.../debrief_engine.py` re-reads each NPC turn's *stored
  raw model output* with a plain `json.loads`, so output that needed repair — or
  that arrived pre-parsed from the runtime adapter — loses its observations on
  the way to the debrief. Compare `raw_npc_output` from the `/debug` payload
  against the per-turn `rubric_observation_count` in the artifact.
- **`rubric_observations_seen` is `null` — the harness could not tell.** The NPC
  turn payloads carried no readable `rubric_observations` list, so the per-turn
  `rubric_observation_count` is `null` too and the message quotes both causes
  above rather than picking one. `convsim-core` always sends that list today, so
  this is itself worth chasing: the turn response contract changed. The harness
  deliberately does not score an unreadable payload as zero — that would have
  the verdict name the one cause it has no evidence for.

In every case the run is red: *"scored debrief"* is the acceptance criterion for
[#457](https://github.com/outrightmental/ConversationSimulator/issues/457).
No cause is a reason to weaken the check — the first is worth a tracking
issue for the missing rubric prompt layer *and* an investigation of the run that
hit it.

---

## Runtime budget

Target: **under 30 minutes on a standard GitHub-hosted runner.** The job sets
`timeout-minutes: 30` as a hard ceiling, and the harness runs with
`--wall-clock-budget-s 1200` (20 min) so *it* fails first and names the phase
that ran long — a GitHub-side timeout would only say "the operation was
canceled".

The 10-minute gap between the two is not slack. `timeout-minutes` covers the
whole job, and the harness only starts after checkout, three `pip install`
steps, the cache restore and — on a cache miss — a 2.5 GB download *and* the
cache save that follows it: up to ~9 min that the harness's own clock never
sees. A 25 min harness budget would lose the race to the job timeout on exactly
the cold-cache nights where an attributed verdict matters most.

On `ubuntu-latest` (CPU-only, 4B Q4\_K\_M):

| Phase | Cold cache | Warm cache |
|---|---|---|
| Checkout + `setup-python` | ~1 min | ~1 min |
| `pip install` (prompt-composer, convsim-core, llama-cpp-python wheel) | ~2 min | ~2 min |
| Model download (2.5 GB from Hugging Face) | ~2 min | — |
| SHA-256 verification | ~1 min (×2) | ~0.5 min |
| Cache save (2.5 GB) | ~1 min | — |
| `llama-server` model load | ~0.5 min | ~0.5 min |
| Authored opening + 3 scripted turns † | ~7 min | ~7 min |
| Debrief generation † | ~4 min | ~4 min |
| **Total** | **~19 min** | **~15 min** |

† The download, verification, cache and model-load rows are measured. The two
inference rows are *projected* from the only latency this job has measured so
far — ~116 s for a single behavioral-interview turn (see below) — because the
multi-turn conversation and the debrief have never run on a runner. Replace them
with the real `phase_durations_s` from the first green nightly's report artifact.

The model is cached between runs under the key
`model-gguf-v1-<registry-sha256>`, so the download only recurs when the registry
pin changes. Cache *restore* and *save* are separate steps and the save is gated
on `success()`, so a file that fails verification is never written to the cache.

If the smoke step creeps past ~15 min — or the job past ~25 min — shorten
`SCRIPTED_PLAYER_TURNS` rather than raising either ceiling: a nightly that
routinely runs near its timeout flaps.

### Latency budget on CI hardware

CPU-only CI hardware is far slower than the mid-spec reference machine the
product budgets target ([Performance and hardware tiers](/play/performance/)), so the harness
scales the documented budget:

```
CI ceiling = documented budget × CI_HARDWARE_FACTOR × REGRESSION_TOLERANCE
           = 10 000 ms        × 20                 × 1.20   = 240 000 ms
```

`CI_HARDWARE_FACTOR` (20) is calibrated empirically: a full behavioral-interview
turn on this runner measures ~116 s, i.e. ~11.6× the 10 s documented budget. The
factor leaves roughly 2× headroom so runner-to-runner variance does not flap the
nightly, while a genuine >2× regression still fails. The headline
`full_response_ms` is the **median** of the scripted turns, so one unlucky turn
cannot flap the job either.

This factor models CI slowness only — the product's 10 s target-hardware budget
is unchanged. Re-measure and re-tune it if the runner class or the starter model
changes.

`session_start_ms` and `debrief_ms` are measured and reported but **not**
budget-checked: the NPC opening is authored text rather than inference, and
debrief generation has no documented SLO.

---

## Checksum drift

The checksum is verified in two places: right after a fresh download, and again
at the start of every run (including cache hits) before the weights are loaded.
A cache hit with drifted bytes therefore fails loudly instead of silently
feeding a corrupt model to the smoke.

Exit 3 means one of two things:

- **The pinned upstream file was replaced.** All registry URLs are pinned to a
  specific Hugging Face revision, so this should not happen silently — if it
  did, review the new file and re-pin with `scripts/pin-model.py`.
- **The cached download is corrupt or truncated.** The harness deletes the bad
  local file, but Actions cache entries are immutable, so a poisoned entry would
  be restored again on the next run. Delete it
  (`gh cache delete model-gguf-v1-<sha>`) or bump `MODEL_CACHE_PREFIX` in the
  workflow.

Never "fix" a drift by updating the expected hash to whatever is on disk — that
is exactly the check this job exists to perform.

---

## Running it locally

You need the starter model on disk and `llama-cpp-python[server]` installed.
Nothing here touches the network except the one-time model download.

```bash
# 1. Install the harness dependencies
pip install -e "packages/prompt-composer[dev]"
pip install -e "services/convsim-core[dev]"
pip install "llama-cpp-python[server]" \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu

# 2. Resolve the starter model's id / url / sha256 from the registry
python scripts/nightly-model-smoke.py --print-registry-model starter

# 3. Download it (~2.5 GB) into ~/.convsim/models/llm/, verifying the checksum
python scripts/nightly-model-smoke.py --download-only \
  --model-id qwen3-4b-instruct-q4_k_m \
  --model-url "<model_url from step 2>" \
  --model-sha256 "<model_sha256 from step 2>"

# 4. Run the smoke. --ci-hardware-factor 1 holds your machine to the real
#    product budget; use 20 to reproduce what CI accepts.
python scripts/nightly-model-smoke.py \
  --model-id qwen3-4b-instruct-q4_k_m \
  --model-sha256 "<model_sha256 from step 2>" \
  --ci-hardware-factor 1 \
  --report-path /tmp/smoke-report.json
```

Useful extras:

- `--verify-only` — re-verify an already-downloaded model and exit.
- `--models-dir <dir>` — look for `<model-id>.gguf` somewhere other than
  `~/.convsim/models/llm/`.
- `--wall-clock-budget-s` — the self-imposed deadline (default 1200 s).

The harness binds `llama-server` on port 7356 and `convsim-core` on port 7399,
and refuses to start (exit 4) if either is already taken. That is deliberate
rather than fussy: readiness is a URL poll, so a server the harness did not
start would answer it, the child that lost the bind would die unnoticed, and the
run would report a **pass** for a model it never checksum-verified. Stop whatever
owns the port — do not work around it.

To exercise the harness's own logic without a model:

```bash
python -m pytest tests/scripts/ -v
```

---

## Privacy

The conversation is 100 % scripted (`SCRIPTED_PLAYER_TURNS` in the harness) and
contains no user data, so short NPC excerpts are printed to the log and recorded
in the report artifact — they are the evidence that a real model, rather than a
canned fallback, drove the conversation. Sessions are created with
`save_transcript: false`, so no transcript file is written, and `convsim-core`
runs against a throwaway data directory that is deleted when the run ends.

---

## Related

- [Offline smoke tests](/dev/offline-smoke-tests/) — proves no cloud service is
  contacted during play (fake runtime, per-PR).
- [Voice smoke tests](/dev/voice-smoke-tests/) — STT/TTS sidecar checks.
- [Performance and hardware tiers](/play/performance/) — where the latency budgets
  come from.
- [Release checklist](/dev/release-checklist/) — Part F covers manual real-model
  verification of a packaged build.
