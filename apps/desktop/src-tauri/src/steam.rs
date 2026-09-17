// SPDX-License-Identifier: Apache-2.0
//
// Thin Steam integration bridge. Safe to use on non-Steam builds: all paths
// that require the SDK are gated behind the `steam` Cargo feature, and all
// paths that require Steam to be running are guarded by runtime checks.

use serde::Serialize;

/// Valve's Spacewar sample app-id (480). Useful for local SDK testing without
/// a real Steam app registration:
///   SteamAppId=480 cargo tauri dev --features steam
pub const SPACEWAR_APP_ID: u32 = 480;

// ── Achievement API names ─────────────────────────────────────────────────────
//
// These must match the API names configured in the Steamworks App Admin portal
// (Achievements tab). See docs/steam-achievements-stats-rich-presence.md for
// the full configuration guide and all required Steamworks settings.

pub mod achievements {
    pub const FIRST_SCENARIO: &str = "ACH_FIRST_SCENARIO";
    pub const FIRST_DEBRIEF: &str = "ACH_FIRST_DEBRIEF";
    pub const PRACTICE_STREAK: &str = "ACH_PRACTICE_STREAK";
    pub const PACK_EXPLORER: &str = "ACH_PACK_EXPLORER";
    pub const CREATOR_FIRST_VALIDATE: &str = "ACH_CREATOR_FIRST_VALIDATE";
}

// ── Stat API names ────────────────────────────────────────────────────────────
//
// Integer stats only. No session content, transcript text, or personally
// identifiable information is ever stored in Steam stats — only aggregate
// counts safe to appear on a player's Steam profile.

pub mod stats {
    pub const SCENARIOS_COMPLETED: &str = "STAT_SCENARIOS_COMPLETED";
    pub const DEBRIEFS_GENERATED: &str = "STAT_DEBRIEFS_GENERATED";
    pub const PACKS_VALIDATED: &str = "STAT_PACKS_VALIDATED";
    pub const TEXT_MODE_SESSIONS: &str = "STAT_TEXT_MODE_SESSIONS";
    pub const VOICE_MODE_SESSIONS: &str = "STAT_VOICE_MODE_SESSIONS";
}

// ── Rich presence ─────────────────────────────────────────────────────────────
//
// Reveals only generic activity — never session details, scenario names,
// transcript excerpts, or NPC identifiers. Tokens match the Steamworks rich
// presence localization file (see docs/steam-achievements-stats-rich-presence.md).

pub mod rich_presence {
    /// The rich presence key written for every state update.
    pub const KEY: &str = "steam_display";
    /// Player is mid-conversation with an NPC.
    pub const IN_SCENARIO: &str = "#InScenario";
    /// Player is reading the debrief screen.
    pub const REVIEWING_DEBRIEF: &str = "#ReviewingDebrief";
    /// Player is in the creator workbench.
    pub const EDITING_PACK: &str = "#EditingPack";
    /// Player is on the home / scenario library screen.
    pub const AT_MAIN_MENU: &str = "#AtMainMenu";
}

// ── DLC ownership ─────────────────────────────────────────────────────────────
//
// DLC App IDs are not hard-coded here; they are resolved at build time from the
// VITE_STEAM_DLC_APP_IDS build variable (set via the STEAM_DLC_APP_IDS
// repository variable).  The open-source repo therefore contains no live Valve
// App IDs — the pack layer reads `dlc_registry_from_env()` to map pack IDs to
// their corresponding DLC App IDs.

pub mod dlc {
    // Intentionally empty: live DLC App IDs are not committed to the public
    // repository.  Use `dlc_registry_from_env()` to load them at build time
    // from the STEAM_DLC_APP_IDS repository variable.
}

// ── Workshop UGC ──────────────────────────────────────────────────────────────

pub mod workshop {
    /// Steamworks tag applied to all scenario packs published via the in-app
    /// Creator Workbench. Allows Workshop search to filter ConversationSimulator
    /// content without requiring a dedicated Community Hub query.
    pub const PACK_TAG: &str = "scenario-pack";
}

/// Metadata for a single Steam Workshop item the local user is subscribed to.
///
/// Fields are populated from synchronous UGC API calls; no async query is
/// required for the subscribe-sync flow. The `title` and `author_name` are
/// populated after the pack has been imported (from its validated manifest).
#[derive(Clone, Debug, Default, Serialize)]
pub struct WorkshopItem {
    /// Workshop item ID serialised as a decimal string to avoid JS precision
    /// loss on 64-bit integers larger than `Number.MAX_SAFE_INTEGER`.
    pub item_id: String,
    /// Absolute path to the locally installed item content directory, or an
    /// empty string when the item has not yet been downloaded by Steam.
    pub install_path: String,
    /// Whether the locally installed version is behind the current Workshop
    /// version. The app should re-sync and re-validate when `true`.
    pub needs_update: bool,
    /// Unix timestamp (seconds) of the last Workshop update to this item.
    pub updated_at: u32,
}

