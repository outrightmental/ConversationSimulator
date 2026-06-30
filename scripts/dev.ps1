# SPDX-License-Identifier: Apache-2.0
# Start the Conversation Simulator local dev services (Windows PowerShell).
# Launches convsim-core (port 7355) and convsim-ui (port 7354).
# Checks for port conflicts before starting. Press Ctrl-C to stop all services.

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$CoreDir  = Join-Path $RepoRoot "services\convsim-core"
$WebDir   = Join-Path $RepoRoot "apps\web"

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
Write-Host "Conversation Simulator — local dev"
Write-Host "===================================="
Write-Host ""

# --- Port conflict checks ---
Test-PortInUse $CorePort "convsim-core"
Test-PortInUse $WebPort  "convsim-ui"

# --- Locate uvicorn ---
$VenvUvicorn = Join-Path $CoreDir ".venv\Scripts\uvicorn.exe"
$Uvicorn = $null
if (Test-Path $VenvUvicorn) {
    $Uvicorn = $VenvUvicorn
} elseif (Get-Command uvicorn -ErrorAction SilentlyContinue) {
    $Uvicorn = (Get-Command uvicorn).Source
} else {
    Fail "uvicorn not found. Run setup first:`n  .\scripts\setup.ps1"
}

# --- Locate package manager ---
$PkgManager = $null
$PkgManagerPath = $null
if (Get-Command pnpm -ErrorAction SilentlyContinue) {
    $PkgManager     = "pnpm"
    $PkgManagerPath = (Get-Command pnpm).Source
} elseif (Get-Command npm -ErrorAction SilentlyContinue) {
    $PkgManager     = "npm"
    $PkgManagerPath = (Get-Command npm).Source
} else {
    Fail "npm or pnpm not found. Run setup first:`n  .\scripts\setup.ps1"
}

# --- Ensure log directory exists ---
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "Service URLs:"
Write-Host ""
Write-Host "  convsim-ui    http://127.0.0.1:$WebPort  (browser UI)"
Write-Host "  convsim-core  http://127.0.0.1:$CorePort  (API server)"
Write-Host ""
Write-Host "Logs: $LogDir"
Write-Host ""
Write-Host "Press Ctrl-C to stop all services."
Write-Host ""

$Jobs = @()

try {
    # --- Start convsim-core ---
    Write-Host "Starting convsim-core..."
    $CoreJob = Start-Job -ScriptBlock {
        param($Dir, $Uvicorn, $Port, $LogDir)
        Set-Location $Dir
        $env:CONVSIM_LOG_DIR = $LogDir
        & $Uvicorn convsim_core.main:app --host 127.0.0.1 --port $Port --reload
    } -ArgumentList $CoreDir, $Uvicorn, $CorePort, $LogDir
    $Jobs += $CoreJob

    # --- Start convsim-ui ---
    Write-Host "Starting convsim-ui..."
    $WebJob = Start-Job -ScriptBlock {
        param($Dir, $PkgMgrPath, $PkgMgr)
        Set-Location $Dir
        if ($PkgMgr -eq "pnpm") {
            & $PkgMgrPath dev
        } else {
            & $PkgMgrPath run dev
        }
    } -ArgumentList $WebDir, $PkgManagerPath, $PkgManager
    $Jobs += $WebJob

    Write-Host ""

    # Stream output from both jobs until interrupted or a job exits unexpectedly
    while ($true) {
        foreach ($job in $Jobs) {
            $out = Receive-Job -Job $job -ErrorAction SilentlyContinue
            if ($out) { Write-Host $out }
        }
        $dead = @($Jobs | Where-Object { $_.State -ne "Running" })
        if ($dead.Count -gt 0) {
            Write-Host ""
            Write-Host "A service stopped unexpectedly. Check logs at: $LogDir" -ForegroundColor Yellow
            break
        }
        Start-Sleep -Milliseconds 200
    }
} finally {
    Write-Host ""
    Write-Host "Stopping services..."
    foreach ($job in $Jobs) {
        Stop-Job   -Job $job -ErrorAction SilentlyContinue
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Done."
}
