// SPDX-License-Identifier: Apache-2.0
//! Lifetime of the `convsim-core` child process: how it is spawned so that it
//! can be stopped, and how it is stopped so that *nothing it started* survives.
//!
//! ## Why this is not just `Child::kill()`
//!
//! `convsim-core` is not one process. The shipped binary is a PyInstaller
//! **one-file** bundle: the executable we spawn is a bootloader that unpacks
//! itself to a temp directory and runs the real Python server as a child of its
//! own. That server then supervises sidecars of its own — `llama-server`,
//! Kokoro TTS. The handle we hold therefore points at the *outermost* process,
//! and `Child::kill()` (a bare `TerminateProcess` / `SIGKILL`, neither of which
//! the bootloader can forward) takes out only that one.
//!
//! The result, on every platform but most visibly on Windows: the app window
//! closed, `convsim-core.exe` stayed in the task list still holding port 7355,
//! and Steam went on reporting Conversation Simulator as running (issue #485).
//!
//! ## How it is stopped
//!
//! 1. **Ask.** The child is spawned with a pipe on stdin whose write end we
//!    hold for our whole life. Closing it is the shutdown request:
//!    `convsim_core.parent_watch` reads EOF and asks uvicorn for a graceful
//!    stop, which runs the FastAPI lifespan teardown — and *that* is what stops
//!    the sidecars rather than orphaning them. A pipe rather than a signal or a
//!    PID poll, because the kernel closes it when we exit for **any** reason,
//!    including a crash or being killed by Steam, and because PIDs get recycled.
//! 2. **Insist.** If the tree is still up after [`GRACE`], kill all of it: one
//!    signal to the process group on Unix, `taskkill /T` on Windows.
//!
//! Step 1 also covers the one exit the shell cannot tear down itself: an engine
//! spawned by the launch thread in the instant *after* the exit handler has
//! already looked for a child to stop. Nobody holds a handle on it, but it
//! inherited the pipe, so it leaves when the shell's fd closes a moment later.

use std::{
    process::{Child, Command, Stdio},
    time::{Duration, Instant},
};

/// Tells `convsim-core` that its stdin pipe is a launcher heartbeat and that
/// EOF on it means "shut down". Read by `convsim_core.parent_watch`; the engine
/// ignores stdin without it, because stdin is a TTY under a plain terminal run
/// and `/dev/null` under `scripts/dev.sh` — both of which would otherwise look
/// like a launcher that had already exited.
pub const SHUTDOWN_ON_STDIN_EOF_ENV: &str = "CONVSIM_SHUTDOWN_ON_STDIN_EOF";

/// Windows: spawn without allocating a console window. `convsim-core.exe` and
/// `taskkill.exe` are both console-subsystem binaries, and a GUI app spawning
/// one without this flag gets a stray black window over the UI.
#[cfg(windows)]
pub const CREATE_NO_WINDOW: u32 = 0x0800_0000;

/// How long the engine gets to wind itself down after we close its stdin.
///
/// Sized from the engine's own worst case: up to 3 s draining in-flight
/// requests (`GRACEFUL_SHUTDOWN_TIMEOUT` in `convsim_core/main.py`) plus up to
/// 5 s stopping sidecars concurrently (`_TERMINATE_TIMEOUT` in
/// `convsim_core/runtime/sidecar.py`). Any shorter and we would routinely kill
/// a shutdown that was about to succeed. In practice an engine with no model
/// loaded is gone in well under a second.
const GRACE: Duration = Duration::from_secs(10);

/// Unix: how long the process group gets after `SIGTERM` before `SIGKILL`.
#[cfg(unix)]
const TERM_GRACE: Duration = Duration::from_secs(2);

/// Poll interval while waiting for the child to exit. Short enough that the
/// common case — a prompt, clean exit — is not padded out by the wait itself.
const POLL: Duration = Duration::from_millis(50);

/// What it took to stop the engine. Reported for logging and asserted by tests;
/// callers do not branch on it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Shutdown {
    /// It was already gone before we asked — it crashed, or never started.
    AlreadyExited,
    /// It wound itself down after we closed its stdin.
    Graceful,
    /// It outstayed [`GRACE`] and the whole process tree was killed.
    Forced,
}

