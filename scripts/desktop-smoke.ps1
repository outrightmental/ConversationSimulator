# SPDX-License-Identifier: Apache-2.0
# Verify that the Tauri desktop crate compiles without errors.
# Requires: Rust toolchain (rustup) and Tauri system dependencies for Windows.
# See apps/desktop/README.md for the full prerequisite list.
param()

$ErrorActionPreference = 'Stop'

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot   = Split-Path -Parent $ScriptDir
$DesktopDir = Join-Path $RepoRoot 'apps\desktop\src-tauri'

Write-Host ""
Write-Host "Conversation Simulator — desktop smoke check"
Write-Host "=============================================="
Write-Host ""

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Write-Error "Rust toolchain not found.`nInstall via rustup: https://rustup.rs/"
    exit 1
}

Write-Host "Running cargo check on apps/desktop/src-tauri..."
Push-Location $DesktopDir
try {
    cargo check
    if ($LASTEXITCODE -ne 0) {
        Write-Error "cargo check failed (exit code $LASTEXITCODE)."
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}
Write-Host "  OK  cargo check passed."

# Unit tests for the shell's own logic: Steam status derivation and convsim-core
# process teardown (src/core_process.rs). Run without the `steam` feature — the
# Steam tests call `steam::init()` from several threads at once, which is fine
# against the no-SDK stub but is NOT a supported way to call the real
# `SteamAPI_Init`.
Write-Host "Running cargo test on apps/desktop/src-tauri..."
Push-Location $DesktopDir
try {
    cargo test
    if ($LASTEXITCODE -ne 0) {
        Write-Error "cargo test failed (exit code $LASTEXITCODE)."
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}
Write-Host "  OK  cargo test passed."

Write-Host ""
Write-Host "Desktop smoke check passed."
Write-Host ""
exit 0
