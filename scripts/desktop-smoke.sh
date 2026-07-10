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

# Tauri's bundle.resources glob ("resources/**") panics if no visible file
# matches. The real convsim-core binary is placed here by build-core.sh before
# a release tauri build. When absent, create a zero-byte stub so cargo check
# can pass, then remove it on exit.
CORE_STUB="$DESKTOP_TAURI/resources/bin/convsim-core"
if [[ ! -f "$CORE_STUB" ]]; then
    touch "$CORE_STUB"
    trap 'rm -f "$CORE_STUB"' EXIT
fi

echo "Running cargo check on apps/desktop/src-tauri..."
(cd "$DESKTOP_TAURI" && cargo check 2>&1)
echo "  OK  cargo check passed."

echo ""
echo "Desktop smoke check passed."
echo ""
exit 0
