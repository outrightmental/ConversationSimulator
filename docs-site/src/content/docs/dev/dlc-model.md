---
title: "DLC model"
description: "How paid premium scenario-pack expansions are produced, shipped as Steam DLC, and unlocked — without any DLC content entering the public open-source repository."
sidebar:
  order: 35
---

> **Purpose:** Define how paid **premium scenario-pack expansions** are produced,
> shipped, and unlocked — without any of their content entering the public,
> open-source repository. This is the contract between the public repo (open core)
> and the private DLC repo (paid content).

## The distribution model in one picture

```
  GitHub (public, open source)          Steam (paid)                Private repo
  ────────────────────────────          ────────────                ───────────────
  ConversationSimulator/                 Base app — $9.99            ConversationSimulator-DLC/
   • engine (Apache-2.0)         ───▶     (packaged build of ───┐     • premium pack YAML
   • 4 official packs (CC BY 4.0)         the open source)      │     • pack art / audio
   • docs, this contract                                        │     • pack-build script
   • DLC ownership integration           Premium DLC packs  ◀───┘  (never merged to public)
   • DLC depot VDF template               (one Steam DLC per        │
                                          expansion pack)   ◀───────┘  built + uploaded from here
```

Three channels, one honest story:

1. **GitHub — free.** The full source builds and runs at zero cost. Nothing here
   is paid or proprietary except the *pointer* to DLC (App IDs, ownership checks).
2. **Steam base app — $9.99.** A packaged build of this same open source. Buying it
   funds development; it does not unlock anything the source build lacks.
3. **Steam DLC — paid, private-sourced.** Premium expansion packs, authored in the
   private repo, sold only as Steam DLC.

**Invariant:** the open core never shrinks. A pack that is free and open today is
never relocked as paid DLC. DLC is only ever *additional* content.

## What lives where

| Artifact | Public repo (`ConversationSimulator`) | Private repo (`ConversationSimulator-DLC`) |
|----------|:---:|:---:|
| Engine, app, official free packs, docs | ✅ | — |
| DLC ownership check (Steamworks integration) | ✅ | — |
| DLC depot VDF template (`steam/depot_dlc_scenariopacks.vdf.tpl`) | ✅ | — |
| Premium pack content (scenarios, NPCs, rubrics, art, audio) | ❌ **never** | ✅ |
| Premium pack build/packaging + Steam upload workflow | — | ✅ |
| DLC App IDs / depot IDs | ✅ (as CI variables, non-secret) | ✅ |

The public repo carries the **contract** — the integration points and the depot
template — but **no DLC content**. The guarantee is *repo separation*: premium pack
content only ever exists in the private repo, so it cannot enter a public commit or
a base depot built from this repo. `.gitignore` guards against a stray local copy
being committed; the CI depot audit catches weights, binaries, and secrets in staged
depots but **cannot itself tell a premium pack from a free one** — both are
declarative YAML + assets — so it is not the control that keeps premium content out.
Keeping that content in the private repo entirely is.

## The private repo: `ConversationSimulator-DLC`

A separate **private** GitHub repository owned by Outright Mental. Its layout mirrors
the public pack layout so packs validate against the same open schemas:

```
ConversationSimulator-DLC/
  packs/
    advanced-professional-skills/     # one directory per premium expansion pack
      manifest.yaml                   # id: com.outrightmental.dlc.advanced_professional_skills
      scenarios/  npcs/  rubrics/  safety/  scenes/
    extended-language-course/
    ...
  scripts/build-dlc-depot.sh          # validates packs + stages Steam depot content
  .github/workflows/dlc-steam-deploy.yml
  STEAM_DLC_REGISTRY.md               # DLC App ID ↔ pack id ↔ depot id mapping
```

Rules for the private repo:

- Every premium pack is **declarative YAML + static assets only** — no executable
  code, exactly like public packs. It must pass `convsim validate-pack` with zero
  errors and the same [safety review](/dev/marketplace-architecture/) as any
  Outright Mental-distributed pack.
- Premium packs carry a **proprietary** license identifier in their manifest, not
  CC BY 4.0. They may not be redistributed outside Steam DLC.
- The private repo consumes the **public** repo's open schemas and validator as a
  dependency; it never forks the engine.

## How a premium pack becomes Steam DLC

Steam models DLC as a separate product (its own **App ID**) tied to the base app,
with its own **depot** for content. For each premium expansion pack:

1. **Register the DLC** in Steamworks: a new DLC App ID and content depot associated
   with the base app. Set its price.
2. **Author + validate** the pack in the private repo.
3. **Build + upload** the DLC depot from the private repo's deploy workflow, using
   the depot VDF template shape defined in the public repo
   (`steam/depot_dlc_scenariopacks.vdf.tpl`), pointed at the DLC depot ID and the
   private pack content.
4. **Install location.** When a player owns and installs the DLC, Steam places its
   content under the DLC depot's install path inside the base app's install
   directory (e.g. `dlc/<dlc_pack_id>/`). The base app discovers premium packs there
   at startup.

DLC content is **excluded from the base app's depots** — the base app never bundles
paid packs. The DLC depot is uploaded separately, only from the private repo.

## How the app unlocks owned DLC

The base app is the same open-source binary for everyone; DLC packs are gated at
runtime by **Steam ownership**, not by shipping different builds.

- **`apps/desktop/src-tauri/src/steam.rs`** — `SteamRuntime::is_dlc_installed(dlc_app_id)`
  wraps `steamworks::Apps::is_dlc_installed(AppId)`. Returns `false` when Steam is
  disabled, not running, or the DLC is not owned.
- **`steam_is_dlc_installed`** Tauri command exposes it to the front end.
- **`apps/web/src/hooks/useSteamDlc.ts`** — resolves to "not owned" outside
  Tauri/Steam, so the open-source browser build behaves identically.
- **Pack library** — owned premium packs load as playable; unowned ones show as
  **available to buy** with a link to the DLC's Steam store page.

Ownership resolution is **offline-friendly**: once Steam has confirmed ownership and
the DLC is installed locally, play needs no network — consistent with the local-first
guarantee. No conversation content, transcript, or DLC-usage event is ever sent to
Steam or any server (see [Steam integration](/dev/steam-integration/)).

## Refunds, safety, and ratings

- **Refunds:** Steam's standard refund policy (2-week / 2-hour window) applies to the
  base game and every DLC. A DLC removed for a content-policy violation triggers a
  refund to all purchasers regardless of the window.
- **Safety:** DLC packs are bound by the same non-overridable safety rules as every
  pack — minors and self-harm crisis content are handled identically and cannot be
  weakened by a paid pack. DLC packs must not exceed the PG-13 cap.
- **Ratings:** base game and all DLC stay within the PG–PG-13 boundaries declared on
  the store page. A DLC that would change the rating requires a fresh IARC review.

## Guardrails (must stay true)

- No premium/DLC pack content is ever committed to the public repository.
- The base app builds and runs fully from open source with **all four official packs
  free**; DLC absence is never an error or a nag beyond a normal "available to buy"
  affordance.
- The DLC ownership check degrades to "not owned" in every non-Steam context.
- No in-app payment UI, Steam Wallet, or microtransaction system — paid content is
  delivered only through Steam's DLC storefront.
