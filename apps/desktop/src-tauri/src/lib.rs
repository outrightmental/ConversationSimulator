// SPDX-License-Identifier: Apache-2.0
use std::{
    net::SocketAddr,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    time::Duration,
};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_updater::UpdaterExt;
use tauri_plugin_shell::ShellExt;

mod steam;

// ── Status events emitted to the front-end ────────────────────────────────────

#[derive(Clone, serde::Serialize)]
struct CoreStatusPayload {
    phase: String,
    message: String,
    error: Option<String>,
    /// Absolute path to the app log directory on this platform.
    /// Included so the recovery card can show (and open) the correct path
    /// without hardcoding ~/.convsim or any other platform-specific default.
    log_dir: Option<String>,
}

// ── Update check ─────────────────────────────────────────────────────────────

#[derive(Clone, serde::Serialize)]
struct UpdateInfo {
    version: String,
    release_url: String,
}

/// Stores the release page URL for the latest available beta update so that
/// `install_update` can open it without accepting an untrusted URL from the
/// frontend.
struct PendingUpdateState(Arc<Mutex<Option<String>>>);

/// Check for a beta update.  Fails silently when offline or when the updater
/// manifest is unavailable — the frontend shows nothing in that case.
#[tauri::command]
async fn check_for_update(
    app: AppHandle,
    state: tauri::State<'_, PendingUpdateState>,
) -> Result<Option<UpdateInfo>, String> {
    let updater = match app.updater() {
        Ok(u) => u,
        Err(e) => {
            eprintln!("Updater unavailable (will retry on next launch): {e}");
            return Ok(None);
        }
    };
    let maybe_update = match updater.check().await {
        Ok(r) => r,
        Err(e) => {
            // Offline or missing manifest — expected for users without network
            // access; do not surface to the user.
            eprintln!("Update check failed (offline or no manifest): {e}");
            return Ok(None);
        }
    };
    let update = match maybe_update {
        Some(u) => u,
        None => return Ok(None),
    };
    let version = update.version.clone();
    let release_url = format!(
        "https://github.com/outrightmental/ConversationSimulator/releases/tag/v{version}"
    );
    if let Ok(mut guard) = state.0.lock() {
        *guard = Some(release_url.clone());
    }
    Ok(Some(UpdateInfo { version, release_url }))
}

/// Open the GitHub release page for manual installation of the pending beta
/// update.  The URL is always constructed on the Rust side and never accepted
/// from the frontend.
#[tauri::command]
fn install_update(
    state: tauri::State<'_, PendingUpdateState>,
    app: AppHandle,
) -> Result<(), String> {
    let url = state
        .0
        .lock()
        .map_err(|e| e.to_string())?
        .clone()
        .ok_or_else(|| "No pending update — run check_for_update first".to_string())?;
    // `Shell::open` takes `impl Into<String>`; `&String` does not implement it,
    // so pass the owned `String` (it is not needed afterwards).
    app.shell().open(url, None).map_err(|e| e.to_string())
}

// ── Steam integration state ───────────────────────────────────────────────────

/// Holds the Steam status snapshot so the front-end can query it at any time
/// via `get_steam_status`.  Initialised once during `setup()`.
struct SteamState(Arc<Mutex<steam::SteamStatus>>);

/// Holds the live Steamworks runtime handle for achievement/stat/rich-presence
/// calls issued from the front-end. Always present; methods are no-ops outside
/// Steam or when the `steam` feature is disabled.
struct SteamRuntimeState(Arc<Mutex<steam::SteamRuntime>>);

/// Returns the current Steam integration status.
/// Safe to call on non-Steam builds; always returns `is_steam_enabled: false`
/// unless the `steam` Cargo feature is enabled and Steam is running.
#[tauri::command]
fn get_steam_status(state: tauri::State<'_, SteamState>) -> steam::SteamStatus {
    state
        .0
        .lock()
        .map(|g| g.clone())
        .unwrap_or_default()
}

/// Unlock a Steam achievement by its Steamworks API name.
/// Returns `false` when not running under Steam or the `steam` feature is off.
#[tauri::command]
fn steam_unlock_achievement(
    name: String,
    state: tauri::State<'_, SteamRuntimeState>,
) -> bool {
    state
        .0
        .lock()
        .map(|r| r.unlock_achievement(&name))
        .unwrap_or(false)
}

