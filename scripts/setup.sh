#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Set up the Conversation Simulator development environment.
# Checks dependencies, installs frontend packages, creates a Python virtual
# environment for convsim-core, and creates local data directories.
# Does not modify global state or download model files.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CORE_DIR="$REPO_ROOT/services/convsim-core"

REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=10
REQUIRED_NODE_MAJOR=18
PKG_MANAGER=""
PY_CMD=""

LOG_DIR="${CONVSIM_LOG_DIR:-$HOME/.convsim/logs}"
DATA_DIR="${CONVSIM_DATA_DIR:-$HOME/.convsim/data}"
DB_DIR="${CONVSIM_DB_DIR:-$HOME/.convsim/db}"

fail() {
    echo "" >&2
    echo "ERROR: $1" >&2
    echo "" >&2
    exit 1
}

check_python() {
    if command -v python3 &>/dev/null; then
        PY_CMD="python3"
    elif command -v python &>/dev/null; then
        PY_CMD="python"
    else
        fail "Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}+ is required but not found.
       Install it from https://www.python.org/downloads/
       (version ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR} or newer)"
    fi

    local version major minor
    version=$("$PY_CMD" -c "import sys; print('%d.%d' % (sys.version_info.major, sys.version_info.minor))")
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)

    if [[ "$major" -lt "$REQUIRED_PYTHON_MAJOR" ]] || \
       [[ "$major" -eq "$REQUIRED_PYTHON_MAJOR" && "$minor" -lt "$REQUIRED_PYTHON_MINOR" ]]; then
        fail "Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}+ is required. Found: $version
       Install a newer version from https://www.python.org/downloads/"
    fi

    echo "  $PY_CMD $version ... OK"
}

check_node() {
    if ! command -v node &>/dev/null; then
        fail "Node.js ${REQUIRED_NODE_MAJOR}+ is required but not found.
       Install it from https://nodejs.org/ (${REQUIRED_NODE_MAJOR}.x LTS or newer)"
    fi

    local version major
    version=$(node --version | sed 's/^v//')
    major=$(echo "$version" | cut -d. -f1)

    if [[ "$major" -lt "$REQUIRED_NODE_MAJOR" ]]; then
        fail "Node.js ${REQUIRED_NODE_MAJOR}+ is required. Found: $version
       Install a newer version from https://nodejs.org/"
    fi

    echo "  node $version ... OK"
}

check_package_manager() {
    if command -v pnpm &>/dev/null; then
        PKG_MANAGER="pnpm"
    elif command -v npm &>/dev/null; then
        PKG_MANAGER="npm"
    else
        fail "npm or pnpm is required but not found.
       npm is included with Node.js — install Node.js from https://nodejs.org/"
    fi

    echo "  $PKG_MANAGER ... OK"
}

echo ""
echo "Conversation Simulator — setup"
echo "================================"
echo ""
echo "Checking required dependencies..."
echo ""

check_python
check_node
check_package_manager

# --- Frontend dependencies ---
echo ""
echo "Installing frontend dependencies..."
echo ""
cd "$REPO_ROOT"
$PKG_MANAGER install
echo ""
echo "  Frontend dependencies installed."

# --- Python virtual environment ---
echo ""
echo "Setting up Python environment (services/convsim-core)..."
echo ""
if [[ ! -d "$CORE_DIR/.venv" ]]; then
    echo "  Creating virtual environment..."
    "$PY_CMD" -m venv "$CORE_DIR/.venv"
fi
"$CORE_DIR/.venv/bin/pip" install -q --upgrade pip
"$CORE_DIR/.venv/bin/pip" install -q -e "$REPO_ROOT/packages/prompt-composer"
"$CORE_DIR/.venv/bin/pip" install -q -e "${CORE_DIR}[dev]"
echo "  Python packages installed."

# --- Local data directories ---
echo ""
echo "Creating local data directories..."
echo ""
mkdir -p "$LOG_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$DB_DIR"
echo "  $LOG_DIR"
echo "  $DATA_DIR"
echo "  $DB_DIR"

echo ""
echo "Setup complete."
echo ""
echo "Start local dev with:"
echo ""
echo "  ./scripts/dev.sh       (macOS / Linux)"
echo "  .\\scripts\\dev.ps1      (Windows PowerShell)"
echo ""
echo "NOTE: No model files are downloaded by this script."
echo "      The app will prompt you to install a model on first run."
echo ""
exit 0
