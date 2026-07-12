---
title: "Sample pack: Hello Conversation"
description: "A minimal CC0 sample pack — one scenario, one NPC, one rubric, one safety policy, and one smoke test — for learning the Creator Workbench."
sidebar:
  order: 2
---

A **minimal sample pack** for learning the Creator Workbench. It contains
one scenario, one NPC, one rubric, one safety policy, and one smoke test —
the smallest complete pack that demonstrates every required file type.

The pack lives at [`packs/sample/hello-conversation/`](https://github.com/outrightmental/ConversationSimulator/tree/main/packs/sample/hello-conversation) in the GitHub repository.

**Licence: CC0-1.0 (public domain).** No conditions. Fork it, strip it,
rename everything, and use it as the skeleton for your own pack.

## What is inside

| File | Purpose |
|------|---------|
| `manifest.yaml` | Pack identity, content rating, safety reference, and entry scenario list |
| `scenarios/friendly_introduction.yaml` | The conversation: a networking event introduction |
| `npcs/sam_chen.yaml` | The NPC: Sam Chen, a software developer |
| `rubrics/introduction_rubric.yaml` | Two-dimension scoring rubric |
| `safety/hello_safety.yaml` | G-rated safety policy |
| `tests/smoke_friendly_introduction.yaml` | Smoke test that runs in CI without a model |

## How to use it

**In the Creator Workbench:**

```
1. Navigate to the Creator Workbench (http://127.0.0.1:7354/workbench).
2. Click "Import Pack (.zip)" in the Packs panel.
3. Select a zip of this directory, or paste the folder into packs/local-dev/.
4. The pack appears under Local Dev — click it and start editing.
```

**CLI:**

```sh
# Copy the sample pack into local-dev and start editing
cp -r packs/sample/hello-conversation packs/local-dev/my-new-pack

# Validate your edits
convsim validate-pack packs/local-dev/my-new-pack/

# Run the smoke test
convsim test-pack packs/local-dev/my-new-pack/
```

## Next steps

- [Scenario authoring guide](/create/scenario-authoring/) — full
  step-by-step tutorial that builds a pack from scratch using the Workbench.
- [Pack validation reference](/create/pack-validation/) — error codes,
  smoke tests, golden transcript tests, and CI integration.
- [Official quality bar](/create/quality-bar/) — what
  makes a pack ready to submit as an official pack.
