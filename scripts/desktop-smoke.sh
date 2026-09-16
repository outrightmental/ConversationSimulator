#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Verify that the Tauri desktop crate compiles without errors.
# Requires: Rust toolchain (rustup) and Tauri system dependencies for your OS.
# See apps/desktop/README.md for the full prerequisite list.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DESKTOP_TAURI="$REPO_ROOT/apps/desktop/src-tauri"

echo ""
echo "Conversation Simulator — desktop smoke check"
echo "=============================================="
echo ""

fail() {
    echo "ERROR: $1" >&2
    echo "" >&2
    exit 1
}

if ! command -v cargo &>/dev/null; then
    fail "Rust toolchain not found.
Install via rustup: https://rustup.rs/
Then re-run this script."
fi

echo "Running cargo check on apps/desktop/src-tauri..."
(cd "$DESKTOP_TAURI" && cargo check 2>&1)
echo "  OK  cargo check passed."

# The Steam depot is built with `--features steam` (Steamworks SDK bridge).
# steamworks-sys bundles Valve's redistributable library, so this needs no SDK
# download.  On Linux/macOS this covers everything except the Windows-only
# overlay compositing surface, which CI checks separately on windows-latest.
echo "Running cargo check --features steam on apps/desktop/src-tauri..."
(cd "$DESKTOP_TAURI" && cargo check --features steam 2>&1)
echo "  OK  cargo check --features steam passed."

echo ""
echo "Desktop smoke check passed."
echo ""
exit 0
