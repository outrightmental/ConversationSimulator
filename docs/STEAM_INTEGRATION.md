<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Steam Integration

> **Purpose:** Developer reference for the optional Steam API bridge built into
> the Tauri desktop app. Covers the feature-flag model, Steam Cloud exclusions,
> achievements / stats / rich presence configuration, and graceful fallback
> behaviour when Steam is absent.
>
> **Audience:** Platform engineers implementing or modifying the Steamworks
> integration in `apps/desktop/src-tauri/src/steam.rs` and the corresponding
> React hooks. See [`docs/steam-achievements-stats-rich-presence.md`](steam-achievements-stats-rich-presence.md)
> for the Steamworks portal configuration companion (what to enter in App Admin).
>
> **Privacy guarantee:** No conversation content, transcript text, audio, or
> session details are ever transmitted to Steam. Only aggregate integer counts
> and generic activity tokens are sent — and only when the Steamworks SDK is
> active and the player is inside Steam. This is enforced by the integration
> design, not just policy.

---

## Feature flag and build variants

The Steam integration is compiled in only when the `steam` Cargo feature is
enabled. Enabling the feature links the `steamworks` crate and activates the
`SteamRuntime` implementation.

```toml
# apps/desktop/src-tauri/Cargo.toml
[features]
steam = ["steamworks"]
```

### Build variants

| Build command | Steam SDK | Use case |
|---------------|-----------|----------|
| `cargo tauri build` | Not linked | Standard open-source build; Steam features are no-ops |
| `cargo tauri build --features steam` | Linked | Steam depot build; full integration active when Steam is running |

The open-source release and the Steam depot release are compiled from the same
source. Enabling the `steam` feature in the Steam depot build is the only
structural difference between the two.

### Testing with Steam App ID 480

Valve's test App ID `480` (Spacewar) can be used for local integration testing
without registering the production App ID.

```bash
# Start the Tauri dev server with the Steam feature and the test App ID.
SteamAppId=480 cargo tauri dev --features steam
```

The real App ID is embedded in the depot build by the release workflow via
`STEAM_APPID` in `tauri.conf.json`. Do not hardcode the production App ID in
source files — use the variable substitution in the VDF templates and the
workflow environment.

---

## Steam API bridge

The bridge consists of:

1. **`apps/desktop/src-tauri/src/steam.rs`** — Rust module that wraps the
   `steamworks` crate. Contains the `SteamRuntime` struct, all Tauri command
   handlers, and the graceful-fallback logic.
2. **`useSteamAchievements`** React hook — front-end wrapper that invokes the
   Tauri `steam_unlock_achievement` and `steam_increment_stat` commands.
3. **`useSteamRichPresence`** React hook — front-end wrapper that invokes the
   Tauri `steam_set_rich_presence` command.

### Tauri commands

| Command | Arguments | Effect when Steam active | Effect when Steam absent |
|---------|-----------|--------------------------|--------------------------|
| `steam_unlock_achievement` | `name: String` | Calls `steamworks::UserStats::achievement(name).set()` then `store_stats()` | Returns `false`, no-op |
| `steam_increment_stat` | `name: String` | Reads current value, increments by 1, calls `store_stats()` | Returns `false`, no-op |
| `steam_set_rich_presence` | `key: String, value: String` | Calls `steamworks::Friends::set_rich_presence(key, value)` | Returns `false`, no-op |

Commands can be called freely without checking whether Steam is available.
The `SteamRuntime` managed-state object absorbs all failures silently.

### `SteamRuntime` managed state

`SteamRuntime` is registered as a Tauri managed state object in `lib.rs`:

```rust
// apps/desktop/src-tauri/src/lib.rs
use crate::steam::SteamRuntime;

tauri::Builder::default()
    .manage(SteamRuntime::new())
    ...
```

`SteamRuntime::new()` attempts `steamworks::Client::init()`. If init fails for
any reason — Steam not running, `steam` feature disabled, wrong App ID, SDK
missing — the runtime stores a `None` client and all subsequent commands return
`false` immediately without logging errors.

---

## Steam Cloud exclusions