impl Shutdown {
    /// Short label for the launch log.
    pub fn as_str(self) -> &'static str {
        match self {
            Shutdown::AlreadyExited => "already exited",
            Shutdown::Graceful => "graceful",
            Shutdown::Forced => "forced (process tree killed)",
        }
    }
}

/// Apply the spawn settings [`shutdown`] depends on.
///
/// Every `convsim-core` launch must go through this: without the stdin pipe
/// there is no way to ask for a clean stop, and without the process group there
/// is no way to insist.
pub fn configure_lifetime(cmd: &mut Command) {
    // A pipe, not `Stdio::null()`: the write end is the launcher heartbeat the
    // engine watches. Nothing is ever written to it.
    cmd.stdin(Stdio::piped()).env(SHUTDOWN_ON_STDIN_EOF_ENV, "1");

    #[cfg(unix)]
    {
        use std::os::unix::process::CommandExt;
        // Make the child the leader of a brand-new process group, which the
        // bootloader's Python server and every sidecar either of them starts
        // inherits. That group id is what lets one `killpg` reach all of them.
        cmd.process_group(0);
    }
}

/// Stop `convsim-core` and everything it started.
///
/// Blocks for up to [`GRACE`] (plus, on Unix, [`TERM_GRACE`]) waiting for the
/// tree to go away. That is deliberate: this runs from the app's exit path with
/// the window already gone, and returning before the tree is down is precisely
/// the bug — Steam keeps the game marked as running until the last process in
/// it exits.
pub fn shutdown(child: &mut Child) -> Shutdown {
    shutdown_within(child, GRACE)
}

fn shutdown_within(child: &mut Child, grace: Duration) -> Shutdown {
    // Already dead: nothing to ask, and nothing safe to kill. Observing the
    // exit reaps the child, which frees its pid for reuse — so the process
    // group id derived from that pid may no longer be ours, and signalling it
    // could hit an unrelated process. Leave it alone.
    if matches!(child.try_wait(), Ok(Some(_))) {
        return Shutdown::AlreadyExited;
    }

    // Dropping our end of the pipe is the entire shutdown request.
    drop(child.stdin.take());

    if wait_for_exit(child, grace) {
        return Shutdown::Graceful;
    }

    kill_tree(child);
    // Reap, so the process handle is released.
    let _ = child.wait();
    Shutdown::Forced
}

/// Poll until the child exits or *timeout* elapses. `true` if it exited.
///
/// An error from `try_wait` resolves as "not observable" rather than blocking:
/// the caller's next move is to kill the tree, which is the right response to a
/// child we can no longer watch.
fn wait_for_exit(child: &mut Child, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => return true,
            Err(_) => return false,
            Ok(None) => {}
        }
        if Instant::now() >= deadline {
            return false;
        }
        std::thread::sleep(POLL);
    }
}

/// Kill the child and every descendant, having already given it [`GRACE`] to
/// leave on its own.
#[cfg(unix)]
fn kill_tree(child: &mut Child) {
    // The child leads its own process group (see `configure_lifetime`), so a
    // signal to that group reaches the bootloader, the Python server it
    // re-execs, and any sidecar either of them started — in one call, with no
    // process-tree walking and no race against a sidecar spawned meanwhile.
    //
    // Addressing the group by the child's pid is sound here: we only reach this
    // path with the child unreaped, and the kernel cannot recycle the pid of a
    // process that has not been waited for. For the same reason the child is
    // deliberately NOT reaped between the two signals below — an unreaped
    // leader, even a zombie one, keeps the group id pinned to our group.
    let pgid = child.id() as libc::pid_t;

    // SIGTERM first: the engine and llama-server both shut down cleanly on it.
    unsafe { libc::killpg(pgid, libc::SIGTERM) };
    std::thread::sleep(TERM_GRACE);
    // Then the uncatchable one, for whatever is left.
    unsafe { libc::killpg(pgid, libc::SIGKILL) };
}

