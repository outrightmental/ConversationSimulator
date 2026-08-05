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
steam = ["dep:steamworks"]

[dependencies]
steamworks = { version = "0.11", optional = true }
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
   `steamworks` crate. Contains the `SteamRuntime` struct (with the
   `unlock_achievement`, `increment_stat`, and `set_rich_presence` methods) and
   the graceful-fallback logic. The `#[tauri::command]` handlers that expose
   these methods to the front end live in `apps/desktop/src-tauri/src/lib.rs`.
2. **`useSteamAchievements`** React hook — front-end wrapper that invokes the
   Tauri `steam_unlock_achievement` and `steam_increment_stat` commands.
3. **`useSteamRichPresence`** React hook — front-end wrapper that invokes the
   Tauri `steam_set_rich_presence` command.

### Tauri commands

| Command | Arguments | Effect when Steam active | Effect when Steam absent |
|---------|-----------|--------------------------|--------------------------|
| `steam_unlock_achievement` | `name: String` | Calls `steamworks::UserStats::achievement(name).set()` then `store_stats()` | Returns `false`, no-op |
| `steam_increment_stat` | `name: String` | Reads current value, increments by 1, calls `store_stats()` | Returns `false`, no-op |
| `steam_set_rich_presence` | `value: String` | Calls `steamworks::Friends::set_rich_presence("steam_display", Some(value))` — the key is fixed internally | Returns `false`, no-op |
| `steam_activate_overlay` | — | Calls `steamworks::Friends::activate_game_overlay("")` to open the overlay (the Shift+Tab chord). See [Steam overlay (Windows WebView2 caveat)](#steam-overlay-windows-webview2-caveat) | Returns `false`, no-op |
| `steam_is_dlc_installed` | `dlc_app_id: u32` | Calls `steamworks::Apps::is_dlc_installed(AppId)` — reports whether the player owns and installed that premium DLC | Returns `false`, treated as not-owned |

Commands can be called freely without checking whether Steam is available.
The `SteamRuntime` managed-state object absorbs all failures silently.

### `SteamRuntime` managed state

`SteamRuntime` is constructed once by `steam::init()` during `setup()` and
registered as a Tauri managed state object in `lib.rs`, wrapped in an
`Arc<Mutex<…>>` newtype (`SteamRuntimeState`) so the command handlers can share it:

```rust
// apps/desktop/src-tauri/src/lib.rs
let (steam_status_val, steam_runtime_val) = steam::init();
let steam_runtime = Arc::new(Mutex::new(steam_runtime_val));

tauri::Builder::default()
    .manage(SteamRuntimeState(Arc::clone(&steam_runtime)))
    ...
```

`steam::init()` attempts `steamworks::Client::init()`. If init fails for
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
files are written by the FastAPI app lifespan hook in
`services/convsim-core/convsim_core/app.py`, which touches a
`.nosteamcloudpath` marker in each data subdirectory on startup. The exclusion
semantics are documented in `services/convsim-core/convsim_core/steam_cloud.py`.

### `steam_cloud_settings.json` schema

This is the only file allowed to reach Steam Cloud. It carries a small set of
non-sensitive preferences so a second machine can pick up where the last one
left off. The schema is the `CloudSettings` model in
[`services/convsim-core/convsim_core/steam_cloud.py`](../services/convsim-core/convsim_core/steam_cloud.py);
today it holds a single field:

```json
{
  "last_model_id": "qwen3-4b-q4_k_m"
}
```

`last_model_id` pre-selects the same model on a new device. It must be an
opaque model identifier — a `field_validator` in `CloudSettings` rejects any
value containing a path separator on both write and read, so a filesystem path
(which could leak a username or home directory) can never reach the cloud file.

The `docs/steam-mvp-scope.md` sync scope also permits display preferences and
UI layout state as future additions, but only `last_model_id` is synced today.
Any new field must be added to `CloudSettings` and reviewed for privacy impact
before it ships.

Fields that may **never** appear in this file:
- Conversation text, prompts, or transcript excerpts
- Session IDs, session history, or session scores
- NPC names or scenario identifiers beyond the model preference
- Audio data of any kind
- Personal or identifying information

The authoritative sync scope is
the **Steam Cloud sync for non-sensitive settings** row in
[`docs/steam-mvp-scope.md`](steam-mvp-scope.md) (display preferences,
last-used model ID, UI layout state only — transcripts, model weights, audio
files, and session history must never sync), and the privacy risks PR-01
through PR-03 in
[`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md).

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

## DLC ownership (premium scenario packs)

Premium scenario-pack expansions ship as **paid Steam DLC**; their content is
authored in the private `ConversationSimulator-DLC` repository and is never in this
public repo. The full private-repo → Steam-DLC contract is in
[`docs/DLC_MODEL.md`](DLC_MODEL.md). This section covers only the integration point.

The base app is the **same open-source binary for everyone**. Premium packs are
gated purely by Steam ownership, checked at runtime:

- **`SteamRuntime::is_dlc_installed(dlc_app_id)`** in `steam.rs` wraps
  `steamworks::Apps::is_dlc_installed(AppId)`. It returns `false` when the `steam`
  feature is off, Steam is not running, or the player does not own the DLC.
- The **`steam_is_dlc_installed`** Tauri command exposes it to the front end.
- The **`useSteamDlc`** hook (`apps/web/src/hooks/useSteamDlc.ts`) exposes
  `isDlcInstalled(dlcAppId)` and `isDlcInstalledForPack(packId)` (the latter resolves
  the pack's DLC App ID from the build-time `DLC_REGISTRY`, populated from
  `STEAM_DLC_APP_IDS`). Both resolve to "not owned" in any non-Tauri / non-Steam
  context, so the open-source and browser builds treat every premium pack as
  available-to-buy without special-casing.

Privacy: the ownership check reads local Steam state only. No DLC-usage event,
pack identifier, or conversation content is transmitted to Steam or any server —
consistent with the local-first guarantee above. Once a DLC is owned and installed,
playing it requires no network.

```typescript
// apps/web/src/hooks/useSteamDlc.ts
const { isDlcInstalledForPack } = useSteamDlc()
const owned = await isDlcInstalledForPack(packId)   // false outside Steam / when unowned
// owned packs load and show as playable; unowned show as "available to buy"
```

---

## Steam overlay (Windows WebView2 caveat)

The Steam overlay is the `G3-03` release gate. On a Tauri app it does **not**
work the way it does on a native game, and — critically — **it fails in a way
that looks like success**. Read this before signing off G3-03 on Windows.

### Root cause

Steam draws its overlay by injecting `gameoverlayrenderer64.dll` into the game
process and hooking the graphics API's `Present` call, compositing the overlay
into the frame the game is about to show. A Tauri app never creates a swapchain
in its own process: the UI is rendered by **WebView2 in separate
`msedgewebview2.exe` processes** and composited through DWM. Steam's hook finds
nothing to draw into, so the overlay has no surface. This is the same class of
problem that makes Electron games pass `--in-process-gpu`.

There are two independent failures, and both must be fixed:

1. **The Shift+Tab chord never reaches Steam.** Steam opens the overlay by
   catching Shift+Tab in the game process via an input hook. In a Tauri app the
   keystroke lands in the WebView2 process, which Steam's hook never sees, so the
   default chord is a silent no-op.
2. **The overlay has nothing to render into** (the swapchain problem above), so
   even once opened it is not visible on Windows.

### Why this is dangerous: every Steamworks signal says success

When the overlay is activated on a Tauri app, Steam still reports success on
every channel that a tester would check:

- the friends list shows the player as **"In-Game"**;
- `is_overlay_enabled()` returns **true**;
- `GameOverlayActivated` **fires**.

Only the *visible* overlay is missing. A tester following the G3-03 wording
("Shift+Tab opens and closes without breaking the app or the current session")
sees no crash and no session disruption, so the honest report is an ambiguous
"nothing happened" rather than a clear FAIL. **Do not treat "no crash" as a pass
on Windows.** See the G3-03 pass criterion in
[`docs/steam-mvp-scope.md`](steam-mvp-scope.md) and the QA step in
[`docs/QA_STEAM_PLATFORM_MATRIX.md`](QA_STEAM_PLATFORM_MATRIX.md), which now
require the overlay to be *visibly composited over the app* on Windows.

### The fix has two halves

**Half 1 — chord forwarding (implemented, all platforms).** The front-end
`useSteamOverlay` hook (`apps/web/src/hooks/useSteamOverlay.ts`) listens for
Shift+Tab in the webview and forwards it to the `steam_activate_overlay` Tauri
command, which calls `steamworks::Friends::activate_game_overlay("")`. This is
the portable half and is required on every platform — without it the chord is
dead even when a compositing surface exists. It only repurposes Shift+Tab when
`get_steam_status().is_steam_enabled` is true, so the standard reverse-tab
keyboard affordance is untouched in the browser and non-Steam builds.

**Half 2 — decoy compositing surface (Windows only, not yet vendored).** For the
overlay to be *visible* on Windows, the app must give Steam's injected layer
something to composite into: a **transparent, click-through, borderless child
window** covering the main window, with a **wgpu swapchain presenting empty
frames at vsync**. Steam composites the overlay, notifications, and toasts into
those frames at `Present` time; the app stays visible through every untouched
pixel. This is Win32 + wgpu native code and is intentionally **not** committed
here yet — it needs verification on real Steam-launched Windows hardware before
it ships. An MIT-licensed extraction that implements exactly this surface (with
**no `steamworks` dependency** — the app owns SDK init and the callback pump and
forwards one callback, so there is no version coupling) is available for
integration:

- Plugin: <https://github.com/PSG-Team/tauri-steam-overlay-surface>
- Context and demo: issue #444 (outside-contributor finding; verified on a real
  Steam build across open/close/alt-tab cycles and 1920×1080 → 2560×1440 →
  5120×1440 including live resolution switches and fullscreen↔windowed).

### Known limitation and a trap not to fall into

- **Alt-tab deafness (Windows).** After alt-tabbing away and back, the Shift+Tab
  forwarder is deaf until the user clicks the page once, because Windows
  reactivates the native window without returning keyboard focus to the webview.
- **Do NOT "fix" it with `webview.set_focus()`** in the Rust focus handlers.
  Shipping exactly that was reported to kill Shift+Tab entirely, even on a fresh
  launch (reverted). `useSteamOverlay` deliberately contains no focus workaround.

### Platform scope

The compositing surface is **Windows only**. It does nothing for the macOS and
Linux legs, where overlay-over-webview is a separate and largely unsolved
problem. So Half 1 + the surface closes **one third of G3-03** (the Windows leg),
not the whole gate.

### Compatibility data wanted

Overlay behaviour is GPU- and driver-sensitive, and the surface's verification
sample so far is small (hybrid-GPU laptops are the least-tested case). When
testing G3-03 on Windows, record GPU, Windows build, and whether the surface
came up in [`docs/QA_STEAM_PLATFORM_MATRIX.md`](QA_STEAM_PLATFORM_MATRIX.md).

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
- [`docs/steam-mvp-scope.md`](steam-mvp-scope.md) — release gates and the authoritative Steam Cloud sync scope (non-sensitive settings only)
- [`docs/release-checklist.md`](release-checklist.md) — B.11 Steam Cloud sync verification
- [`publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md`](../publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md) — privacy risks PR-01 through PR-03
