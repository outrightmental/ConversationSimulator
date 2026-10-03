<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Contributing to Conversation Simulator

Conversation Simulator is a local-first, offline-capable conversation practice
tool. Every contribution runs on the contributor's own machine — no cloud
account required.

There are many ways to contribute. Find the path that fits your craft below.

---

## Paths by role

### Scenario writers

The most accessible contribution. Packs are plain YAML files — no build step,
no compilation, no programming experience required.

- **Start here:** [docs/scenario-authoring.md](docs/scenario-authoring.md) —
  walks through the full workflow: open the Creator Workbench, copy an
  official pack, edit the NPC and scenario, validate, quick-test, and export.
- **Quality bar:** [docs/official-pack-quality-bar.md](docs/official-pack-quality-bar.md) —
  what makes a pack ready for the official repository.
- **Validation reference:** [docs/pack-validation.md](docs/pack-validation.md) —
  error codes and how to fix them.
- **Safety rules:** [docs/safety-policy.md](docs/safety-policy.md) —
  content and NPC policies all packs must follow.

To submit an official pack, use the
[Scenario Pack Submission](.github/ISSUE_TEMPLATE/scenario_pack_submission.yml)
issue template.

### Local AI hackers

Work on model integration, runtime adapters, the prompt pipeline, or GGUF
loader.

- **Architecture overview:** [docs/architecture.md](docs/architecture.md) —
  service topology, turn pipeline, session state machine, WebSocket contract.
- **Runtime adapters:** [docs/runtime-adapters.md](docs/runtime-adapters.md) —
  how to add support for a new local model backend.
- **Local models guide:** [docs/local-models.md](docs/local-models.md) —
  supported formats, download flow, and hardware requirements.
- **Performance:** [docs/performance.md](docs/performance.md) —
  latency targets and graceful degradation strategy.
- **Entry points in code:** `services/convsim-core/` (FastAPI, Python) and
  `packages/prompt-composer/` (prompt construction).

### Frontend developers

The web app is React + TypeScript + Vite. The desktop wrapper is Tauri v2.

- **Architecture overview:** [docs/architecture.md](docs/architecture.md)
- **Package layout:** `apps/web/` (browser UI), `apps/desktop/` (Tauri),
  `packages/shared-types/` (shared TypeScript types).
- **Run locally:**

  ```sh
  pnpm install
  pnpm --filter @convsim/web dev
  ```

- **Typecheck:**

  ```sh
  pnpm --filter @convsim/shared-types build
  pnpm --filter @convsim/scenario-schema build
  pnpm --filter @convsim/web typecheck
  ```

- **Tests:**

  ```sh
  pnpm --filter @convsim/web test
  ```

### Speech developers

Work on STT (speech-to-text) or TTS (text-to-speech) integration.

- **Voice smoke tests:** [docs/voice-smoke-tests.md](docs/voice-smoke-tests.md) —
  manual and automated tests for input/output audio paths.
- **Architecture:** the voice stack lives in `services/convsim-core/` under
  the speech provider modules.
- For STT bugs, use the [Speech / STT Issue](.github/ISSUE_TEMPLATE/stt_issue.yml)
  template. For TTS bugs, use the [TTS Issue](.github/ISSUE_TEMPLATE/tts_issue.yml)
  template.

### Game designers

Work on NPC state machines, scenario events, rubric scoring, and debrief
generation.

- **Full specification:** [docs/SPEC.md](docs/SPEC.md) — sections on NPC state
  modelling, scenario events, scoring, and debrief.
- **Schema reference:** `schemas/` — JSON Schema definitions for scenarios,
  NPCs, rubrics, safety policies, and pack tests.
- **Example packs:** `packs/official/` — four fully worked packs covering
  interviews, negotiations, language practice, and difficult conversations.

### Safety reviewers

Help maintain the content safety system and review submitted packs.

- **Safety policy:** [docs/safety-policy.md](docs/safety-policy.md)
- **Privacy:** [docs/privacy.md](docs/privacy.md)
- **Network security:** [docs/network-security.md](docs/network-security.md)
- **Report a safety concern:** use the
  [Safety Issue](.github/ISSUE_TEMPLATE/safety_issue.yml) template.
  For responsible disclosure, follow [SECURITY.md](SECURITY.md).

### Language learners and localization contributors

Contribute scenario packs for additional languages or correct language use in
existing packs.

- **Language Café pack** (`packs/official/language-cafe/`) is the reference
  implementation for multi-language packs.
- Read [docs/scenario-authoring.md](docs/scenario-authoring.md) and
  [docs/official-pack-quality-bar.md](docs/official-pack-quality-bar.md)
  before writing new language-practice scenarios.