/// Resolve one of Windows' own tools under `%SystemRoot%` instead of trusting
/// PATH, so a shadowed or missing PATH entry cannot quietly turn teardown into
/// a no-op. Falls back to the bare name when the variable is somehow unset.
#[cfg(windows)]
fn system32(tool: &str) -> String {
    std::env::var("SystemRoot")
        .map(|root| format!("{root}\\System32\\{tool}"))
        .unwrap_or_else(|_| tool.to_string())
}

/// The `taskkill` arguments that take down *pid* **and every descendant**.
///
/// Split out from [`kill_tree`] so its shape can be asserted on Windows
/// without killing anything. `/T` is the whole point: without it this is the
/// single-process kill that left `convsim-core.exe` in the task list holding
/// port 7355 (issue #485). `/F` because the engine has already had [`GRACE`]
/// to leave politely.
#[cfg(windows)]
fn taskkill_args(pid: u32) -> [String; 4] {
    [
        "/PID".to_string(),
        pid.to_string(),
        "/T".to_string(),
        "/F".to_string(),
    ]
}

/// Kill the child and every descendant, having already given it [`GRACE`] to
/// leave on its own.
#[cfg(windows)]
fn kill_tree(child: &mut Child) {
    use std::os::windows::process::CommandExt;

    // `taskkill /T` walks the parent-pid chain and terminates the whole tree:
    // the bootloader, the Python server it re-execs, and any sidecar either of
    // them started. There is no process-group signal to use instead — the child
    // has no console of its own to receive a CTRL_BREAK_EVENT (it is spawned
    // with CREATE_NO_WINDOW, and this process is a GUI app with no console to
    // share).
    //
    // Addressing it by pid is sound: we hold an open handle to the process, so
    // Windows cannot recycle its pid onto something unrelated.
    //
    // Resolved under %SystemRoot% rather than trusting PATH, so a shadowed or
    // missing PATH entry cannot quietly turn teardown into a no-op.
    let _ = Command::new(system32("taskkill.exe"))
        .args(taskkill_args(child.id()))
        .creation_flags(CREATE_NO_WINDOW)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .status();

    // Backstop: if taskkill itself could not run, at least take out the process
    // we hold a handle on.
    let _ = child.kill();
}

