---
title: "Contributing"
description: "How to contribute to Conversation Simulator: contribution paths by role, development setup, local CI commands, and the pull request checklist."
sidebar:
  order: 4
---

Conversation Simulator is a local-first, offline-capable conversation practice
tool. Every contribution runs on the contributor's own machine — no cloud
account required.

There are many ways to contribute. Find the path that fits your craft below.

---

## Paths by role

### Scenario writers

The most accessible contribution. Packs are plain YAML files — no build step,
no compilation, no programming experience required.

- **Start here:** [Scenario Authoring](/create/scenario-authoring/) —
  walks through the full workflow: open the Creator Workbench, copy an
  official pack, edit the NPC and scenario, validate, quick-test, and export.
- **Quality bar:** [Official Pack Quality Bar](/create/quality-bar/) —
  what makes a pack ready for the official repository.
- **Validation reference:** [Pack Validation](/create/pack-validation/) —
  error codes and how to fix them.
- **Safety rules:** [Safety Policy](/trust/safety-policy/) —
  content and NPC policies all packs must follow.

To submit an official pack, use the
[Scenario Pack Submission](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/ISSUE_TEMPLATE/scenario_pack_submission.yml)
issue template.

### Local AI hackers

Work on model integration, runtime adapters, the prompt pipeline, or GGUF
loader.

- **Architecture overview:** [Architecture](/reference/architecture/) —
  service topology, turn pipeline, session state machine, WebSocket contract.
- **Runtime adapters:** [Runtime Adapters](/reference/runtime-adapters/) —
  how to add support for a new local model backend.
- **Local models guide:** [Local Models](/play/local-models/) —
  supported formats, download flow, and hardware requirements.
- **Performance:** [Performance](/play/performance/) —
  latency targets and graceful degradation strategy.
- **Entry points in code:** [`services/convsim-core/`](https://github.com/outrightmental/ConversationSimulator/tree/main/services/convsim-core) (FastAPI, Python) and
  [`packages/prompt-composer/`](https://github.com/outrightmental/ConversationSimulator/tree/main/packages/prompt-composer) (prompt construction).

### Frontend developers

The web app is React + TypeScript + Vite. The desktop wrapper is Tauri v2.

- **Architecture overview:** [Architecture](/reference/architecture/)
- **Package layout:** [`apps/web/`](https://github.com/outrightmental/ConversationSimulator/tree/main/apps/web) (browser UI), [`apps/desktop/`](https://github.com/outrightmental/ConversationSimulator/tree/main/apps/desktop) (Tauri),
  [`packages/shared-types/`](https://github.com/outrightmental/ConversationSimulator/tree/main/packages/shared-types) (shared TypeScript types).
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

- **Voice smoke tests:** [Voice Smoke Tests](/dev/voice-smoke-tests/) —
  manual and automated tests for input/output audio paths.
- **Architecture:** the voice stack lives in [`services/convsim-core/`](https://github.com/outrightmental/ConversationSimulator/tree/main/services/convsim-core) under
  the speech provider modules.
- For STT bugs, use the [Speech / STT Issue](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/ISSUE_TEMPLATE/stt_issue.yml)
  template. For TTS bugs, use the [TTS Issue](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/ISSUE_TEMPLATE/tts_issue.yml)
  template.

### Game designers

Work on NPC state machines, scenario events, rubric scoring, and debrief
generation.

- **Full specification:** [SPEC](/reference/spec/) — sections on NPC state
  modelling, scenario events, scoring, and debrief.
- **Schema reference:** [`schemas/`](https://github.com/outrightmental/ConversationSimulator/tree/main/schemas) — JSON Schema definitions for scenarios,
  NPCs, rubrics, safety policies, and pack tests.
- **Example packs:** [`packs/official/`](https://github.com/outrightmental/ConversationSimulator/tree/main/packs/official) — four fully worked packs covering
  interviews, negotiations, language practice, and difficult conversations.

### Safety reviewers

Help maintain the content safety system and review submitted packs.

- **Safety policy:** [Safety Policy](/trust/safety-policy/)
- **Privacy:** [Privacy](/trust/privacy/)
- **Network security:** [Network Security](/trust/network-security/)
- **Report a safety concern:** use the
  [Safety Issue](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/ISSUE_TEMPLATE/safety_issue.yml) template.
  For responsible disclosure, follow [Security](/project/security/).

### Language learners and localization contributors

Contribute scenario packs for additional languages or correct language use in
existing packs.

- **Language Café pack** ([`packs/official/language-cafe/`](https://github.com/outrightmental/ConversationSimulator/tree/main/packs/official/language-cafe)) is the reference
  implementation for multi-language packs.
- Read [Scenario Authoring](/create/scenario-authoring/) and
  [Official Pack Quality Bar](/create/quality-bar/)
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

Full install details: [Developer install](/dev/developer-install/).

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
- [ ] Pack files are data and assets only (YAML/JSON, images, audio, docs) — no executables, scripts, or symlinks
- [ ] New pack files include `license` metadata in `manifest.yaml`
- [ ] `SPDX-License-Identifier` header added to new documentation files
- [ ] NPC characters are clearly fictional (no named real persons)
- [ ] Safety policy YAML present and validator accepts the pack

See the PR template ([`.github/PULL_REQUEST_TEMPLATE.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/PULL_REQUEST_TEMPLATE.md)) — it embeds this
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
- **Security issues:** do **not** use public issues. Follow [Security](/project/security/).
- **Code of conduct concerns:** contact maintainers privately as described in
  the [Code of Conduct](/project/code-of-conduct/).

---

## License

Contributions to documentation and scenario content are accepted under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
Contributions to source code are accepted under the
[Apache 2.0](https://www.apache.org/licenses/LICENSE-2.0) license.
New files must include the appropriate `SPDX-License-Identifier` header.
