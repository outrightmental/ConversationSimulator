<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Contributing to Conversation Simulator

> **Status:** Early-stage. The skeleton is in place and CI is running.
> Broader contribution guidelines will be written once the first simulation
> milestone lands and the codebase is open for external contribution.

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

### Backend tests — convsim-core (FastAPI service)

```sh
pip install -e "services/convsim-core[dev]"
cd services/convsim-core && python -m pytest
```

### Backend tests — prompt-composer

```sh
pip install -e "packages/prompt-composer[dev]"
cd packages/prompt-composer && python -m pytest
```

### Frontend — typecheck shared packages

```sh
pnpm install
pnpm test:types
```

### Frontend — typecheck web app

```sh
pnpm install
pnpm --filter @convsim/shared-types build
pnpm --filter @convsim/scenario-schema build
pnpm --filter @convsim/web typecheck
```

### Frontend — run web tests

```sh
pnpm install
pnpm --filter @convsim/web test
```

### Schema load tests

```sh
node packages/scenario-schema/tests/load-schemas.js
```

### Pack validation

No pack validator exists yet. This CI job is a placeholder for the quality
gate that will validate scenario packs once a validator is implemented.

---

## Contributing a scenario pack

Scenario packs are the most accessible way to contribute. A pack is a
folder of YAML files — no code, no build step, no compilation.

- **Tutorial:** [docs/scenario-authoring.md](docs/scenario-authoring.md) —
  walks through the full workflow: open the Creator Workbench, copy an
  official pack, edit the NPC and scenario, validate, quick-test, export,
  and share.
- **Quality bar:** [docs/official-pack-quality-bar.md](docs/official-pack-quality-bar.md) —
  what makes a pack ready for the official repository, including the
  contribution checklist and submission review rubric.
- **Validation reference:** [docs/pack-validation.md](docs/pack-validation.md) —
  full list of validator error codes and how to fix them.

Before opening a pull request for a new pack, run both commands locally and
confirm both exit `0`:

```sh
convsim validate-pack packs/official/my-pack/
convsim test-pack packs/official/my-pack/
```

---

## For now

If you want to contribute ideas or report issues, please use
[GitHub Issues](https://github.com/outrightmental/ConversationSimulator/issues).

## Coming soon

This file will cover:

- How to set up a local development environment
- Code style and commit message conventions
- Pull request review process
- How to report security issues (see [SECURITY.md](SECURITY.md))