// ── Tests ─────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::ffi::OsStr;

    /// Stand-ins for the engine, as `(program, args)`.
    ///
    /// The programs differ per platform; the behaviours they stand in for do
    /// not, which is why the tests below are shared. Plain executables rather
    /// than shell one-liners: `Stdio` already gives us the redirection, and
    /// avoiding `sh -c` / `cmd /C` keeps quoting out of it.
    #[cfg(unix)]
    mod fake_engine {
        /// Exits when the launcher's end of the stdin pipe closes — what
        /// `parent_watch` makes the real engine do.
        pub const READS_STDIN: (&str, &[&str]) = ("cat", &[]);
        /// Never looks at stdin: a wedged engine, or a bootloader still
        /// unpacking itself when the app quit.
        pub const IGNORES_STDIN: (&str, &[&str]) = ("sleep", &["30"]);
        /// Gone before anybody asks it to stop.
        pub const EXITS_AT_ONCE: (&str, &[&str]) = ("true", &[]);
    }

    #[cfg(windows)]
    mod fake_engine {
        /// `sort` with no file argument is a stdin filter: it reads to EOF and
        /// then exits, which is the engine behaviour under test.
        pub const READS_STDIN: (&str, &[&str]) = ("sort", &[]);
        /// `ping` never reads stdin — and unlike `timeout.exe` it does not
        /// abort when stdin is a pipe rather than a console, which is exactly
        /// how the real engine is spawned.
        pub const IGNORES_STDIN: (&str, &[&str]) = ("ping", &["-n", "31", "127.0.0.1"]);
        /// One echo request and done.
        pub const EXITS_AT_ONCE: (&str, &[&str]) = ("ping", &["-n", "1", "127.0.0.1"]);
    }

    /// Spawn a test child configured exactly as a real core launch is, with its
    /// stdout piped so a test can read what it reports.
    fn spawn_configured(program: &str, args: &[&str]) -> Child {
        let mut cmd = Command::new(program);
        cmd.args(args).stdout(Stdio::piped()).stderr(Stdio::null());
        configure_lifetime(&mut cmd);
        // As in production: these stand-ins are console binaries too, and a
        // test run should not flash console windows.
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(CREATE_NO_WINDOW);
        }
        cmd.spawn()
            .unwrap_or_else(|e| panic!("failed to spawn test child {program}: {e}"))
    }

    /// Read the pid a test child printed on its first line of stdout.
    ///
    /// One byte at a time up to the newline: a block read would park until the
    /// pipe filled or closed, and the child deliberately keeps it open.
    fn read_pid_line(child: &mut Child) -> u32 {
        use std::io::Read;
        let mut out = child.stdout.take().expect("stdout pipe");
        let mut line = Vec::new();
        let mut byte = [0u8; 1];
        loop {
            match out.read(&mut byte) {
                Ok(0) => break,
                Ok(_) if byte[0] == b'\n' => break,
                Ok(_) => line.push(byte[0]),
                Err(e) => panic!("reading the sidecar pid failed: {e}"),
            }
        }
        let text = String::from_utf8_lossy(&line);
        // Strip a BOM explicitly rather than filtering to digits: a stream that
        // arrived in an unexpected encoding must fail here, not get salvaged
        // into some *other* valid-looking pid that the assertions would then
        // happily check for being gone.
        let text = text.trim().trim_start_matches('\u{feff}');
        assert!(
            !text.is_empty(),
            "the test child printed no pid before closing stdout, so it never \
             started the sidecar this test is about"
        );
        text.parse()
            .unwrap_or_else(|e| panic!("sidecar pid {text:?} is not a number: {e}"))
    }

    /// An engine that ignores the closed pipe, which has already started a
    /// grandchild standing in for a sidecar — the process the old teardown left
    /// running. Returns the engine and the sidecar's pid.
    #[cfg(unix)]
    fn spawn_engine_with_sidecar() -> (Child, u32) {
        let mut engine = spawn_configured("sh", &["-c", "sleep 30 & echo $! ; sleep 30"]);
        let sidecar = read_pid_line(&mut engine);
        (engine, sidecar)
    }

    /// As above. PowerShell rather than `cmd`, because `Start-Process
    /// -PassThru` is the only readily available way to start a grandchild *and*
    /// learn its pid, which the assertion needs. The outer `powershell.exe`
    /// stands in for the engine: it sleeps and never reads stdin.
    #[cfg(windows)]
    fn spawn_engine_with_sidecar() -> (Child, u32) {
        // Single-quoted arguments only: the whole script is passed as one argv
        // entry, so embedded double quotes would have to survive two levels of
        // unquoting.
        const SCRIPT: &str = "$ErrorActionPreference = 'Stop'; \
             $p = Start-Process -FilePath ping \
                 -ArgumentList '-n','31','127.0.0.1' -NoNewWindow -PassThru; \
             [Console]::Out.WriteLine($p.Id); \
             [Console]::Out.Flush(); \
             Start-Sleep -Seconds 31";
        let mut engine = spawn_configured(
            "powershell",
            &["-NoProfile", "-NonInteractive", "-Command", SCRIPT],
        );
        let sidecar = read_pid_line(&mut engine);
        (engine, sidecar)
    }

    #[cfg(unix)]
    fn is_alive(pid: u32) -> bool {
        // ESRCH is the only "gone" answer; EPERM means alive but not ours.
        if unsafe { libc::kill(pid as libc::pid_t, 0) } == 0 {
            return true;
        }
        std::io::Error::last_os_error().raw_os_error() == Some(libc::EPERM)
    }

    #[cfg(windows)]
    fn is_alive(pid: u32) -> bool {
        use std::os::windows::process::CommandExt;
        // `tasklist` keeps this dependency-free, and the filter makes the
        // answer unambiguous: a process that is gone produces no row at all, so
        // a pid that happens to appear in some unrelated process's row cannot
        // be mistaken for a match.
        let listed = Command::new(system32("tasklist.exe"))
            .args(["/FI", &format!("PID eq {pid}"), "/NH"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::null())
            .output();
        match listed {
            Ok(out) => String::from_utf8_lossy(&out.stdout).contains(&pid.to_string()),
            // Cannot tell. Report "gone" rather than spinning until the
            // caller's deadline on a question we can no longer answer.
            Err(_) => false,
        }
    }

    fn wait_until_gone(pid: u32, timeout: Duration) -> bool {
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            if !is_alive(pid) {
                return true;
            }
            std::thread::sleep(POLL);
        }
        !is_alive(pid)
    }

    // ── Spawn settings ───────────────────────────────────────────────────────

    #[test]
    fn configure_lifetime_opts_the_engine_into_the_stdin_watch() {
        let mut cmd = Command::new("does-not-need-to-exist");
        configure_lifetime(&mut cmd);
        let opted_in = cmd.get_envs().any(|(key, value)| {
            key == OsStr::new(SHUTDOWN_ON_STDIN_EOF_ENV) && value == Some(OsStr::new("1"))
        });
        assert!(
            opted_in,
            "without {SHUTDOWN_ON_STDIN_EOF_ENV} the engine ignores stdin, so \
             closing the pipe asks it for nothing"
        );
    }

    #[test]
    fn the_child_gets_a_stdin_pipe_to_watch() {
        let (program, args) = fake_engine::IGNORES_STDIN;
        let mut child = spawn_configured(program, args);
        assert!(
            child.stdin.is_some(),
            "no pipe on stdin, so there is no way to ask for a clean shutdown"
        );
        let _ = child.kill();
        let _ = child.wait();
    }

    #[cfg(unix)]
    #[test]
    fn the_child_leads_its_own_process_group() {
        let (program, args) = fake_engine::IGNORES_STDIN;
        let mut child = spawn_configured(program, args);
        let pid = child.id() as libc::pid_t;
        let pgid = unsafe { libc::getpgid(pid) };
        assert_eq!(
            pgid, pid,
            "the child must lead a fresh process group; sharing ours would make \
             a group-wide kill take this process down too"
        );
        let _ = child.kill();
        let _ = child.wait();
    }

    /// Windows has no process group to assert on — `taskkill /T` walking the
    /// parent-pid chain is what stands in for it, so pin the invocation.
    #[cfg(windows)]
    #[test]
    fn the_windows_tree_kill_targets_descendants() {
        assert_eq!(
            taskkill_args(4321),
            ["/PID", "4321", "/T", "/F"].map(String::from),
            "/T is what makes this a tree kill; without it only the bootloader \
             dies and the real server keeps port 7355 (issue #485)"
        );
        let exe = system32("taskkill.exe");
        assert!(
            std::path::Path::new(&exe).exists(),
            "teardown resolves taskkill to {exe}, which does not exist — \
             forced shutdown would be a silent no-op"
        );
    }

    // ── Teardown ─────────────────────────────────────────────────────────────

    #[test]
    fn closing_stdin_is_enough_for_a_well_behaved_engine() {
        let (program, args) = fake_engine::READS_STDIN;
        let mut child = spawn_configured(program, args);
        assert_eq!(
            shutdown_within(&mut child, Duration::from_secs(10)),
            Shutdown::Graceful
        );
    }

    #[test]
    fn an_unresponsive_engine_is_killed_along_with_its_descendants() {
        let (mut engine, sidecar) = spawn_engine_with_sidecar();
        assert!(is_alive(sidecar), "test setup: the sidecar never started");

        let engine_pid = engine.id();
        assert_eq!(
            shutdown_within(&mut engine, Duration::from_millis(200)),
            Shutdown::Forced
        );

        assert!(
            wait_until_gone(engine_pid, Duration::from_secs(5)),
            "the engine survived teardown"
        );
        assert!(
            wait_until_gone(sidecar, Duration::from_secs(5)),
            "a descendant survived — this is the orphan that kept Steam \
             reporting the game as running (issue #485)"
        );
    }

    #[test]
    fn an_already_dead_engine_is_reported_not_signalled() {
        let (program, args) = fake_engine::EXITS_AT_ONCE;
        let mut child = spawn_configured(program, args);
        child.wait().expect("wait");
        assert_eq!(
            shutdown_within(&mut child, Duration::from_millis(200)),
            Shutdown::AlreadyExited
        );
    }
}
