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

    /// Initialise the Steamworks SDK and return the current status.
    /// Returns a disabled fallback rather than panicking when Steam is absent
    /// or not running.
    pub fn init() -> SteamStatus {
        let launched = is_launched_by_steam();
        let env_app_id = app_id_from_env();

        match steamworks::Client::init() {
            Ok((client, _single)) => SteamStatus {
                is_steam_enabled: true,
                launched_by_steam: launched,
                app_id: Some(client.utils().app_id().0),
                persona_name: Some(client.friends().name()),
            },
            Err(_) => SteamStatus {
                is_steam_enabled: false,
                launched_by_steam: launched,
                app_id: env_app_id,
                persona_name: None,
            },
        }
    }
}

#[cfg(not(feature = "steam"))]
mod sdk {
    use super::*;

    /// Fallback when the `steam` feature is disabled: report env-based
    /// detection only; never touch the Steamworks SDK.
    pub fn init() -> SteamStatus {
        SteamStatus {
            is_steam_enabled: false,
            launched_by_steam: is_launched_by_steam(),
            app_id: app_id_from_env(),
            persona_name: None,
        }
    }
}

/// Initialise the Steam bridge and return the current status. Safe to call on
/// any build regardless of whether Steam is present or the SDK feature is on.
pub fn init() -> SteamStatus {
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
        // SAFETY: single-threaded access is guaranteed by ENV_LOCK above.
        unsafe { std::env::set_var("SteamAppId", id) }
        f();
        match prev {
            Some(v) => unsafe { std::env::set_var("SteamAppId", v) },
            None => unsafe { std::env::remove_var("SteamAppId") },
        }
    }

    fn without_steam_env_vars(f: impl FnOnce()) {
        let _g = ENV_LOCK.lock().unwrap_or_else(|e| e.into_inner());
        let prev_app = std::env::var("SteamAppId").ok();
        let prev_game = std::env::var("SteamGameId").ok();
        unsafe {
            std::env::remove_var("SteamAppId");
            std::env::remove_var("SteamGameId");
        }
        f();
        if let Some(v) = prev_app {
            unsafe { std::env::set_var("SteamAppId", v) }
        }
        if let Some(v) = prev_game {
            unsafe { std::env::set_var("SteamGameId", v) }
        }
    }

    // ── Steam absent ─────────────────────────────────────────────────────────

    #[test]
    fn steam_absent_is_disabled() {
        without_steam_env_vars(|| {
            let status = init();
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
        unsafe {
            std::env::remove_var("SteamAppId");
            std::env::set_var("SteamGameId", "480");
        }
        assert!(is_launched_by_steam());
        // Restore.
        unsafe { std::env::remove_var("SteamGameId") }
        if let Some(v) = prev_app {
            unsafe { std::env::set_var("SteamAppId", v) }
        }
        if let Some(v) = prev_game {
            unsafe { std::env::set_var("SteamGameId", v) }
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
            let status = init();
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
}
