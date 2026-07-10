#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# build-core.sh — Build the convsim-core standalone binary using PyInstaller.
#
# Creates a self-contained executable that ships inside the Tauri app bundle and
# runs without a developer virtual environment or a Python installation.
#
# Usage:
#   ./scripts/build-core.sh [--clean] [--help]
#
# Options:
#   --clean   Remove PyInstaller build/ and dist/ directories before building.
#   --help    Print this help and exit.
#
# Prerequisites:
#   The convsim-core venv must be active, or the CONVSIM_PYTHON environment
#   variable must point to a Python interpreter that has convsim-core and its
#   dependencies installed.  If pyinstaller is not yet installed in the venv,
#   this script installs it automatically (build extra from pyproject.toml).
#
#   Run ./scripts/setup.sh first to create the venv.
#
# Output:
#   apps/desktop/src-tauri/resources/bin/convsim-core
#
#   The Tauri shell locates this binary at runtime via find_core_executable()
#   in apps/desktop/src-tauri/src/lib.rs.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CORE_DIR="$REPO_ROOT/services/convsim-core"
OUT_DIR="$REPO_ROOT/apps/desktop/src-tauri/resources/bin"

# ── Parse options ─────────────────────────────────────────────────────────────

CLEAN=0

for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=1 ;;
        --help|-h)
            sed -n '2,/^set /p' "$0" | grep '^#' | sed 's/^# \?//'
            exit 0
            ;;
        *)
            echo "Unknown option: $arg" >&2
            exit 1
            ;;
    esac
done

# ── Locate Python interpreter ──────────────────────────────────────────────────

PY="${CONVSIM_PYTHON:-}"
if [[ -z "$PY" ]]; then
    VENV_PY="$CORE_DIR/.venv/bin/python"
    if [[ -f "$VENV_PY" ]]; then
        PY="$VENV_PY"
    elif command -v python3 &>/dev/null; then
        PY="python3"
    elif command -v python &>/dev/null; then
        PY="python"
    else
        echo "ERROR: Python not found. Run ./scripts/setup.sh first." >&2
        exit 1
    fi
fi

echo ""
echo "Conversation Simulator — build-core"
echo "======================================"
echo "Python   : $("$PY" --version)"
echo "Core dir : $CORE_DIR"
echo "Output   : $OUT_DIR"
echo ""

# ── Ensure pyinstaller is available ───────────────────────────────────────────

if ! "$PY" -m PyInstaller --version &>/dev/null 2>&1; then
    echo "Installing pyinstaller into the project environment..."
    "$PY" -m pip install -q pyinstaller
fi

PYINSTALLER_VERSION="$("$PY" -m PyInstaller --version 2>&1)"
echo "PyInstaller : $PYINSTALLER_VERSION"
echo ""

# ── Clean previous artefacts ──────────────────────────────────────────────────

if [[ "$CLEAN" -eq 1 ]]; then
    echo "Cleaning previous build artefacts..."
    rm -rf "$CORE_DIR/build" "$CORE_DIR/dist"
    echo "  Removed $CORE_DIR/build and $CORE_DIR/dist"
    echo ""
fi

# ── Run PyInstaller ────────────────────────────────────────────────────────────

echo "Building convsim-core (this may take a minute)..."
cd "$CORE_DIR"
"$PY" -m PyInstaller convsim-core.spec --noconfirm

echo ""
echo "Build complete."

# ── Copy to Tauri resources ────────────────────────────────────────────────────

BINARY_NAME="convsim-core"
BUILT="$CORE_DIR/dist/$BINARY_NAME"

if [[ ! -f "$BUILT" ]]; then
    echo "ERROR: expected binary not found at $BUILT" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
cp -f "$BUILT" "$OUT_DIR/$BINARY_NAME"
chmod +x "$OUT_DIR/$BINARY_NAME"

echo ""
echo "Installed to : $OUT_DIR/$BINARY_NAME"
echo "Size         : $(du -sh "$OUT_DIR/$BINARY_NAME" | cut -f1)"
echo ""
echo "The Tauri desktop build will bundle this binary automatically."
echo "Run: pnpm --filter @convsim/desktop build"
echo ""
