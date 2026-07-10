// SPDX-License-Identifier: Apache-2.0
use std::{
    net::SocketAddr,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Arc, Mutex},
    time::Duration,
};
use tauri::{AppHandle, Emitter, Manager};

// ── Status events emitted to the front-end ────────────────────────────────────

#[derive(Clone, serde::Serialize)]
struct CoreStatusPayload {
    phase: String,
    message: String,
    error: Option<String>,
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
    //    produced by scripts/build-core.sh (via "resources/**" in tauri.conf.json).
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

        // Tell convsim-core where the bundled sidecar binaries live so it can
        // start llama-server, whisper-cli, and sherpa-onnx-offline-tts without
        // requiring a system PATH entry (Steam build convention).
        //
        // Check both runtimes/ (legacy direct resource) and resources/runtimes/
        // (produced by the "resources/**" glob in tauri.conf.json).
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

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .manage(CoreProcessState(Arc::clone(&process_inner)))
        .manage(CoreStatusState(Arc::clone(&status_inner)))
        .invoke_handler(tauri::generate_handler![get_core_status])
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