// ── Status payload sent to the front-end ──────────────────────────────────────

/// Snapshot of the Steam integration state.
/// `null` fields indicate information that is unavailable in the current
/// environment (e.g. running outside Steam, or the `steam` feature is off).
#[derive(Clone, Debug, Default, Serialize)]
pub struct SteamStatus {
    /// `true` only when the Steamworks SDK was successfully initialized.
    /// Always `false` when the `steam` Cargo feature is disabled.
    pub is_steam_enabled: bool,

    /// `true` when the process was launched by the Steam client, detected via
    /// the `SteamAppId` / `SteamGameId` environment variables that Steam sets
    /// before exec-ing the game binary.  Reliable even without the SDK.
    pub launched_by_steam: bool,

    /// Steam AppID, from the SDK (preferred) or environment variable fallback.
    pub app_id: Option<u32>,

    /// Display name (persona name) of the current Steam user.
    /// Requires a successful SDK initialization.
    pub persona_name: Option<String>,
}

/// Diagnostic readout for the Steam overlay — the G3-03 release gate
/// (docs/STEAM_INTEGRATION.md, "Steam overlay"). Every field is `false`/`null`
/// outside Steam or when the `steam` Cargo feature is disabled.
///
/// Read it as: `overlay_enabled && surface_active` ⇒ Shift+Tab should
/// *visibly* open the overlay on Windows. `overlay_enabled && !surface_active`
/// ⇒ Steam is willing but the app has no compositing surface, and
/// `surface_error` says why (or the platform has no surface implementation).
#[derive(Clone, Debug, Default, Serialize)]
pub struct SteamOverlayStatus {
    /// `ISteamUtils::IsOverlayEnabled` — the Steam client has the overlay
    /// enabled for this game (user setting + successful DLL injection).
    pub overlay_enabled: bool,
    /// The in-process decoy swapchain is up and presenting (Windows only).
    pub surface_active: bool,
    /// Why the decoy surface gave up, if it did (Windows only).
    pub surface_error: Option<String>,
    /// Steam's own F12 grab is disabled and the app supplies live frames
    /// instead (`ISteamScreenshots::HookScreenshots`). Windows only.
    pub screenshots_hooked: bool,
}

// ── Runtime handle for ongoing Steamworks API calls ───────────────────────────

/// Live handle for achievement unlock, stat increment, and rich presence calls.
///
/// Constructed once by [`init`] and stored in managed state. All methods
/// gracefully return `false` when the `steam` Cargo feature is disabled or
/// Steam was not running at launch — callers do not need to guard on
/// `SteamStatus::is_steam_enabled` before calling.
pub struct SteamRuntime {
    #[cfg(feature = "steam")]
    client: Option<steamworks::Client>,
    /// Registered Steamworks callbacks. A `CallbackHandle` unregisters its
    /// callback when dropped, so they live here for the process lifetime.
    #[cfg(feature = "steam")]
    callbacks: Vec<steamworks::CallbackHandle>,
    #[cfg(not(feature = "steam"))]
    _phantom: std::marker::PhantomData<()>,
}

