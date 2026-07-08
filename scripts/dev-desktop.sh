#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Start Conversation Simulator in desktop (Tauri) dev mode.
# Launches convsim-core (port 7355), then runs `tauri dev` which starts the
# web dev server (port 7354) and opens the native window.
# Prerequisites: Rust toolchain (rustup), Tauri system deps, and a completed
# `./scripts/setup.sh`. Press Ctrl-C to stop all services.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CORE_DIR="$REPO_ROOT/services/convsim-core"
DESKTOP_DIR="$REPO_ROOT/apps/desktop"

CORE_PORT=7355
WEB_PORT=7354
LOG_DIR="${CONVSIM_LOG_DIR:-$HOME/.convsim/logs}"

PIDS=()
_CLEANING_UP=0

fail() {
    echo "" >&2
    echo "ERROR: $1" >&2
    echo "" >&2
    exit 1
}

check_port() {
    local port="$1"
    local service="$2"

    if command -v lsof &>/dev/null; then
        local pid
        pid=$(lsof -ti ":$port" 2>/dev/null | head -1 || true)
        if [[ -n "$pid" ]]; then
            local cmd
            cmd=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
            fail "Port $port is already in use by PID $pid ($cmd).
       Stop that process before starting $service."
        fi
    elif command -v ss &>/dev/null; then
        local info
        info=$(ss -tlnp 2>/dev/null | grep -E ":${port}[[:space:]]" || true)
        if [[ -n "$info" ]]; then
            fail "Port $port is already in use.
       Stop the blocking process before starting $service."
        fi
    fi
}

cleanup() {
    [[ $_CLEANING_UP -eq 1 ]] && return
    _CLEANING_UP=1
    echo ""
    echo "Stopping services..."
    for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
        kill "$pid" 2>/dev/null || true
    done
    for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
        wait "$pid" 2>/dev/null || true
    done
    echo "Done."
}
trap cleanup EXIT
trap 'cleanup; exit 0' INT TERM

echo ""
echo "Conversation Simulator — desktop dev"
echo "======================================"
echo ""

# --- Dependency checks ---
if ! command -v cargo &>/dev/null; then
    fail "Rust toolchain not found. Install via rustup:
  https://rustup.rs/
  Then re-run: rustup target add x86_64-apple-darwin  (macOS)
              rustup target add x86_64-unknown-linux-gnu  (Linux)"
fi

UVICORN=""
if [[ -f "$CORE_DIR/.venv/bin/uvicorn" ]]; then
    UVICORN="$CORE_DIR/.venv/bin/uvicorn"
elif command -v uvicorn &>/dev/null; then
    UVICORN="uvicorn"
else
    fail "uvicorn not found. Run setup first:
  ./scripts/setup.sh"
fi

PKG_MANAGER=""
if command -v pnpm &>/dev/null; then
    PKG_MANAGER="pnpm"
elif command -v npm &>/dev/null; then
    PKG_MANAGER="npm"
else
    fail "npm or pnpm not found. Run setup first:
  ./scripts/setup.sh"
fi

# --- Port conflict checks ---
check_port $CORE_PORT "convsim-core"
check_port $WEB_PORT  "convsim-ui"

# --- Ensure log directory exists ---
mkdir -p "$LOG_DIR"

echo "Starting convsim-core on port $CORE_PORT..."
(
    cd "$CORE_DIR"
    exec env CONVSIM_LOG_DIR="$LOG_DIR" \
        "$UVICORN" convsim_core.main:app \
        --host 127.0.0.1 --port $CORE_PORT --reload
) &
PIDS+=($!)

echo "Waiting for convsim-core to be ready..."
for _ in $(seq 1 20); do
    if curl -sf "http://127.0.0.1:$CORE_PORT/health" >/dev/null 2>&1; then
        echo "  convsim-core ready."
        break
    fi
    sleep 1
done

echo ""
echo "Starting Tauri desktop dev (opens native window)..."
echo "  Tauri will also start convsim-ui on port $WEB_PORT."
echo ""
echo "Logs: $LOG_DIR"
echo "Press Ctrl-C to stop all services."
echo ""

(
    cd "$DESKTOP_DIR"
    if [[ "$PKG_MANAGER" == "pnpm" ]]; then
        exec pnpm tauri dev
    else
        exec npx tauri dev
    fi
) &
PIDS+=($!)

while true; do
    for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
        if ! kill -0 "$pid" 2>/dev/null; then
            echo "" >&2
            echo "A service stopped unexpectedly. Check logs at: $LOG_DIR" >&2
            exit 1
        fi
    done
    sleep 1
done
