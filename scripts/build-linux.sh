#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# build-linux.sh — Build the Conversation Simulator Linux desktop artifacts.
#
# Produces:
#   apps/desktop/src-tauri/target/release/bundle/appimage/*.AppImage
#   apps/desktop/src-tauri/target/release/bundle/deb/*.deb
#
# Both artifacts include the packaged convsim-core binary, official scenario
# packs, and all required sidecars. No Python or Node.js installation is
# required on the player's machine after installing either artifact.
#
# Usage:
#   ./scripts/build-linux.sh [--skip-deps] [--skip-core] [--clean] [--help]
#
# Options:
#   --skip-deps   Skip apt-get installation of system packages.
#                 Use when packages are already installed or you manage deps manually.
#   --skip-core   Skip rebuilding the convsim-core PyInstaller binary.
#                 Use when a binary already exists in resources/bin/ and has not changed.
#   --clean       Remove previous Tauri build artifacts before building.
#   --help        Print this help and exit.
#
# Prerequisites:
#   - Debian/Ubuntu x86_64 host (Ubuntu 22.04 LTS or newer strongly recommended)
#   - sudo access for system package installation (unless --skip-deps is used)
#   - Rust toolchain via rustup: https://rustup.rs/
#   - Node.js 18+ and pnpm 9+
#   - Python 3.10+ (3.11 recommended to match CI)
#
#   Run ./scripts/setup.sh first to create the convsim-core Python venv.
#
# GLibC note:
#   AppImage artifacts built on Ubuntu 22.04 (glibc 2.35) require glibc >= 2.35
#   on the target system. Ubuntu 22.04+, Fedora 38+, Debian 12+, and
#   SteamOS 3.x all satisfy this. See docs/linux-steamos-requirements.md.
#
# Steam Deck:
#   The AppImage runs on SteamOS 3.x (Arch-based, glibc 2.37+). After building,
#   copy the AppImage to the Steam Deck and launch it from a terminal or the
#   Steam library entry configured in Steamworks.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── Parse options ─────────────────────────────────────────────────────────────

SKIP_DEPS=0
SKIP_CORE=0
CLEAN=0

for arg in "$@"; do
    case "$arg" in
        --skip-deps) SKIP_DEPS=1 ;;
        --skip-core) SKIP_CORE=1 ;;
        --clean)     CLEAN=1 ;;
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

# ── Guard: Linux only ─────────────────────────────────────────────────────────

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: This script must run on Linux. Current platform: $(uname -s)" >&2
    echo "       For macOS, use: pnpm --filter @convsim/desktop build" >&2
    printf '%s\n' "       For Windows, use: .\\scripts\\build-core.ps1 then pnpm --filter @convsim/desktop build" >&2
    exit 1
fi

# ── Banner ────────────────────────────────────────────────────────────────────

echo ""
echo "Conversation Simulator — Linux desktop build"
echo "=============================================="
echo "Host : $(uname -s) $(uname -m)"
echo "glibc: $(ldd --version 2>&1 | head -1 | grep -oE '[0-9]+\.[0-9]+$' || echo 'unknown')"
echo "Root : $REPO_ROOT"
echo ""

# ── System dependencies ───────────────────────────────────────────────────────
# Tauri requires WebKitGTK 4.1, GTK 3, and a few support libraries.
# These are build-time AND runtime dependencies for the .deb package.
# The AppImage bundles most of them; the .deb does not.

SYSTEM_PACKAGES=(
    libwebkit2gtk-4.1-dev
    libgtk-3-dev
    libayatana-appindicator3-dev
    librsvg2-dev
)

if [[ "$SKIP_DEPS" -eq 0 ]]; then
    echo "Installing system dependencies..."
    if ! command -v apt-get &>/dev/null; then
        echo "WARNING: apt-get not found. Install these packages manually:" >&2
        printf '  %s\n' "${SYSTEM_PACKAGES[@]}" >&2
        echo "  Then re-run with --skip-deps." >&2
        # Do not exit — the build may succeed if packages are already installed
        # via another package manager.
    else
        sudo apt-get update -qq
        sudo apt-get install -y "${SYSTEM_PACKAGES[@]}"
        echo "  OK — system packages installed."
    fi
    echo ""
fi

# ── Verify toolchain ──────────────────────────────────────────────────────────

echo "Checking toolchain..."

check_tool() {
    local name="$1"
    local cmd="$2"
    local hint="$3"
    if ! command -v "$cmd" &>/dev/null; then
        echo "  ERROR: $name not found. $hint" >&2
        return 1
    fi
    echo "  OK    $name: $("$cmd" --version 2>&1 | head -1)"
}

TOOLCHAIN_OK=1
check_tool "Rust (cargo)" "cargo" "Install via: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh" || TOOLCHAIN_OK=0
check_tool "Node.js"      "node"  "Install via NodeSource: https://github.com/nodesource/distributions" || TOOLCHAIN_OK=0
check_tool "pnpm"         "pnpm"  "Install via: npm install -g pnpm" || TOOLCHAIN_OK=0

PY=""
for py_cmd in python3.11 python3.10 python3 python; do
    if command -v "$py_cmd" &>/dev/null; then
        PY="$py_cmd"
        break
    fi
done
if [[ -z "$PY" ]]; then
    echo "  ERROR: Python 3.10+ not found. Install via: sudo apt-get install python3.11 python3.11-venv" >&2
    TOOLCHAIN_OK=0
else
    echo "  OK    Python: $("$PY" --version 2>&1 | head -1) ($PY)"
fi

