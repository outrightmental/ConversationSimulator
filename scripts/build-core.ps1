# SPDX-License-Identifier: Apache-2.0
# build-core.ps1 — Build the convsim-core standalone binary using PyInstaller (Windows).
#
# Creates a self-contained executable that ships inside the Tauri app bundle and
# runs without a developer virtual environment or a Python installation.
#
# Usage:
#   .\scripts\build-core.ps1 [-Clean] [-Help]
#
# Options:
#   -Clean   Remove PyInstaller build\ and dist\ directories before building.
#   -Help    Print this help and exit.
#
# Prerequisites:
#   The convsim-core venv must be active, or CONVSIM_PYTHON must point to a
#   Python interpreter that has convsim-core and its dependencies installed.
#   Run .\scripts\setup.ps1 first to create the venv.
#
# Output:
#   apps\desktop\src-tauri\resources\bin\convsim-core.exe

[CmdletBinding()]
param(
    [switch]$Clean,
    [switch]$Help
)

if ($Help) {
    Get-Content $MyInvocation.MyCommand.Path |
        Where-Object { $_ -match "^#" } |
        ForEach-Object { $_ -replace "^# ?", "" }
    exit 0
}

$RepoRoot  = Split-Path -Parent $PSScriptRoot
$CoreDir   = Join-Path $RepoRoot "services\convsim-core"
$OutDir    = Join-Path $RepoRoot "apps\desktop\src-tauri\resources\bin"

# ── Locate Python interpreter ──────────────────────────────────────────────────

$PyCmd = $env:CONVSIM_PYTHON
if (-not $PyCmd) {
    $VenvPy = Join-Path $CoreDir ".venv\Scripts\python.exe"
    if (Test-Path $VenvPy) {
        $PyCmd = $VenvPy
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        $PyCmd = "python"
    } else {
        Write-Error "Python not found. Run .\scripts\setup.ps1 first."
        exit 1
    }
}

Write-Host ""
Write-Host "Conversation Simulator — build-core"
Write-Host "======================================"
$pyVer = & $PyCmd --version 2>&1
Write-Host "Python   : $pyVer"
Write-Host "Core dir : $CoreDir"
Write-Host "Output   : $OutDir"
Write-Host ""

# ── Ensure pyinstaller is available ───────────────────────────────────────────

$piVer = & $PyCmd -m PyInstaller --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing pyinstaller into the project environment..."
    & $PyCmd -m pip install -q pyinstaller
    $piVer = & $PyCmd -m PyInstaller --version 2>&1
}
Write-Host "PyInstaller : $piVer"
Write-Host ""

# ── Clean previous artefacts ──────────────────────────────────────────────────

if ($Clean) {
    Write-Host "Cleaning previous build artefacts..."
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $CoreDir "build")
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue (Join-Path $CoreDir "dist")
    Write-Host "  Removed build\ and dist\"
    Write-Host ""
}

# ── Run PyInstaller ────────────────────────────────────────────────────────────

Write-Host "Building convsim-core (this may take a minute)..."
$prevLocation = Get-Location
Set-Location $CoreDir
try {
    & $PyCmd -m PyInstaller convsim-core.spec --noconfirm
    if ($LASTEXITCODE -ne 0) {
        Write-Error "PyInstaller exited with code $LASTEXITCODE"
        exit 1
    }
} finally {
    Set-Location $prevLocation
}

Write-Host ""
Write-Host "Build complete."

# ── Copy to Tauri resources ────────────────────────────────────────────────────

$BuiltExe = Join-Path $CoreDir "dist\convsim-core.exe"
if (-not (Test-Path $BuiltExe)) {
    Write-Error "Expected binary not found at $BuiltExe"
    exit 1
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
Copy-Item -Force $BuiltExe (Join-Path $OutDir "convsim-core.exe")

$sizeKB = [Math]::Round((Get-Item (Join-Path $OutDir "convsim-core.exe")).Length / 1KB, 0)
Write-Host ""
Write-Host "Installed to : $(Join-Path $OutDir "convsim-core.exe")"
Write-Host "Size         : ${sizeKB} KB"
Write-Host ""
Write-Host "The Tauri desktop build will bundle this binary automatically."
Write-Host "Run: pnpm --filter @convsim/desktop build"
Write-Host ""
