#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Verify that all expected monorepo paths exist after a fresh clone.
# Exit 0 when every path is present; exit 1 and list what is missing otherwise.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0

check_dir() {
    if [[ -d "$REPO_ROOT/$1" ]]; then
        echo "  OK  $1/"
    else
        echo "  MISSING  $1/" >&2
        ERRORS=$((ERRORS + 1))
    fi
}

check_file() {
    if [[ -f "$REPO_ROOT/$1" ]]; then
        echo "  OK  $1"
    else
        echo "  MISSING  $1" >&2
        ERRORS=$((ERRORS + 1))
    fi
}

echo ""
echo "Conversation Simulator — smoke check"
echo "======================================"
echo ""
echo "Checking expected monorepo paths..."
echo ""

# Top-level workspace directories
check_dir "apps"
check_dir "packages"
check_dir "services"
check_dir "runtimes"
check_dir "packs"
check_dir "schemas"
check_dir "model-registry"
check_dir "docs"
check_dir "scripts"

echo ""

# Application workspaces
check_dir "apps/web"
check_dir "apps/desktop"
check_file "apps/web/package.json"
check_file "apps/desktop/package.json"

echo ""

# Package workspaces
check_dir "packages/ui"
check_dir "packages/scenario-schema"
check_dir "packages/shared-types"
check_dir "packages/shared"
check_dir "packages/pack-loader"
check_dir "packages/convsim-cli"
check_file "packages/ui/package.json"
check_file "packages/scenario-schema/package.json"
check_file "packages/shared-types/package.json"
check_file "packages/shared/package.json"
check_file "packages/pack-loader/package.json"
check_file "packages/convsim-cli/package.json"

echo ""

# Backend service
check_dir "services/convsim-core"
check_file "services/convsim-core/pyproject.toml"

echo ""

# Runtime adapters
check_dir "runtimes/llama_cpp"
check_dir "runtimes/whisper_cpp"

echo ""

# Scenario packs
check_dir "packs/official"
check_dir "packs/official/job-interview-basic"
check_dir "packs/official/everyday-negotiation"
check_dir "packs/official/language-cafe"
check_dir "packs/official/difficult-conversations"

echo ""

# Root files
check_file "README.md"
check_file "LICENSE"
check_file "NOTICE"
check_file "package.json"
check_file ".editorconfig"
check_file ".gitignore"
check_file ".prettierrc"

echo ""

# Developer scripts (all four variants required)
check_file "scripts/setup.sh"
check_file "scripts/dev.sh"
check_file "scripts/setup.ps1"
check_file "scripts/dev.ps1"
check_file "scripts/dev-desktop.sh"
check_file "scripts/dev-desktop.ps1"

# First-run and release scripts
check_file "scripts/first-run-check.sh"
check_file "scripts/first-run-check.ps1"
check_file "scripts/release-smoke.sh"
check_file "scripts/release-smoke.ps1"
check_file "scripts/desktop-smoke.sh"
check_file "scripts/desktop-smoke.ps1"

# Packaging and audit scripts
check_file "scripts/build-core.sh"
check_file "scripts/build-core.ps1"
check_file "scripts/build-linux.sh"
check_file "scripts/depot-audit.sh"
check_file "scripts/depot-audit.ps1"
check_file "services/convsim-core/convsim-core.spec"
check_file "apps/desktop/src-tauri/resources/bin/.gitkeep"
check_file "apps/desktop/src-tauri/resources/placeholder"

echo ""

# Release infrastructure
check_file ".github/workflows/release.yml"
check_file ".github/workflows/release-smoke.yml"
check_file "docs/release-notes-template.md"
check_file "docs/platform-notes.md"
check_file "docs/release-checklist.md"
check_file "docs/linux-steamos-requirements.md"

echo ""

# Steam publishing and depot policy docs
check_dir  "steam"
check_file "steam/app_build.vdf.tpl"
check_file "steam/depot_windows.vdf.tpl"
check_file "steam/depot_macos.vdf.tpl"
check_file "steam/depot_linux.vdf.tpl"
check_dir  "publishing"
check_file "publishing/STEAM_DEPOT_CONTENTS.md"
check_file "publishing/STEAM_COMPLIANCE_AND_RISK_REGISTER.md"
check_file "publishing/STEAM_APP_REGISTRATION.md"
check_file "docs/model-download-policy.md"
check_file "docs/pack-download-policy.md"
check_file ".github/workflows/steam-deploy.yml"

echo ""

# Desktop Tauri wrapper
check_dir  "apps/desktop/src-tauri"
check_file "apps/desktop/src-tauri/Cargo.toml"
check_file "apps/desktop/src-tauri/tauri.conf.json"
check_file "apps/desktop/src-tauri/build.rs"
check_file "apps/desktop/src-tauri/src/main.rs"
check_file "apps/desktop/src-tauri/src/lib.rs"
check_file "apps/desktop/src-tauri/capabilities/default.json"
# macOS Hardened Runtime entitlements — required for notarization (G3-01) and
# Steam overlay compatibility (G3-03).  Referenced by tauri.conf.json and by
# convsim-core.spec when APPLE_SIGNING_IDENTITY is set.
check_file "apps/desktop/src-tauri/entitlements.plist"
# Icons referenced by tauri.conf.json are embedded at compile time; a missing
# file breaks `tauri dev`/`tauri build`, so verify the placeholder set is present.
check_file "apps/desktop/src-tauri/icons/32x32.png"
check_file "apps/desktop/src-tauri/icons/128x128.png"
check_file "apps/desktop/src-tauri/icons/128x128@2x.png"
check_file "apps/desktop/src-tauri/icons/icon.icns"
check_file "apps/desktop/src-tauri/icons/icon.ico"

echo ""

if [[ "$ERRORS" -gt 0 ]]; then
    echo "FAIL: $ERRORS expected path(s) are missing." >&2
    echo "" >&2
    exit 1
fi

echo "All expected paths are present."
echo ""
exit 0
