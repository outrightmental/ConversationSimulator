# SPDX-License-Identifier: Apache-2.0
# Verify that all expected monorepo paths exist after a fresh clone (Windows PowerShell).
# Exit 0 when every path is present; exit 1 and list what is missing otherwise.

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Errors = 0

function Check-Dir {
    param([string]$RelPath)
    $full = Join-Path $RepoRoot $RelPath
    if (Test-Path -PathType Container $full) {
        Write-Host "  OK  $RelPath/"
    } else {
        Write-Host "  MISSING  $RelPath/" -ForegroundColor Red
        $script:Errors++
    }
}

function Check-File {
    param([string]$RelPath)
    $full = Join-Path $RepoRoot $RelPath
    if (Test-Path -PathType Leaf $full) {
        Write-Host "  OK  $RelPath"
    } else {
        Write-Host "  MISSING  $RelPath" -ForegroundColor Red
        $script:Errors++
    }
}

Write-Host ""
Write-Host "Conversation Simulator — smoke check"
Write-Host "======================================"
Write-Host ""
Write-Host "Checking expected monorepo paths..."
Write-Host ""

# Top-level workspace directories
Check-Dir "apps"
Check-Dir "packages"
Check-Dir "services"
Check-Dir "runtimes"
Check-Dir "packs"
Check-Dir "schemas"
Check-Dir "model-registry"
Check-Dir "docs"
Check-Dir "scripts"

Write-Host ""

# Application workspaces
Check-Dir "apps\web"
Check-Dir "apps\desktop"
Check-File "apps\web\package.json"
Check-File "apps\desktop\package.json"

Write-Host ""

# Package workspaces
Check-Dir "packages\ui"
Check-Dir "packages\scenario-schema"
Check-Dir "packages\shared-types"
Check-File "packages\ui\package.json"
Check-File "packages\scenario-schema\package.json"
Check-File "packages\shared-types\package.json"

Write-Host ""

# Backend service
Check-Dir "services\convsim-core"
Check-File "services\convsim-core\pyproject.toml"

Write-Host ""

# Runtime adapters
Check-Dir "runtimes\llama_cpp"
Check-Dir "runtimes\whisper_cpp"

Write-Host ""

# Scenario packs
Check-Dir "packs\official"
Check-Dir "packs\official\job-interview-basic"
Check-Dir "packs\official\everyday-negotiation"
Check-Dir "packs\official\language-cafe"
Check-Dir "packs\official\difficult-conversations"

Write-Host ""

# Root files
Check-File "README.md"
Check-File "LICENSE"
Check-File "NOTICE"
Check-File "package.json"
Check-File ".editorconfig"
Check-File ".gitignore"
Check-File ".prettierrc"

Write-Host ""

# Developer scripts (all four variants required)
Check-File "scripts\setup.sh"
Check-File "scripts\dev.sh"
Check-File "scripts\setup.ps1"
Check-File "scripts\dev.ps1"
Check-File "scripts\dev-desktop.sh"
Check-File "scripts\dev-desktop.ps1"

# First-run and release scripts
Check-File "scripts\first-run-check.sh"
Check-File "scripts\first-run-check.ps1"
Check-File "scripts\release-smoke.sh"
Check-File "scripts\release-smoke.ps1"

Write-Host ""

# Release infrastructure
Check-File ".github\workflows\release.yml"
Check-File ".github\workflows\release-smoke.yml"
Check-File "docs\release-notes-template.md"
Check-File "docs\platform-notes.md"
Check-File "docs\release-checklist.md"

Write-Host ""

# Desktop Tauri wrapper
Check-Dir  "apps\desktop\src-tauri"
Check-File "apps\desktop\src-tauri\Cargo.toml"
Check-File "apps\desktop\src-tauri\tauri.conf.json"
Check-File "apps\desktop\src-tauri\build.rs"
Check-File "apps\desktop\src-tauri\src\main.rs"
Check-File "apps\desktop\src-tauri\src\lib.rs"
Check-File "apps\desktop\src-tauri\capabilities\default.json"
# Icons referenced by tauri.conf.json are embedded at compile time; a missing
# file breaks `tauri dev`/`tauri build`, so verify the placeholder set is present.
Check-File "apps\desktop\src-tauri\icons\32x32.png"
Check-File "apps\desktop\src-tauri\icons\128x128.png"
Check-File "apps\desktop\src-tauri\icons\128x128@2x.png"
Check-File "apps\desktop\src-tauri\icons\icon.icns"
Check-File "apps\desktop\src-tauri\icons\icon.ico"

Write-Host ""

if ($Errors -gt 0) {
    Write-Host "FAIL: $Errors expected path(s) are missing." -ForegroundColor Red
    Write-Host ""
    exit 1
}

Write-Host "All expected paths are present."
Write-Host ""
exit 0