Steam Cloud is configured in the Steamworks partner portal to sync only the
non-sensitive settings file. The integration is documented in detail in
[`publishing/STEAM_APP_REGISTRATION.md` — Steam Cloud configuration](../publishing/STEAM_APP_REGISTRATION.md#steam-cloud-configuration).

### How exclusions are enforced (two layers)

**Layer 1 — Steamworks portal exclusion patterns**

The authoritative exclusion list is in the Steamworks App Admin → Steam Cloud
configuration. Every data subdirectory (`db/`, `logs/`, `models/`, `packs/`,
`exports/`, `cache/`, `crashes/`, `data/`) is excluded with recursive patterns.
Only `steam_cloud_settings.json` is included.

**Layer 2 — `.nosteamcloudpath` sentinel files**

The app writes a `.nosteamcloudpath` file to each data subdirectory on first
launch. This sentinel file tells the Steam client not to sync its directory
even if the portal configuration changes or is misconfigured. The sentinel
files are created by `convsim_core/paths.py` at the `ensure_data_dirs()` call.

### `steam_cloud_settings.json` schema

This is the only file allowed to reach Steam Cloud. Its purpose is to carry
non-sensitive UI preferences across the player's machines.

```json
{
  "schema_version": 1,
  "display_theme": "system",
  "last_used_model_id": "qwen3-4b-q4_k_m",
  "ui_layout": {}
}
```

Fields that may **never** appear in this file:
- Conversation text, prompts, or transcript excerpts
- Session IDs, session history, or session scores
- NPC names or scenario identifiers beyond the model preference
- Audio data of any kind
- Personal or identifying information

If a field is added to `steam_cloud_settings.json`, it must be reviewed for
privacy impact before the feature is merged. The gate G4-04 in
[`docs/steam-mvp-scope.md`](steam-mvp-scope.md) requires explicit sign-off
from the platform team on any new synced field.

### Verifying the Steam Cloud configuration

After configuring Steam Cloud in the Steamworks portal, verify with the
**B.11 Steam Cloud sync verification** steps in
[`docs/release-checklist.md`](release-checklist.md).

---

## Achievements

Full Steamworks portal configuration (App Admin → Achievements tab) is in
[`docs/steam-achievements-stats-rich-presence.md`](steam-achievements-stats-rich-presence.md).

This section covers the integration points.

### Defined achievements

| Display name | Enum | API name | Unlock event |
|---|---|---|---|
| First Scenario | `SteamAchievement::FIRST_SCENARIO` | `ACH_FIRST_SCENARIO` | Session ends or is manually ended |
| First Debrief | `SteamAchievement::FIRST_DEBRIEF` | `ACH_FIRST_DEBRIEF` | Debrief screen rendered |
| Practice Streak | `SteamAchievement::PRACTICE_STREAK` | `ACH_PRACTICE_STREAK` | 3 consecutive calendar days with completed sessions |
| Pack Explorer | `SteamAchievement::PACK_EXPLORER` | `ACH_PACK_EXPLORER` | Session completed from 3+ distinct packs |
| Creator First Validate | `SteamAchievement::CREATOR_FIRST_VALIDATE` | `ACH_CREATOR_FIRST_VALIDATE` | Creator workbench validates first custom pack |

### Unlock call pattern

```typescript
// apps/web/src/hooks/useSteamAchievements.ts
const { unlock } = useSteamAchievements()

// Called at the debrief screen boundary
unlock(SteamAchievement.FIRST_SCENARIO)
```

The hook resolves to a no-op when `window.__TAURI__` is absent (browser context)
or when the Tauri command returns `false` (Steam not running).

Achievement unlock is **idempotent** — calling `unlock` on an already-unlocked
achievement is silently ignored by the Steamworks API.

---

## Stats

Full Steamworks portal configuration is in
[`docs/steam-achievements-stats-rich-presence.md`](steam-achievements-stats-rich-presence.md).

### Defined stats

| Display name | Enum | API name | Increment event |
|---|---|---|---|
| Scenarios Completed | `SteamStat::SCENARIOS_COMPLETED` | `STAT_SCENARIOS_COMPLETED` | Session ends |
| Debriefs Generated | `SteamStat::DEBRIEFS_GENERATED` | `STAT_DEBRIEFS_GENERATED` | Debrief screen displayed |
| Packs Validated | `SteamStat::PACKS_VALIDATED` | `STAT_PACKS_VALIDATED` | Creator workbench validates a pack |
| Text Mode Sessions | `SteamStat::TEXT_MODE_SESSIONS` | `STAT_TEXT_MODE_SESSIONS` | Session starts in text mode |
| Voice Mode Sessions | `SteamStat::VOICE_MODE_SESSIONS` | `STAT_VOICE_MODE_SESSIONS` | Session starts in voice mode |

All stats are **INT** type, **monotonically increasing**, and **count-only**.
A stat value reveals how many times an event occurred — nothing about the
content of the event.

### Increment call pattern

```typescript
const { incrementStat } = useSteamAchievements()

// Called when the session-start API returns success
incrementStat(SteamStat.TEXT_MODE_SESSIONS)
```

---

## Rich presence

Full Steamworks portal configuration (including the `richpresence.vdf`
localization file) is in
[`docs/steam-achievements-stats-rich-presence.md`](steam-achievements-stats-rich-presence.md).

### Defined tokens

| Token | Display string | Set when |
|-------|---------------|----------|
| `#AtMainMenu` | `Browsing scenarios` | `screens/Home` and `screens/ScenarioLibrary` mount |
| `#InScenario` | `In a practice scenario` | `screens/Conversation` mounts |
| `#ReviewingDebrief` | `Reviewing a debrief` | `screens/Debrief` mounts |
| `#EditingPack` | `Editing a scenario pack` | `screens/CreatorWorkbench` mounts |

Tokens are **category labels only**. No scenario title, NPC name, turn count,
or any content from the conversation is transmitted to Steam.

### Set call pattern

```typescript
const { setPresence } = useSteamRichPresence()

// Called in screens/Conversation.tsx's useEffect
setPresence(SteamActivity.IN_SCENARIO)
```

The `steam_display` key is the only key used. Valve uses the
`#<token>` value to look up the localized string from the uploaded
`richpresence.vdf` file.

---

## Graceful fallback outside Steam

Every integration point degrades gracefully when Steam is absent. The
fallback layers are:

| Layer | Condition | Behaviour |
|-------|-----------|-----------|
| Cargo feature disabled | `steam` feature not in build | `SteamRuntime` stubs compile to instant no-ops at zero runtime cost |
| Feature enabled but `Client::init()` fails | Steam not running, wrong App ID, SDK unavailable | `SteamRuntime` stores `None` client; all commands return `false` |
| Tauri context absent | App running in browser (not Tauri shell) | Hooks check `window.__TAURI__`; calls are skipped entirely |
| Command returns `false` | Any of the above | Caller receives `false`; no retry, no error UI shown |

The application functions identically whether Steam is present or not. No UI
state, no feature gate, no error message is conditioned on Steam availability.
This is a deliberate product decision: the Steam integration is additive, not
structural.

---

## End-to-end test

Run this manual test before the Stage 4 public release gate to confirm the
integration is wired correctly:

```bash
# Start the app with the test App ID and the steam feature enabled.
SteamAppId=480 cargo tauri dev --features steam
```

1. Open Steam in the background (must be logged in).
2. Launch the Tauri dev app.
3. Navigate to a scenario and complete it. Confirm the Steam overlay shows the
   `ACH_FIRST_SCENARIO` unlock notification.
4. Open the Debrief screen. Confirm `ACH_FIRST_DEBRIEF` notification appears.
5. Navigate to the Creator Workbench. Confirm rich presence changes to
   `"Editing a scenario pack"` in the Steam friends list.
6. Confirm no session title, NPC name, or turn content appears in any
   Steam-facing string.

Also run with Steam closed to confirm the no-op fallback: all three actions
above must complete without any error, console warning, or UI change.

---

## Checklist

Use this checklist at the Stage 4 gate:

- [ ] All five achievements created in App Admin with correct API names and icon pairs.
- [ ] Hidden flag set on `ACH_PRACTICE_STREAK` and `ACH_PACK_EXPLORER`.
- [ ] All five stats created as INT type.
- [ ] Rich presence localization file uploaded for English (at minimum).
- [ ] End-to-end test above completed with Steam running: achievements, stats,
      and rich presence all fire correctly.
- [ ] End-to-end test completed with Steam closed: no errors, no UI changes.
- [ ] Steam Cloud configured in Steamworks portal — only `steam_cloud_settings.json`
      included; all data subdirectories excluded.
- [ ] B.11 Steam Cloud sync verification steps in `docs/release-checklist.md`
      completed and passing.
- [ ] Confirmed no session content appears in any Steam-facing string.

---

## Links

- [`apps/desktop/src-tauri/src/steam.rs`](../apps/desktop/src-tauri/src/steam.rs) — Rust Steam bridge implementation
- [`docs/steam-achievements-stats-rich-presence.md`](steam-achievements-stats-rich-presence.md) — Steamworks portal configuration: achievements, stats, rich presence
- [`publishing/STEAM_APP_REGISTRATION.md`](../publishing/STEAM_APP_REGISTRATION.md) — Steam Cloud quota, root paths, and exclusion patterns
- [`docs/privacy.md`](privacy.md) — local-first data handling; base privacy policy
- [`docs/steam-mvp-scope.md`](steam-mvp-scope.md) — Stage 4 gate criteria (G4-04 covers synced-field sign-off)
- [`docs/release-checklist.md`](release-checklist.md) — B.11 Steam Cloud sync verification
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — privacy risks PR-01 through PR-03
