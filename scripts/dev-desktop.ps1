# SPDX-License-Identifier: Apache-2.0
# Start Conversation Simulator in desktop (Tauri) dev mode (Windows PowerShell).
# Launches convsim-core (port 7355), then runs `tauri dev` which starts the
# web dev server (port 7354) and opens the native window.
# Prerequisites: Rust toolchain (rustup), Tauri system deps, and a completed
# .\scripts\setup.ps1. Press Ctrl-C to stop all services.

$RepoRoot   = (Resolve-Path "$PSScriptRoot\..").Path
$CoreDir    = Join-Path $RepoRoot "services\convsim-core"
$DesktopDir = Join-Path $RepoRoot "apps\desktop"

$CorePort = 7355
$WebPort  = 7354
$LogDir   = if ($env:CONVSIM_LOG_DIR) { $env:CONVSIM_LOG_DIR } else { Join-Path $env:USERPROFILE ".convsim\logs" }

function Fail([string]$Message) {
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host ""
    exit 1
}

function Test-PortInUse([int]$Port, [string]$Service) {
    $hits = netstat -ano 2>$null | Select-String "TCP\s+[\d.]+:$Port\s+[\d.:]+\s+LISTENING"
    if ($hits) {
        $parts  = ($hits[0].Line.Trim() -split '\s+')
        $procId = $parts[-1]
        $name   = try { (Get-Process -Id $procId -ErrorAction Stop).Name } catch { "unknown" }
        Fail "Port $Port is already in use by PID $procId ($name).`nStop that process before starting $Service."
    }
}

Write-Host ""
Write-Host "Conversation Simulator — desktop dev"
Write-Host "======================================"
Write-Host ""

# --- Dependency checks ---
if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    Fail "Rust toolchain not found. Install via rustup:`n  https://rustup.rs/"
}

$VenvUvicorn = Join-Path $CoreDir ".venv\Scripts\uvicorn.exe"
$Uvicorn = $null
if (Test-Path $VenvUvicorn) {
    $Uvicorn = $VenvUvicorn
} elseif (Get-Command uvicorn -ErrorAction SilentlyContinue) {
    $Uvicorn = (Get-Command uvicorn).Source
} else {
    Fail "uvicorn not found. Run setup first:`n  .\scripts\setup.ps1"
}

$PkgManager = $null
if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    $PkgManager = "pnpm"
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    $PkgManager = "npm"
} else {
    Fail "npm or pnpm not found. Run setup first:`n  .\scripts\setup.ps1"
}

# --- Port conflict checks ---
Test-PortInUse $CorePort "convsim-core"
Test-PortInUse $WebPort  "convsim-ui"

# --- Ensure log directory exists ---
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "Starting convsim-core on port $CorePort..."
# Forward CONVSIM_LOG_DIR so uvicorn's ServiceConfig picks it up via env prefix.
# Set it on the parent (children inherit) rather than Start-Process -Environment,
# which only exists on PowerShell 7.4+ and would fail on Windows PowerShell 5.1.
$env:CONVSIM_LOG_DIR = $LogDir
$CoreProc = Start-Process -FilePath $Uvicorn `
    -ArgumentList "convsim_core.main:app", "--host", "127.0.0.1", "--port", $CorePort, "--reload" `
    -WorkingDirectory $CoreDir `
    -PassThru -NoNewWindow

Write-Host "Waiting for convsim-core to be ready..."
$ready = $false
for ($i = 0; $i -lt 20; $i++) {
    try {
        $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$CorePort/api/health" -UseBasicParsing -TimeoutSec 1 -ErrorAction SilentlyContinue
        if ($resp.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
    Start-Sleep -Seconds 1
}
if ($ready) { Write-Host "  convsim-core ready." }

Write-Host ""
Write-Host "Starting Tauri desktop dev (opens native window)..."
Write-Host "  Tauri will also start convsim-ui on port $WebPort."
Write-Host ""
Write-Host "Logs: $LogDir"
Write-Host "Press Ctrl-C to stop all services."
Write-Host ""

$TauriArgs = if ($PkgManager -eq "pnpm") { @("tauri", "dev") } else { @("x", "tauri", "dev") }
$TauriCmd  = if ($PkgManager -eq "pnpm") { "pnpm" } else { "npx" }

$TauriProc = Start-Process -FilePath $TauriCmd `
    -ArgumentList $TauriArgs `
    -WorkingDirectory $DesktopDir `
    -PassThru -NoNewWindow

try {
    while (-not $CoreProc.HasExited -and -not $TauriProc.HasExited) {
        Start-Sleep -Seconds 1
    }
    if ($CoreProc.HasExited -or $TauriProc.HasExited) {
        Write-Host ""
        Write-Host "A service stopped unexpectedly. Check logs at: $LogDir" -ForegroundColor Red
    }
} finally {
    if (-not $CoreProc.HasExited)  { Stop-Process -Id $CoreProc.Id  -Force -ErrorAction SilentlyContinue }
    if (-not $TauriProc.HasExited) { Stop-Process -Id $TauriProc.Id -Force -ErrorAction SilentlyContinue }
}
