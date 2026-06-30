# SPDX-License-Identifier: Apache-2.0
# Set up the Conversation Simulator development environment (Windows PowerShell).
# Checks dependencies, installs frontend packages, creates a Python virtual
# environment for convsim-core, and creates local data directories.
# Does not modify global state or download model files.

$RequiredPythonMajor = 3
$RequiredPythonMinor = 10
$RequiredNodeMajor = 18

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$CoreDir = Join-Path $RepoRoot "services\convsim-core"

$LogDir  = if ($env:CONVSIM_LOG_DIR)  { $env:CONVSIM_LOG_DIR }  else { Join-Path $env:USERPROFILE ".convsim\logs" }
$DataDir = if ($env:CONVSIM_DATA_DIR) { $env:CONVSIM_DATA_DIR } else { Join-Path $env:USERPROFILE ".convsim\data" }
$DbDir   = if ($env:CONVSIM_DB_DIR)   { $env:CONVSIM_DB_DIR }   else { Join-Path $env:USERPROFILE ".convsim\db" }

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host ""
    exit 1
}

Write-Host ""
Write-Host "Conversation Simulator — setup"
Write-Host "================================"
Write-Host ""
Write-Host "Checking required dependencies..."
Write-Host ""

# --- Python ---
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $pythonCmd) {
    Fail "Python ${RequiredPythonMajor}.${RequiredPythonMinor}+ is required but not found.`n       Install it from https://www.python.org/downloads/"
}

$pythonVersion = & $pythonCmd.Source -c "import sys; print('%d.%d' % (sys.version_info.major, sys.version_info.minor))" 2>$null
$parts = $pythonVersion -split '\.'
$pyMajor = [int]$parts[0]
$pyMinor = [int]$parts[1]

if ($pyMajor -lt $RequiredPythonMajor -or ($pyMajor -eq $RequiredPythonMajor -and $pyMinor -lt $RequiredPythonMinor)) {
    Fail "Python ${RequiredPythonMajor}.${RequiredPythonMinor}+ is required. Found: $pythonVersion`n       Install a newer version from https://www.python.org/downloads/"
}

Write-Host "  python $pythonVersion ... OK"

# --- Node.js ---
$nodeCmd = Get-Command node -ErrorAction SilentlyContinue
if (-not $nodeCmd) {
    Fail "Node.js ${RequiredNodeMajor}+ is required but not found.`n       Install it from https://nodejs.org/ (${RequiredNodeMajor}.x LTS or newer)"
}

$nodeVersionRaw = & node --version 2>$null
$nodeVersion = $nodeVersionRaw -replace '^v', ''
$nodeMajor = [int]($nodeVersion -split '\.')[0]

if ($nodeMajor -lt $RequiredNodeMajor) {
    Fail "Node.js ${RequiredNodeMajor}+ is required. Found: $nodeVersion`n       Install a newer version from https://nodejs.org/"
}

Write-Host "  node $nodeVersion ... OK"

# --- Package manager ---
$pkgManager = $null
$pkgManagerPath = $null
if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    $pkgManager = "pnpm"
    $pkgManagerPath = (Get-Command pnpm).Source
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    $pkgManager = "npm"
    $pkgManagerPath = (Get-Command npm).Source
} else {
    Fail "npm or pnpm is required but not found.`n       npm is included with Node.js — install Node.js from https://nodejs.org/"
}

Write-Host "  $pkgManager ... OK"

# --- Frontend dependencies ---
Write-Host ""
Write-Host "Installing frontend dependencies..."
Write-Host ""
Push-Location $RepoRoot
& $pkgManagerPath install
Pop-Location
Write-Host ""
Write-Host "  Frontend dependencies installed."

# --- Python virtual environment ---
Write-Host ""
Write-Host "Setting up Python environment (services\convsim-core)..."
Write-Host ""

$VenvDir    = Join-Path $CoreDir ".venv"
$VenvPip    = Join-Path $VenvDir "Scripts\pip.exe"

if (-not (Test-Path $VenvDir)) {
    Write-Host "  Creating virtual environment..."
    & $pythonCmd.Source -m venv $VenvDir
}

& $VenvPip install -q --upgrade pip
& $VenvPip install -q -e "$CoreDir[dev]"
Write-Host "  Python packages installed."

# --- Local data directories ---
Write-Host ""
Write-Host "Creating local data directories..."
Write-Host ""

New-Item -ItemType Directory -Force -Path $LogDir  | Out-Null
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
New-Item -ItemType Directory -Force -Path $DbDir   | Out-Null

Write-Host "  $LogDir"
Write-Host "  $DataDir"
Write-Host "  $DbDir"

Write-Host ""
Write-Host "Setup complete."
Write-Host ""
Write-Host "Start local dev with:"
Write-Host ""
Write-Host "  .\scripts\dev.ps1      (Windows PowerShell)"
Write-Host ""
Write-Host "NOTE: No model files are downloaded by this script."
Write-Host "      The app will prompt you to install a model on first run."
Write-Host ""
exit 0
