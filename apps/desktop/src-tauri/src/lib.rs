// SPDX-License-Identifier: Apache-2.0
use std::{
    net::SocketAddr,
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::{
        atomic::{AtomicBool, Ordering},
        Arc, Mutex,
    },
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_updater::UpdaterExt;
use tauri_plugin_shell::ShellExt;

mod core_process;
mod steam;

// ── Edition and data root ─────────────────────────────────────────────────────

/// Bundle identifier of the full app. The per-user data root is derived from
/// this constant for EVERY edition so the demo and the full app share one
/// data directory (see `shared_data_root`). Baked in by `build.rs` from the
/// `identifier` in `tauri.conf.json` — the base config, which the demo's
/// merge-patch overlay never touches — so it cannot drift from the directory
/// the full app has always used.
const DATA_ROOT_IDENTIFIER: &str = env!("CONVSIM_DATA_ROOT_IDENTIFIER");

/// Product edition compiled into this binary: `Some("demo")` for the Steam
/// Next Fest demo, `None` for the full app. Read from the CONVSIM_EDITION
/// build-time environment variable, which `build.rs` validates.
fn build_edition() -> Option<&'static str> {
    match option_env!("CONVSIM_EDITION") {
        Some("demo") => Some("demo"),
        _ => None,
    }
}

/// Registry id of the model a demo build installs, baked in from the
/// CONVSIM_DEMO_MODEL_ID build-time variable (`build.rs` validates it). `None`
/// means "whatever the registry's `role: starter` entry is", which is the
/// engine's own default. Only read for a demo build: Steam launches a packaged
/// app with none of our environment, so a run-time variable would never arrive.
fn build_demo_model_id() -> Option<&'static str> {
    option_env!("CONVSIM_DEMO_MODEL_ID")
        .map(str::trim)
        .filter(|id| !id.is_empty())
}

/// The per-user data root every edition shares: `<local data>/<DATA_ROOT_IDENTIFIER>`.
///
/// Handed to convsim-core as `CONVSIM_DATA_ROOT` and used for the log directory
/// the recovery card shows, so the two can never disagree. (The demo bundle's
/// own `app_local_data_dir()` would be keyed to the demo identifier — an empty
/// folder nothing writes to.)
///
/// The *local* data dir, not `app_data_dir()`: on Windows the latter is
/// %APPDATA% (the Roaming profile), which some sync tools and enterprise
/// policies replicate across machines — a poor home for GBs of model files and
/// private conversation data. `local_data_dir()` is %LOCALAPPDATA%, matching
/// paths.py's Windows convention. On macOS and Linux the two are identical.
fn shared_data_root(app: &AppHandle) -> Option<PathBuf> {
    app.path()
        .local_data_dir()
        .ok()
        .map(|p| p.join(DATA_ROOT_IDENTIFIER))
}

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

/// Whether the updater plugin was registered at startup.  Steam builds ship
/// with `plugins.updater` removed from the merged Tauri config (Steam owns
/// updates via SteamPipe), so the plugin is not registered — see `run()`.
struct UpdaterEnabledState(bool);

