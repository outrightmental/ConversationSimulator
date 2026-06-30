#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Check that all required developer dependencies are present.
# Prints the next dependency to install, or confirms the environment is ready.
# Does not modify global state or download model files.
set -euo pipefail

REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=10
REQUIRED_NODE_MAJOR=18

fail() {
    echo ""
    echo "ERROR: $1"
    echo ""
    exit 1
}

check_python() {
    if ! command -v python3 &>/dev/null; then
        fail "Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}+ is required but not found.
       Install it from https://www.python.org/downloads/
       (version ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR} or newer)"
    fi

    local version major minor
    version=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    major=$(echo "$version" | cut -d. -f1)
    minor=$(echo "$version" | cut -d. -f2)

    if [[ "$major" -lt "$REQUIRED_PYTHON_MAJOR" ]] || \
       [[ "$major" -eq "$REQUIRED_PYTHON_MAJOR" && "$minor" -lt "$REQUIRED_PYTHON_MINOR" ]]; then
        fail "Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}+ is required. Found: $version
       Install a newer version from https://www.python.org/downloads/"
    fi

    echo "  python3 $version ... OK"
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
echo "Conversation Simulator — environment check"
echo "==========================================="
echo ""
echo "Checking required dependencies..."
echo ""

check_python
check_node
check_package_manager

echo ""
echo "All required dependencies found."
echo ""
echo "Next steps:"
echo ""
echo "  1. Install frontend packages:"
echo "       $PKG_MANAGER install"
echo ""
echo "  2. Install Python packages (once convsim-core is implemented):"
echo "       cd services/convsim-core"
echo "       python3 -m venv .venv"
echo "       source .venv/bin/activate"
echo "       pip install -e '.[dev]'"
echo ""
echo "  3. Start local dev:"
echo "       ./scripts/dev.sh"
echo ""
echo "NOTE: No model files are downloaded by this script."
echo "      The app will prompt you to install a model on first run."
echo ""