if [[ "$TOOLCHAIN_OK" -eq 0 ]]; then
    echo "" >&2
    echo "One or more toolchain components are missing. Resolve the errors above and retry." >&2
    exit 1
fi
echo ""

# ── Install JavaScript dependencies ───────────────────────────────────────────

echo "Installing JS dependencies..."
cd "$REPO_ROOT"
pnpm install --frozen-lockfile
echo "  OK — pnpm install complete."
echo ""

# ── Build shared TypeScript packages ──────────────────────────────────────────

echo "Building shared TypeScript packages..."
pnpm --filter @convsim/shared-types build
pnpm --filter @convsim/scenario-schema build
echo "  OK — shared-types and scenario-schema built."
echo ""

# ── Build web frontend ────────────────────────────────────────────────────────

echo "Building web frontend..."
pnpm --filter @convsim/web build
echo "  OK — web frontend built."
echo ""

# ── Build convsim-core standalone binary ─────────────────────────────────────

BIN_DIR="$REPO_ROOT/apps/desktop/src-tauri/resources/bin"
CORE_BIN="$BIN_DIR/convsim-core"

if [[ "$SKIP_CORE" -eq 1 ]]; then
    if [[ -f "$CORE_BIN" ]]; then
        echo "Skipping convsim-core build (--skip-core set)."
        echo "  Found: $CORE_BIN ($(du -sh "$CORE_BIN" | cut -f1))"
    else
        echo "ERROR: --skip-core specified but no binary found at $CORE_BIN" >&2
        echo "       Run without --skip-core to build it first." >&2
        exit 1
    fi
    echo ""
else
    echo "Building convsim-core standalone binary (PyInstaller)..."
    bash "$SCRIPT_DIR/build-core.sh"
    echo ""
fi

# Verify executable bit.
if [[ ! -x "$CORE_BIN" ]]; then
    echo "ERROR: $CORE_BIN is not executable. Fixing..." >&2
    chmod +x "$CORE_BIN"
fi

# ── Clean previous Tauri build artifacts ─────────────────────────────────────

TAURI_TARGET="$REPO_ROOT/apps/desktop/src-tauri/target/release/bundle"

if [[ "$CLEAN" -eq 1 && -d "$TAURI_TARGET" ]]; then
    echo "Removing previous Tauri bundle artifacts..."
    rm -rf "$TAURI_TARGET"
    echo "  Removed $TAURI_TARGET"
    echo ""
fi

# ── Build Tauri desktop (AppImage + .deb) ─────────────────────────────────────

echo "Building Tauri desktop (AppImage + .deb)..."
echo "  This step compiles Rust and may take 5–20 minutes on first run."
echo ""
pnpm --filter @convsim/desktop build
echo ""

# ── Locate and verify artifacts ───────────────────────────────────────────────

echo "Verifying build artifacts..."
echo ""

APPIMAGE=""
DEB=""
ERRORS=0

# Tauri v2 places bundles under target/release/bundle/<format>/
if [[ -d "$TAURI_TARGET/appimage" ]]; then
    APPIMAGE="$(find "$TAURI_TARGET/appimage" -name "*.AppImage" | head -1)"
fi
if [[ -d "$TAURI_TARGET/deb" ]]; then
    DEB="$(find "$TAURI_TARGET/deb" -name "*.deb" | head -1)"
fi

check_artifact() {
    local label="$1"
    local path="$2"
    if [[ -z "$path" || ! -f "$path" ]]; then
        echo "  MISSING  $label" >&2
        ERRORS=$((ERRORS + 1))
        return
    fi
    local perms size
    perms="$(stat -c '%A' "$path")"
    size="$(du -sh "$path" | cut -f1)"
    echo "  OK  $label"
    echo "      Path  : $path"
    echo "      Size  : $size"
    echo "      Perms : $perms"
    if [[ "$label" == "AppImage" ]] && [[ ! -x "$path" ]]; then
        echo "  WARNING: AppImage is not executable — fixing..." >&2
        chmod +x "$path"
        echo "  Fixed   : chmod +x $path"
    fi
}

check_artifact "convsim-core binary" "$CORE_BIN"
check_artifact "AppImage"            "$APPIMAGE"
check_artifact "Debian package"      "$DEB"
echo ""

if [[ "$ERRORS" -gt 0 ]]; then
    echo "ERROR: $ERRORS expected artifact(s) were not produced." >&2
    echo "       Check the pnpm build output above for errors." >&2
    exit 1
fi

# ── Summary ───────────────────────────────────────────────────────────────────

echo "────────────────────────────────────────────────────────────────"
echo "Build complete — Linux desktop artifacts ready."
echo ""
if [[ -n "$APPIMAGE" ]]; then
    echo "  AppImage (portable, any x86_64 Linux / SteamOS 3.x):"
    echo "    $APPIMAGE"
    echo "    Minimum glibc: 2.35  (target: Ubuntu 22.04+, Fedora 38+, SteamOS 3.x)"
fi
if [[ -n "$DEB" ]]; then
    echo ""
    echo "  Debian package (Ubuntu 22.04+ / Debian 12+):"
    echo "    $DEB"
fi
echo ""
echo "Steam Deck: copy the AppImage to the device and run it from a terminal"
echo "  or configure it as a non-Steam game entry in Gaming Mode."
echo "  See docs/linux-steamos-requirements.md for the full verification guide."
echo ""
echo "SHA-256 checksums:"
if [[ -n "$APPIMAGE" ]]; then
    sha256sum "$APPIMAGE"
fi
if [[ -n "$DEB" ]]; then
    sha256sum "$DEB"
fi
echo "────────────────────────────────────────────────────────────────"
echo ""
