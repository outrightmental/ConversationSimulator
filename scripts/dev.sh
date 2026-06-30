#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Start the Conversation Simulator local dev services.
# Launches convsim-core (port 7355) and convsim-ui (port 7354).
# Checks for port conflicts before starting. Press Ctrl-C to stop all services.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CORE_DIR="$REPO_ROOT/services/convsim-core"
WEB_DIR="$REPO_ROOT/apps/web"

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

# Check if a port is occupied and report which process is blocking it.
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
            local pid
            pid=$(echo "$info" | grep -oP '(?<=pid=)\d+' | head -1 || true)
            if [[ -n "$pid" ]]; then
                local cmd
                cmd=$(ps -p "$pid" -o comm= 2>/dev/null || echo "unknown")
                fail "Port $port is already in use by PID $pid ($cmd).
       Stop that process before starting $service."
            else
                fail "Port $port is already in use.
       Stop the blocking process before starting $service."
            fi
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
trap cleanup EXIT INT TERM

echo ""
echo "Conversation Simulator — local dev"
echo "===================================="
echo ""

# --- Port conflict checks ---
check_port $CORE_PORT "convsim-core"
check_port $WEB_PORT "convsim-ui"

# --- Locate uvicorn ---
UVICORN=""
if [[ -f "$CORE_DIR/.venv/bin/uvicorn" ]]; then
    UVICORN="$CORE_DIR/.venv/bin/uvicorn"
elif command -v uvicorn &>/dev/null; then
    UVICORN="uvicorn"
else
    fail "uvicorn not found. Run setup first:
  ./scripts/setup.sh"
fi

# --- Locate package manager ---
PKG_MANAGER=""
if command -v pnpm &>/dev/null; then
    PKG_MANAGER="pnpm"
elif command -v npm &>/dev/null; then
    PKG_MANAGER="npm"
else
    fail "npm or pnpm not found. Run setup first:
  ./scripts/setup.sh"
fi

# --- Ensure log directory exists ---
mkdir -p "$LOG_DIR"

echo "Service URLs:"
echo ""
echo "  convsim-ui    http://127.0.0.1:$WEB_PORT  (browser UI)"
echo "  convsim-core  http://127.0.0.1:$CORE_PORT  (API server)"
echo ""
echo "Logs: $LOG_DIR"
echo ""
echo "Press Ctrl-C to stop all services."
echo ""

# --- Start convsim-core ---
echo "Starting convsim-core..."
(
    cd "$CORE_DIR"
    exec env CONVSIM_LOG_DIR="$LOG_DIR" \
        "$UVICORN" convsim_core.main:app \
        --host 127.0.0.1 --port $CORE_PORT --reload
) &
PIDS+=($!)

# --- Start convsim-ui ---
echo "Starting convsim-ui..."
(
    cd "$WEB_DIR"
    if [[ "$PKG_MANAGER" == "pnpm" ]]; then
        exec pnpm dev
    else
        exec npm run dev
    fi
) &
PIDS+=($!)

echo ""

# Wait for both services (Ctrl-C triggers cleanup trap)
wait "${PIDS[@]}" 2>/dev/null || true