impl SteamRuntime {
    /// Unlock a Steam achievement by its Steamworks API name and persist the
    /// change. Returns `false` when Steam is unavailable.
    pub fn unlock_achievement(&self, api_name: &str) -> bool {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            let us = client.user_stats();
            // `set()` and `store_stats()` return `Result<(), ()>`; treat a
            // successful `set` as the unlock result and best-effort persist.
            let ok = us.achievement(api_name).set().is_ok();
            let _ = us.store_stats();
            return ok;
        }
        false
    }

    /// Increment an integer stat by 1. Reads the current value first so the
    /// counter is always monotonically increasing. Stores stats immediately.
    /// Returns `false` when Steam is unavailable.
    pub fn increment_stat(&self, api_name: &str) -> bool {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            let us = client.user_stats();
            // `get_stat_i32` returns `Err` until stats have been received from
            // Steam; falling back to 0 keeps the increment best-effort.
            let current = us.get_stat_i32(api_name).unwrap_or(0);
            let ok = us.set_stat_i32(api_name, current + 1).is_ok();
            let _ = us.store_stats();
            return ok;
        }
        false
    }

    /// Set the player's Steam rich presence to a generic activity token.
    /// Use the constants in [`rich_presence`] to keep disclosure generic.
    /// Returns `false` when Steam is unavailable.
    pub fn set_rich_presence(&self, value: &str) -> bool {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            return client
                .friends()
                .set_rich_presence(rich_presence::KEY, Some(value));
        }
        false
    }

    /// Show the Steam floating on-screen keyboard over the game window.
    ///
    /// Called whenever a text input or textarea gains focus so the Steam Deck
    /// on-screen keyboard appears without the player needing to invoke it
    /// manually — a requirement for the Steam Deck Verified tier.
    ///
    /// The keyboard is automatically dismissed when the player confirms or
    /// cancels input.  Returns `false` when Steam is unavailable.
    pub fn show_floating_keyboard(&self) -> bool {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            use steamworks::FloatingGamepadTextInputMode;
            // Position the keyboard in the lower third of the screen so it
            // overlaps as little of the UI as possible at 1280×800.
            //
            // `show_floating_gamepad_text_input` requires a `dismissed_cb`
            // closure (invoked when the player closes the keyboard).  For the
            // floating keyboard Steam injects the entered text directly into
            // the focused field as key events, so nothing needs to be read
            // back on dismiss and the callback is a no-op.
            return client.utils().show_floating_gamepad_text_input(
                FloatingGamepadTextInputMode::SingleLine,
                0,
                534,
                1280,
                266,
                || {},
            );
        }
        false
    }

    /// Dismiss the Steam floating on-screen keyboard if it is visible.
    /// Returns `false` when Steam is unavailable.
    ///
    /// NOTE: `steamworks` (through 0.13) does not bind
    /// `ISteamUtils::DismissFloatingGamepadTextInput`, so there is no way to
    /// programmatically hide the floating keyboard from Rust.  The floating
    /// keyboard is instead dismissed by the player (or automatically when they
    /// confirm input), so this is a no-op that reports `false`.  The Tauri
    /// command and front-end wiring are kept so hide becomes effective for free
    /// once the crate exposes the binding.
    pub fn hide_floating_keyboard(&self) -> bool {
        false
    }

    // ── Steam overlay ─────────────────────────────────────────────────────────
    //
    // The overlay needs two things a WebView2 app does not give it by default
    // (docs/STEAM_INTEGRATION.md, "Steam overlay (Windows WebView2 caveat)"):
    //
    //   1. An input path. Steam opens the overlay by catching Shift+Tab in the
    //      game process; in a Tauri app the chord lands in the WebView2 child
    //      process instead. The front-end forwards it to `activate_overlay`.
    //   2. A surface to draw into. Steam renders by hooking the game's graphics
    //      `Present` call, and this process never presents a swapchain of its
    //      own. On Windows the vendored overlay-surface plugin supplies a decoy
    //      swapchain, and Steam's `GameOverlayActivated` callback (forwarded in
    //      `wire_overlay_callbacks`) tells it when to take and release input.
    //
    // Both halves need `SteamAPI_Init` to have succeeded, i.e. a build with
    // `--features steam` launched through the Steam client.

    /// Open the Steam overlay in its default view (equivalent to the player
    /// pressing Shift+Tab). Returns `false` when Steam is unavailable or the
    /// Steam client reports the overlay as disabled for this game.
    ///
    /// The front-end listens for Shift+Tab and forwards it here (see
    /// `useSteamOverlay`) because the chord is delivered to the WebView2 child
    /// process, which Steam's input hook never sees. On Windows the vendored
    /// overlay-surface plugin gives Steam a swapchain to composite into, so the
    /// request is user-visible; on macOS and Linux it is not yet (separate,
    /// still-open problem — see the docs section above).
    pub fn activate_overlay(&self) -> bool {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            if !client.utils().is_overlay_enabled() {
                return false;
            }
            // An empty dialog string opens the overlay in its default state,
            // matching the behaviour of the Shift+Tab chord.
            client.friends().activate_game_overlay("");
            return true;
        }
        false
    }

    /// Diagnostic snapshot for the overlay gate — see [`SteamOverlayStatus`].
    pub fn overlay_status(&self) -> SteamOverlayStatus {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            return SteamOverlayStatus {
                overlay_enabled: client.utils().is_overlay_enabled(),
                surface_active: overlay_surface::surface_active(),
                surface_error: overlay_surface::surface_error(),
                screenshots_hooked: client.screenshots().is_screenshots_hooked(),
            };
        }
        SteamOverlayStatus::default()
    }

    /// Register the Steamworks callbacks the overlay surface depends on. Call
    /// once from Tauri `setup()`, after the main window exists. No-op outside
    /// Steam, without the `steam` feature, or on platforms without a surface.
    ///
    /// - `GameOverlayActivated` → the surface shows itself and takes input while
    ///   the overlay is open, then hides and hands focus back to the webview.
    /// - `ScreenshotRequested` (with `HookScreenshots(true)`) → the app hands
    ///   Steam a live capture of the main window. Without this, Steam's F12
    ///   copies the decoy's backbuffer, which never contains the game.
    ///
    /// Callbacks run on the callback-pump thread started by [`init`]; every
    /// Tauri window call the surface makes is thread-safe (proxied to the event
    /// loop), and `PrintWindow` capture is documented safe off the main thread.
    pub fn wire_overlay_callbacks(&mut self, app: tauri::AppHandle) {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            if !overlay_surface::AVAILABLE {
                return;
            }
            let handle = app.clone();
            self.callbacks.push(client.register_callback(
                move |ev: steamworks::GameOverlayActivated| {
                    overlay_surface::on_overlay_activated(&handle, ev.active);
                },
            ));

            client.screenshots().hook_screenshots(true);
            let handle = app.clone();
            let shot_client = client.clone();
            self.callbacks.push(client.register_callback(
                move |_: steamworks::screenshots::ScreenshotRequested| {
                    capture_and_add_screenshot(&shot_client, &handle);
                },
            ));
        }
        #[cfg(not(feature = "steam"))]
        let _ = app;
    }

    /// Take a Steam screenshot of the main window now and add it to the
    /// player's Steam screenshot library. The front-end forwards F12 here for
    /// the same reason it forwards Shift+Tab: the key lands in the WebView2
    /// process, so Steam's own hotkey hook only sees it while the overlay is
    /// open. Returns `false` when Steam is unavailable or capture failed.
    ///
    /// Deliberately does NOT go through `ISteamScreenshots::TriggerScreenshot`:
    /// with hooking enabled that call never delivers a `ScreenshotRequested`
    /// callback (verified live by the plugin author against Spacewar).
    pub fn trigger_screenshot(&self, app: &tauri::AppHandle) -> bool {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            return capture_and_add_screenshot(client, app);
        }
        #[cfg(not(feature = "steam"))]
        let _ = app;
        false
    }

    // ── Workshop / UGC ───────────────────────────────────────────────────────

    /// Return the list of Workshop items the local user is currently subscribed
    /// to, including their local install paths and update state.
    ///
    /// Only items that have been downloaded by Steam (non-empty `install_path`)
    /// are suitable for immediate validation and import; items that are still
    /// downloading will have an empty `install_path` and should be deferred.
    ///
    /// Returns an empty vector when Steam is unavailable.
    pub fn get_subscribed_items(&self) -> Vec<WorkshopItem> {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            let ugc = client.ugc();
            // `false`: skip items the player has locally disabled in the
            // Workshop UI (steamworks 0.13 exposes the SDK's
            // `bIncludeLocallyDisabled` flag; 0.11 always passed false).
            return ugc
                .subscribed_items(false)
                .into_iter()
                .map(|id| {
                    let install_info = ugc.item_install_info(id);
                    let needs_update = ugc
                        .item_state(id)
                        .contains(steamworks::ItemState::NEEDS_UPDATE);
                    WorkshopItem {
                        item_id: id.0.to_string(),
                        // `item_install_info` returns `Option<InstallInfo>`, a
                        // struct with `folder: String`, `size_on_disk: u64`, and
                        // `timestamp: u32` — not a tuple. The folder is already a
                        // `String`, so no lossy path conversion is needed.
                        install_path: install_info
                            .as_ref()
                            .map(|info| info.folder.clone())
                            .unwrap_or_default(),
                        needs_update,
                        updated_at: install_info
                            .as_ref()
                            .map(|info| info.timestamp)
                            .unwrap_or(0),
                    }
                })
                .collect();
        }
        Vec::new()
    }

    /// Open the Steam overlay to the Workshop submission flow for the given
    /// validated pack directory. The overlay prompts the creator to authorise
    /// the upload before any data leaves the local machine.
    ///
    /// This is a best-effort call: it opens the overlay and returns `true` if
    /// Steam is available, or `false` if not. The actual upload is handled by
    /// the Steam client — no pack content is transmitted by this function.
    ///
    /// The `pack_path` argument must be the absolute path to a directory that
    /// has already passed two-phase pack validation; the caller is responsible
    /// for running validation before invoking this.
    pub fn publish_pack(&self, _pack_path: &str) -> bool {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            // Open the Steam overlay to the Workshop landing page. The creator
            // reviews and consents via the Steam UI before any upload occurs.
            client
                .friends()
                .activate_game_overlay_to_web_page(
                    "https://steamcommunity.com/workshop/edititem/",
                );
            return true;
        }
        false
    }

    // ── DLC ownership ────────────────────────────────────────────────────────

    /// Returns `true` when the DLC with the given Steam App ID is currently
    /// installed (owned and downloaded) for the current user.
    ///
    /// Pass the Valve-assigned DLC App ID (not the base game's App ID). Use
    /// `dlc_registry_from_env()` to resolve a pack ID to its DLC App ID before
    /// calling this.
    ///
    /// Returns `false` when Steam is unavailable or the `steam` Cargo feature
    /// is disabled — callers should treat a `false` return as not-owned.
    pub fn is_dlc_installed(&self, dlc_app_id: u32) -> bool {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            return client
                .apps()
                .is_dlc_installed(steamworks::AppId(dlc_app_id));
        }
        false
    }

    /// Unsubscribe from a Workshop item by its numeric item ID.
    ///
    /// Returns `true` when the unsubscribe request was submitted to Steam.
    /// Steam will remove the locally installed files asynchronously; call
    /// `DELETE /api/workshop/:pack_id` to remove the pack from the local index
    /// once the UI confirms the unsubscription.
    pub fn unsubscribe_item(&self, item_id: u64) -> bool {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            let published_file_id = steamworks::PublishedFileId(item_id);
            client.ugc().unsubscribe_item(published_file_id, |_result| {
                // Callback fires after Steam acknowledges the request.
                // Errors are intentionally ignored: the front-end polls
                // Workshop item state to confirm removal.
            });
            return true;
        }
        false
    }
}