/// Increment an integer stat by 1 and persist it to Steam.
/// Returns `false` when not running under Steam or the `steam` feature is off.
#[tauri::command]
fn steam_increment_stat(
    name: String,
    state: tauri::State<'_, SteamRuntimeState>,
) -> bool {
    state
        .0
        .lock()
        .map(|r| r.increment_stat(&name))
        .unwrap_or(false)
}

/// Set the player's Steam rich presence to a generic activity token.
/// Use the token constants from `steam::rich_presence` to keep disclosure
/// generic (no session details, scenario names, or transcript content).
/// Returns `false` when not running under Steam or the `steam` feature is off.
#[tauri::command]
fn steam_set_rich_presence(
    value: String,
    state: tauri::State<'_, SteamRuntimeState>,
) -> bool {
    state
        .0
        .lock()
        .map(|r| r.set_rich_presence(&value))
        .unwrap_or(false)
}

/// Report whether the premium DLC with the given Steam DLC App ID is owned and
/// installed. Used to gate premium scenario-pack expansions (see
/// docs/DLC_MODEL.md). Returns `false` outside Steam or when the DLC is not owned,
/// so non-Steam builds treat every premium pack as available-to-buy.
#[tauri::command]
fn steam_is_dlc_installed(
    dlc_app_id: u32,
    state: tauri::State<'_, SteamRuntimeState>,
) -> bool {
    state
        .0
        .lock()
        .map(|r| r.is_dlc_installed(dlc_app_id))
        .unwrap_or(false)
}

/// Show the Steam floating on-screen keyboard over the game window.
/// Called by the front-end whenever a text input gains focus so the
/// Steam Deck keyboard appears without requiring manual player action.
/// Returns `false` when not running under Steam or the `steam` feature is off.
#[tauri::command]
fn steam_show_floating_keyboard(state: tauri::State<'_, SteamRuntimeState>) -> bool {
    state
        .0
        .lock()
        .map(|r| r.show_floating_keyboard())
        .unwrap_or(false)
}

/// Dismiss the Steam floating on-screen keyboard if it is currently visible.
/// Returns `false` when not running under Steam or the `steam` feature is off.
#[tauri::command]
fn steam_hide_floating_keyboard(state: tauri::State<'_, SteamRuntimeState>) -> bool {
    state
        .0
        .lock()
        .map(|r| r.hide_floating_keyboard())
        .unwrap_or(false)
}

/// Return the list of Steam Workshop items the local user is subscribed to.
///
/// Each item includes its install path and update state so the front-end can
/// drive the subscribe-sync flow (validate → import via `/api/workshop/sync`).
/// Returns an empty array when not running under Steam or the `steam` feature
/// is disabled — the Workshop UI should be hidden in those cases.
#[tauri::command]
fn steam_workshop_get_subscribed_items(
    state: tauri::State<'_, SteamRuntimeState>,
) -> Vec<steam::WorkshopItem> {
    state
        .0
        .lock()
        .map(|r| r.get_subscribed_items())
        .unwrap_or_default()
}

/// Open the Steam overlay to the Workshop submission flow for the given
/// validated pack directory. The overlay prompts the creator to authorise the
/// upload before any content leaves the local machine.
///
/// `pack_path` must be an absolute path to a pack that has already passed
/// two-phase validation (the caller is responsible for this precondition).
///
/// Returns `false` when not running under Steam or the `steam` feature is off.
#[tauri::command]
fn steam_workshop_publish_pack(
    pack_path: String,
    state: tauri::State<'_, SteamRuntimeState>,
) -> bool {
    state
        .0
        .lock()
        .map(|r| r.publish_pack(&pack_path))
        .unwrap_or(false)
}

/// Unsubscribe from a Workshop item by its numeric item ID (decimal string).
///
/// Returns `false` when not running under Steam or the `steam` feature is off.
/// On success the front-end should call `DELETE /api/workshop/:pack_id` to
/// remove the pack from the local index once the files are gone.
#[tauri::command]
fn steam_workshop_unsubscribe(
    item_id: String,
    state: tauri::State<'_, SteamRuntimeState>,
) -> bool {
    let id: u64 = match item_id.parse() {
        Ok(n) => n,
        Err(_) => return false,
    };
    state
        .0
        .lock()
        .map(|r| r.unsubscribe_item(id))
        .unwrap_or(false)
}

// ── Managed state (owns the convsim-core child process) ───────────────────────

struct CoreProcessState(Arc<Mutex<Option<Child>>>);

