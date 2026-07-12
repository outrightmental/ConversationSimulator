---
title: "Pack download & import policy"
description: "How scenario packs reach players — depot-bundled official packs, manual community imports, local-dev loading, and the validation rules applied on import."
sidebar:
  order: 5
---

> **Purpose:** Define how scenario packs reach players — which packs ship in
> the Steam depot, which packs require an explicit download, and how players
> import community or local-development packs.
>
> **Scope:** Conversation Simulator Steam edition and open-source desktop build.
>
> **Compliance cross-references:** CP-01 (executable code in packs), CP-02
> (external URLs), CP-03 (NSFW content), CP-04 (prompt injection) in
> [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md).

---

## Pack categories

| Category | Who creates it | How it reaches the player |
|----------|---------------|--------------------------|
| Official | Outright Mental | Bundled in the Steam depot — no download needed |
| Community | Third-party authors | Manual import by the player (v1); in-app browser deferred to Stage 5 |
| Local-dev | Developer or pack author | Loaded directly from a local filesystem path |

---

## 1. Official packs

### What ships in the depot

All four official scenario packs ship inside the app bundle in every Steam
depot (Windows, macOS, Linux). No download is required after installation.
See [`publishing/STEAM_DEPOT_CONTENTS.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/STEAM_DEPOT_CONTENTS.md)
for the exact path (`resources/packs/` inside the Tauri bundle).

| Pack ID | Title |
|---------|-------|
| `job-interview-basic` | Job Interview Practice |
| `everyday-negotiation` | Everyday Negotiation |
| `language-cafe` | Language Café |
| `difficult-conversations` | Difficult Conversations |

### Updating official packs

Official pack updates ship as part of a new app version — not as standalone
pack downloads. A player receives updated packs automatically when Steam
delivers an app update. There is no separate pack auto-update mechanism in v1.

### Quality gate

All official packs must pass the full quality bar defined in
[`docs/official-pack-quality-bar.md`](/create/quality-bar/) and the pack validation gate
(`convsim validate-pack`) before a release build is tagged. The
`pack-validation` CI job in [`.github/workflows/ci.yml`](https://github.com/outrightmental/ConversationSimulator/blob/main/.github/workflows/ci.yml) enforces this on every
push to `main`.

---

## 2. Community packs

### v1: manual import only

In v1 the app ships **no in-app community pack browser**. Community packs are
distributed outside the app (GitHub releases, itch.io, direct links, etc.) and
installed by the player using the **Settings → Packs → Import pack** flow.

A future Stage 5 milestone may add an in-app browser. Until that milestone is
approved, no network fetch to a community pack index or CDN may be added.

### Import process

1. The player obtains a community pack as a directory or a `.zip` / `.tar.gz`
   archive from an external source.
2. The player opens **Settings → Packs → Import pack** and selects the
   directory or archive.
3. The app validates the pack against the pack schema before installation (see
   [Section 4 — Pack validation on import](#4-pack-validation-on-import)).
4. If validation passes, the pack is copied to `~/.convsim/packs/community/`
   and immediately available from the scenario library.
5. If validation fails, an error is shown listing each failing constraint; the
   pack is not installed.

### No silent community pack downloads

The app never downloads a community pack from a remote URL on behalf of the
player — even if the pack manifest includes a `source_url` field. All
community pack bytes must originate from the player's own filesystem or be
manually transferred by the player.

### Community pack storage

Installed community packs are stored at:

```
~/.convsim/packs/
  community/
    <pack-id>/
      manifest.yaml
      scenarios/
      assets/        (optional)
  local/             (local-dev packs loaded by path, not copied)
```

Community packs are stored separately from official packs so they can be
removed individually without affecting the official bundle.

---

## 3. Local-development packs

### What counts as a local-dev pack

Any directory that contains a valid `manifest.yaml` conforming to
[`schemas/pack.schema.json`](https://github.com/outrightmental/ConversationSimulator/blob/main/schemas/pack.schema.json) may be loaded as a local-dev pack. The pack does
not need to be installed — it can be loaded directly from its source tree.

### Loading a local-dev pack

```sh
# Load by path in the CLI
convsim start --pack /path/to/my-pack

# Or set in the Settings UI: Settings → Packs → Add local path
```

The path is recorded in `~/.convsim/config.yaml` as an entry in
`local_pack_paths`. On startup, the app attempts to load each registered path.
If the directory is missing or fails validation, a warning is shown but the
app continues loading other packs.

### Local-dev packs are not validated at CI level

Local-dev packs are outside the CI validation gate because they exist only on
the developer's machine. A developer loading a deliberately incomplete pack for
iteration purposes should not be blocked by the CI pack-validation job.

---

## 4. Pack validation on import

All packs — official, community, and local-dev — are validated against the
pack schema at load time. The validator enforces the constraints below. A pack
that fails validation is **rejected and not installed**.

### Hard rules (cannot be overridden by any pack)

| Rule | Enforcement |
|------|-------------|
| No `scripts` field in any manifest section | Schema rejects it; pack validator fails if present |
| `allow_external_urls: false` | Packs must not reference external URLs for any asset |
| NSFW content policy cannot be weakened | Global `nsfw_sexual_content: stop` is non-overridable |
| Minors romantic/sexual content — absolute prohibition | Cannot be set to anything other than `stop` |
| Self-harm crisis rule — absolute prohibition | Cannot be weakened; must include resource messaging |

### Soft rules (warnings in official packs, errors in community packs)

| Rule | Enforcement in official | Enforcement in community |
|------|------------------------|-------------------------|
| Missing `version` field | Warning | Error — rejected |
| Missing `license` field | Warning | Error — rejected |
| Asset files referenced in manifest must exist on disk | Warning | Error — rejected |
| NPC `bio` field must not contain injection markers | Warning | Error — rejected |

### Running the validator manually

```sh
# Validate a pack directory
convsim validate-pack /path/to/pack-dir

# Validate all official packs (also runs in CI)
pnpm test:packs
```

---

## 5. Pack licence disclosure

### Official packs

Official packs are distributed under the Apache 2.0 licence and are included
in the Steam depot without separate licence disclosure beyond the `LICENSE` and
`NOTICE` files at the depot root.

### Community packs

The `license` field in a community pack's `manifest.yaml` is shown to the
player in the import confirmation dialog before the pack is installed. If the
field is absent, the import confirmation displays:

> "This pack does not declare a licence. Install it only if you trust the
> source."

The player must confirm before the pack is installed. This disclosure is
informational — the app does not enforce specific licence compatibility between
community packs and the app's own licence.

### Local-dev packs

Local-dev packs are loaded by path without a licence disclosure step (the
developer is assumed to be aware of their own pack's licence).

---

## 6. Removing an installed pack

### Official packs

Official packs cannot be uninstalled individually. They are part of the app
bundle and are removed only when the player uninstalls the app.

### Community packs

The player may remove any installed community pack from **Settings → Packs →
Manage packs → Remove**. This deletes the pack directory from
`~/.convsim/packs/community/`. Any sessions that referenced the removed pack
retain their transcript data in `~/.convsim/db/sessions.db` but will show a
"Pack no longer installed" warning if the player attempts to review scenario
metadata.

### Local-dev packs

Removing a local-dev path from **Settings → Packs → Local paths** de-registers
the path from `~/.convsim/config.yaml`. The pack directory on disk is not
deleted.

---

## 7. Compliance checklist items for packs

From [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) SR-05:

- [ ] Pack validator rejects any pack declaring a `scripts` field.
- [ ] Pack validator rejects any pack setting `allow_external_urls: true`.
- [ ] Safety policy blocks `nsfw_sexual_content` at the input router level.
- [ ] Global non-overridable rules (`minors_romantic_or_sexual`,
  `self_harm_crisis`) cannot be weakened by any pack policy.
- [ ] All four official packs pass `convsim validate-pack` with no warnings.

---

## Links

- [`schemas/pack.schema.json`](https://github.com/outrightmental/ConversationSimulator/blob/main/schemas/pack.schema.json) — pack manifest schema
- [`docs/scenario-authoring.md`](/create/scenario-authoring/) — pack authoring guide
- [`docs/official-pack-quality-bar.md`](/create/quality-bar/) — quality criteria for official packs
- [`docs/pack-validation.md`](/create/pack-validation/) — validator CLI reference
- [`docs/safety-policy.md`](/trust/safety-policy/) — content policy, pack sandboxing, and prohibited categories
- [`publishing/STEAM_DEPOT_CONTENTS.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/STEAM_DEPOT_CONTENTS.md) — what ships in the depot
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](https://github.com/outrightmental/ConversationSimulator/blob/main/publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — risk register (CP-01–CP-04)
- [`packs/official/`](https://github.com/outrightmental/ConversationSimulator/tree/main/packs/official/) — official pack source