// ── Environment-variable helpers (always compiled) ────────────────────────────

/// Returns `true` when the process was launched by the Steam client.
/// Steam sets `SteamAppId` (and sometimes `SteamGameId`) in the game
/// process environment before handing control to the executable.
pub fn is_launched_by_steam() -> bool {
    std::env::var("SteamAppId").is_ok() || std::env::var("SteamGameId").is_ok()
}

/// Parses the AppID from the `SteamAppId` environment variable set by Steam.
fn app_id_from_env() -> Option<u32> {
    std::env::var("SteamAppId")
        .ok()
        .and_then(|s| s.parse::<u32>().ok())
}

/// Parses `VITE_STEAM_DLC_APP_IDS` (the STEAM_DLC_APP_IDS repository variable
/// injected at build time) into a pack-id → DLC App ID registry.
///
/// Expected format: comma-separated `pack_id:dlc_app_id` pairs, e.g.
///   `official.premium_pack:2123456,official.other_pack:2123457`
///
/// Silently skips malformed entries so a single typo does not block the whole
/// registry. Returns an empty `Vec` when the variable is absent or empty —
/// all DLC is treated as not-owned in that case (open-source / browser build).
pub fn dlc_registry_from_env() -> Vec<(String, u32)> {
    let raw = match std::env::var("VITE_STEAM_DLC_APP_IDS") {
        Ok(s) if !s.is_empty() => s,
        _ => return Vec::new(),
    };
    raw.split(',')
        .filter_map(|entry| {
            let entry = entry.trim();
            let colon = entry.find(':')?;
            let pack_id = entry[..colon].trim().to_string();
            let app_id: u32 = entry[colon + 1..].trim().parse().ok()?;
            if pack_id.is_empty() {
                return None;
            }
            Some((pack_id, app_id))
        })
        .collect()
}

