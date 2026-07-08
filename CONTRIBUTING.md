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
- **Package layout:** `apps/web/` (browser UI), `runtimes/desktop/` (Tauri),
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

---

## Pull request checklist

Before opening a PR, confirm every applicable item:

- [ ] All existing tests pass locally (`pnpm test:types`, `python -m pytest`, etc.)
- [ ] New behaviour is covered by new or updated tests
- [ ] Schema changes are validated (`node packages/scenario-schema/tests/validate-schemas.js`)
- [ ] Official packs still validate (`node packages/scenario-schema/tests/validate-packs.js packs/official`)
- [ ] Offline smoke test passes where possible (`bash scripts/smoke-check.sh`)
- [ ] Pack files contain only YAML/JSON — no scripts, executables, or symlinks
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
