// SPDX-License-Identifier: Apache-2.0
use std::{
    net::SocketAddr,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    time::Duration,
};
use tauri::{AppHandle, Emitter, Manager};

mod steam;

// ── Status events emitted to the front-end ────────────────────────────────────

#[derive(Clone, serde::Serialize)]
struct CoreStatusPayload {
    phase: String,
    message: String,
    error: Option<String>,
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
) {
    let payload = CoreStatusPayload {
        phase: phase.to_string(),
        message: message.to_string(),
        error: error.map(|s| s.to_string()),
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

        // If core is already responding (e.g. started by dev-desktop.sh), signal
        // ready immediately.
        if is_port_open(CORE_PORT) {
            emit_core_status(&app, &status_arc, "ready", "Core service is ready.", None);
            return;
        }

        // In debug (dev) builds the dev-desktop.sh script is responsible for
        // starting convsim-core before Tauri. Wait briefly in case of a race.
        if cfg!(debug_assertions) {
            for _ in 0..20u32 {
                std::thread::sleep(Duration::from_millis(500));
                if is_port_open(CORE_PORT) {
                    emit_core_status(&app, &status_arc, "ready", "Core service is ready.", None);
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
            );
            return;
        }

        // ── Release mode: find, launch, and supervise convsim-core ───────────

        emit_core_status(&app, &status_arc, "starting", "Locating core service…", None);

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
                );
                return;
            }
        };

        emit_core_status(&app, &status_arc, "starting", "Starting core service…", None);

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
        if let Ok(data_dir) = app.path().app_data_dir() {
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
                    "Failed to start the core service process. \
                     Check the logs at ~/.convsim/logs for details."
                };
                emit_core_status(&app, &status_arc, "error", hint, Some(&e.to_string()));
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
                            Some("Check the logs at ~/.convsim/logs for details."),
                        );
                        return;
                    }
                }
            }

            if is_port_open(CORE_PORT) {
                emit_core_status(&app, &status_arc, "ready", "Core service is ready.", None);
                return;
            }

            if attempt == 10 {
                emit_core_status(
                    &app,
                    &status_arc,
                    "starting",
                    "Still starting core service — this may take a moment on first run…",
                    None,
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
                 Check the logs at ~/.convsim/logs, then restart the app.",
            ),
        );
    });
}

// ── Public entry point ────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let process_inner: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let status_inner: Arc<Mutex<Option<CoreStatusPayload>>> = Arc::new(Mutex::new(None));

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
        .manage(CoreProcessState(Arc::clone(&process_inner)))
        .manage(CoreStatusState(Arc::clone(&status_inner)))
        .manage(SteamState(Arc::clone(&steam_status)))
        .manage(SteamRuntimeState(Arc::clone(&steam_runtime)))
        .invoke_handler(tauri::generate_handler![
            get_core_status,
            get_steam_status,
            steam_unlock_achievement,
            steam_increment_stat,
            steam_set_rich_presence,
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