// ── Overlay compositing surface (platform shim) ──────────────────────────────
//
// The vendored `tauri-plugin-steam-overlay-surface` crate is a Windows-only
// dependency (see Cargo.toml). This shim gives `SteamRuntime` one
// platform-independent API so the rest of this file — and the Linux
// `cargo check --features steam` in CI — never has to know the difference.

#[cfg(all(feature = "steam", windows))]
mod overlay_surface {
    /// A compositing surface implementation exists for this platform.
    pub const AVAILABLE: bool = true;
    pub use tauri_plugin_steam_overlay_surface::{
        capture_screenshot_png, on_overlay_activated, surface_active, surface_error,
    };
}

#[cfg(all(feature = "steam", not(windows)))]
mod overlay_surface {
    /// No compositing surface on this platform yet: the overlay opens (Steam
    /// reports success) but has nothing to draw into. Tracked as risk SP-06.
    pub const AVAILABLE: bool = false;

    pub struct CapturedScreenshot {
        pub path: std::path::PathBuf,
        pub width: u32,
        pub height: u32,
    }
    pub fn on_overlay_activated(_app: &tauri::AppHandle, _active: bool) {}
    pub fn surface_active() -> bool {
        false
    }
    pub fn surface_error() -> Option<String> {
        None
    }
    pub fn capture_screenshot_png(_app: &tauri::AppHandle) -> Option<CapturedScreenshot> {
        None
    }
}

/// Capture the main window and hand the PNG to Steam's screenshot library.
/// Shared by the `ScreenshotRequested` callback (Steam saw F12 — overlay open)
/// and the forwarded F12 command (overlay closed — only the webview saw it).
#[cfg(feature = "steam")]
fn capture_and_add_screenshot(client: &steamworks::Client, app: &tauri::AppHandle) -> bool {
    let Some(shot) = overlay_surface::capture_screenshot_png(app) else {
        return false;
    };
    client
        .screenshots()
        .add_screenshot_to_library(&shot.path, None, shot.width as i32, shot.height as i32)
        .is_ok()
}

