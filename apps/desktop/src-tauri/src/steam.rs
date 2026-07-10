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

// ── Runtime handle for ongoing Steamworks API calls ───────────────────────────

/// Live handle for achievement unlock, stat increment, and rich presence calls.
///
/// Constructed once by [`init`] and stored in managed state. All methods
/// gracefully return `false` when the `steam` Cargo feature is disabled or
/// Steam was not running at launch — callers do not need to guard on
/// `SteamStatus::is_steam_enabled` before calling.
pub struct SteamRuntime {
    #[cfg(feature = "steam")]
    client: Option<steamworks::Client<steamworks::ClientManager>>,
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
            return client.utils().show_floating_gamepad_text_input(
                FloatingGamepadTextInputMode::SingleLine,
                0,
                534,
                1280,
                266,
            );
        }
        false
    }

    /// Dismiss the Steam floating on-screen keyboard if it is visible.
    /// Returns `false` when Steam is unavailable.
    pub fn hide_floating_keyboard(&self) -> bool {
        #[cfg(feature = "steam")]
        if let Some(ref client) = self.client {
            client.utils().dismiss_floating_gamepad_text_input();
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

// ── Feature-gated Steamworks SDK bridge ──────────────────────────────────────
//
// To build with real Steam API support:
//   1. Obtain the Steamworks SDK from https://partner.steamgames.com/doc/sdk
//   2. Set STEAM_SDK_LOCATION to the unpacked SDK root directory.
//   3. cargo tauri build --features steam
//
// In local dev with the Spacewar test app:
//   SteamAppId=480 cargo tauri dev --features steam

#[cfg(feature = "steam")]
mod sdk {
    use super::*;

    pub fn init() -> (SteamStatus, SteamRuntime) {
        let launched = is_launched_by_steam();
        let env_app_id = app_id_from_env();

        match steamworks::Client::init() {
            Ok((client, _single)) => {
                let status = SteamStatus {
                    is_steam_enabled: true,
                    launched_by_steam: launched,
                    app_id: Some(client.utils().app_id().0),
                    persona_name: Some(client.friends().name()),
                };
                (status, SteamRuntime { client: Some(client) })
            }
            Err(_) => (
                SteamStatus {
                    is_steam_enabled: false,
                    launched_by_steam: launched,
                    app_id: env_app_id,
                    persona_name: None,
                },
                SteamRuntime { client: None },
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
}