/// Check for a beta update.  Fails silently when offline or when the updater
/// manifest is unavailable — the frontend shows nothing in that case.
#[tauri::command]
async fn check_for_update(
    app: AppHandle,
    enabled: tauri::State<'_, UpdaterEnabledState>,
    state: tauri::State<'_, PendingUpdateState>,
) -> Result<Option<UpdateInfo>, String> {
    // Steam builds do not register the updater plugin at all; touching
    // `app.updater()` without the plugin's managed state would panic (and with
    // `panic = "abort"` take the whole app down). Report "no update" — Steam
    // delivers updates through SteamPipe.
    if !enabled.0 {
        return Ok(None);
    }
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

/// Open the Steam overlay (equivalent to the Shift+Tab chord).
///
/// The front-end forwards Shift+Tab here because the chord is delivered to the
/// WebView2 child process and never reaches Steam's input hook — see
/// `useSteamOverlay` on the front-end and `SteamRuntime::activate_overlay`.
/// Returns `false` when not running under Steam or the `steam` feature is off.
#[tauri::command]
fn steam_activate_overlay(state: tauri::State<'_, SteamRuntimeState>) -> bool {
    state
        .0
        .lock()
        .map(|r| r.activate_overlay())
        .unwrap_or(false)
}

/// Open the Steam overlay on the store page of `app_id` — the demo edition's
/// upsell to the full game (issue #495). Returns `false` outside Steam, with
/// the overlay disabled, or without the `steam` feature; the front-end then
/// opens the web store page in the browser instead.
#[tauri::command]
fn steam_open_store_page(app_id: u32, state: tauri::State<'_, SteamRuntimeState>) -> bool {
    state
        .0
        .lock()
        .map(|r| r.open_store_page(app_id))
        .unwrap_or(false)
}

/// Diagnostic readout for the overlay gate (G3-03): whether the Steam client
/// has the overlay enabled, whether the in-process compositing surface is
/// presenting, and why not if it gave up. All-off outside Steam.
#[tauri::command]
fn steam_overlay_status(state: tauri::State<'_, SteamRuntimeState>) -> steam::SteamOverlayStatus {
    state
        .0
        .lock()
        .map(|r| r.overlay_status())
        .unwrap_or_default()
}

/// Take a Steam screenshot (the F12 hotkey) of the main window and add it to
/// the player's Steam screenshot library. The front-end forwards F12 here
/// because, like Shift+Tab, the key lands in the WebView2 process where
/// Steam's hotkey hook cannot see it — see `SteamRuntime::trigger_screenshot`.
/// Returns `false` when not running under Steam or capture is unsupported.
#[tauri::command]
fn steam_trigger_screenshot(app: AppHandle, state: tauri::State<'_, SteamRuntimeState>) -> bool {
    state
        .0
        .lock()
        .map(|r| r.trigger_screenshot(&app))
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

/// Check whether a Steam DLC App is currently installed (owned and downloaded)
/// for the current user.
///
/// `dlc_app_id` is the Valve-assigned Steam App ID for the DLC — not the base
/// game's App ID. Use the pack-id → DLC App ID registry (built from
/// `VITE_STEAM_DLC_APP_IDS` at compile time) to resolve a pack ID before
/// calling this command.
///
/// Returns `false` when not running under Steam or the `steam` feature is off.
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

/// Owns the convsim-core child process, plus the flag that tells the supervisor
/// thread the app is on its way out.
///
/// Without the flag a core we killed on purpose during teardown is
/// indistinguishable from one that crashed, and the supervisor would respawn an
/// engine on top of a closing window — leaving an orphan holding port 7355 that
/// the next launch then reports as a port conflict.
struct CoreProcessState {
    child: Arc<Mutex<Option<Child>>>,
    shutting_down: Arc<AtomicBool>,
}

impl Drop for CoreProcessState {
    fn drop(&mut self) {
        self.shutting_down.store(true, Ordering::SeqCst);
        if let Ok(mut guard) = self.child.lock() {
            if let Some(mut child) = guard.take() {
                core_process::shutdown(&mut child);
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

// ── Readiness probe ───────────────────────────────────────────────────────────

/// The loopback port convsim-core binds. Fixed on purpose: the web client
/// hardcodes the same number (apps/web/src/api/client.ts) and the whole stack
/// is loopback-only, so there is nothing to negotiate.
const CORE_PORT: u16 = 7355;

const HEALTH_REQUEST: &[u8] = b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\n\
                                Accept: application/json\r\nConnection: close\r\n\r\n";

/// Total wall-clock a single probe spends writing and reading, regardless of
/// how the occupant paces its answer.
///
/// Sized from the engine's own worst case rather than picked round, because a
/// budget *below* it turns a healthy convsim-core into `CoreProbe::Occupied` —
/// and the shell then tells the player to close the program holding port 7355,
/// which is their own engine. `/api/health` awaits its three probes in
/// sequence, and two of them are HTTP calls to sidecars that can be alive but
/// wedged: `LlamaCppRuntime.health()` allows 5 s (`_HEALTH_TIMEOUT` in
/// services/convsim-core/convsim_core/runtime/llama_cpp.py) and
/// `KokoroTtsWorker.health()` another 5 s (tts/kokoro.py); STT is filesystem
/// checks only. So a legitimate answer can take just over 10 s, and the budget
/// has to clear that with room for the handshake and the body.
const PROBE_RESPONSE_BUDGET: Duration = Duration::from_secs(14);

/// Hard cap on how much of a probe response is buffered. A real health
/// response is a few kilobytes; this is two orders of magnitude of headroom
/// and still bounds what an unrelated program on the port can make the shell
/// allocate.
const PROBE_RESPONSE_LIMIT: usize = 1024 * 1024;

/// How long a probe waits for the TCP handshake. Loopback either answers at
/// once or has nothing listening, so this only has to outlast a full listen
/// backlog. Shared by `probe_core` and `port_is_listening` so the two cannot
/// disagree about what "nothing is there" means.
const PROBE_CONNECT_TIMEOUT: Duration = Duration::from_millis(300);

/// What is — or is not — answering on 127.0.0.1:`CORE_PORT`.
#[derive(Debug, Clone, PartialEq, Eq)]
enum CoreProbe {
    /// `GET /api/health` answered 200 with a convsim-core body. Carries the
    /// edition it reported (`"full"` for an engine older than the field).
    Ready { edition: String },
    /// Something accepted the connection but did not answer `/api/health`:
    /// either our own engine still inside uvicorn's lifespan startup, or an
    /// unrelated program squatting on the port.
    Occupied,
    /// Nothing is listening.
    Closed,
}

/// Split a raw HTTP/1.1 response into its status code and body.
///
/// Pure, so the parsing is unit-testable without a socket: the shell carries no
/// HTTP client of its own and this plus `edition_from_health_body` is the whole
/// of its client.
fn parse_http_response(raw: &str) -> Option<(u16, &str)> {
    let (head, body) = raw.split_once("\r\n\r\n")?;
    let mut status = head.lines().next()?.split_whitespace();
    // The version token is checked, not skipped: without this a status line
    // like "GARBAGE 200 OK" reads as a 200 from something that never spoke
    // HTTP. `edition_from_health_body` would still reject such an occupant, so
    // this is not the only thing standing between us and adopting a stranger's
    // socket — but a probe that accepts foreign framing as a well-formed
    // response has already lost the thread, and the port is untrusted input.
    if !status.next()?.starts_with("HTTP/") {
        return None;
    }
    Some((status.next()?.parse::<u16>().ok()?, body))
}

/// The `edition` a `/api/health` body reports: `"demo"`, or `"full"` (also for
/// an older engine without the field).
///
/// `None` when the body is not a convsim-core health response at all, so an
/// unrelated local service that happens to answer 200 on this port is reported
/// as a port conflict rather than adopted as our engine.
fn edition_from_health_body(body: &str) -> Option<String> {
    // Tolerate a chunked body: the JSON object is the outermost {...}.
    let start = body.find('{')?;
    let end = body.rfind('}')?;
    // Only when the braces are in that order. A body like "} {" — or a chunked
    // framing whose last chunk ends before the first brace — puts `rfind` ahead
    // of `find`, and `&body[start..=end]` on a reversed range PANICS. Whatever
    // is on port 7355 is untrusted input and this runs on every probe, so that
    // panic is reachable from outside the app; with `panic = "abort"` in the
    // release profile it would take the whole window down rather than merely
    // reporting a port conflict.
    if end < start {
        return None;
    }
    let json: serde_json::Value = serde_json::from_str(&body[start..=end]).ok()?;
    // Three required fields of HealthResponse, not one.
    //
    // `{"status":"ok"}` is the single most common health-response shape there
    // is, and `/api/health` is a common path — so a lone `status` key is not
    // evidence of convsim-core. Adopting such an occupant is exactly the bug
    // this probe exists to prevent, one step deeper: the shell would report
    // ready and mount the UI over a stranger's socket, where every API call
    // fails with nothing on screen to explain it.
    //
    // `status`, `version` and `database` have all been required fields of
    // HealthResponse since the service's first commit, so this rejects nothing
    // that has ever been a convsim-core. (`edition` has not — hence the
    // `"full"` default below.) `database` is checked for its type too: an
    // object there is what makes the trio distinctive rather than three
    // plausible scalars.
    if !json.get("status").is_some_and(serde_json::Value::is_string)
        || !json.get("version").is_some_and(serde_json::Value::is_string)
        || !json.get("database").is_some_and(serde_json::Value::is_object)
    {
        return None;
    }
    Some(
        json.get("edition")
            .and_then(|v| v.as_str())
            .unwrap_or("full")
            .to_string(),
    )
}

/// Probe 127.0.0.1:`port` for a convsim-core that is actually serving.
///
/// A bare TCP connect answers "something is on this port", which is not the
/// question. The shell used to accept that as readiness, so any program holding
/// 7355 — not just our engine — made it declare ready and mount the UI over a
/// stranger's socket, where every API call failed with nothing on screen to
/// explain it. Asking for `/api/health` and requiring a convsim-core body
/// answers the question the shell actually has, and in the same exchange tells
/// it which edition is running (see `foreign_edition_error`).
///
/// (`uvicorn.run()` binds its socket *after* the FastAPI lifespan completes, so
/// for an engine we started ourselves an open port does follow readiness by
/// ~40 ms. That is a property of how the engine is launched, not a contract —
/// and it never distinguished our engine from anybody else's.)
fn probe_core(port: u16) -> CoreProbe {
    probe_core_within(port, PROBE_RESPONSE_BUDGET)
}

/// `probe_core` with the read budget injected, so the "an occupant that never
/// finishes answering" cases are testable without an eight-second test.
fn probe_core_within(port: u16, budget: Duration) -> CoreProbe {
    use std::io::{Read, Write};
    let addr: SocketAddr = ([127u8, 0, 0, 1], port).into();
    let mut stream = match std::net::TcpStream::connect_timeout(&addr, PROBE_CONNECT_TIMEOUT) {
        Ok(s) => s,
        Err(_) => return CoreProbe::Closed,
    };
    // One deadline for the whole exchange, started before the write. A write
    // timeout of its own would be a *second* budget: an occupant that accepts
    // the connection and never reads it stalls `write_all` once its receive
    // window fills, and the probe would then cost up to two budgets — which
    // breaks what `OCCUPIED_GRACE` is sized for (see
    // `the_occupied_grace_allows_a_retry_after_a_full_probe`), because the
    // grace deadline is only consulted *between* probes.
    let deadline = Instant::now() + budget;
    if stream.set_write_timeout(Some(budget)).is_err() || stream.write_all(HEALTH_REQUEST).is_err()
    {
        return CoreProbe::Occupied;
    }

    // `Connection: close` makes a well-behaved server hang up after the body,
    // so the read ends on EOF. The occupant is not necessarily well behaved:
    // this probe exists precisely because the thing on the port may be some
    // other program, and whatever answers is untrusted input.
    //
    // A socket read timeout is per-`read` call, not per-exchange, so
    // `read_to_end` against a peer that dribbles one byte every few seconds
    // never returns — it would hang this thread forever on the "checking
    // whether it is the engine…" screen, and the occupied-grace deadline is
    // only consulted *between* probes, so no error card would ever appear.
    // `read_to_end` is also unbounded in size: on loopback a flood fills
    // memory faster than any timeout can intervene. Bound both.
    let mut raw = Vec::new();
    let mut chunk = [0u8; 8192];
    while raw.len() < PROBE_RESPONSE_LIMIT {
        let remaining = deadline.saturating_duration_since(Instant::now());
        // `set_read_timeout(Some(ZERO))` is an error ("cannot set a 0 duration
        // timeout"), and a zero budget means we are out of time anyway.
        if remaining.is_zero() || stream.set_read_timeout(Some(remaining)).is_err() {
            break;
        }
        match stream.read(&mut chunk) {
            Ok(0) => break,
            Ok(n) => raw.extend_from_slice(&chunk[..n]),
            // A signal interrupted the syscall, not the peer: `read_to_end`
            // retried these, and treating one as the end of the response would
            // read a healthy engine as a port conflict. The deadline above
            // still bounds the retrying.
            Err(e) if e.kind() == std::io::ErrorKind::Interrupted => continue,
            // Timed out, reset, or refused — parse whatever did arrive rather
            // than discarding it.
            Err(_) => break,
        }
    }

    let text = String::from_utf8_lossy(&raw);
    match parse_http_response(&text) {
        Some((200, body)) => match edition_from_health_body(body) {
            Some(edition) => CoreProbe::Ready { edition },
            None => CoreProbe::Occupied,
        },
        _ => CoreProbe::Occupied,
    }
}

/// Whether *anything* is listening on 127.0.0.1:`port`.
///
/// Deliberately not `probe_core`. Readiness needs to know *who* is on the port,
/// which is why that function exists; this answers only "is the socket still
/// there", and `CoreProbe::Closed` is returned exactly when `probe_core`'s own
/// connect fails — so running the `/api/health` exchange to reach the same
/// answer would discard every byte of it. The caller is
/// `wait_for_adopted_core_to_leave`, which runs for as long as the app does:
/// asking for health there would make the shell drive the engine's LLM, STT and
/// TTS probes every `ADOPTED_POLL_INTERVAL` for the whole session to learn
/// something the handshake already said.
fn port_is_listening(port: u16) -> bool {
    let addr: SocketAddr = ([127u8, 0, 0, 1], port).into();
    std::net::TcpStream::connect_timeout(&addr, PROBE_CONNECT_TIMEOUT).is_ok()
}

/// Refuse to attach to the *other* edition's engine (issue #495). The demo
/// and the full app share port 7355 and one data directory, and Steam lets
/// both run at once: the full app attaching to the demo's engine would get a
/// five-conversation library and `EDITION_RESTRICTED` on the Workbench, and
/// the demo attaching to the full engine would show everything the demo
/// hides. Returns the message and hint to report, or `None` when the running
/// engine matches this build.
fn foreign_edition_error(theirs: &str) -> Option<(String, String)> {
    let mine = build_edition().unwrap_or("full");
    if theirs == mine {
        return None;
    }
    let (running, this) = if theirs == "demo" {
        ("Conversation Simulator Demo", "the full version")
    } else {
        ("Conversation Simulator", "the demo")
    };
    Some((
        "Another edition of Conversation Simulator is already running.".to_string(),
        format!(
            "{running} is using the conversation engine on port {port}. \
             Close it, then start {this} again.",
            port = CORE_PORT
        ),
    ))
}

// ── Executable resolution (mirrors the Python three-step order) ───────────────
//
// 1. CONVSIM_CORE_EXECUTABLE env-var override
// 2. CONVSIM_BUNDLED_RUNTIME_DIR/<name> (Steam / packaged builds)
// 3. Tauri resource directory (app bundle)
// 4. PATH lookup

const CORE_BINARY_NAMES: [&str; 2] = ["convsim-core", "convsim-core.exe"];

/// Where the core binary sits relative to the Tauri resource directory.
/// `resources/bin/` is what `scripts/build-core.sh` writes and what the
/// `"resources/**/*"` glob in tauri.conf.json bundles; the shorter paths cover
/// bundlers that flatten the resource tree.
const CORE_RESOURCE_RELATIVE_PATHS: [&str; 6] = [
    "convsim-core",
    "convsim-core.exe",
    "bin/convsim-core",
    "bin/convsim-core.exe",
    "resources/bin/convsim-core",
    "resources/bin/convsim-core.exe",
];

const CORE_NOT_FOUND_MESSAGE: &str = "convsim-core executable not found.\n\
     In dev mode, run ./scripts/setup.sh first (the venv must be active or \
     convsim-core must be on PATH).\n\
     In a packaged build this indicates a bundle issue — please report it at \
     https://github.com/outrightmental/ConversationSimulator/issues";

/// Resolve the core binary from explicitly supplied inputs.
///
/// Split out from `find_core_executable` so the precedence order is unit-tested
/// without mutating process-wide environment variables (which would race across
/// the test threads). `path_lookup` is the final PATH probe, injected so tests
/// can state "not on PATH" without shelling out.
fn resolve_core_executable(
    env_override: Option<&str>,
    bundled_runtime_dir: Option<&str>,
    resource_dir: Option<&Path>,
    path_lookup: impl FnOnce() -> Option<PathBuf>,
) -> Result<PathBuf, String> {
    // 1. Explicit env-var override.
    if let Some(path) = env_override {
        let p = PathBuf::from(path);
        if p.exists() {
            return Ok(p);
        }
        return Err(format!(
            "CONVSIM_CORE_EXECUTABLE is set to '{path}' but that file does not exist."
        ));
    }

    // 2. Bundled runtime dir (Steam / packaged builds).
    if let Some(dir) = bundled_runtime_dir {
        for name in CORE_BINARY_NAMES {
            let p = Path::new(dir).join(name);
            if p.exists() {
                return Ok(p);
            }
        }
    }

    // 3. Tauri resource directory (adjacent to the app bundle).
    if let Some(res) = resource_dir {
        for rel in CORE_RESOURCE_RELATIVE_PATHS {
            let p = res.join(rel);
            if p.exists() {
                return Ok(p);
            }
        }
    }

    // 4. PATH lookup.
    if let Some(p) = path_lookup() {
        return Ok(p);
    }

    Err(CORE_NOT_FOUND_MESSAGE.to_string())
}

/// `which convsim-core` / `where convsim-core`, for dev builds run from a venv.
fn core_on_path() -> Option<PathBuf> {
    let probe = if cfg!(windows) {
        Command::new("where").arg("convsim-core").output()
    } else {
        Command::new("which").arg("convsim-core").output()
    };
    let out = probe.ok()?;
    if !out.status.success() {
        return None;
    }
    let path = String::from_utf8_lossy(&out.stdout)
        .lines()
        .next()?
        .trim()
        .to_string();
    if path.is_empty() {
        None
    } else {
        Some(PathBuf::from(path))
    }
}

fn find_core_executable(resource_dir: Option<&PathBuf>) -> Result<PathBuf, String> {
    let env_override = std::env::var("CONVSIM_CORE_EXECUTABLE").ok();
    let bundled = std::env::var("CONVSIM_BUNDLED_RUNTIME_DIR").ok();
    resolve_core_executable(
        env_override.as_deref(),
        bundled.as_deref(),
        resource_dir.map(|p| p.as_path()),
        core_on_path,
    )
}

// ── Core launch / supervision ─────────────────────────────────────────────────

/// How long a port that is already occupied gets to answer `/api/health` before
/// the shell calls it a conflict. Not instant: `/api/health` aggregates the LLM,
/// STT and TTS probes, so one answer can take seconds, and the occupant may be
/// an engine in the middle of restarting. Only an occupant that stays silent for
/// this long is somebody else's program.
///
/// Must leave room for at least two complete probes; a test pins that against
/// `PROBE_RESPONSE_BUDGET`. The deadline is wall-clock and is only consulted
/// *between* probes, so a grace shorter than two budgets means the first slow
/// answer uses the whole period and a one-off stall — a sidecar HTTP probe
/// timing out once — is reported as a port conflict with no second chance.
const OCCUPIED_GRACE: Duration = Duration::from_secs(30);

/// How long a core the shell started itself gets to answer `/api/health`.
///
/// Sized for the *first* launch after an install, which is the slowest one by a
/// wide margin and the only one a new player ever sees: the PyInstaller one-file
/// binary unpacks its whole payload to a temp directory (every file of which an
/// on-access virus scanner may read first), then the engine migrates the
/// database, seeds six official packs, and seeds the model registry before
/// uvicorn binds. `scripts/packaged-core-smoke.sh` budgets 120 s for exactly
/// that sequence against exactly that binary; the shell must not be stricter
/// than the check that certifies the build, or a slow fresh install shows
/// "did not become ready in time" for an engine that was moments from serving —
/// and a webview reload cannot recover, because the stored status is terminal.
///
/// A longer budget costs nothing in the failure cases it does not cover: an
/// engine that dies instead of hanging is noticed within `PROBE_INTERVAL` by
/// the `try_wait` below, not by this timeout.
const STARTUP_TIMEOUT: Duration = Duration::from_secs(120);

/// How long a dev build waits for the core that `./scripts/dev-desktop.sh` owns.
const DEV_WAIT: Duration = Duration::from_secs(20);

/// Interval between readiness probes, and between checks on a running child.
const PROBE_INTERVAL: Duration = Duration::from_millis(500);

/// How often an engine the shell *adopted* (rather than started) is re-checked.
/// Slower than `PROBE_INTERVAL` because this one runs for the whole session and
/// nothing about it is time critical: the shell is waiting to find out it has to
/// take over, not racing anything. The check itself is a bare connect (see
/// `port_is_listening`), so the engine pays nothing for being watched.
const ADOPTED_POLL_INTERVAL: Duration = Duration::from_secs(3);

/// How many times a core that exits on its own is restarted before the shell
/// gives up and shows the recovery card.
const MAX_RESTARTS: u32 = 3;

/// A core that served healthily for at least this long before dying is a fresh
/// problem, not a restart loop, so earlier crashes stop counting against it.
const HEALTHY_RUN_RESET: Duration = Duration::from_secs(300);

/// Matched by `classifyError` in apps/web/src/screens/CoreStartup.tsx, which
/// turns it into the port-conflict recovery card.
const PORT_BUSY_MESSAGE: &str = "Port 7355 is already in use by another program.";

/// Matched by `classifyError` in apps/web/src/screens/CoreStartup.tsx, which
/// turns it into the "keeps stopping" recovery card. It must stay distinct
/// from the startup failures: this engine *did* start and serve, so a card
/// headed "didn't start" would describe the wrong thing entirely.
const KEEPS_STOPPING_MESSAGE: &str = "The conversation engine keeps stopping.";

/// Matched by `classifyError` in apps/web/src/screens/CoreStartup.tsx, which
/// turns it into the "already running" recovery card.
///
/// Reached when the engine this shell spawned could not bind because a
/// convsim-core of *this* edition took the port first — a second copy of the
/// app launched while this one was still starting. Nothing stops that: there is
/// no single-instance plugin, and the window is as wide as a cold first launch
/// (the installer .exe and the AppImage can both be run twice; Steam and macOS
/// LaunchServices refuse a second launch of their own accord).
///
/// It must not report `PORT_BUSY_MESSAGE`, whose hint tells the player to close
/// "whatever is using that port" — here that is the engine the window they
/// already have is talking to, and following the advice breaks the launch that
/// worked. It also must not be confused with `foreign_edition_error`, which is
/// the same race between the demo and the full app and needs the opposite
/// advice: there, closing the other one is exactly right.
const ALREADY_RUNNING_MESSAGE: &str = "Conversation Simulator is already running.";

fn port_busy_hint() -> String {
    format!(
        "Conversation Simulator needs port {port} on 127.0.0.1, but another program is \
         holding it and does not answer as the conversation engine. Close whatever is using \
         that port, then start the app again.",
        port = CORE_PORT
    )
}

/// The hint beside `ALREADY_RUNNING_MESSAGE`. Names no action against the port:
/// the engine holding it is the one serving the window that did start.
fn already_running_hint() -> String {
    format!(
        "Another window of Conversation Simulator is already using the conversation \
         engine on port {port}. Switch to that window — this one is not needed.",
        port = CORE_PORT
    )
}

/// What to report when a convsim-core — answering `/api/health` with `edition`
/// — holds port 7355 and the engine this shell started therefore cannot.
///
/// The two answers need opposite advice, which is the whole reason this is not
/// one message: the *other* edition has to be closed
/// (`foreign_edition_error`), while an engine of our own edition is the one
/// serving the window that did start, so the player is sent to that window
/// rather than told to kill it.
fn lost_the_port_to_a_convsim_core(edition: &str) -> (String, String) {
    foreign_edition_error(edition)
        .unwrap_or_else(|| (ALREADY_RUNNING_MESSAGE.to_string(), already_running_hint()))
}

/// The progress message shown while the shell is asking an occupied port who
/// holds it. Shared by the two places that ask, so the player sees the same
/// sentence whether the port was taken before our engine started or during.
fn occupant_check_message() -> String {
    format!(
        "Something is already using port {port} — checking whether it is the engine…",
        port = CORE_PORT
    )
}

/// Ask who holds 127.0.0.1:`port`, retrying for up to `grace` while the only
/// answer is `CoreProbe::Occupied`.
///
/// `Occupied` is not an answer, it is the absence of one: the occupant accepted
/// the connection and did not identify itself *this time*. Acting on it directly
/// reports `PORT_BUSY_MESSAGE`, whose hint tells the player to close whatever
/// holds the port — so a convsim-core that was merely slow (`/api/health` awaits
/// the LLM and TTS probes in sequence, 5 s each, and may be behind an engine
/// still bringing a model up) gets the one piece of advice that breaks the launch
/// which worked. The attach loop in `supervise_core` already allows for that with
/// `OCCUPIED_GRACE`, interleaving its own progress messages; this is the same
/// grace for the callers that cannot.
fn identify_port_occupant(port: u16, grace: Duration) -> CoreProbe {
    let deadline = Instant::now() + grace;
    loop {
        let probe = probe_core(port);
        if probe != CoreProbe::Occupied || Instant::now() >= deadline {
            return probe;
        }
        std::thread::sleep(PROBE_INTERVAL);
    }
}

/// The hint beside `KEEPS_STOPPING_MESSAGE`.
///
/// "Restarted {max} times", not "stopped {max} times": the supervisor reaches
/// this on the stop AFTER the last restart, so the engine has died
/// `MAX_RESTARTS + 1` times.
///
/// Its own function so a test can check it against `classifyError`'s patterns —
/// which are matched against the message and the hint concatenated, and try
/// port-conflict first, so a stray "port" here would pick the wrong card.
fn keeps_stopping_hint() -> String {
    format!(
        "It was restarted {max} times and stopped again every time, so it will not be \
         restarted again. Open the logs folder for details, then restart the app.",
        max = MAX_RESTARTS
    )
}

/// Backoff before restart attempt `attempt` (1-based): 1 s, 2 s, 4 s, then 8 s.
fn restart_backoff(attempt: u32) -> Duration {
    Duration::from_secs(1u64 << attempt.saturating_sub(1).min(3))
}

/// Spawn convsim-core with the environment the packaged engine needs.
fn spawn_core(
    app: &AppHandle,
    exe: &Path,
    resource_dir: Option<&PathBuf>,
) -> std::io::Result<Child> {
    // convsim-core reads its bind address from CONVSIM_HOST / CONVSIM_PORT
    // (see services/convsim-core/convsim_core/config.py); it does not parse
    // CLI flags. Set them explicitly so the shell controls the port it polls.
    let mut cmd = Command::new(exe);
    cmd.env("CONVSIM_HOST", "127.0.0.1")
        .env("CONVSIM_PORT", CORE_PORT.to_string())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());

    // Spawn settings the teardown path depends on: a pipe on stdin whose
    // closure asks the engine to shut itself down, and (on Unix) a process
    // group of its own so the whole tree can be signalled at once. Every
    // launch must go through this — `core_process::shutdown` has nothing to
    // ask and nothing to insist to without it. Note it sets stdin itself, so
    // it must come after the `Stdio` calls above rather than before.
    core_process::configure_lifetime(&mut cmd);

    // Pass the OS-native app data directory as CONVSIM_DATA_ROOT so the
    // Python backend uses the same platform-specific location that Tauri
    // considers the app's home for user data (rather than the legacy
    // ~/.convsim dev location). convsim_core.paths.platform_data_root()
    // reads this env var and falls back to OS conventions when it is absent
    // (e.g. in dev mode without Tauri).
    //
    // The directory is keyed by DATA_ROOT_IDENTIFIER, not the bundle's own
    // identifier: the Steam Next Fest demo (issue #495) is a separate Steam
    // app with its own bundle identifier, and it must share this directory
    // with the full app so the model a player downloaded in the demo (and
    // their sessions and logbook) are picked up by the full version instead
    // of being downloaded again. For the full app the two are the same path.
    // See `shared_data_root` for why it is the *local* data dir.
    if let Some(root) = shared_data_root(app) {
        cmd.env("CONVSIM_DATA_ROOT", root);
    }

    // Product edition (issue #495). A demo build is compiled with
    // CONVSIM_EDITION=demo in its environment (see build.rs); it hands the
    // same value to convsim-core so the engine narrows itself to the demo's
    // one model and five conversations. Unset = the full app, and nothing
    // is passed so the engine's own default applies.
    if let Some(edition) = build_edition() {
        cmd.env("CONVSIM_EDITION", edition);
    }

    // The release version the player is running (issue #490). release.yml
    // stamps tauri.conf.json's `version` from the release tag, but the
    // PyInstaller-built core only knows its own package version, so its
    // diagnostics reported `app: 0.1.0` for every build. Hand it the real
    // one; convsim_core.app_version reads it back.
    cmd.env("CONVSIM_APP_VERSION", app.package_info().version.to_string());

    // Tell convsim-core where the bundled sidecar binaries live so it can
    // start llama-server, whisper-cli, and sherpa-onnx-offline-tts without
    // requiring a system PATH entry (Steam build convention).
    //
    // Check both runtimes/ (legacy direct resource) and resources/runtimes/
    // (produced by the "resources/**/*" glob in tauri.conf.json).
    if let Some(res) = resource_dir {
        for runtimes_rel in &["runtimes", "resources/runtimes"] {
            let runtimes = res.join(runtimes_rel);
            if runtimes.exists() {
                cmd.env("CONVSIM_BUNDLED_RUNTIME_DIR", &runtimes);
                break;
            }
        }
    }

    // convsim-core.exe is a console-subsystem binary; spawned from this GUI
    // app without CREATE_NO_WINDOW it allocates a visible console window
    // that pops over the UI for the whole session. Suppress it — core's
    // output still lands in its own log files (and our inherited stdio when
    // launched from a terminal on other platforms).
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(core_process::CREATE_NO_WINDOW);
    }

    cmd.spawn()
}

/// Spawn convsim-core and block until it answers `/api/health`.
///
/// Returns true once the engine is serving. On failure the terminal `error`
/// status has already been emitted — with the message the recovery card needs to
/// classify it — and the caller stops supervising.
fn start_and_await_core(
    app: &AppHandle,
    status_arc: &Arc<Mutex<Option<CoreStatusPayload>>>,
    process_arc: &Arc<Mutex<Option<Child>>>,
    shutting_down: &Arc<AtomicBool>,
    exe: &Path,
    resource_dir: Option<&PathBuf>,
    log_dir: Option<&str>,
) -> bool {
    // Spawn while HOLDING the process lock, after one last look at the teardown
    // flag. Teardown sets the flag and then takes this lock to stop the child,
    // so checking the flag anywhere outside the lock leaves a window in which
    // teardown finds no child, the event loop calls `std::process::exit()`, and
    // the engine spawned a moment later is orphaned on port 7355 — which the
    // next launch then reports as a port conflict. Under the lock the two
    // orders are both safe: either we see the flag and never spawn, or teardown
    // waits for the handle to land and stops it.
    let spawned = {
        let mut guard = match process_arc.lock() {
            Ok(g) => g,
            Err(_) => return false,
        };
        if shutting_down.load(Ordering::SeqCst) {
            return false;
        }
        match spawn_core(app, exe, resource_dir) {
            Ok(child) => {
                *guard = Some(child);
                Ok(())
            }
            Err(e) => Err(e),
        }
    };

    if let Err(e) = spawned {
        let message = if e.kind() == std::io::ErrorKind::PermissionDenied {
            "The core service binary is not executable. \
             This may indicate a corrupted installation — reinstall the app."
        } else {
            "Failed to start the core service process."
        };
        emit_core_status(app, status_arc, "error", message, Some(&e.to_string()), log_dir);
        return false;
    }

    emit_core_status(
        app,
        status_arc,
        "starting",
        "Waiting for core service to be ready…",
        None,
        log_dir,
    );

    let started = Instant::now();
    let mut nudged = false;
    while started.elapsed() < STARTUP_TIMEOUT {
        std::thread::sleep(PROBE_INTERVAL);

        // Detect premature exit instead of waiting out the whole timeout.
        let exited = {
            let mut guard = match process_arc.lock() {
                Ok(g) => g,
                Err(_) => return false,
            };
            match guard.as_mut() {
                Some(child) => child.try_wait().ok().flatten(),
                // Teardown took the handle while we were waiting.
                None => return false,
            }
        };
        if let Some(status) = exited {
            // An engine that dies this early usually could not bind: something
            // took the port between our probe and its bind. Ask the port what
            // it is, the same way the attach path above does, rather than
            // reporting a crash the logs cannot explain.
            //
            // And ask with the same patience, for a sharper version of the same
            // reason. Reaching here means the port was free a moment ago and our
            // child died for failing to bind it, so whatever won that race
            // almost certainly IS a convsim-core — another copy of the app, or
            // the other edition. Taking one unidentified answer as proof of a
            // stranger reports `PORT_BUSY_MESSAGE`, whose hint tells the player
            // to close the program holding port 7355: the engine serving the
            // window that did start.
            let occupant = match probe_core(CORE_PORT) {
                CoreProbe::Occupied => {
                    emit_core_status(
                        app,
                        status_arc,
                        "starting",
                        &occupant_check_message(),
                        None,
                        log_dir,
                    );
                    identify_port_occupant(CORE_PORT, OCCUPIED_GRACE)
                }
                answered => answered,
            };
            let (message, hint) = match occupant {
                // A convsim-core won the race, so ours could not bind. Name the
                // edition when it is the other one: the demo and the full app
                // are separate Steam apps that may be launched together, and a
                // cold start takes long enough (STARTUP_TIMEOUT) that each can
                // still be unpacking while the other probes and finds the port
                // free. Reporting that as "stopped during startup (exit status:
                // 1)" sends the player to logs that only say the port was
                // taken. This path is release-only — the dev branch in
                // `supervise_core` returns before the launch path — so the
                // edition guard applies here unconditionally.
                //
                // A convsim-core of OUR edition is a second copy of this app
                // racing us, not a stranger: `PORT_BUSY_MESSAGE` would send the
                // player to close the engine their other window is using.
                CoreProbe::Ready { edition } => lost_the_port_to_a_convsim_core(&edition),
                CoreProbe::Occupied => (PORT_BUSY_MESSAGE.to_string(), port_busy_hint()),
                // The port is free, so the exit was not a failure to bind.
                CoreProbe::Closed => (
                    format!("Core service stopped during startup (exit status: {status})."),
                    "Open the logs folder for details, then restart the app.".to_string(),
                ),
            };
            // Drop the reaped handle: teardown must not be handed an exited
            // pid, and nothing is left to supervise.
            if let Ok(mut guard) = process_arc.lock() {
                *guard = None;
            }
            emit_core_status(app, status_arc, "error", &message, Some(&hint), log_dir);
            return false;
        }

        if let CoreProbe::Ready { edition } = probe_core(CORE_PORT) {
            // Whoever answers here is not necessarily the child we just
            // spawned. The port was free when the attach loop asked, but
            // another convsim-core can bind it during the tens of seconds ours
            // spends unpacking its payload and migrating the database — and
            // ours then exits for failing to bind, which is *later* than this,
            // so the probe above gets its answer from the winner. Reporting
            // the OTHER edition's engine as ready would mount this build over
            // it: the wrong library, `EDITION_RESTRICTED` on the Workbench
            // (issue #495) — precisely what the attach path's own edition
            // check refuses. Release-only path, so the guard is unconditional
            // for the same reason as the exit branch above.
            if let Some((message, hint)) = foreign_edition_error(&edition) {
                // Stop our own child first. It is still starting, so it never
                // reached its failed bind: left alone it would take port 7355
                // the moment the other edition released it, serving nothing
                // and outliving this now-terminal launch.
                if let Ok(mut guard) = process_arc.lock() {
                    if let Some(mut child) = guard.take() {
                        core_process::shutdown(&mut child);
                    }
                }
                emit_core_status(app, status_arc, "error", &message, Some(&hint), log_dir);
                return false;
            }
            emit_core_status(app, status_arc, "ready", "Core service is ready.", None, log_dir);
            return true;
        }

        if !nudged && started.elapsed() >= Duration::from_secs(8) {
            nudged = true;
            emit_core_status(
                app,
                status_arc,
                "starting",
                "Still starting core service — this may take a moment on first run…",
                None,
                log_dir,
            );
        }
    }

    emit_core_status(
        app,
        status_arc,
        "error",
        "Core service did not become ready in time.",
        Some(&format!(
            "The engine started but did not answer on 127.0.0.1:{port} within {secs}s. \
             Open the logs folder for details, then restart the app.",
            port = CORE_PORT,
            secs = STARTUP_TIMEOUT.as_secs()
        )),
        log_dir,
    );
    false
}

/// Block until the core child exits, the app starts shutting down, or the handle
/// disappears. Returns true only when the child exited on its own — the one case
/// that warrants a restart.
fn wait_for_child_exit(
    process_arc: &Arc<Mutex<Option<Child>>>,
    shutting_down: &Arc<AtomicBool>,
) -> bool {
    loop {
        if shutting_down.load(Ordering::SeqCst) {
            return false;
        }
        std::thread::sleep(Duration::from_secs(1));
        let mut guard = match process_arc.lock() {
            Ok(g) => g,
            Err(_) => return false,
        };
        let child = match guard.as_mut() {
            Some(c) => c,
            // Teardown took the handle — there is nothing left to supervise.
            None => return false,
        };
        match child.try_wait() {
            Ok(Some(_)) => return true,
            Ok(None) => {}
            // The child can no longer be observed; do not guess that it crashed.
            Err(_) => return false,
        }
    }
}

/// Block until nothing is listening on `port` any more, or the app starts
/// shutting down. Returns true only when the port went quiet.
///
/// For an engine the shell adopted rather than started: there is no child handle
/// to supervise, but the shell can still notice it leave and take the port over.
///
/// A socket that still accepts keeps the watch waiting, and that is the right
/// reading even when the engine behind it is too busy to answer a request: the
/// case that matters cannot look like silence anyway, because uvicorn closes its
/// listening socket at the START of its shutdown, well before the process exits.
/// An engine on its way out therefore stops accepting, which is what this sees.
fn wait_for_adopted_core_to_leave(
    port: u16,
    shutting_down: &Arc<AtomicBool>,
    poll: Duration,
) -> bool {
    loop {
        std::thread::sleep(poll);
        // Checked before the probe: on the way out the port goes quiet too, and
        // taking over then would spawn an engine the closing app never stops.
        if shutting_down.load(Ordering::SeqCst) {
            return false;
        }
        if !port_is_listening(port) {
            return true;
        }
    }
}

fn launch_or_verify_core(
    app: AppHandle,
    process_arc: Arc<Mutex<Option<Child>>>,
    status_arc: Arc<Mutex<Option<CoreStatusPayload>>>,
    shutting_down: Arc<AtomicBool>,
) {
    std::thread::spawn(move || {
        supervise_core(app, process_arc, status_arc, shutting_down);
    });
}

fn supervise_core(
    app: AppHandle,
    process_arc: Arc<Mutex<Option<Child>>>,
    status_arc: Arc<Mutex<Option<CoreStatusPayload>>>,
    shutting_down: Arc<AtomicBool>,
) {
    // Compute the platform-specific log directory once so every status event
    // carries the correct absolute path for the recovery card to display.
    //
    // Create it eagerly: convsim-core normally creates logs/ when it runs
    // configure_logging(), but if it never starts (binary missing, immediate
    // exec failure) that never happens — leaving the recovery card's "Open
    // logs folder" button pointing at a non-existent path and dead-ending the
    // very stranded user the card exists to help. Making the directory here
    // guarantees the path shown always exists and is openable.
    //
    // Under the SHARED data root (not the bundle's own app_local_data_dir):
    // convsim-core logs to <CONVSIM_DATA_ROOT>/logs, and for the demo
    // build those two directories differ (issue #495).
    let log_dir: Option<String> = shared_data_root(&app)
        .map(|p| p.join("logs"))
        .map(|p| {
            let _ = std::fs::create_dir_all(&p);
            p.to_string_lossy().into_owned()
        });
    let log_dir_ref = log_dir.as_deref();

    // ── Attach to an engine that is already serving ───────────────────────────
    //
    // One may be: `dev-desktop.sh` started it, or a previous run of the app left
    // it behind, or — on Steam, where the demo and the full app share the port —
    // the other edition is running. An occupant that never answers /api/health
    // is somebody else's program and is reported as a port conflict rather than
    // silently adopted.
    let occupied_deadline = Instant::now() + OCCUPIED_GRACE;
    let mut announced_wait = false;
    loop {
        match probe_core(CORE_PORT) {
            CoreProbe::Ready { edition } => {
                // Release builds must not attach to the other edition's engine.
                // Dev builds skip the check on purpose — `CONVSIM_EDITION=demo
                // ./scripts/dev.sh` runs a demo engine under a shell compiled
                // without the flag, and the web UI adopts the engine's edition
                // from /api/health.
                if !cfg!(debug_assertions) {
                    if let Some((message, hint)) = foreign_edition_error(&edition) {
                        emit_core_status(
                            &app,
                            &status_arc,
                            "error",
                            &message,
                            Some(&hint),
                            log_dir_ref,
                        );
                        return;
                    }
                }
                emit_core_status(
                    &app,
                    &status_arc,
                    "ready",
                    "Core service is ready.",
                    None,
                    log_dir_ref,
                );

                // Dev builds stop here: `dev-desktop.sh` owns that engine, the
                // developer has its terminal, and polling /api/health for the
                // whole session would only add noise to both logs.
                if cfg!(debug_assertions) {
                    return;
                }

                // Release builds keep watching it. An adopted engine is not our
                // child, so it cannot be supervised — but it can be noticed
                // leaving, and it leaves more often than it used to: teardown now
                // drains the engine rather than killing it, and that takes as
                // long as the engine needs, so a player who quits and reopens
                // the app inside that window adopts an engine already on its
                // way out.
                // Without this the UI mounts over a port that disappears a moment
                // later and every request fails with nothing on screen to say why
                // — the exact failure the readiness probe exists to prevent.
                if !wait_for_adopted_core_to_leave(
                    CORE_PORT,
                    &shutting_down,
                    ADOPTED_POLL_INTERVAL,
                ) {
                    return;
                }
                emit_core_status(
                    &app,
                    &status_arc,
                    "restarting",
                    "The conversation engine stopped. Starting a new one…",
                    None,
                    log_dir_ref,
                );
                // Take over: fall through to the launch path below.
                break;
            }
            // Nothing is listening: start our own below.
            CoreProbe::Closed => break,
            CoreProbe::Occupied => {
                if !announced_wait {
                    announced_wait = true;
                    emit_core_status(
                        &app,
                        &status_arc,
                        "starting",
                        &occupant_check_message(),
                        None,
                        log_dir_ref,
                    );
                }
                if Instant::now() >= occupied_deadline {
                    emit_core_status(
                        &app,
                        &status_arc,
                        "error",
                        PORT_BUSY_MESSAGE,
                        Some(&port_busy_hint()),
                        log_dir_ref,
                    );
                    return;
                }
                std::thread::sleep(PROBE_INTERVAL);
            }
        }
    }

    // ── Dev builds: the dev script owns the engine ────────────────────────────
    //
    // `./scripts/dev-desktop.sh` starts convsim-core before Tauri. Wait in case
    // of a startup race, then explain rather than starting a second one.
    if cfg!(debug_assertions) {
        let deadline = Instant::now() + DEV_WAIT;
        while Instant::now() < deadline {
            std::thread::sleep(PROBE_INTERVAL);
            if let CoreProbe::Ready { .. } = probe_core(CORE_PORT) {
                emit_core_status(
                    &app,
                    &status_arc,
                    "ready",
                    "Core service is ready.",
                    None,
                    log_dir_ref,
                );
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

    // ── Release mode: find, launch, and supervise convsim-core ───────────────

    emit_core_status(
        &app,
        &status_arc,
        "starting",
        "Locating core service…",
        None,
        log_dir_ref,
    );

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

    emit_core_status(
        &app,
        &status_arc,
        "starting",
        "Starting core service…",
        None,
        log_dir_ref,
    );

    if !start_and_await_core(
        &app,
        &status_arc,
        &process_arc,
        &shutting_down,
        &exe,
        resource_dir.as_ref(),
        log_dir_ref,
    ) {
        return;
    }

    // ── Keep it running ──────────────────────────────────────────────────────
    //
    // The engine can die under a running window — the OOM killer during a model
    // load, a sidecar taking it down, a bad GGUF. Nothing used to notice, so
    // every request from then on failed against a dead port with no explanation
    // anywhere in the UI. Restart it a bounded number of times, and when that
    // stops working say so instead of retrying forever.
    let mut restarts: u32 = 0;
    loop {
        let ready_since = Instant::now();

        if !wait_for_child_exit(&process_arc, &shutting_down) {
            return;
        }
        if shutting_down.load(Ordering::SeqCst) {
            return;
        }

        // Drop the reaped handle before respawning so teardown never waits on a
        // zombie and teardown is never handed an exited pid.
        if let Ok(mut guard) = process_arc.lock() {
            *guard = None;
        }

        // A convsim-core still serving 7355 now means the engine that just
        // exited was never the one on the port: another copy of the app (or the
        // other edition) won the bind race while ours was starting, and the
        // readiness probe answered for the winner. Restarting cannot help —
        // every replacement fails the same bind — so say which window to use
        // instead of flapping the UI through MAX_RESTARTS attempts and landing
        // on "keeps stopping", which blames the engine for a port it never had.
        // A genuine crash leaves the port closed (uvicorn drops its listening
        // socket before the process goes), so this costs a refused connect.
        if let CoreProbe::Ready { edition } = probe_core(CORE_PORT) {
            let (message, hint) = lost_the_port_to_a_convsim_core(&edition);
            emit_core_status(&app, &status_arc, "error", &message, Some(&hint), log_dir_ref);
            return;
        }

        if ready_since.elapsed() >= HEALTHY_RUN_RESET {
            restarts = 0;
        }
        restarts += 1;

        if restarts > MAX_RESTARTS {
            emit_core_status(
                &app,
                &status_arc,
                "error",
                KEEPS_STOPPING_MESSAGE,
                Some(&keeps_stopping_hint()),
                log_dir_ref,
            );
            return;
        }

        emit_core_status(
            &app,
            &status_arc,
            "restarting",
            &format!(
                "The conversation engine stopped unexpectedly. \
                 Restarting… (attempt {restarts} of {max})",
                max = MAX_RESTARTS
            ),
            None,
            log_dir_ref,
        );

        std::thread::sleep(restart_backoff(restarts));
        if shutting_down.load(Ordering::SeqCst) {
            return;
        }

        if !start_and_await_core(
            &app,
            &status_arc,
            &process_arc,
            &shutting_down,
            &exe,
            resource_dir.as_ref(),
            log_dir_ref,
        ) {
            return;
        }
    }
}

// ── Public entry point ────────────────────────────────────────────────────────

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let process_inner: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
    let status_inner: Arc<Mutex<Option<CoreStatusPayload>>> = Arc::new(Mutex::new(None));
    let pending_update_inner: Arc<Mutex<Option<String>>> = Arc::new(Mutex::new(None));

    // Set before the engine is stopped on the way out so the supervisor thread
    // can tell a deliberate teardown from a crash and does not restart a core on
    // top of a closing window. Moved into the setup closure; the clones below
    // serve the managed state and the exit handler.
    let shutting_down: Arc<AtomicBool> = Arc::new(AtomicBool::new(false));
    let shutting_down_for_state = Arc::clone(&shutting_down);
    let shutting_down_on_exit = Arc::clone(&shutting_down);

    // Kept for the `RunEvent::Exit` handler below. Relying on `CoreProcessState`'s
    // `Drop` alone is not enough: on desktop the tao event loop terminates the
    // process via `std::process::exit()` when the app exits, so managed-state
    // destructors are never run and `convsim-core` would be orphaned (leaving
    // port 7355 held). Tearing the child down explicitly on `RunEvent::Exit` is
    // the reliable path; `Drop` remains as a backstop for other exit paths.
    //
    // `RunEvent::Exit` is also the LAST point at which we can wait for the
    // engine: once this handler returns the event loop exits the process, and
    // whatever is still running becomes an orphan Steam counts as the game
    // still being open (issue #485). `core_process::shutdown` therefore blocks
    // until the whole tree is down.
    let process_on_exit = Arc::clone(&process_inner);

    // Initialise the Steam bridge early so the status is available before the
    // webview requests it. Gracefully returns a disabled status when Steam is
    // absent or the `steam` Cargo feature is off. The runtime handle is kept
    // alive for the process lifetime to service achievement/stat/rich-presence
    // commands.
    //
    // ORDER MATTERS: this must run before `tauri::Builder` builds anything.
    // Steam's injected overlay DLL hooks graphics device/swapchain creation, so
    // `SteamAPI_Init` has to be resident before the overlay-surface plugin
    // (registered below) creates its wgpu device — or the Present hook misses
    // the decoy swapchain and the overlay never draws.
    let (steam_status_val, steam_runtime_val) = steam::init();
    let steam_sdk_up = steam_status_val.is_steam_enabled;
    let steam_status = Arc::new(Mutex::new(steam_status_val));
    let steam_runtime = Arc::new(Mutex::new(steam_runtime_val));
    let steam_runtime_for_setup = Arc::clone(&steam_runtime);

    // Register the updater plugin ONLY when the merged Tauri config actually
    // carries an updater entry.
    //
    // Steam builds pass `--config tauri.steam.conf.json`, whose
    // `"updater": null` removes the key from the merged config (JSON Merge
    // Patch, RFC 7396) so the app never polls GitHub for updates — Steam owns
    // updates via SteamPipe. But `tauri_plugin_updater` REQUIRES its config
    // (`pubkey` is a mandatory field): registering it while the config key is
    // absent makes plugin initialisation fail, and with `panic = "abort"` the
    // app dies before a window ever appears (Windows fail-fast 0xc0000409).
    // That was exactly the "app doesn't launch" failure in the v0.2.4 Steam
    // build (BuildID 24354771) — and invisible in non-Steam builds, whose
    // tauri.conf.json carries a full updater config.
    let context = tauri::generate_context!();
    let updater_enabled = context
        .config()
        .plugins
        .0
        .get("updater")
        .map(|v| !v.is_null())
        .unwrap_or(false);

    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init());
    if updater_enabled {
        builder = builder.plugin(tauri_plugin_updater::Builder::new().build());
    }

    // Steam overlay compositing surface (Windows, Steam builds only).
    //
    // Steam draws its overlay by hooking the game's graphics `Present` call.
    // This process never presents a swapchain of its own — WebView2 renders
    // out-of-process and composites through DWM — so without this plugin the
    // overlay opens (every Steamworks signal reports success) but has nothing
    // to draw into and Shift+Tab looks dead. The plugin creates a transparent,
    // click-through window over the main window with a real swapchain
    // presenting empty frames at vsync for Steam to composite into. See
    // docs/STEAM_INTEGRATION.md, "Steam overlay (Windows WebView2 caveat)".
    //
    // Registered only when `SteamAPI_Init` succeeded: without a Steam client
    // there is no overlay to host, and a decoy window presenting frames for
    // nobody would be pure GPU waste (the depot exe also runs outside Steam).
    #[cfg(all(feature = "steam", windows))]
    if steam_sdk_up {
        builder = builder.plugin(
            tauri_plugin_steam_overlay_surface::Builder::new()
                .main_window_label("main")
                .overlay_title("Conversation Simulator (Steam overlay surface)")
                .snapshot_backdrop(true)
                .build(),
        );
    }
    #[cfg(not(all(feature = "steam", windows)))]
    let _ = steam_sdk_up;

    let app = builder
        .manage(UpdaterEnabledState(updater_enabled))
        .manage(CoreProcessState {
            child: Arc::clone(&process_inner),
            shutting_down: shutting_down_for_state,
        })
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
            steam_show_floating_keyboard,
            steam_hide_floating_keyboard,
            steam_activate_overlay,
            steam_open_store_page,
            steam_overlay_status,
            steam_trigger_screenshot,
            steam_is_dlc_installed,
            steam_workshop_get_subscribed_items,
            steam_workshop_publish_pack,
            steam_workshop_unsubscribe,
        ])
        .setup(move |app| {
            launch_or_verify_core(
                app.handle().clone(),
                Arc::clone(&process_inner),
                Arc::clone(&status_inner),
                Arc::clone(&shutting_down),
            );
            // Forward the Steamworks callbacks the overlay surface needs
            // (GameOverlayActivated → input handoff; ScreenshotRequested →
            // live F12 capture). No-op outside Steam / without the feature.
            if let Ok(mut runtime) = steam_runtime_for_setup.lock() {
                runtime.wire_overlay_callbacks(app.handle().clone());
            }
            Ok(())
        })
        .build(context)
        .expect("error while building tauri application");

    app.run(move |_app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            // Flag first: the supervisor thread must see a deliberate shutdown
            // before the child disappears, or it reads the exit as a crash and
            // starts a replacement engine the closing app will never stop.
            shutting_down_on_exit.store(true, Ordering::SeqCst);
            if let Ok(mut guard) = process_on_exit.lock() {
                // `take()`, so the `Drop` backstop does not run the whole
                // teardown a second time against a process already reaped, and
                // so `CoreProcessState::drop` has nothing left to stop if it
                // does get a chance to run.
                if let Some(mut child) = guard.take() {
                    let outcome = core_process::shutdown(&mut child);
                    eprintln!("convsim-core shutdown: {}", outcome.as_str());
                }
            }
        }
    });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    // ── HTTP response parsing ────────────────────────────────────────────────

    #[test]
    fn parses_status_and_body() {
        let raw = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\"status\":\"ok\"}";
        let (code, body) = parse_http_response(raw).expect("parsed");
        assert_eq!(code, 200);
        assert_eq!(body, "{\"status\":\"ok\"}");
    }

    #[test]
    fn reads_a_non_200_status() {
        let (code, _) =
            parse_http_response("HTTP/1.1 503 Service Unavailable\r\n\r\n{}").expect("parsed");
        assert_eq!(code, 503);
    }

    #[test]
    fn rejects_a_response_with_no_header_terminator() {
        assert!(parse_http_response("HTTP/1.1 200 OK\r\nContent-Type: text/plain").is_none());
    }

    #[test]
    fn rejects_a_status_line_that_is_not_http() {
        // One token, so there is no status code to find at all.
        assert!(parse_http_response("GARBAGE\r\n\r\nbody").is_none());
        // And the case this test used to miss: a status line shaped exactly
        // like HTTP's, carrying a parseable code, whose version token is not
        // HTTP. Only the version check rejects this one.
        assert!(parse_http_response("GARBAGE 200 OK\r\n\r\n{\"status\":\"ok\"}").is_none());
        // A lowercase or truncated version is not HTTP/1.x either.
        assert!(parse_http_response("http/1.1 200 OK\r\n\r\n{}").is_none());
    }

    // ── Health body ──────────────────────────────────────────────────────────

    /// The smallest body that is genuinely a convsim-core health response: the
    /// three required fields `edition_from_health_body` takes as proof of
    /// identity, plus whatever *extra* the caller wants appended.
    fn health_body(extra: &str) -> String {
        format!(
            "{{\"status\":\"ok\",\"version\":\"0.1.0\",\
             \"database\":{{\"status\":\"ok\",\"path\":\"/tmp/convsim.db\"}}{extra}}}"
        )
    }

    #[test]
    fn a_health_body_without_an_edition_field_reads_as_full() {
        // An engine older than the edition field (issue #495) is the full app.
        assert_eq!(edition_from_health_body(&health_body("")).as_deref(), Some("full"));
    }

    #[test]
    fn a_health_body_reports_the_demo_edition() {
        assert_eq!(
            edition_from_health_body(&health_body(",\"edition\":\"demo\"")).as_deref(),
            Some("demo")
        );
    }

    #[test]
    fn a_chunked_health_body_still_parses() {
        let json = health_body(",\"edition\":\"full\"");
        let framed = format!("{:x}\r\n{json}\r\n0\r\n\r\n", json.len());
        assert_eq!(edition_from_health_body(&framed).as_deref(), Some("full"));
    }

    #[test]
    fn a_stranger_on_the_port_is_not_mistaken_for_the_engine() {
        // Valid JSON, but not a convsim-core health response: an unrelated local
        // service answering 200 must read as a port conflict, not as ready.
        assert!(edition_from_health_body("{\"hello\":\"world\"}").is_none());
        assert!(edition_from_health_body("<html>not json</html>").is_none());
    }

    #[test]
    fn a_generic_health_response_is_not_evidence_of_convsim_core() {
        // `{"status":"ok"}` is the most common health-response shape there is,
        // and `/api/health` is a common path — so a lone `status` key cannot be
        // what identifies our engine. An occupant answering it would otherwise
        // be adopted as convsim-core and the UI mounted over its socket, which
        // is the failure this whole probe exists to prevent.
        assert!(edition_from_health_body("{\"status\":\"ok\"}").is_none());
        assert!(edition_from_health_body("{\"status\":\"UP\",\"version\":\"2.1\"}").is_none());
        // A `status` key that is present but not a string is not it either.
        assert!(edition_from_health_body(
            "{\"status\":null,\"version\":\"0.1.0\",\"database\":{}}"
        )
        .is_none());
        // Nor is a `database` that is a plausible scalar rather than the object
        // HealthResponse declares.
        assert!(edition_from_health_body(
            "{\"status\":\"ok\",\"version\":\"0.1.0\",\"database\":\"ok\"}"
        )
        .is_none());
    }

    #[test]
    fn a_body_whose_braces_are_reversed_does_not_panic() {
        // The outermost-{...} scan takes `find('{')` and `rfind('}')`; when the
        // closing brace comes first that is a reversed range, and slicing one
        // panics. The body comes from whatever holds port 7355 — untrusted
        // input on the shell's hottest path — and the release profile is
        // `panic = "abort"`, so a panic here is an app crash, not a bad probe.
        assert!(edition_from_health_body("} {").is_none());
        assert!(edition_from_health_body("}{").is_none());
        assert!(edition_from_health_body("oops } mid { text").is_none());
        // And a body carrying only one of the two braces.
        assert!(edition_from_health_body("}").is_none());
        assert!(edition_from_health_body("{").is_none());
    }

    #[test]
    fn a_probe_response_with_reversed_braces_reads_as_occupied() {
        // The same input through the whole probe: an occupant answering 200
        // with that body is a port conflict, and the shell survives to say so.
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let _ = stream.read(&mut buf);
            let _ = stream.write_all(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n\
                  Content-Length: 3\r\nConnection: close\r\n\r\n} {",
            );
        });
        assert_eq!(probe_core(port), CoreProbe::Occupied);
        let _ = server.join();
    }

    // ── Edition guard ────────────────────────────────────────────────────────

    #[test]
    fn an_engine_of_this_edition_is_adopted() {
        // Read from the build rather than hardcoded to "full": `cargo test` now
        // runs from desktop-smoke.sh, and a developer checking a demo build runs
        // that with CONVSIM_EDITION=demo — which would turn a working guard into
        // two red tests that say nothing about the guard.
        let mine = build_edition().unwrap_or("full");
        assert!(foreign_edition_error(mine).is_none());
    }

    #[test]
    fn the_other_edition_is_refused() {
        let theirs = if build_edition() == Some("demo") {
            "full"
        } else {
            "demo"
        };
        let (message, hint) = foreign_edition_error(theirs).expect("refused");
        assert!(message.contains("Another edition"));
        assert!(hint.contains("7355"));
    }

    #[test]
    fn losing_the_port_names_the_edition_that_took_it() {
        // Every place the shell finds a convsim-core on 7355 that is not the
        // child it started routes through this, because the two answers need
        // opposite advice: close the other edition, but switch to the other
        // window of our own.
        let mine = build_edition().unwrap_or("full");
        let theirs = if mine == "demo" { "full" } else { "demo" };

        let (message, hint) = lost_the_port_to_a_convsim_core(mine);
        assert_eq!(message, ALREADY_RUNNING_MESSAGE);
        assert_eq!(hint, already_running_hint());
        assert!(
            !hint.to_lowercase().contains("close"),
            "the engine on the port is the one serving the window that started: {hint}"
        );

        let (message, _) = lost_the_port_to_a_convsim_core(theirs);
        assert!(message.contains("Another edition"), "{message}");
    }

    #[test]
    fn the_foreign_edition_message_is_what_the_recovery_card_classifies() {
        // apps/web/src/screens/CoreStartup.tsx matches /another edition/ to pick
        // a card that names the real fix — close the OTHER Conversation
        // Simulator. Without it this fell through to 'crash', headed "The
        // conversation engine didn't start": an engine is running perfectly
        // well here, just the wrong one, and the message explaining that is not
        // one of the strings the card displays.
        //
        // classifyError matches against `${message} ${error}`, so the hint
        // counts too. The edition branch is checked first, but the hint says
        // "port 7355" and the generic port-conflict card tells the player to
        // close an unrelated program — so keep the two readable apart.
        let theirs = if build_edition() == Some("demo") {
            "full"
        } else {
            "demo"
        };
        let (message, hint) = foreign_edition_error(theirs).expect("refused");
        let text = format!("{message} {hint}").to_lowercase();
        assert!(text.contains("another edition"));
        assert!(!text.contains("in use"));
        assert!(!text.contains("busy"));
        assert!(!text.contains("port conflict"));
        assert!(!text.contains("keeps stopping"));
        assert!(!text.contains("not found"));
    }

    // ── Startup budget ───────────────────────────────────────────────────────

    #[test]
    fn the_startup_budget_is_not_stricter_than_the_packaged_smoke_check() {
        // scripts/packaged-core-smoke.sh gives the same binary READY_TIMEOUT
        // seconds to answer /api/health, and that is the check CI uses to
        // certify a build. If the shell were stricter, a first launch slow
        // enough to matter would be declared a failure by the shipped app and a
        // success by the pipeline that released it.
        let script = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../../scripts/packaged-core-smoke.sh");
        let Ok(text) = std::fs::read_to_string(&script) else {
            // Building from a source tree without scripts/ — nothing to pin.
            return;
        };
        let budget: u64 = text
            .lines()
            .find_map(|l| l.trim().strip_prefix("READY_TIMEOUT="))
            .expect("READY_TIMEOUT is declared in packaged-core-smoke.sh")
            .trim()
            .parse()
            .expect("READY_TIMEOUT is a plain number of seconds");
        assert!(
            STARTUP_TIMEOUT.as_secs() >= budget,
            "STARTUP_TIMEOUT is {}s but the packaged smoke check allows the same \
             binary {budget}s to become ready",
            STARTUP_TIMEOUT.as_secs()
        );
    }

    #[test]
    fn the_occupied_grace_allows_a_retry_after_a_full_probe() {
        // The grace deadline is wall-clock and is only consulted BETWEEN probes,
        // so a grace narrower than two budgets gives a slow occupant exactly one
        // attempt: the first probe spends the whole period and the shell reports
        // `PORT_BUSY_MESSAGE` without ever asking again. The occupant whose
        // answer is slow is most often our OWN engine with a wedged sidecar
        // (`/api/health` awaits two 5 s HTTP probes in sequence), and that card
        // tells the player to close the program holding port 7355 — the engine
        // they are waiting for.
        assert!(
            OCCUPIED_GRACE >= PROBE_RESPONSE_BUDGET * 2,
            "OCCUPIED_GRACE is {:?} but one probe may spend {:?}, so a slow \
             occupant gets no second attempt",
            OCCUPIED_GRACE,
            PROBE_RESPONSE_BUDGET
        );
    }

    // ── Restart policy ───────────────────────────────────────────────────────

    #[test]
    fn restart_backoff_grows_then_levels_off() {
        assert_eq!(restart_backoff(1), Duration::from_secs(1));
        assert_eq!(restart_backoff(2), Duration::from_secs(2));
        assert_eq!(restart_backoff(3), Duration::from_secs(4));
        // Clamped, so a long-lived session can never schedule an absurd wait.
        assert_eq!(restart_backoff(9), Duration::from_secs(8));
    }

    #[test]
    fn the_port_busy_message_is_what_the_recovery_card_classifies() {
        // apps/web/src/screens/CoreStartup.tsx matches /port.*in use/ to pick the
        // port-conflict card. Keep the two in step.
        let text = format!("{} {}", PORT_BUSY_MESSAGE, port_busy_hint()).to_lowercase();
        assert!(PORT_BUSY_MESSAGE.contains(&CORE_PORT.to_string()));
        assert!(text.contains("port"));
        assert!(text.contains("in use"));
        // And it must miss the two branches now checked BEFORE port-conflict.
        // Both are about a Conversation Simulator holding the port, and their
        // cards say to switch windows or close the other edition — the opposite
        // of this one's "close whatever is using that port", which is only safe
        // advice when the occupant is not ours. "Already in use" is one word
        // away from matching the already-running branch, so pin it.
        assert!(!text.contains("already running"));
        assert!(!text.contains("another edition"));
    }

    #[test]
    fn the_already_running_message_is_what_the_recovery_card_classifies() {
        // classifyError matches against `${message} ${error}` and tries its
        // branches in order, so this pair must miss every branch above its own:
        // 'another edition' (the demo/full race, which needs the OPPOSITE
        // advice — there, closing the other one is right) and 'port in use'
        // (whose card tells the player to close whatever holds 7355, which here
        // is the engine serving the window that did start).
        let text = format!("{} {}", ALREADY_RUNNING_MESSAGE, already_running_hint()).to_lowercase();
        assert!(text.contains("already running"));
        assert!(!text.contains("another edition"));
        assert!(!text.contains("in use"));
        assert!(!text.contains("busy"));
        assert!(!text.contains("port conflict"));
        assert!(!text.contains("keeps stopping"));
        assert!(!text.contains("not found"));
        assert!(!text.contains("executable"));
        assert!(!text.contains("binary"));
        assert!(!text.contains("cannot locate"));
        // And it is not the message an unidentified occupant gets, which is the
        // whole point of telling the two apart.
        assert_ne!(ALREADY_RUNNING_MESSAGE, PORT_BUSY_MESSAGE);
    }

    #[test]
    fn the_keeps_stopping_message_is_what_the_recovery_card_classifies() {
        // apps/web/src/screens/CoreStartup.tsx matches /keeps stopping/ to pick
        // a card that says the engine stopped, not that it never started.
        //
        // classifyError matches against `${message} ${error}` — the hint too —
        // and tries the port-conflict and not-found patterns first, so neither
        // half may read as one of those.
        let text = format!("{} {}", KEEPS_STOPPING_MESSAGE, keeps_stopping_hint()).to_lowercase();
        assert!(text.contains("keeps stopping"));
        assert!(!text.contains("another edition"));
        assert!(!text.contains("already running"));
        assert!(!text.contains("port"));
        assert!(!text.contains("in use"));
        assert!(!text.contains("not found"));
        assert!(!text.contains("executable"));
        assert!(!text.contains("binary"));
        assert!(!text.contains("cannot locate"));
    }

    #[test]
    fn the_keeps_stopping_hint_counts_restarts_not_stops() {
        // The supervisor reaches the give-up branch on the stop AFTER the last
        // restart, so it cannot claim the engine stopped MAX_RESTARTS times.
        let hint = keeps_stopping_hint();
        assert!(hint.contains(&format!("restarted {MAX_RESTARTS} times")));
        assert!(!hint.contains(&format!("stopped {MAX_RESTARTS} times")));
    }

    // ── Executable resolution ────────────────────────────────────────────────

    fn scratch_dir(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("convsim-core-resolve-{name}"));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("create scratch dir");
        dir
    }

    fn touch(path: &Path) {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).expect("create parent dir");
        }
        std::fs::write(path, b"#!/bin/sh\n").expect("write stub binary");
    }

    #[test]
    fn the_env_override_wins_over_every_bundled_location() {
        let dir = scratch_dir("override");
        let override_path = dir.join("my-own-core");
        touch(&override_path);
        let resources = dir.join("resources");
        touch(&resources.join("bin").join("convsim-core"));

        let found = resolve_core_executable(
            Some(override_path.to_str().expect("utf-8 path")),
            None,
            Some(&resources),
            || None,
        )
        .expect("resolved");
        assert_eq!(found, override_path);
    }

    #[test]
    fn an_env_override_pointing_nowhere_is_an_actionable_error() {
        let err = resolve_core_executable(
            Some("/nonexistent/convsim-core"),
            None,
            None,
            // Present on PATH, and still not used: an explicit override that is
            // wrong must be reported, not silently papered over.
            || Some(PathBuf::from("/usr/bin/convsim-core")),
        )
        .expect_err("rejected");
        assert!(err.contains("CONVSIM_CORE_EXECUTABLE"));
    }

    #[test]
    fn the_bundled_runtime_dir_is_preferred_over_the_resource_dir() {
        let dir = scratch_dir("bundled");
        let runtimes = dir.join("runtimes");
        touch(&runtimes.join("convsim-core"));
        let resources = dir.join("resources");
        touch(&resources.join("bin").join("convsim-core"));

        let found = resolve_core_executable(
            None,
            Some(runtimes.to_str().expect("utf-8 path")),
            Some(&resources),
            || None,
        )
        .expect("resolved");
        assert_eq!(found, runtimes.join("convsim-core"));
    }

    #[test]
    fn the_resource_bin_subdirectory_is_found() {
        // What scripts/build-core.sh writes and tauri.conf.json bundles.
        let dir = scratch_dir("resource-bin");
        let resources = dir.join("resources");
        let expected = resources.join("bin").join("convsim-core");
        touch(&expected);

        let found =
            resolve_core_executable(None, None, Some(&resources), || None).expect("resolved");
        assert_eq!(found, expected);
    }

    #[test]
    fn a_path_lookup_is_the_last_resort() {
        let dir = scratch_dir("path-lookup");
        let on_path = dir.join("convsim-core");
        touch(&on_path);

        let found = resolve_core_executable(None, None, None, || Some(on_path.clone()))
            .expect("resolved");
        assert_eq!(found, on_path);
    }

    #[test]
    fn finding_nothing_explains_how_to_fix_it() {
        let err = resolve_core_executable(None, None, None, || None).expect_err("not found");
        assert!(err.contains("convsim-core executable not found"));
        assert!(err.contains("setup.sh"));
    }

    // ── Probing a live socket ────────────────────────────────────────────────

    /// A loopback port nothing is listening on: bind to pick a free one, then
    /// drop the listener.
    fn free_port() -> u16 {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        drop(listener);
        port
    }

    #[test]
    fn a_closed_port_probes_as_closed() {
        assert_eq!(probe_core(free_port()), CoreProbe::Closed);
    }

    #[test]
    fn a_listener_that_answers_nothing_probes_as_occupied() {
        // The shape of an unrelated program squatting on the engine's port: the
        // old TCP-connect check called this "ready" and loaded the UI against it.
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        let server = std::thread::spawn(move || {
            let _ = listener.accept();
        });
        assert_eq!(probe_core(port), CoreProbe::Occupied);
        let _ = server.join();
    }

    #[test]
    fn a_silent_occupant_that_holds_the_connection_cannot_hang_the_probe() {
        // The test above drops its connection as soon as it has accepted it, so
        // the read ends on EOF and the probe's timeout path is never exercised
        // at all. The squatter that matters holds the connection OPEN and says
        // nothing — accepts the socket and then ignores it — which is what a
        // program bound to 7355 for its own reasons looks like. The probe has
        // to come back on its own budget rather than parking the supervisor
        // thread on "checking whether it is the engine…" forever.
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        let (done_tx, done_rx) = std::sync::mpsc::channel::<()>();
        let server = std::thread::spawn(move || {
            let held = listener.accept();
            // Hold both the connection and the listener until the probe is
            // done, so nothing the probe sees is an EOF we handed it early.
            let _ = done_rx.recv();
            drop(held);
        });

        let budget = Duration::from_millis(400);
        let started = Instant::now();
        let probe = probe_core_within(port, budget);
        let elapsed = started.elapsed();
        let _ = done_tx.send(());

        assert_eq!(probe, CoreProbe::Occupied);
        assert!(
            elapsed < Duration::from_secs(3),
            "probe took {elapsed:?} against a {budget:?} budget"
        );
        let _ = server.join();
    }

    #[test]
    fn an_engine_answering_the_health_endpoint_probes_as_ready() {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let _ = stream.read(&mut buf);
            let body = health_body(",\"edition\":\"demo\"");
            let response = format!(
                "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\
                 Content-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.len(),
                body
            );
            let _ = stream.write_all(response.as_bytes());
        });
        assert_eq!(
            probe_core(port),
            CoreProbe::Ready {
                edition: "demo".to_string()
            }
        );
        let _ = server.join();
    }

    #[test]
    fn an_occupant_that_dribbles_forever_cannot_hang_the_probe() {
        // A socket read timeout is per-read, so each byte resets it and
        // `read_to_end` never returns. The supervisor would sit on "checking
        // whether it is the engine…" forever: the occupied-grace deadline is
        // only consulted between probes, so no error card would ever appear.
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let _ = stream.read(&mut buf);
            // One byte every 200 ms, for far longer than the probe's budget.
            for _ in 0..50 {
                if stream.write_all(b"x").is_err() {
                    return;
                }
                std::thread::sleep(Duration::from_millis(200));
            }
        });

        let started = Instant::now();
        let probe = probe_core_within(port, Duration::from_millis(400));
        let elapsed = started.elapsed();

        assert_eq!(probe, CoreProbe::Occupied);
        assert!(
            elapsed < Duration::from_secs(3),
            "probe took {elapsed:?} against a 400ms budget"
        );
        let _ = server.join();
    }

    #[test]
    fn a_flood_on_the_port_is_bounded_rather_than_buffered_whole() {
        // read_to_end has no size cap, and on loopback a flood arrives faster
        // than any timeout can intervene. The probe must stop at the limit.
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let _ = stream.read(&mut buf);
            // Never EOFs: writes until the client gives up and disconnects.
            let block = vec![b'x'; 64 * 1024];
            while stream.write_all(&block).is_ok() {}
        });

        let started = Instant::now();
        // A budget far longer than the flood needs: finishing quickly proves
        // the size cap stopped the read, not the clock.
        let probe = probe_core_within(port, Duration::from_secs(30));
        let elapsed = started.elapsed();

        assert_eq!(probe, CoreProbe::Occupied);
        assert!(
            elapsed < Duration::from_secs(10),
            "probe took {elapsed:?} — the size cap did not stop the read"
        );
        let _ = server.join();
    }

    // ── Watching the child the shell started ─────────────────────────────────

    /// A stand-in engine, as `(program, args)`. The same split
    /// `core_process`'s tests use, and for the same reason: the programs differ
    /// per platform, the behaviours they stand in for do not.
    #[cfg(unix)]
    mod fake_engine {
        /// Dies on its own almost at once — a crash, from the watcher's side.
        pub const EXITS_AT_ONCE: (&str, &[&str]) = ("true", &[]);
        /// Blocks on the launcher's stdin pipe, so it is still running when the
        /// app quits and then leaves as soon as `core_process::shutdown` asks —
        /// which keeps the test's own cleanup off the `GRACE` timeout.
        pub const WAITS_FOR_THE_LAUNCHER: (&str, &[&str]) = ("cat", &[]);
    }

    #[cfg(windows)]
    mod fake_engine {
        pub const EXITS_AT_ONCE: (&str, &[&str]) = ("ping", &["-n", "1", "127.0.0.1"]);
        /// `sort` with no file argument reads stdin to EOF: alive while the pipe
        /// is open, gone when it closes.
        pub const WAITS_FOR_THE_LAUNCHER: (&str, &[&str]) = ("sort", &[]);
    }

    fn spawn_fake_engine((program, args): (&str, &[&str])) -> Child {
        let mut cmd = Command::new(program);
        cmd.args(args).stdout(Stdio::null()).stderr(Stdio::null());
        core_process::configure_lifetime(&mut cmd);
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(core_process::CREATE_NO_WINDOW);
        }
        cmd.spawn()
            .unwrap_or_else(|e| panic!("failed to spawn the stand-in engine {program}: {e}"))
    }

    #[test]
    fn a_child_that_exits_on_its_own_is_reported_for_restart() {
        // The entry point of the whole crash-restart path: `supervise_core`
        // restarts the engine on, and only on, a true from here.
        let child = spawn_fake_engine(fake_engine::EXITS_AT_ONCE);
        let process_arc = Arc::new(Mutex::new(Some(child)));
        let flag = Arc::new(AtomicBool::new(false));
        assert!(wait_for_child_exit(&process_arc, &flag));
    }

    #[test]
    fn a_shutting_down_app_is_not_a_crash() {
        // Teardown stops the engine itself, and its exit must not be read as a
        // crash: a restart then spawns a replacement on top of a closing window
        // that nothing will ever stop — an orphan on port 7355 the next launch
        // reports as a conflict. The flag is checked before the poll, so a
        // teardown already under way is noticed without waiting out an interval.
        let child = spawn_fake_engine(fake_engine::WAITS_FOR_THE_LAUNCHER);
        let process_arc = Arc::new(Mutex::new(Some(child)));
        let flag = Arc::new(AtomicBool::new(true));

        let started = Instant::now();
        assert!(!wait_for_child_exit(&process_arc, &flag));
        assert!(
            started.elapsed() < Duration::from_secs(1),
            "took {:?} to notice a teardown already in progress",
            started.elapsed()
        );

        // Leave nothing behind for the rest of the suite.
        let leftover = process_arc.lock().ok().and_then(|mut g| g.take());
        if let Some(mut child) = leftover {
            core_process::shutdown(&mut child);
        }
    }

    #[test]
    fn a_handle_taken_by_teardown_ends_the_watch() {
        // `RunEvent::Exit` `take()`s the child before stopping it, so the
        // watcher can find the slot empty rather than exited. Nothing is left to
        // supervise either way, and guessing "crashed" here would respawn into a
        // closing app.
        let process_arc: Arc<Mutex<Option<Child>>> = Arc::new(Mutex::new(None));
        let flag = Arc::new(AtomicBool::new(false));
        assert!(!wait_for_child_exit(&process_arc, &flag));
    }

    // ── Watching an adopted engine ───────────────────────────────────────────

    #[test]
    fn an_adopted_core_that_is_already_gone_is_noticed_at_once() {
        let flag = Arc::new(AtomicBool::new(false));
        let started = Instant::now();
        assert!(wait_for_adopted_core_to_leave(
            free_port(),
            &flag,
            Duration::from_millis(50)
        ));
        assert!(
            started.elapsed() < Duration::from_secs(2),
            "took {:?} to notice a port nothing is listening on",
            started.elapsed()
        );
    }

    #[test]
    fn a_shutting_down_app_stops_watching_instead_of_taking_over() {
        // Teardown makes the port go quiet too. If that read as "the engine
        // left", the shell would spawn a replacement on top of a closing window
        // — an orphan holding 7355 that the next launch reports as a conflict.
        let flag = Arc::new(AtomicBool::new(true));
        assert!(!wait_for_adopted_core_to_leave(
            free_port(),
            &flag,
            Duration::from_millis(50)
        ));
    }

    #[test]
    fn a_live_adopted_core_keeps_the_watch_waiting() {
        // The watch must return on the port going quiet, not on the first poll —
        // and it must keep waiting on a socket that accepts without answering
        // anything, which is what a busy engine looks like. This server accepts
        // two connections, says nothing at all to either, and only then stops
        // listening; `accept` blocks until each one arrives, so reaching the
        // second proves the watch polled a live socket and carried on.
        use std::sync::atomic::AtomicUsize;

        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        let accepted = Arc::new(AtomicUsize::new(0));
        let accepted_in_thread = Arc::clone(&accepted);
        std::thread::spawn(move || {
            for _ in 0..2 {
                match listener.accept() {
                    Ok(_) => accepted_in_thread.fetch_add(1, Ordering::SeqCst),
                    Err(_) => break,
                };
            }
            // `listener` drops here: the port goes quiet and the watch returns.
        });

        let flag = Arc::new(AtomicBool::new(false));
        assert!(wait_for_adopted_core_to_leave(
            port,
            &flag,
            Duration::from_millis(50)
        ));
        assert_eq!(
            accepted.load(Ordering::SeqCst),
            2,
            "the watch gave up on a socket that was still accepting"
        );
    }

    // ── Identifying who holds the port ───────────────────────────────────────

    #[test]
    fn a_slow_occupant_gets_a_second_chance_to_identify_itself() {
        // The regression this guards: `start_and_await_core` used to take one
        // `CoreProbe::Occupied` as proof that a stranger held the port, and so
        // reported `PORT_BUSY_MESSAGE` — "close whatever is using that port" —
        // for an engine whose only fault was answering slowly. On that path the
        // occupant is almost always a convsim-core (the port was free moments
        // earlier and our own child just died for failing to bind it), so the
        // program the player would close is the engine serving the window that
        // did start.
        //
        // The stand-in answers nothing at all the first time and a real health
        // body the second, which is what a sidecar HTTP probe timing out once
        // looks like from here. One probe reads it as a conflict; this must not.
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        let server = std::thread::spawn(move || {
            // First connection: accept, read the request, hang up without a
            // response. The probe sees EOF and has nothing to parse.
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 1024];
                let _ = stream.read(&mut buf);
            }
            // Second connection: answer properly.
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buf = [0u8; 1024];
                let _ = stream.read(&mut buf);
                let body = health_body(",\"edition\":\"full\"");
                let _ = stream.write_all(
                    format!(
                        "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\
                         Content-Length: {}\r\nConnection: close\r\n\r\n{}",
                        body.len(),
                        body
                    )
                    .as_bytes(),
                );
            }
        });

        assert_eq!(
            identify_port_occupant(port, Duration::from_secs(5)),
            CoreProbe::Ready {
                edition: "full".to_string()
            }
        );
        let _ = server.join();
    }

    #[test]
    fn an_occupant_that_never_identifies_itself_is_still_a_conflict() {
        // The other half: the grace is bounded, so a program that holds the port
        // for its own reasons is reported rather than waited on forever.
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        let (done_tx, done_rx) = std::sync::mpsc::channel::<()>();
        let server = std::thread::spawn(move || {
            while done_rx.try_recv().is_err() {
                listener
                    .set_nonblocking(true)
                    .expect("set the listener non-blocking");
                if let Ok((stream, _)) = listener.accept() {
                    drop(stream);
                }
                std::thread::sleep(Duration::from_millis(10));
            }
        });

        let started = Instant::now();
        assert_eq!(
            identify_port_occupant(port, Duration::from_millis(600)),
            CoreProbe::Occupied
        );
        let elapsed = started.elapsed();
        let _ = done_tx.send(());
        let _ = server.join();
        assert!(
            elapsed < Duration::from_secs(5),
            "the grace did not bound the retrying: took {elapsed:?}"
        );
    }

    #[test]
    fn a_closed_port_is_not_retried() {
        // `Closed` is an answer — on the lost-bind path it means the exit was not
        // a failure to bind at all — so it must be returned at once rather than
        // costing the whole grace before the crash is reported.
        let started = Instant::now();
        assert_eq!(
            identify_port_occupant(free_port(), Duration::from_secs(30)),
            CoreProbe::Closed
        );
        assert!(
            started.elapsed() < Duration::from_secs(5),
            "a closed port was retried for {:?}",
            started.elapsed()
        );
    }

    #[test]
    fn a_server_that_answers_503_probes_as_occupied() {
        use std::io::{Read, Write};
        let listener = std::net::TcpListener::bind("127.0.0.1:0").expect("bind");
        let port = listener.local_addr().expect("local addr").port();
        let server = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().expect("accept");
            let mut buf = [0u8; 1024];
            let _ = stream.read(&mut buf);
            let _ = stream.write_all(
                b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\
                  Connection: close\r\n\r\n",
            );
        });
        assert_eq!(probe_core(port), CoreProbe::Occupied);
        let _ = server.join();
    }
}
