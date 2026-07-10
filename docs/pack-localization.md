# Pack content localization strategy

## Overview

Conversation Simulator has two independent locale axes:

| Axis | Owner | Storage |
|------|-------|---------|
| **UI locale** | User preference | `localStorage` (`convsim.locale`) |
| **Pack content locale** | Pack author declaration | Pack schema (`locale` field) |

Changing the UI language does not change the language of pack content, and vice versa. A user may run the German UI while playing an English-language business-negotiation pack, or run the English UI while playing a Spanish-language immersion pack.

## Pack locale declaration

Every pack declares its content language in `pack.yaml` (or `pack.json`):

```yaml
# pack.yaml
locale: en          # BCP 47 language tag
# ... rest of pack metadata
```

The `locale` field is a required BCP 47 language tag (e.g. `en`, `de`, `es`, `zh-TW`). Pack validation rejects packs that omit this field.

A pack with `locale: de` contains German-language scenario text, NPC lines, and scoring rubrics. The app renders that content as-is; no machine translation is applied automatically.

## Multi-locale packs (future)

A single pack may bundle multiple content locales by providing sibling scenario directories:

```
my-pack/
  pack.yaml          # declares supported_locales: [en, de, es]
  scenarios/
    en/
      negotiate.yaml
    de/
      negotiate.yaml
    es/
      negotiate.yaml
```

When a multi-locale pack is loaded, the app selects the scenario directory whose locale tag most closely matches `navigator.language` (BCP 47 best-fit matching), falling back to the pack's primary `locale` if no match is found. This behavior is not yet implemented — packs currently ship a single locale.

## UI locale independence

The i18n framework (`apps/web/src/i18n/`) controls only the shell UI strings: navigation labels, error messages, settings headings, debrief section titles, and similar chrome. It does not translate or modify pack content at runtime.

This design means:
- Pack authors do not need to know which UI locale the user has selected.
- UI translators do not need access to pack content.
- A new UI locale can be shipped without touching any pack.
- A new pack locale can be shipped without touching the UI string catalog.

## Scenario browser filtering

The scenario library UI exposes a content locale filter so users can find packs that match the language they want to practice or be challenged in. The filter reads the `locale` field from each installed pack's manifest. Packs with `locale: de` appear under the German content filter even when the user's UI locale is `en`.

## Authoring guidance

When creating a pack:

1. Set `locale` to the BCP 47 tag for the **content** language (the language NPCs speak and players are expected to respond in).
2. Write all scenario YAML strings in that language: `name`, `description`, `npc_persona`, turn scripts, scoring rubric labels.
3. Do not hard-code UI-layer strings (e.g. "Settings", "Export") inside pack content — those strings are owned by the i18n catalog.
4. If the same scenario should be available in multiple languages, create separate scenario files per locale directory rather than mixing languages within a single scenario file.

## Adding a new UI locale

To ship a new UI locale (e.g. Spanish):

1. Add the BCP 47 tag to `SUPPORTED_LOCALES` in `apps/web/src/i18n/index.tsx`.
2. Create `apps/web/src/i18n/locales/es.ts` implementing the `LocaleMessages` type exported from `en.ts`. TypeScript enforces completeness: the build fails if any key is missing.
3. Add a `LOCALE_DISPLAY_NAMES` entry in `apps/web/src/screens/Settings.tsx` (native name, e.g. `'Español'`).
4. Run `pnpm --filter @convsim/web check-i18n` and `pnpm --filter @convsim/web test` to confirm no regressions.

The `LocaleMessages` type is derived directly from the English catalog via `typeof en`, so any new key added to `en.ts` automatically becomes a required field in every other locale file.
