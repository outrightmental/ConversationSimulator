---
title: "Workshop moderation"
description: "The moderation stance, player report path, and technical safety guarantees that apply to all Steam Workshop scenario packs."
sidebar:
  order: 6
---

ConversationSimulator distributes free scenario packs through the Steam Workshop.
This document describes the moderation stance, the report path for players, and
the technical safety guarantees that apply to all Workshop content.

## Content scope

Workshop support is limited to **free, declarative scenario packs**. Paid content
distribution remains outside the Workshop scope (see the
[marketplace architecture](/dev/marketplace-architecture/)).

A scenario pack is a collection of YAML files that describe conversation scenarios,
NPC definitions, rubrics, safety policies, and (optionally) scene metadata.
No code, scripts, or executable content is permitted.

## Pack validation at import

Every Workshop item is processed through the **same two-phase validation pipeline**
used for manual zip import:

1. **Forbidden-content scan** — rejects symlinks, executable file extensions
   (`.exe`, `.bat`, `.sh`, `.js`, `.py`, etc.), and disguised binaries detected
   by magic-byte inspection (ELF, Mach-O, PE, WASM, shebang).

2. **Schema validation** — validates all YAML files against the official
   ConversationSimulator schemas ([`schemas/*.schema.json`](https://github.com/outrightmental/ConversationSimulator/tree/main/schemas)) using the `pack-loader`
   library.

Packs that fail either phase are **quarantined**: they are never imported into the
scenario library, never exposed to players, and a readable rejection reason is
stored locally. The library shows creators which packs were quarantined and why.
Invalid packs **never crash the application**.

## Runtime safety layer

The global safety system ([issue #203](https://github.com/outrightmental/ConversationSimulator/issues/203)) applies to **all** Workshop content identically
to official packs. Safety rules encoded in a pack's `safety/policy.yaml` are
enforced at runtime by the AI layer; they can strengthen the default safety policy
but **cannot override or weaken it**. The safety ceiling set by the application is
non-negotiable and not addressable by pack authors.

## Creator responsibilities

Pack creators agree to the Steam Subscriber Agreement and Steam Workshop Terms of
Service at publication time. By submitting a pack, creators affirm that:

- All content is original or appropriately licensed.
- No executable code, scripts, or binaries are included.
- All NPC characters are clearly fictional (`fictional: true` in the manifest).
- The pack's content rating accurately reflects the scenarios within it.
- The pack does not attempt to subvert the application's safety layer.

## Reporting harmful content

ConversationSimulator does **not** maintain its own Workshop moderation team.
Content that violates the Steam Workshop rules should be reported through
Steam's built-in reporting mechanism:

1. Navigate to the Workshop item's page on the Steam Community.
2. Click the **Report** link in the item's right-hand panel.
3. Select the appropriate violation category (e.g., "Spam or misleading",
   "Stolen content", "Cheats / exploits", or "Sexually explicit content").

Valve reviews reported items and may remove them from the Workshop, which
causes the item to be excluded from future subscription syncs. Items that
are already locally installed will remain on disk until the player unsubscribes;
they will no longer receive updates.

**Urgent safety concerns** (content that threatens harm to real individuals)
should be reported directly to Valve via the
[Steam Support contact form](https://help.steampowered.com/).

## Non-Steam builds

Workshop UI elements are hidden in non-Steam builds (`SteamStatus.is_steam_enabled
=== false`). The manual import path (zip file import) remains available on all
builds and follows the identical validation pipeline.

## Summary of guarantees

| Guarantee | How it is enforced |
|---|---|
| No executable content in packs | Forbidden-content scan at import (extensions + magic bytes) |
| Schema-valid YAML only | AJV 2020 schema validation at import |
| Invalid packs never crash the library | Quarantine system; errors are stored, never thrown to the UI |
| Global safety rules apply to Workshop content | Runtime safety layer ([#203](https://github.com/outrightmental/ConversationSimulator/issues/203)) is non-bypassable |
| Report path for harmful content | Steam's built-in Workshop reporting UI |
| Non-Steam builds unaffected | Workshop UI gated on `is_steam_enabled` |