// ── Feature-gated Steamworks SDK bridge ──────────────────────────────────────
//
// To build with real Steam API support:
//   cargo tauri build --features steam
//
// `steamworks-sys` bundles Valve's redistributable client library, so nothing
// needs downloading; set STEAM_SDK_LOCATION only to build against a different
// SDK. At runtime `SteamAPI_Init` succeeds only when the Steam client is
// running AND the app id is known — launched through Steam (the client sets
// `SteamAppId`) or via a `steam_appid.txt` next to the executable in dev.
//
// In local dev with the Spacewar test app:
//   SteamAppId=480 cargo tauri dev --features steam

#[cfg(feature = "steam")]
mod sdk {
    use super::*;

    /// How often the callback pump thread services Steamworks callbacks.
    /// Bounds the latency of `GameOverlayActivated` (overlay input handoff)
    /// and `ScreenshotRequested`; 50 ms is imperceptible and costs nothing.
    const CALLBACK_PUMP_INTERVAL: std::time::Duration = std::time::Duration::from_millis(50);

    pub fn init() -> (SteamStatus, SteamRuntime) {
        let launched = is_launched_by_steam();
        let env_app_id = app_id_from_env();

        match steamworks::Client::init() {
            Ok(client) => {
                // Steamworks delivers callbacks only while something calls
                // `run_callbacks`; before this pump existed no callback in the
                // app ever fired. Runs for the process lifetime. The overlay
                // surface, Workshop unsubscribe acks, and stat-store results
                // all arrive on this thread.
                let pump = client.clone();
                let _ = std::thread::Builder::new()
                    .name("steam-callbacks".into())
                    .spawn(move || loop {
                        pump.run_callbacks();
                        std::thread::sleep(CALLBACK_PUMP_INTERVAL);
                    });

                let status = SteamStatus {
                    is_steam_enabled: true,
                    launched_by_steam: launched,
                    app_id: Some(client.utils().app_id().0),
                    persona_name: Some(client.friends().name()),
                };
                (
                    status,
                    SteamRuntime {
                        client: Some(client),
                        callbacks: Vec::new(),
                    },
                )
            }
            Err(_) => (
                SteamStatus {
                    is_steam_enabled: false,
                    launched_by_steam: launched,
                    app_id: env_app_id,
                    persona_name: None,
                },
                SteamRuntime {
                    client: None,
                    callbacks: Vec::new(),
                },
            ),
        }
    }
}

#[cfg(not(feature = "steam"))]
mod sdk {
    use super::*;

    /// Fallback when the `steam` feature is disabled: report env-based
    /// detection only; never touch the Steamworks SDK.
    pub fn init() -> (SteamStatus, SteamRuntime) {
        (
            SteamStatus {
                is_steam_enabled: false,
                launched_by_steam: is_launched_by_steam(),
                app_id: app_id_from_env(),
                persona_name: None,
            },
            SteamRuntime {
                _phantom: std::marker::PhantomData,
            },
        )
    }
}

