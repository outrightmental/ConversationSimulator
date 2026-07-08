# SPDX-License-Identifier: Apache-2.0
# first-run-check.ps1 — Report system readiness for Conversation Simulator (Windows).
#
# Checks: OS version, CPU architecture, RAM, disk space, audio devices,
#         and local port availability (7354-7358).
#
# Usage:   .\scripts\first-run-check.ps1
# Exit 0:  all required checks passed (warnings may be present)
# Exit 1:  one or more required checks failed

$Errors   = 0
$Warnings = 0

function Status-Pass([string]$msg) { Write-Host "  PASS  $msg" -ForegroundColor Green }
function Status-Warn([string]$msg) { Write-Host "  WARN  $msg" -ForegroundColor Yellow; $script:Warnings++ }
function Status-Fail([string]$msg) { Write-Host "  FAIL  $msg" -ForegroundColor Red; $script:Errors++ }
function Status-Info([string]$msg) { Write-Host "  INFO  $msg" }

# ── OS and CPU architecture ───────────────────────────────────────────────────

function Check-OsArch {
    $os   = [System.Environment]::OSVersion
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture

    $winVer = $os.Version
    if ($winVer.Major -lt 10) {
        Status-Fail "OS: Windows $($winVer) — Windows 10 or newer required"
    } else {
        # Windows 10 build 19041 is 20H1 (minimum for WebView2 / Tauri).
        $buildNum = $winVer.Build
        if ($buildNum -lt 19041) {
            Status-Warn "OS: Windows 10 build $buildNum — build 19041 (20H1) or newer recommended for WebView2"
        } else {
            Status-Pass "OS: Windows $($winVer.Major).$($winVer.Minor) build $buildNum"
        }
    }

    switch ($arch) {
        'X64'   { Status-Pass "CPU: 64-bit x86 ($arch)" }
        'Arm64' { Status-Pass "CPU: 64-bit ARM ($arch)" }
        default  { Status-Warn "CPU: $arch — may not have a pre-built binary; build from source if needed" }
    }
}

# ── RAM ───────────────────────────────────────────────────────────────────────

function Check-Ram {
    try {
        $mem = Get-CimInstance -ClassName Win32_PhysicalMemory -ErrorAction Stop |
               Measure-Object -Property Capacity -Sum
        $ramGb = [math]::Floor($mem.Sum / 1GB)
        if ($ramGb -ge 16) {
            Status-Pass "RAM: ${ramGb} GB (sufficient for standard-tier models)"
        } elseif ($ramGb -ge 8) {
            Status-Warn "RAM: ${ramGb} GB — minimum met; 16 GB recommended for smooth inference"
        } else {
            Status-Fail "RAM: ${ramGb} GB — 8 GB minimum required"
        }
    } catch {
        Status-Warn "RAM: could not query physical memory — $_"
    }
}

# ── Disk space ────────────────────────────────────────────────────────────────

