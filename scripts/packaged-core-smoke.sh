#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# packaged-core-smoke.sh — Launch the PACKAGED convsim-core binary and prove it
# serves a playable, offline, loopback-only engine that shuts down cleanly.
#
# This is the automated form of issue #456's acceptance criterion
# "`npx convsim offline-smoke-test` passes against the packaged build": it runs
# the real PyInstaller binary that ships inside the desktop bundle — not the
# developer venv — and plays a pack that binary carried in its own payload.
#
# Checks, in order:
#   1. The packaged binary exists and is executable.
#   2. It answers GET /api/health with status "ok".
#   3. Its listener is bound to loopback only.
#   4. It seeded the official packs embedded in its own payload.
#   5. `convsim offline-smoke-test` plays one of those seeded packs with no
#      outbound network access.
#   6. Closing the launcher's end of the engine's stdin pipe drains the FastAPI
#      lifespan and releases the port. That is how the Tauri shell asks for a
#      shutdown (`core_process::shutdown` in
#      apps/desktop/src-tauri/src/core_process.rs): the engine's
#      `parent_watch` reads the EOF and asks uvicorn to stop gracefully, which
#      is what gives it the chance to stop its OWN sidecars.
#   7. The same, for the SIGTERM the shell falls back to when the ask goes
#      unanswered. Both are checked against the real binary because both cross
#      the PyInstaller one-file bootloader, which is the process the launcher
#      holds — the signal and the inherited stdin fd each have to reach the
#      Python server *behind* it, and nothing but this script tests that.
#
# Usage:
#   ./scripts/packaged-core-smoke.sh [--binary <path>] [--port <n>] [--help]
#
# Defaults:
#   --binary  $CONVSIM_CORE_EXECUTABLE, else
#             apps/desktop/src-tauri/resources/bin/convsim-core[.exe]
#   --port    7355
#
# Build the binary first:  ./scripts/build-core.sh
#
# The engine runs against a throwaway data root with HOME redirected into it, so
# the developer's own data directory is never touched, the official-pack seeding
# check sees a genuinely fresh install, and the legacy ~/.convsim migration
# cannot fire (it would otherwise copy real data in and mark the real directory
# as migrated).
#
# Exit 0: every required check passed.
# Exit 1: a check failed, or the binary is missing.
# Exit 2: bad usage.
#
# Linux / macOS only. The engine's launch path is platform-independent, and the
# Windows payload is covered by scripts/depot-audit.ps1 and the artifact
# inspection tests, so a pwsh twin would re-prove a platform-independent claim.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Settings ──────────────────────────────────────────────────────────────────

PORT="${CONVSIM_PORT:-7355}"
BINARY="${CONVSIM_CORE_EXECUTABLE:-}"

# How long the engine gets to answer /api/health. A first run migrates the
# database and seeds every pack in the binary's bundled packs/official (six
# today, five of them official.*) plus the model registry, and a PyInstaller
# one-file binary unpacks itself before any of that happens.
READY_TIMEOUT=120

# How long either teardown request gets to unwind the FastAPI lifespan.
# convsim-core allows in-flight requests 3 s to drain and its own sidecars 5 s
# to terminate, so this has to clear both; it is also above the shell's own
# `core_process::GRACE` (10 s), after which the shell stops asking and kills the
# process group — a budget below that would fail a drain the shipped app itself
# would have waited for.
SHUTDOWN_TIMEOUT=15

# Minimum official packs a packaged build must seed — the same floor as
# services/convsim-core/tests/test_packaged_smoke.py.
MINIMUM_OFFICIAL_PACKS=4

ERRORS=0
PASSED=0
CORE_PID=""
DATA_ROOT=""

# ── Output ────────────────────────────────────────────────────────────────────

pass() { printf "  PASS  %s\n" "$1"; PASSED=$((PASSED + 1)); }
fail() { printf "  FAIL  %s\n" "$1" >&2; ERRORS=$((ERRORS + 1)); }
info() { printf "  INFO  %s\n" "$1"; }

usage() {
    grep '^#' "$0" | grep -v '!/usr/bin' | sed 's/^# \{0,1\}//'
    exit 0
}

dump_core_output() {
    if [[ -n "$DATA_ROOT" && -f "$DATA_ROOT/core-output.log" ]]; then
        echo "  ---- convsim-core output ----" >&2
        sed 's/^/  /' "$DATA_ROOT/core-output.log" >&2
        echo "  -----------------------------" >&2
    fi
}