impl Drop for CoreProcessState {
    fn drop(&mut self) {
        if let Ok(mut guard) = self.0.lock() {
            if let Some(ref mut child) = *guard {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

// Holds the most recently emitted status so the front-end can reconcile any
// event it missed. The launch thread starts emitting from `setup()`, which runs
// before the webview has loaded and subscribed to `core-status`; Tauri does not
// replay events, so a fast failure (e.g. missing binary) would otherwise leave
// the UI stuck on the initial "starting" message. The front-end queries
// `get_core_status` once after subscribing to recover the current state.
struct CoreStatusState(Arc<Mutex<Option<CoreStatusPayload>>>);

// ── Helpers ───────────────────────────────────────────────────────────────────

fn emit_core_status(
    app: &AppHandle,
    store: &Arc<Mutex<Option<CoreStatusPayload>>>,
    phase: &str,
    message: &str,
    error: Option<&str>,
    log_dir: Option<&str>,
) {
    let payload = CoreStatusPayload {
        phase: phase.to_string(),
        message: message.to_string(),
        error: error.map(|s| s.to_string()),
        log_dir: log_dir.map(|s| s.to_string()),
    };
    if let Ok(mut guard) = store.lock() {
        *guard = Some(payload.clone());
    }
    let _ = app.emit("core-status", payload);
}

// Snapshot of the latest core status, used by the front-end to recover events
// emitted before it subscribed.
#[tauri::command]
fn get_core_status(state: tauri::State<'_, CoreStatusState>) -> Option<CoreStatusPayload> {
    state.0.lock().ok().and_then(|guard| guard.clone())
}

fn is_port_open(port: u16) -> bool {
    let addr: SocketAddr = ([127u8, 0, 0, 1], port).into();
    std::net::TcpStream::connect_timeout(&addr, Duration::from_millis(200)).is_ok()
}

// ── Executable resolution (mirrors the Python three-step order) ───────────────
//
// 1. CONVSIM_CORE_EXECUTABLE env-var override
// 2. CONVSIM_BUNDLED_RUNTIME_DIR/<name> (Steam / packaged builds)
// 3. Tauri resource directory (app bundle)
// 4. PATH lookup

fn find_core_executable(resource_dir: Option<&PathBuf>) -> Result<PathBuf, String> {
    // 1. Explicit env-var override.
    if let Ok(path) = std::env::var("CONVSIM_CORE_EXECUTABLE") {
        let p = PathBuf::from(&path);
        if p.exists() {
            return Ok(p);
        }
        return Err(format!(
            "CONVSIM_CORE_EXECUTABLE is set to '{}' but that file does not exist.",
            path
        ));
    }

    // 2. Bundled runtime dir (Steam / packaged builds).
    if let Ok(dir) = std::env::var("CONVSIM_BUNDLED_RUNTIME_DIR") {
        for name in &["convsim-core", "convsim-core.exe"] {
            let p = PathBuf::from(&dir).join(name);
            if p.exists() {
                return Ok(p);
            }
        }
    }

    // 3. Tauri resource directory (adjacent to the app bundle).
    //    Checks both the resource dir root and the resources/bin/ sub-path
    //    produced by scripts/build-core.sh (via "resources/**/*" in tauri.conf.json).
    if let Some(res) = resource_dir {
        for rel in &[
            "convsim-core",
            "convsim-core.exe",
            "bin/convsim-core",
            "bin/convsim-core.exe",
            "resources/bin/convsim-core",
            "resources/bin/convsim-core.exe",
        ] {
            let p = res.join(rel);
            if p.exists() {
                return Ok(p);
            }
        }
    }

    // 4. PATH lookup.
    let probe = if cfg!(windows) {
        Command::new("where").arg("convsim-core").output()
    } else {
        Command::new("which").arg("convsim-core").output()
    };
    if let Ok(out) = probe {
        if out.status.success() {
            let path = String::from_utf8_lossy(&out.stdout)
                .lines()
                .next()
                .unwrap_or("")
                .trim()
                .to_string();
            if !path.is_empty() {
                return Ok(PathBuf::from(path));
            }
        }
    }

    Err(
        "convsim-core executable not found.\n\
         In dev mode, run ./scripts/setup.sh first (the venv must be active or \
         convsim-core must be on PATH).\n\
         In a packaged build this indicates a bundle issue — please report it at \
         https://github.com/outrightmental/ConversationSimulator/issues"
            .to_string(),
    )
}

// ── Core launch / supervision ─────────────────────────────────────────────────

fn launch_or_verify_core(
    app: AppHandle,
    process_arc: Arc<Mutex<Option<Child>>>,
    status_arc: Arc<Mutex<Option<CoreStatusPayload>>>,
) {
    std::thread::spawn(move || {
        const CORE_PORT: u16 = 7355;

        // Compute the platform-specific log directory once so every status event
        // carries the correct absolute path for the recovery card to display.
        //
        // Create it eagerly: convsim-core normally creates logs/ when it runs
        // configure_logging(), but if it never starts (binary missing, immediate
        // exec failure) that never happens — leaving the recovery card's "Open
        // logs folder" button pointing at a non-existent path and dead-ending the
        // very stranded user the card exists to help. Making the directory here
        // guarantees the path shown always exists and is openable.
        let log_dir: Option<String> = app.path()
            .app_local_data_dir()
            .ok()
            .map(|p| p.join("logs"))
            .map(|p| {
                let _ = std::fs::create_dir_all(&p);
                p.to_string_lossy().into_owned()
            });
        let log_dir_ref = log_dir.as_deref();

        // If core is already responding (e.g. started by dev-desktop.sh), signal
        // ready immediately.
        if is_port_open(CORE_PORT) {
            emit_core_status(&app, &status_arc, "ready", "Core service is ready.", None, log_dir_ref);
            return;
        }

        // In debug (dev) builds the dev-desktop.sh script is responsible for
        // starting convsim-core before Tauri. Wait briefly in case of a race.
        if cfg!(debug_assertions) {
            for _ in 0..20u32 {
                std::thread::sleep(Duration::from_millis(500));
                if is_port_open(CORE_PORT) {
                    emit_core_status(&app, &status_arc, "ready", "Core service is ready.", None, log_dir_ref);
                    return;
                }
            }
            emit_core_status(
                &app,
                &status_arc,
                "error",
                "Core service is not running.",
                Some(
                    "In dev mode, start convsim-core before launching the desktop app:\n\
                     ./scripts/dev-desktop.sh",
                ),
                log_dir_ref,
            );
            return;
        }

        // ── Release mode: find, launch, and supervise convsim-core ───────────

        emit_core_status(&app, &status_arc, "starting", "Locating core service…", None, log_dir_ref);

        let resource_dir = app.path().resource_dir().ok();

        let exe = match find_core_executable(resource_dir.as_ref()) {
            Ok(p) => p,
            Err(e) => {
                emit_core_status(
                    &app,
                    &status_arc,
                    "error",
                    "Could not locate core service.",
                    Some(&e),
                    log_dir_ref,
                );
                return;
            }
        };

        emit_core_status(&app, &status_arc, "starting", "Starting core service…", None, log_dir_ref);

        // convsim-core reads its bind address from CONVSIM_HOST / CONVSIM_PORT
        // (see services/convsim-core/convsim_core/config.py); it does not parse
        // CLI flags. Set them explicitly so the shell controls the port it polls.
        let mut cmd = Command::new(&exe);
        cmd.env("CONVSIM_HOST", "127.0.0.1")
            .env("CONVSIM_PORT", CORE_PORT.to_string())
            .stdin(Stdio::null())
            .stdout(Stdio::inherit())
            .stderr(Stdio::inherit());

        // Pass the OS-native app data directory as CONVSIM_DATA_ROOT so the
        // Python backend uses the same platform-specific location that Tauri
        // considers the app's home for user data (rather than the legacy
        // ~/.convsim dev location). convsim_core.paths.platform_data_root()
        // reads this env var and falls back to OS conventions when it is absent
        // (e.g. in dev mode without Tauri).
        //
        // Use the *local* app data dir, not app_data_dir(): on Windows the
        // latter resolves to %APPDATA% (the Roaming profile), which some sync
        // tools and enterprise policies replicate across machines — a poor home
        // for GBs of model files and private conversation data. app_local_data_dir()
        // resolves to %LOCALAPPDATA%, matching paths.py's Windows convention.
        // On macOS and Linux the two are identical.
        if let Ok(data_dir) = app.path().app_local_data_dir() {
            cmd.env("CONVSIM_DATA_ROOT", &data_dir);
        }

        // Tell convsim-core where the bundled sidecar binaries live so it can
        // start llama-server, whisper-cli, and sherpa-onnx-offline-tts without
        // requiring a system PATH entry (Steam build convention).
        //
        // Check both runtimes/ (legacy direct resource) and resources/runtimes/
        // (produced by the "resources/**/*" glob in tauri.conf.json).
        if let Some(ref res) = resource_dir {
            for runtimes_rel in &["runtimes", "resources/runtimes"] {
                let runtimes = res.join(runtimes_rel);
                if runtimes.exists() {
                    cmd.env("CONVSIM_BUNDLED_RUNTIME_DIR", &runtimes);
                    break;
                }
            }
        }

        let child = match cmd.spawn() {
            Ok(c) => c,
            Err(e) => {
                let hint = if e.kind() == std::io::ErrorKind::PermissionDenied {
                    "The core service binary is not executable. \
                     This may indicate a corrupted installation — reinstall the app."
                } else {
                    "Failed to start the core service process."
                };
                emit_core_status(&app, &status_arc, "error", hint, Some(&e.to_string()), log_dir_ref);
                return;
            }
        };

        {
            let mut lock = process_arc.lock().unwrap();
            *lock = Some(child);
        }

        // ── Poll until healthy ────────────────────────────────────────────────

        emit_core_status(
            &app,
            &status_arc,
            "starting",
            "Waiting for core service to be ready…",
            None,
            log_dir_ref,
        );

        for attempt in 0..30u32 {
            std::thread::sleep(Duration::from_millis(500));

            // Detect premature exit.
            {
                let mut lock = process_arc.lock().unwrap();
                if let Some(ref mut child) = *lock {
                    if let Ok(Some(status)) = child.try_wait() {
                        let msg = format!(
                            "Core service stopped during startup (exit status: {}).",
                            status
                        );
                        emit_core_status(
                            &app,
                            &status_arc,
                            "error",
                            &msg,
                            None,
                            log_dir_ref,
                        );
                        return;
                    }
                }
            }

            if is_port_open(CORE_PORT) {
                emit_core_status(&app, &status_arc, "ready", "Core service is ready.", None, log_dir_ref);
                return;
            }

            if attempt == 10 {
                emit_core_status(
                    &app,
                    &status_arc,
                    "starting",
                    "Still starting core service — this may take a moment on first run…",
                    None,
                    log_dir_ref,
                );
            }
        }

        // Timeout after ~15 s.
        emit_core_status(
            &app,
            &status_arc,
            "error",
            "Core service did not become ready in time.",
            Some(
                "The service started but did not respond within 15 seconds. \
                 Open the logs folder for details, then restart the app.",
            ),
            log_dir_ref,
        );
    });
}

// ── Public entry point ────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let process_inner: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let status_inner: Arc<Mutex<Option<CoreStatusPayload>>> = Arc::new(Mutex::new(None));
    let pending_update_inner: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(None));

    // Kept for the `RunEvent::Exit` handler below. Relying on `CoreProcessState`'s
    // `Drop` alone is not enough: on desktop the tao event loop terminates the
    // process via `std::process::exit()` when the app exits, so managed-state
    // destructors are never run and `convsim-core` would be orphaned (leaving
    // port 7355 held). Killing the child explicitly on `RunEvent::Exit` is the
    // reliable teardown path; `Drop` remains as a backstop for other exit paths.
    let process_on_exit = Arc::clone(&process_inner);

    // Initialise the Steam bridge early so the status is available before the
    // webview requests it. Gracefully returns a disabled status when Steam is
    // absent or the `steam` Cargo feature is off. The runtime handle is kept
    // alive for the process lifetime to service achievement/stat/rich-presence
    // commands.
    let (steam_status_val, steam_runtime_val) = steam::init();
    let steam_status = Arc::new(Mutex::new(steam_status_val));
    let steam_runtime = Arc::new(Mutex::new(steam_runtime_val));

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(CoreProcessState(Arc::clone(&process_inner)))
        .manage(CoreStatusState(Arc::clone(&status_inner)))
        .manage(PendingUpdateState(Arc::clone(&pending_update_inner)))
        .manage(SteamState(Arc::clone(&steam_status)))
        .manage(SteamRuntimeState(Arc::clone(&steam_runtime)))
        .invoke_handler(tauri::generate_handler![
            get_core_status,
            get_steam_status,
            check_for_update,
            install_update,
            steam_unlock_achievement,
            steam_increment_stat,
            steam_set_rich_presence,
            steam_is_dlc_installed,
            steam_show_floating_keyboard,
            steam_hide_floating_keyboard,
            steam_workshop_get_subscribed_items,
            steam_workshop_publish_pack,
            steam_workshop_unsubscribe,
        ])
        .setup(move |app| {
            launch_or_verify_core(
                app.handle().clone(),
                Arc::clone(&process_inner),
                Arc::clone(&status_inner),
            );
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(move |_app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Ok(mut guard) = process_on_exit.lock() {
                if let Some(ref mut child) = *guard {
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        }
    });
}