- Language packs follow the same submission flow as other packs.

---

## Labels, fields, and milestones

Three systems run the tracker. Each answers exactly one question, and none of them
duplicates another — that non-overlap is the point, and it is enforced:
[.github/project-structure.yml](.github/project-structure.yml) declares the whole
shape of the tracker, and `scripts/project-structure.py validate` fails CI if this
section, the issue forms, or the manifest fall out of step.

### Labels — *where* the work lands

Labels exist for one reason: so the board shows the pie chart of development effort
by product area. There are no type labels and no priority labels, because those are
fields.

| Axis | Labels | Question it answers |
| ---- | ------ | ------------------- |
| Area | `area:engine` · `area:ui` · `area:models` · `area:packs` · `area:safety` · `area:steam` · `area:docs` · `area:infra` | Which product surface does it touch? |
| Workflow | `manual` · `review` · `good first issue` · `help wanted` | Who picks it up, and how |
| Housekeeping | `meta` | Tracker or repo chore that ships no product change |

- Add **one or two** area labels when the surface is clear. Epics span areas by
  design and carry none.
- `manual` and `review` are contracts with the
  [yoke](https://github.com/outrightmental/yoke) orchestrator: `manual` keeps an
  issue or PR out of automated work entirely; `review` lets yoke implement but
  leaves the final PR to a human.
- `good first issue` and `help wanted` mark the community on-ramps — scenario packs
  are the friendliest entry point.
- `meta` is the only escape hatch from the milestone and area rules below. Use it
  for tracker and repository housekeeping, nothing else.

Please do not invent new labels ad hoc. A new label is a change to the manifest, so
propose it in an issue first.

### Fields — *what kind* of work, and *how urgent*

| Field | Where | Values | Question it answers |
| ----- | ----- | ------ | ------------------- |
| Type | Native GitHub issue type | Bug · Feature · Task · Epic | What kind of change is this? |
| Priority | Delivery board single-select | P0 — blocker · P1 — next · P2 — later | P0 blocks the next release; P1 is next up; P2 is opportunistic |
| Phase | Delivery board single-select | 01 · Alpha build … 07 · Future | Which era of the project shipped it? |

Set Type and Priority on every open issue at triage. The factory reads Type — it
takes Bugs first — and Phase is append-only history, not a planning field.

### Milestones — *when* it ships

Milestones are release trains with deadlines, which is what makes velocity readable.
Every open issue belongs to exactly one, unless it is `meta`. The next three:

| Milestone | Due | What it delivers |
| --------- | --- | ---------------- |
| v0.4 — Demo and Next Fest | Oct 31, 2026 | A free demo build in front of players: Next Fest submission, its own client identity, a self-explaining first session |
| v1.0 — Paid launch | Nov 28, 2026 | The $9.99 Steam edition goes live — bundled desktop engine, real-model CI gate, store and DLC registration |
| v1.1 — Post-launch | Jan 16, 2027 | The groomed backlog released to the factory: auto-update, accessibility, performance targets, the UGC on-ramp |

Closed work is attributed to the Phase that shipped it instead — a milestone invented
after the fact has no burndown to show.

### Checking the tracker

```sh
python scripts/project-structure.py validate   # offline — the CI gate
python scripts/project-structure.py audit      # live tracker vs. the manifest
python scripts/project-structure.py apply      # converge the live tracker
```

`audit` and `apply` need the gh CLI authenticated with the `project` scope
(`gh auth refresh -s project`), so they are maintainer commands; `validate` needs
neither network nor credentials and runs in CI on every pull request.

---

## Development setup

```sh
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
./scripts/setup.sh      # macOS / Linux
# scripts\setup.ps1    # Windows PowerShell
./scripts/dev.sh        # start all services
```

Then open **http://127.0.0.1:7354**.

Full install details: [docs/install.md](docs/install.md).

---

## Running CI locally

Every CI job has an equivalent local command. Run these before pushing to
catch failures without waiting for GitHub Actions.

### Smoke check — verify monorepo structure

```sh
bash scripts/smoke-check.sh
```

### Shell script linting

```sh
shellcheck scripts/*.sh
```

### Backend tests

```sh
pip install -e "packages/prompt-composer[dev]"
cd packages/prompt-composer && python -m pytest

pip install -e "services/convsim-core[dev]"
cd services/convsim-core && python -m pytest
```

### Frontend typecheck and tests

```sh
pnpm install
pnpm --filter @convsim/shared-types build
pnpm --filter @convsim/scenario-schema build
pnpm test:types
pnpm --filter @convsim/web typecheck
pnpm --filter @convsim/web test
pnpm --filter @convsim/pack-loader test
pnpm --filter @convsim/cli test
```

### Schema validation

```sh
node packages/scenario-schema/tests/load-schemas.js
node packages/scenario-schema/tests/validate-schemas.js
pnpm --filter @convsim/scenario-schema exec vitest run
```

### Pack validation

```sh
# Schema check
node packages/scenario-schema/tests/validate-packs.js packs/official

# Full policy check (requires convsim-core installed)
pip install -e "services/convsim-core[dev]"
for d in packs/official/*/; do convsim-validate-pack "$d"; done
```

### Project structure

```sh
pip install pyyaml
python scripts/project-structure.py self-test
python scripts/project-structure.py validate
```

### Onboarding e2e suite

The onboarding e2e suite (issue #387) covers the first-run journeys P1–P8
from a wiped profile.  It is a release gate and a required check on PRs
touching the onboarding surface (`apps/web/src/setup/**`, `App.tsx`,
`routers/preflight.py`, `routers/sidecar.py`, and related install services).

**Run locally:**

```sh
pip install -e "packages/prompt-composer[dev]"
pip install -e "services/convsim-core[dev]"

# Fast trio (P1 / P2 / P7) — same as the PR required check, ~1-2 min
python -m pytest \
  e2e/onboarding/test_p1_happy_path.py \
  e2e/onboarding/test_p2_instant_play.py \
  e2e/onboarding/test_p7_regression_loop.py -v

# Full suite P1–P8 — same as the release gate
python -m pytest e2e/onboarding/ -v
```

**Adding a new first-run journey test:**

Every test in `e2e/onboarding/` starts from a wiped profile using the
`fresh_profile` fixture.  Use it as a one-liner:

```python
def test_my_new_journey(fresh_profile):
    client, app = fresh_profile
    # client is a FastAPI TestClient; app exposes app.state.db, app.state.sidecar, etc.
    assert client.get("/api/setup/status").json()["kind"] == "never-run"
```

The `fresh_profile` fixture creates a fresh temporary data directory with no
recorded onboarding outcome, no installed models, and the same environment
variables the Tauri shell sets on a real first-run install.  This ensures every
journey test starts from a genuinely clean slate.

Include the `assert_no_forbidden_in_preflight` and `assert_fix_action_not_welcome`
helpers from `e2e/onboarding/helpers.py` in every new path test so the
forbidden-vocabulary and loop-regression invariants are always active.

**Network allowlist (automatic):**

The `network_allowlist_guard` fixture in `conftest.py` is `autouse`, so every
journey test — existing or new — mechanically enforces the privacy promise: any
socket connection to a non-loopback host fails the test immediately. New path
tests inherit this invariant for free; no per-test call is required.

**Fixture server:**

Tests that exercise model downloads use the `fixture_server` fixture, which
starts a local HTTP server serving a deterministic 64 KB file.  No test depends
on Hugging Face or GitHub availability — the suite passes with networking
disabled except for localhost.

---

## Pull request checklist

Before opening a PR, confirm every applicable item:

- [ ] All existing tests pass locally (`pnpm test:types`, `python -m pytest`, etc.)
- [ ] New behaviour is covered by new or updated tests
- [ ] Schema changes are validated (`node packages/scenario-schema/tests/validate-schemas.js`)
- [ ] Official packs still validate (`node packages/scenario-schema/tests/validate-packs.js packs/official`)
- [ ] Offline smoke test passes where possible (`bash scripts/smoke-check.sh`)
- [ ] Pack files are data and assets only (YAML/JSON, images, audio, docs) — no executables, scripts, or symlinks
- [ ] New pack files include `license` metadata in `manifest.yaml`
- [ ] `SPDX-License-Identifier` header added to new documentation files
- [ ] NPC characters are clearly fictional (no named real persons)
- [ ] Safety policy YAML present and validator accepts the pack

See the PR template (`.github/PULL_REQUEST_TEMPLATE.md`) — it embeds this
checklist.

---

## Commit message style

Use a plain imperative sentence. No conventional-commit prefixes required.

```
Add smoke test for language-cafe pack
Fix STT reconnection loop on silence timeout
Expand rubric scoring docs
```

---

## Maintainers and contact

This project is maintained by the Outright Mental team.

- **GitHub Issues:** use the appropriate issue template for bugs, ideas, and
  submissions.
- **Security issues:** do **not** use public issues. Follow [SECURITY.md](SECURITY.md).
- **Code of conduct concerns:** contact maintainers privately as described in
  [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

## License

Contributions to documentation and scenario content are accepted under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Contributions to source code are accepted under the
[Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) license.
New files must include the appropriate `SPDX-License-Identifier` header.