# Invoked by the EXIT trap below. ShellCheck does not follow a bare function name
# through `trap`, so it calls this dead code — SC2329 on the declaration (0.10+,
# what Homebrew ships) or SC2317 on every command in the body (0.9.0, what the CI
# runner's apt gives it). Both disabled: either one fails the lint on its own.
# shellcheck disable=SC2317,SC2329
cleanup() {
    if [[ -n "$CORE_PID" ]] && kill -0 "$CORE_PID" 2>/dev/null; then
        kill -KILL "$CORE_PID" 2>/dev/null
        # Reap before removing the data root: an engine still alive would be
        # writing into a directory pulled out from under it, and on a shared
        # runner it would keep holding the port for whatever runs next.
        wait "$CORE_PID" 2>/dev/null
    fi
    if [[ -n "$DATA_ROOT" && -d "$DATA_ROOT" ]]; then
        rm -rf "$DATA_ROOT"
    fi
}
trap cleanup EXIT

# ── CLI ───────────────────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --binary)
            if [[ $# -lt 2 ]]; then echo "--binary needs a path" >&2; exit 2; fi
            BINARY="$2"; shift 2 ;;
        --port)
            if [[ $# -lt 2 ]]; then echo "--port needs a number" >&2; exit 2; fi
            PORT="$2"; shift 2 ;;
        --help|-h) usage ;;
        *) echo "Unknown option: $1" >&2; exit 2 ;;
    esac
done

echo ""
echo "Conversation Simulator — packaged core smoke"
echo "==========================================="
echo ""

# ── Prerequisites ─────────────────────────────────────────────────────────────

if ! command -v curl >/dev/null 2>&1; then
    fail "curl not found — required to probe the health endpoint."
    exit 1
fi

# ── 1. The packaged binary ────────────────────────────────────────────────────

if [[ -z "$BINARY" ]]; then
    for candidate in \
        "$REPO_ROOT/apps/desktop/src-tauri/resources/bin/convsim-core" \
        "$REPO_ROOT/apps/desktop/src-tauri/resources/bin/convsim-core.exe"; do
        if [[ -f "$candidate" ]]; then
            BINARY="$candidate"
            break
        fi
    done
fi

if [[ -z "$BINARY" || ! -f "$BINARY" ]]; then
    fail "No packaged convsim-core binary found."
    info "Build one first: ./scripts/build-core.sh"
    info "Or point at an existing binary: --binary <path>"
    exit 1
fi

if [[ ! -x "$BINARY" ]]; then
    fail "Packaged binary is not executable: $BINARY"
    exit 1
fi
pass "Packaged binary present and executable: $BINARY"

# ── 2. Launch and wait for readiness ──────────────────────────────────────────

# Bash's /dev/tcp: a connection that opens means something is listening. Used
# instead of lsof/ss so the pre-flight works wherever bash does.
is_listening() {
    ( : < "/dev/tcp/127.0.0.1/$1" ) >/dev/null 2>&1
}

if is_listening "$PORT"; then
    fail "Port $PORT is already in use."
    info "Stop any running core (./scripts/dev.sh) or pass --port <n>."
    exit 1
fi

DATA_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/convsim-packaged-smoke.XXXXXX")"
CORE_LOG="$DATA_ROOT/core-output.log"
LAUNCHER_PIPE="$DATA_ROOT/launcher-stdin"
info "Throwaway data root: $DATA_ROOT"

# Written before launch so the data root is non-empty: the legacy-directory
# migration only fires into an EMPTY root, and letting it fire would both
# pollute the fresh-install check and write a "migrated" marker into the
# developer's real ~/.convsim.
: > "$CORE_LOG"

# Launched the way the desktop shell launches it: stdin on a pipe whose write
# end the launcher holds for its own lifetime, and CONVSIM_SHUTDOWN_ON_STDIN_EOF
# to opt the engine into watching it (`configure_lifetime` in
# apps/desktop/src-tauri/src/core_process.rs). Closing that write end is the
# shutdown request check 6 makes.
#
# A FIFO with fd 9 held read-write is how a POSIX shell keeps a write end open
# with nothing to write. `9>&-` closes it in the child on purpose: fds opened by
# `exec` are inherited across a fork, so without it the engine would hold a
# writer to its own stdin and EOF could never arrive.
mkfifo "$LAUNCHER_PIPE"
exec 9<>"$LAUNCHER_PIPE"

HOME="$DATA_ROOT" \
CONVSIM_HOST=127.0.0.1 \
CONVSIM_PORT="$PORT" \
CONVSIM_DATA_ROOT="$DATA_ROOT" \
CONVSIM_RUNTIME_ID=fake \
CONVSIM_SHUTDOWN_ON_STDIN_EOF=1 \
    "$BINARY" <"$LAUNCHER_PIPE" 9>&- >>"$CORE_LOG" 2>&1 &
CORE_PID=$!

HEALTH_URL="http://127.0.0.1:$PORT/api/health"
HEALTH_JSON="$DATA_ROOT/health.json"

# Poll /api/health until $CORE_PID serves it. 0 on a 200 whose body is in
# $HEALTH_JSON; 1 if the engine died or never answered. A function because
# check 7 starts a second engine and has the same question.
await_ready() {
    local deadline
    deadline=$(( $(date +%s) + READY_TIMEOUT ))
    while [[ "$(date +%s)" -lt "$deadline" ]]; do
        if ! kill -0 "$CORE_PID" 2>/dev/null; then
            fail "The packaged core exited before becoming ready."
            return 1
        fi
        # -m 20, not 5: /api/health awaits the LLM, STT and TTS probes in
        # sequence, and the two that make HTTP calls to sidecars allow 5 s each,
        # so one answer can legitimately take just over 10 s. The Tauri shell
        # allows the same request PROBE_RESPONSE_BUDGET (14 s — see probe_core);
        # this stays above it, because a per-attempt cap below the shell's would
        # fail a request the shipped app itself would accept, and no later
        # attempt would do any better.
        if curl -fsS -m 20 "$HEALTH_URL" -o "$HEALTH_JSON" 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    fail "No 200 from $HEALTH_URL within ${READY_TIMEOUT}s."
    return 1
}

if ! await_ready; then
    dump_core_output
    exit 1
fi

if grep -q '"status"[[:space:]]*:[[:space:]]*"ok"' "$HEALTH_JSON"; then
    pass "GET /api/health reports status \"ok\""
else
    fail "GET /api/health answered but did not report status \"ok\"."
    sed 's/^/        /' "$HEALTH_JSON" >&2
fi

# ── 3. Loopback-only binding ──────────────────────────────────────────────────
#
# The offline guarantee starts with the socket: every service must bind
# 127.0.0.1 (or ::1) and nothing else. See docs/network-security.md.

listener_addresses() {
    if command -v lsof >/dev/null 2>&1; then
        lsof -nP -iTCP:"$PORT" -sTCP:LISTEN 2>/dev/null | awk 'NR > 1 { print $9 }'
    elif command -v ss >/dev/null 2>&1; then
        ss -ltnH "sport = :$PORT" 2>/dev/null | awk '{ print $4 }'
    fi
}

ADDRESSES="$(listener_addresses)"
if [[ -z "$ADDRESSES" ]]; then
    info "Could not enumerate listeners (no lsof or ss) — binding check skipped"
else
    NON_LOOPBACK=0
    while IFS= read -r addr; do
        [[ -z "$addr" ]] && continue
        case "$addr" in
            '127.0.0.1:'*|'[::1]:'*|'localhost:'*) ;;
            *) fail "Listening on a non-loopback address: $addr"; NON_LOOPBACK=1 ;;
        esac
    done <<< "$ADDRESSES"
    if [[ "$NON_LOOPBACK" -eq 0 ]]; then
        pass "Listener is bound to loopback only"
    fi
