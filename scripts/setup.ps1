# SPDX-License-Identifier: Apache-2.0
# Check that all required developer dependencies are present (Windows PowerShell version).
# Prints the next dependency to install, or confirms the environment is ready.
# Does not modify global state or download model files.

$RequiredPythonMajor = 3
$RequiredPythonMinor = 10
$RequiredNodeMajor = 18

function Fail {
    param([string]$Message)
    Write-Error $Message
    exit 1
}

Write-Host ""
Write-Host "Conversation Simulator — environment check"
Write-Host "==========================================="
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
if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    $pkgManager = "pnpm"
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    $pkgManager = "npm"
} else {
    Fail "npm or pnpm is required but not found.`n       npm is included with Node.js — install Node.js from https://nodejs.org/"
}

Write-Host "  $pkgManager ... OK"

Write-Host ""
Write-Host "All required dependencies found."
Write-Host ""
Write-Host "Next steps:"
Write-Host ""
Write-Host "  1. Install frontend packages:"
Write-Host "       $pkgManager install"
Write-Host ""
Write-Host "  2. Install Python packages (once convsim-core is implemented):"
Write-Host "       cd services\convsim-core"
Write-Host "       python -m venv .venv"
Write-Host "       .venv\Scripts\activate"
Write-Host "       pip install -e '.[dev]'"
Write-Host ""
Write-Host "  3. Start local dev:"
Write-Host "       .\scripts\dev.ps1"
Write-Host ""
Write-Host "NOTE: No model files are downloaded by this script."
Write-Host "      The app will prompt you to install a model on first run."
Write-Host ""