/// Initialise the Steam bridge and return the current status and a runtime
/// handle for ongoing achievement/stat/rich-presence calls. Safe to call on
/// any build regardless of whether Steam is present or the SDK feature is on.
pub fn init() -> (SteamStatus, SteamRuntime) {
    sdk::init()
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    // Serialize env-var mutations across test threads so tests do not race.
    static ENV_LOCK: Mutex<()> = Mutex::new(());

    fn with_steam_app_id(id: &str, f: impl FnOnce()) {
        let _g = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let prev = std::env::var("SteamAppId").ok();
        // Serialised by ENV_LOCK above so the mutation is race-free. On the
        // 2021 edition `set_var`/`remove_var` are safe fns (they only became
        // `unsafe` in the 2024 edition), so no `unsafe` block is needed.
        std::env::set_var("SteamAppId", id);
        f();
        match prev {
            Some(v) => std::env::set_var("SteamAppId", v),
            None => std::env::remove_var("SteamAppId"),
        }
    }

    fn without_steam_env_vars(f: impl FnOnce()) {
        let _g = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let prev_app = std::env::var("SteamAppId").ok();
        let prev_game = std::env::var("SteamGameId").ok();
        std::env::remove_var("SteamAppId");
        std::env::remove_var("SteamGameId");
        f();
        if let Some(v) = prev_app {
            std::env::set_var("SteamAppId", v);
        }
        if let Some(v) = prev_game {
            std::env::set_var("SteamGameId", v);
        }
    }

    // ── Steam absent ─────────────────────────────────────────────────────────

    #[test]
    fn steam_absent_is_disabled() {
        without_steam_env_vars(|| {
            let (status, _runtime) = init();
            assert!(!status.is_steam_enabled, "SDK not initialized without Steam");
            assert!(!status.launched_by_steam);
            assert!(status.app_id.is_none());
            assert!(status.persona_name.is_none());
        });
    }

    #[test]
    fn launched_by_steam_false_without_env_vars() {
        without_steam_env_vars(|| {
            assert!(!is_launched_by_steam());
        });
    }

    #[test]
    fn app_id_none_without_env_var() {
        without_steam_env_vars(|| {
            assert!(app_id_from_env().is_none());
        });
    }

    // ── Steam running (env-var detection) ────────────────────────────────────

    #[test]
    fn launched_by_steam_detected_via_steam_app_id() {
        with_steam_app_id("480", || {
            assert!(is_launched_by_steam());
        });
    }

    #[test]
    fn launched_by_steam_detected_via_steam_game_id() {
        let _g = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let prev_app = std::env::var("SteamAppId").ok();
        let prev_game = std::env::var("SteamGameId").ok();
        std::env::remove_var("SteamAppId");
        std::env::set_var("SteamGameId", "480");
        assert!(is_launched_by_steam());
        // Restore.
        std::env::remove_var("SteamGameId");
        if let Some(v) = prev_app {
            std::env::set_var("SteamAppId", v);
        }
        if let Some(v) = prev_game {
            std::env::set_var("SteamGameId", v);
        }
    }

    #[test]
    fn app_id_parsed_from_env() {
        with_steam_app_id("480", || {
            assert_eq!(app_id_from_env(), Some(480));
        });
    }

    #[test]
    fn init_with_steam_env_reports_launched_by_steam() {
        with_steam_app_id("1234", || {
            let (status, _runtime) = init();
            // Without the `steam` feature the SDK is never initialized, so
            // is_steam_enabled is false even under a real Steam env.
            // launched_by_steam and app_id come from env-var detection.
            assert!(status.launched_by_steam);
            assert_eq!(status.app_id, Some(1234));
        });
    }

    // ── Constants ────────────────────────────────────────────────────────────

    #[test]
    fn spacewar_app_id_is_valve_canonical_value() {
        // Valve's Spacewar test application always uses AppID 480.
        assert_eq!(SPACEWAR_APP_ID, 480);
    }

    // ── Achievement and stat API name constants ───────────────────────────────

    #[test]
    fn achievement_api_names_have_expected_prefix() {
        assert!(achievements::FIRST_SCENARIO.starts_with("ACH_"));
        assert!(achievements::FIRST_DEBRIEF.starts_with("ACH_"));
        assert!(achievements::PRACTICE_STREAK.starts_with("ACH_"));
        assert!(achievements::PACK_EXPLORER.starts_with("ACH_"));
        assert!(achievements::CREATOR_FIRST_VALIDATE.starts_with("ACH_"));
    }

    #[test]
    fn stat_api_names_have_expected_prefix() {
        assert!(stats::SCENARIOS_COMPLETED.starts_with("STAT_"));
        assert!(stats::DEBRIEFS_GENERATED.starts_with("STAT_"));
        assert!(stats::PACKS_VALIDATED.starts_with("STAT_"));
        assert!(stats::TEXT_MODE_SESSIONS.starts_with("STAT_"));
        assert!(stats::VOICE_MODE_SESSIONS.starts_with("STAT_"));
    }

    #[test]
    fn rich_presence_tokens_have_hash_prefix() {
        assert!(rich_presence::IN_SCENARIO.starts_with('#'));
        assert!(rich_presence::REVIEWING_DEBRIEF.starts_with('#'));
        assert!(rich_presence::EDITING_PACK.starts_with('#'));
        assert!(rich_presence::AT_MAIN_MENU.starts_with('#'));
    }

    // ── SteamRuntime graceful no-ops when steam feature is absent ─────────────

    #[test]
    fn unlock_achievement_returns_false_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            assert!(!runtime.unlock_achievement(achievements::FIRST_SCENARIO));
        });
    }

    #[test]
    fn increment_stat_returns_false_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            assert!(!runtime.increment_stat(stats::SCENARIOS_COMPLETED));
        });
    }

    #[test]
    fn set_rich_presence_returns_false_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            assert!(!runtime.set_rich_presence(rich_presence::IN_SCENARIO));
        });
    }

    #[test]
    fn show_floating_keyboard_returns_false_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            assert!(!runtime.show_floating_keyboard());
        });
    }

    #[test]
    fn hide_floating_keyboard_returns_false_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            assert!(!runtime.hide_floating_keyboard());
        });
    }

    #[test]
    fn activate_overlay_returns_false_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            assert!(!runtime.activate_overlay());
        });
    }

    #[test]
    fn overlay_status_is_all_off_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            let s = runtime.overlay_status();
            assert!(!s.overlay_enabled);
            assert!(!s.surface_active);
            assert!(s.surface_error.is_none());
            assert!(!s.screenshots_hooked);
        });
    }

    #[test]
    fn overlay_status_serialises_snake_case_fields() {
        // The front-end reads these exact keys (useSteamOverlay / QA readout).
        let json = serde_json::to_value(SteamOverlayStatus::default()).unwrap();
        for key in [
            "overlay_enabled",
            "surface_active",
            "surface_error",
            "screenshots_hooked",
        ] {
            assert!(json.get(key).is_some(), "missing key {key}");
        }
    }

    // ── Workshop graceful no-ops when steam feature is absent ─────────────────

    #[test]
    fn get_subscribed_items_returns_empty_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            let items = runtime.get_subscribed_items();
            assert!(items.is_empty(), "expected empty vec without Steam");
        });
    }

    #[test]
    fn publish_pack_returns_false_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            assert!(!runtime.publish_pack("/tmp/some-pack"));
        });
    }

    #[test]
    fn unsubscribe_item_returns_false_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            assert!(!runtime.unsubscribe_item(12345678u64));
        });
    }

    // ── Workshop constants ────────────────────────────────────────────────────

    #[test]
    fn workshop_pack_tag_is_non_empty() {
        assert!(!workshop::PACK_TAG.is_empty());
        assert_eq!(workshop::PACK_TAG, "scenario-pack");
    }

    #[test]
    fn workshop_item_default_has_empty_item_id() {
        let item = WorkshopItem::default();
        assert!(item.item_id.is_empty());
        assert!(item.install_path.is_empty());
        assert!(!item.needs_update);
        assert_eq!(item.updated_at, 0);
    }

    // ── DLC ownership graceful no-op when steam feature is absent ─────────────

    #[test]
    fn is_dlc_installed_returns_false_without_steam() {
        without_steam_env_vars(|| {
            let (_status, runtime) = init();
            assert!(!runtime.is_dlc_installed(2123456));
        });
    }

    // ── DLC registry parsing ──────────────────────────────────────────────────

    fn with_dlc_app_ids(value: &str, f: impl FnOnce()) {
        let _g = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let prev = std::env::var("VITE_STEAM_DLC_APP_IDS").ok();
        std::env::set_var("VITE_STEAM_DLC_APP_IDS", value);
        f();
        match prev {
            Some(v) => std::env::set_var("VITE_STEAM_DLC_APP_IDS", v),
            None => std::env::remove_var("VITE_STEAM_DLC_APP_IDS"),
        }
    }

    fn without_dlc_app_ids(f: impl FnOnce()) {
        let _g = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let prev = std::env::var("VITE_STEAM_DLC_APP_IDS").ok();
        std::env::remove_var("VITE_STEAM_DLC_APP_IDS");
        f();
        if let Some(v) = prev {
            std::env::set_var("VITE_STEAM_DLC_APP_IDS", v);
        }
    }

    #[test]
    fn dlc_registry_empty_when_var_absent() {
        without_dlc_app_ids(|| {
            assert!(dlc_registry_from_env().is_empty());
        });
    }

    #[test]
    fn dlc_registry_empty_when_var_is_empty_string() {
        with_dlc_app_ids("", || {
            assert!(dlc_registry_from_env().is_empty());
        });
    }

    #[test]
    fn dlc_registry_parses_single_entry() {
        with_dlc_app_ids("official.premium_pack:2123456", || {
            let reg = dlc_registry_from_env();
            assert_eq!(reg.len(), 1);
            assert_eq!(reg[0], ("official.premium_pack".to_string(), 2123456u32));
        });
    }

    #[test]
    fn dlc_registry_parses_multiple_entries() {
        with_dlc_app_ids("official.pack_a:2000001,official.pack_b:2000002", || {
            let reg = dlc_registry_from_env();
            assert_eq!(reg.len(), 2);
            assert_eq!(reg[0].0, "official.pack_a");
            assert_eq!(reg[0].1, 2000001u32);
            assert_eq!(reg[1].0, "official.pack_b");
            assert_eq!(reg[1].1, 2000002u32);
        });
    }

    #[test]
    fn dlc_registry_skips_malformed_entries() {
        with_dlc_app_ids("official.good:2000001,bad-no-colon,official.also_good:2000002", || {
            let reg = dlc_registry_from_env();
            assert_eq!(reg.len(), 2);
            assert_eq!(reg[0].0, "official.good");
            assert_eq!(reg[1].0, "official.also_good");
        });
    }

    #[test]
    fn dlc_registry_skips_non_numeric_app_ids() {
        with_dlc_app_ids("official.pack:not_a_number,official.valid:2000001", || {
            let reg = dlc_registry_from_env();
            assert_eq!(reg.len(), 1);
            assert_eq!(reg[0].0, "official.valid");
        });
    }

    #[test]
    fn dlc_registry_trims_whitespace() {
        with_dlc_app_ids(" official.pack : 2000001 , official.pack2:2000002 ", || {
            let reg = dlc_registry_from_env();
            assert_eq!(reg.len(), 2);
            assert_eq!(reg[0].0, "official.pack");
            assert_eq!(reg[0].1, 2000001u32);
        });
    }
}