fi

# ── 4. Official packs seeded from the binary's own payload ────────────────────

PACKS_JSON="$DATA_ROOT/packs.json"
if curl -fsS -m 15 "http://127.0.0.1:$PORT/api/packs" -o "$PACKS_JSON" 2>/dev/null; then
    SEEDED="$(grep -o '"pack_id"[[:space:]]*:[[:space:]]*"official\.[^"]*"' "$PACKS_JSON" | wc -l | tr -d ' ')"
    if [[ "$SEEDED" -ge "$MINIMUM_OFFICIAL_PACKS" ]]; then
        pass "Seeded $SEEDED official pack(s) from the packaged payload"
    else
        fail "Only $SEEDED official pack(s) seeded (expected >= $MINIMUM_OFFICIAL_PACKS)."
        info "A packaged build must never boot into an empty library."
    fi
else
    fail "GET /api/packs failed."
fi

# ── 5. Offline smoke test against a pack the packaged build shipped ───────────

CLI_ENTRY="$REPO_ROOT/packages/convsim-cli/dist/index.js"
if [[ ! -f "$CLI_ENTRY" ]]; then
    # release.yml reaches here with no dist/, so this build runs on every
    # release. Keep its output: discarding it turned a tsc error into nothing but
    # "convsim CLI not built", which names a command to run rather than the
    # reason the same command just failed.
    info "Building the convsim CLI (dist/ not present)…"
    CLI_BUILD_LOG="$DATA_ROOT/cli-build.log"
    if ! ( cd "$REPO_ROOT" \
            && pnpm --filter @convsim/pack-loader build \
            && pnpm --filter @convsim/cli build ) >"$CLI_BUILD_LOG" 2>&1; then
        # Not a `fail` of its own: dist/index.js is now missing, so the check
        # below reports it once. This is just the reason, printed before it.
        info "The CLI build failed — its output follows."
        sed 's/^/        /' "$CLI_BUILD_LOG" >&2
    fi
fi

PACK_DIR=""
for dir in "$DATA_ROOT"/packs/*/; do
    [[ -d "$dir" ]] || continue
    if [[ -f "${dir}manifest.yaml" || -f "${dir}pack.json" ]]; then
        PACK_DIR="${dir%/}"
        break
    fi
done

if [[ ! -f "$CLI_ENTRY" ]]; then
    fail "convsim CLI not built — run: pnpm --filter @convsim/cli build"
elif ! command -v node >/dev/null 2>&1; then
    fail "node not found — required to run the convsim CLI."
elif [[ -z "$PACK_DIR" ]]; then
    fail "No seeded pack directory found under $DATA_ROOT/packs."
else
    info "Running: convsim offline-smoke-test $(basename "$PACK_DIR")"
    SMOKE_OUT="$(node "$CLI_ENTRY" offline-smoke-test "$PACK_DIR" 2>&1)"
    SMOKE_RC=$?
    if [[ "$SMOKE_RC" -eq 0 ]]; then
        pass "offline-smoke-test passed against the packaged build's own pack"
    else
        fail "offline-smoke-test exited $SMOKE_RC"
        printf '%s\n' "$SMOKE_OUT" | sed 's/^/        /' >&2
    fi
fi

# ── Teardown assertions, shared by checks 6 and 7 ─────────────────────────────

# Wait up to SHUTDOWN_TIMEOUT for $CORE_PID to leave. 0 if it did.
core_stopped_within_grace() {
    local deadline
    deadline=$(( $(date +%s) + SHUTDOWN_TIMEOUT ))
    while [[ "$(date +%s)" -lt "$deadline" ]]; do
        if ! kill -0 "$CORE_PID" 2>/dev/null; then
            return 0
        fi
        sleep 1
    done
    return 1
}

# Did the FastAPI lifespan shutdown actually run? "Closed database at …" is the
# statement AFTER `await supervisor.stop_all()` in create_app's lifespan, so
# seeing it means the engine got far enough to stop its own sidecars — which is
# the whole point of asking rather than killing. Both sinks are checked because
# configure_logging may route to a file instead of the inherited stdio.
lifespan_drained() {
    grep -q "Closed database at" "$CORE_LOG" 2>/dev/null && return 0
    [[ -d "$DATA_ROOT/logs" ]] \
        && grep -rq "Closed database at" "$DATA_ROOT/logs" 2>/dev/null \
        && return 0
    return 1
}

# ── 6. Clean shutdown: EOF on the launcher's stdin pipe ───────────────────────
#
# The shell's first move, and the only one that stops the engine's own sidecars
# in the normal case. It has to cross the PyInstaller bootloader: the pipe is
# inherited by the Python server the bootloader re-execs, and `parent_watch`
# reads the EOF there.

info "Closing the launcher's end of the engine's stdin pipe"
exec 9>&-

if core_stopped_within_grace; then
    # The 2>/dev/null is only for `wait`'s own diagnostics.
    wait "$CORE_PID" 2>/dev/null
    CORE_RC=$?
    CORE_PID=""
    pass "Closing stdin stopped the engine within ${SHUTDOWN_TIMEOUT}s"
    # Unlike the signal path below, nothing is re-raised here: uvicorn was asked
    # to stop through its own `should_exit` flag, so `main()` returns normally.
    if [[ "$CORE_RC" -eq 0 ]]; then
        pass "Engine exited 0 — it stopped because it was asked, not killed"
    else
        fail "Engine exited $CORE_RC after its stdin closed; a graceful stop through parent_watch exits 0."
        dump_core_output
    fi
    if lifespan_drained; then
        pass "Lifespan shutdown ran — sidecars stopped and the database closed"
    else
        fail "No sign the lifespan shutdown ran: the engine did not act on the EOF, so its own sidecars would be left orphaned."
        dump_core_output
    fi
else
    fail "Engine still running ${SHUTDOWN_TIMEOUT}s after its stdin pipe closed."
    dump_core_output
    # CORE_PID is deliberately kept so the EXIT trap SIGKILLs it. Clearing it
    # here would leave the engine — and its own sidecars — running after the
    # script returns, holding the port for the next release step (or for the
    # developer, who has to find it in a task manager). The port check below
    # still reports the truth, because the trap has not run yet.
fi

if is_listening "$PORT"; then
    fail "Port $PORT is still held after the stdin shutdown."
else
    pass "Port $PORT released"
fi

# ── 7. The SIGTERM fallback ───────────────────────────────────────────────────
#
# What `core_process::shutdown` sends to the engine's process group once the ask
# above has gone unanswered for its grace period. Checked against the packaged
# binary for the same reason as check 6: the signal goes to the bootloader, and
# uvicorn's handler lives in the Python server behind it.
#
# Only attempted when check 6 left the port free — otherwise this would be a
# second engine racing the first one's socket, and the script is already failing.

if [[ -n "$CORE_PID" ]] || is_listening "$PORT"; then
    fail "Skipped the SIGTERM fallback check: the previous engine is still holding port $PORT."
else
    # A warm start: the database is migrated and the packs are seeded, so this
    # run reaches readiness in seconds. The log sinks are cleared first, so the
    # drain evidence found below is this run's and not the previous one's.
    : > "$CORE_LOG"
    rm -rf "$DATA_ROOT/logs"

    HOME="$DATA_ROOT" \
    CONVSIM_HOST=127.0.0.1 \
    CONVSIM_PORT="$PORT" \
    CONVSIM_DATA_ROOT="$DATA_ROOT" \
    CONVSIM_RUNTIME_ID=fake \
        "$BINARY" >>"$CORE_LOG" 2>&1 &
    CORE_PID=$!

    if ! await_ready; then
        dump_core_output
    else
        info "Sending SIGTERM (bash may print its own \"Terminated\" notice for the job — expected)"
        kill -TERM "$CORE_PID" 2>/dev/null
        if core_stopped_within_grace; then
            # bash reports the killed job itself ("Terminated: 15"),
            # asynchronously and on the script's stderr, so that notice shows up
            # regardless — hence the heads-up above. The exit status is NOT
            # evidence either way here: uvicorn re-raises the signal after a
            # complete graceful shutdown, so a correctly-drained engine exits
            # 143 (128 + SIGTERM). The log is the evidence.
            wait "$CORE_PID" 2>/dev/null
            CORE_RC=$?
            CORE_PID=""
            pass "SIGTERM stopped the engine within ${SHUTDOWN_TIMEOUT}s"
            info "Engine exit status $CORE_RC (143 is expected: uvicorn re-raises SIGTERM)"
            if lifespan_drained; then
                pass "SIGTERM reached the lifespan shutdown too"
            else
                fail "No sign the lifespan shutdown ran on SIGTERM: the engine was killed rather than drained, so its own sidecars would be left orphaned."
                dump_core_output
            fi
        else
            fail "Engine still running ${SHUTDOWN_TIMEOUT}s after SIGTERM."
            dump_core_output
            # CORE_PID kept for the EXIT trap, as above.
        fi
    fi
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo ""
if [[ "$ERRORS" -eq 0 ]]; then
    echo "Packaged core smoke passed ($PASSED check(s))."
    echo ""
    exit 0
fi
echo "Packaged core smoke FAILED ($ERRORS of $(( ERRORS + PASSED )) check(s))." >&2
echo "" >&2
exit 1