function Check-Disk {
    $userProfile = $env:USERPROFILE
    if (-not $userProfile) { $userProfile = "C:\" }

    try {
        $drive = Split-Path -Qualifier $userProfile
        $disk  = Get-PSDrive -Name ($drive.TrimEnd(':')) -ErrorAction Stop
        $freeGb = [math]::Floor($disk.Free / 1GB)
        if ($freeGb -ge 20) {
            Status-Pass "Disk: ${freeGb} GB free on $drive (model weights need up to 15 GB)"
        } elseif ($freeGb -ge 5) {
            Status-Warn "Disk: ${freeGb} GB free — 20 GB recommended; starter model needs ~3 GB"
        } else {
            Status-Fail "Disk: ${freeGb} GB free — at least 5 GB required for the starter model"
        }
    } catch {
        Status-Warn "Disk: could not determine available space — $_"
    }
}

# ── Audio devices — microphone and speaker ────────────────────────────────────

function Check-Audio {
    # Microphone
    try {
        # Check for capture devices via the audio endpoint list.
        $micDevices = Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue |
                      Where-Object { $_.FriendlyName -match 'Microphone|Headset|Line In|Capture' }
        if ($micDevices) {
            Status-Pass "Microphone: $($micDevices.Count) input device(s) detected"
        } else {
            Status-Warn "Microphone: no audio input device found — voice input requires a microphone"
        }
    } catch {
        Status-Warn "Microphone: could not query audio devices — $_"
    }

    # Speaker / headphones
    try {
        $speakers = Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue |
                    Where-Object { $_.FriendlyName -match 'Speaker|Headphone|Output|Playback' }
        if ($speakers) {
            Status-Pass "Speaker: $($speakers.Count) output device(s) detected"
        } else {
            Status-Warn "Speaker: no audio output device found — voice output requires speakers or headphones"
        }
    } catch {
        Status-Warn "Speaker: could not query audio output devices — $_"
    }
}

# ── WebView2 runtime ──────────────────────────────────────────────────────────
# Tauri on Windows requires the WebView2 runtime (ships with Windows 11 and
# Windows 10 20H2+; may need manual install on older builds).

function Check-WebView2 {
    $wv2Keys = @(
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
        'HKCU:\SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    )
    $found = $false
    foreach ($key in $wv2Keys) {
        if (Test-Path $key) { $found = $true; break }
    }
    if ($found) {
        Status-Pass "WebView2: runtime is installed (required by the desktop app)"
    } else {
        Status-Warn "WebView2: not detected — install from https://developer.microsoft.com/en-us/microsoft-edge/webview2/"
    }
}

# ── Port availability ─────────────────────────────────────────────────────────

function Check-Port([int]$Port, [string]$Label) {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        # NB: do not name this $pid — that is a read-only automatic variable
        # in PowerShell, and assigning to it throws a terminating error.
        $procId = $conn.OwningProcess | Select-Object -First 1
        $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $name = if ($proc) { $proc.Name } else { 'unknown' }
        Status-Warn "Port $Port ($Label): in use by PID $procId ($name) — stop it before starting services"
    } else {
        Status-Pass "Port $Port ($Label): free"
    }
}

function Check-Ports {
    Check-Port 7354 'convsim-ui'
    Check-Port 7355 'convsim-core'
    Check-Port 7356 'llm-runtime'
    Check-Port 7357 'stt-runtime'
    Check-Port 7358 'tts-runtime'
}

# ── Runtime health (developer path) ──────────────────────────────────────────

function Check-Runtimes {
    Status-Info "Runtime versions (developer path):"

    # Python
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if (-not $pythonCmd) {
        $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
    }
    if ($pythonCmd) {
        $pyVer = & $pythonCmd.Source -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
        $parts = ($pyVer -split '\.')
        $pyMaj = [int]$parts[0]; $pyMin = [int]$parts[1]
        if ($pyMaj -ge 3 -and $pyMin -ge 10) {
            Status-Pass "Python $pyVer (convsim-core requires 3.10+)"
        } else {
            Status-Fail "Python $pyVer — 3.10+ required for convsim-core"
        }
    } else {
        Status-Warn "Python: not found — required for the developer install path"
    }

    # Node.js
    $nodeCmd = Get-Command node -ErrorAction SilentlyContinue
    if ($nodeCmd) {
        $nodeVer = (& node --version 2>$null) -replace '^v', ''
        $nodeMaj = [int]($nodeVer -split '\.')[0]
        if ($nodeMaj -ge 18) {
            Status-Pass "Node.js $nodeVer (requires 18+)"
        } else {
            Status-Fail "Node.js $nodeVer — 18+ required"
        }
    } else {
        Status-Warn "Node.js: not found — required for the developer install path"
    }
}

# ── Main ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "Conversation Simulator — first-run check"
Write-Host "=========================================="
Write-Host ""
Write-Host "OS and CPU:"
Check-OsArch
Write-Host ""
Write-Host "Memory:"
Check-Ram
Write-Host ""
Write-Host "Disk space:"
Check-Disk
Write-Host ""
Write-Host "Audio:"
Check-Audio
Write-Host ""
Write-Host "WebView2 (desktop app):"
Check-WebView2
Write-Host ""
Write-Host "Service ports:"
Check-Ports
Write-Host ""
Check-Runtimes
Write-Host ""
Write-Host "────────────────────────────────────────────"
if ($Errors -gt 0) {
    Write-Host "FAIL  $Errors required check(s) failed — see FAIL lines above." -ForegroundColor Red
    Write-Host ""
    Write-Host "Fix the issues above, then run this script again."
    Write-Host ""
    exit 1
} elseif ($Warnings -gt 0) {
    Write-Host "WARN  All required checks passed. $Warnings warning(s) noted above." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "The app will run, but some features may be degraded."
    Write-Host "See docs\install.md for system requirements."
    Write-Host ""
} else {
    Write-Host "PASS  All checks passed. System is ready to run Conversation Simulator." -ForegroundColor Green
    Write-Host ""
}
