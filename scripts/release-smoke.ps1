# SPDX-License-Identifier: Apache-2.0
# release-smoke.ps1 — Cross-platform release smoke runner (Windows PowerShell).
#
# Runs the automated CI subset by default. Pass -Full to include subsystems
# that require running services and manual confirmation.
#
# Usage:
#   .\scripts\release-smoke.ps1           # CI subset (no model downloads)
#   .\scripts\release-smoke.ps1 -Full     # Full release smoke (services must be running)
#   .\scripts\release-smoke.ps1 -Help
#
# Subsystem labels in output:
#   [setup]            monorepo paths and developer scripts
#   [health]           backend /api/health endpoint
#   [web]              web frontend typecheck
#   [model-mgr]        model manager in fake-runtime mode (no downloads)
#   [scenario-lib]     scenario library API
#   [text-session]     create a session and complete one turn
#   [debrief]          debrief report generation
#   [pack-valid]       official pack schema validation
#   [voice]            voice fallback (TTS-disabled path)
#   [offline]          no outbound network calls during a scripted play session
#   [packaged-startup] packaged binary build infrastructure and startup tests

[CmdletBinding()]
param(
    [switch]$Full,
    [switch]$Help,
    [string]$CoreUrl = $env:CONVSIM_CORE_URL ?? "http://127.0.0.1:7355"
)

if ($Help) {
    Get-Content $MyInvocation.MyCommand.Path | Where-Object { $_ -match "^#" } | ForEach-Object { $_ -replace "^# ?", "" }
    exit 0
}

$Mode = if ($Full) { "full" } else { "ci" }
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ArtifactDir = if ($env:CONVSIM_SMOKE_ARTIFACT_DIR) { $env:CONVSIM_SMOKE_ARTIFACT_DIR } else {
    Join-Path $env:TEMP "convsim-release-smoke-$PID"
}

# ── Status tracking ───────────────────────────────────────────────────────────

$script:Errors  = 0
$script:Skipped = 0
$script:Passed  = 0
$script:ArtifactsWritten = $false

function Write-Pass  { param([string]$Sub, [string]$Msg) Write-Host "  PASS  [$Sub] $Msg"; $script:Passed++ }
function Write-Fail  { param([string]$Sub, [string]$Msg) Write-Host "  FAIL  [$Sub] $Msg" -ForegroundColor Red; $script:Errors++ }
function Write-Skip  { param([string]$Sub, [string]$Msg) Write-Host "  SKIP  [$Sub] $Msg"; $script:Skipped++ }
function Write-Info  { param([string]$Sub, [string]$Msg) Write-Host "  INFO  [$Sub] $Msg" }
function Write-Label { param([string]$Title) Write-Host ""; Write-Host "── $Title ──" }

# ── Artifact helpers ──────────────────────────────────────────────────────────

function Initialize-Artifacts {
    New-Item -ItemType Directory -Force -Path $ArtifactDir | Out-Null
    Write-Info "meta" "Artifact directory: $ArtifactDir"
    @"
platform: Windows
arch: $([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)
mode: $Mode
date: $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssZ' -AsUTC)
"@ | Set-Content (Join-Path $ArtifactDir "smoke-meta.txt")
}

function Save-ArtifactText {
    param([string]$FileName, [string]$Content)
    $Content | Add-Content (Join-Path $ArtifactDir $FileName)
    $script:ArtifactsWritten = $true
}

function Copy-BackendLogs {
    $logDir = if ($env:CONVSIM_LOG_DIR) { $env:CONVSIM_LOG_DIR } else { Join-Path $env:USERPROFILE ".convsim\logs" }
    if (Test-Path $logDir) {
        Copy-Item -Recurse -Force $logDir (Join-Path $ArtifactDir "backend-logs") -ErrorAction SilentlyContinue
        $script:ArtifactsWritten = $true
    }
}

# ── Find pytest ───────────────────────────────────────────────────────────────

function Get-PytestPath {
    $venvPytest = Join-Path $RepoRoot "services\convsim-core\.venv\Scripts\pytest.exe"
    if (Test-Path $venvPytest) { return $venvPytest }
    $global = Get-Command pytest -ErrorAction SilentlyContinue
    if ($global) { return $global.Source }
    return $null
}

# ── [setup] ───────────────────────────────────────────────────────────────────

function Invoke-SmokSetup {
    Write-Label "[setup] Monorepo structure and developer scripts"

    $missing = 0
    $requiredDirs = @(
        "apps", "packages", "services", "runtimes", "packs", "schemas",
        "model-registry", "docs", "scripts",
        "apps\web", "apps\desktop",
        "packages\ui", "packages\scenario-schema", "packages\shared-types",
        "services\convsim-core",
        "runtimes\llama_cpp", "runtimes\whisper_cpp",
        "packs\official",
        "packs\official\job-interview-basic",
        "packs\official\everyday-negotiation",
        "packs\official\language-cafe",
        "packs\official\difficult-conversations"
    )
    $requiredFiles = @(
        "README.md", "LICENSE", "NOTICE", "package.json",
        "scripts\setup.sh", "scripts\setup.ps1",
        "scripts\dev.sh", "scripts\dev.ps1",
        "scripts\dev-desktop.sh", "scripts\dev-desktop.ps1",
        "scripts\first-run-check.sh", "scripts\first-run-check.ps1",
        "scripts\smoke-check.sh", "scripts\smoke-check.ps1",
        "scripts\release-smoke.sh", "scripts\release-smoke.ps1",
        "scripts\build-core.sh", "scripts\build-core.ps1",
        "scripts\depot-audit.sh", "scripts\depot-audit.ps1",
        ".github\workflows\ci.yml", ".github\workflows\release.yml",
        ".github\workflows\release-smoke.yml",
        "docs\release-checklist.md",
        "docs\platform-notes.md", "docs\release-notes-template.md",
        "docs\install.md", "docs\voice-smoke-tests.md",
        "services\convsim-core\pyproject.toml",
        "services\convsim-core\convsim-core.spec",
        "apps\web\package.json", "apps\desktop\package.json",
        "apps\desktop\src-tauri\resources\bin\.gitkeep"
    )

    foreach ($d in $requiredDirs) {
        if (-not (Test-Path -PathType Container (Join-Path $RepoRoot $d))) {
            Write-Fail "setup" "Missing directory: $d"
            $missing++
        }
    }
    foreach ($f in $requiredFiles) {
        if (-not (Test-Path -PathType Leaf (Join-Path $RepoRoot $f))) {
            Write-Fail "setup" "Missing file: $f"
            $missing++
        }
    }

    if ($missing -eq 0) {
        Write-Pass "setup" "All expected monorepo paths present"
    }
}

# ── [pack-valid] ──────────────────────────────────────────────────────────────

function Invoke-SmokePackValidation {
    Write-Label "[pack-valid] Official pack schema validation"

    $schemaTest = Join-Path $RepoRoot "packages\scenario-schema\tests\validate-packs.js"
    if (-not (Test-Path $schemaTest)) {
        Write-Skip "pack-valid" "validate-packs.js not found — run pnpm install first"
        return
    }
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Skip "pack-valid" "node not found"
        return
    }
    if (-not (Test-Path (Join-Path $RepoRoot "node_modules"))) {
        Write-Skip "pack-valid" "node_modules not installed — run pnpm install first"
        return
    }

    $out = node $schemaTest (Join-Path $RepoRoot "packs\official") 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pack-valid" "Pack schema validation failed"
        Save-ArtifactText "pack-valid-error.txt" ($out -join "`n")
        return
    }
    Write-Pass "pack-valid" "Official packs pass schema validation"
}

# ── [voice] ───────────────────────────────────────────────────────────────────

function Invoke-SmokeVoiceFallback {
    Write-Label "[voice] Voice fallback (TTS-disabled path)"

    $testFile = Join-Path $RepoRoot "services\convsim-core\tests\test_voice_smoke.py"
    if (-not (Test-Path $testFile)) {
        Write-Skip "voice" "test_voice_smoke.py not found"
        return
    }
    $pytestPath = Get-PytestPath
    if (-not $pytestPath) {
        Write-Skip "voice" "pytest not found — run setup.ps1 first"
        return
    }

    $prevLocation = Get-Location
    Set-Location (Join-Path $RepoRoot "services\convsim-core")
    try {
        $out = & $pytestPath tests/test_voice_smoke.py -v -k "fallback" 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "voice" "Voice fallback tests failed (TTS-disabled path)"
            Save-ArtifactText "voice-fallback-error.txt" ($out -join "`n")
            Copy-BackendLogs
            return
        }
    } finally {
        Set-Location $prevLocation
    }
    Write-Pass "voice" "Voice unavailable fallback tests passed (no TTS events when tts_enabled=False)"
}

# ── [health] ──────────────────────────────────────────────────────────────────

function Invoke-SmokeBackendHealth {
    Write-Label "[health] Backend /api/health"

    if ($Mode -eq "ci") {
        $testFile = Join-Path $RepoRoot "services\convsim-core\tests\test_health.py"
        if (-not (Test-Path $testFile)) {
            Write-Skip "health" "test_health.py not found"
            return
        }
        $pytestPath = Get-PytestPath
        if (-not $pytestPath) {
            Write-Skip "health" "pytest not found"
            return
        }
        $prevLocation = Get-Location
        Set-Location (Join-Path $RepoRoot "services\convsim-core")
        try {
            $out = & $pytestPath tests/test_health.py tests/test_fake_runtime.py -v 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Fail "health" "Backend health unit tests failed"
                Save-ArtifactText "health-error.txt" ($out -join "`n")
                return
            }
        } finally {
            Set-Location $prevLocation
        }
        Write-Pass "health" "Backend health unit tests passed (fake runtime)"
        return
    }

    try {
        $resp = Invoke-WebRequest -Uri "$CoreUrl/api/health" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        $body = $resp.Content | ConvertFrom-Json
        if ($body.status -ne "ok") {
            Write-Fail "health" "/api/health status=$($body.status) (expected ok)"
            return
        }
        Write-Pass "health" "/api/health status=ok runtime=$($body.runtime.status)"
    } catch {
        Write-Fail "health" "GET $CoreUrl/api/health failed: $_ — is convsim-core running?"
    }
}

# ── [model-mgr] ───────────────────────────────────────────────────────────────

function Invoke-SmokeModelManager {
    Write-Label "[model-mgr] Model manager (fake runtime, no downloads)"

    if ($Mode -eq "ci") {
        $testFile = Join-Path $RepoRoot "services\convsim-core\tests\test_model_manager.py"
        if (-not (Test-Path $testFile)) {
            Write-Skip "model-mgr" "test_model_manager.py not found"
            return
        }
        $pytestPath = Get-PytestPath
        if (-not $pytestPath) {
            Write-Skip "model-mgr" "pytest not found"
            return
        }
        $prevLocation = Get-Location
        Set-Location (Join-Path $RepoRoot "services\convsim-core")
        try {
            $out = & $pytestPath tests/test_model_manager.py tests/test_model_registry.py -v 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Fail "model-mgr" "Model manager unit tests failed"
                Save-ArtifactText "model-mgr-error.txt" ($out -join "`n")
                return
            }
        } finally {
            Set-Location $prevLocation
        }
        Write-Pass "model-mgr" "Model manager unit tests passed (fake runtime, no downloads)"
        return
    }

    try {
        $resp = Invoke-WebRequest -Uri "$CoreUrl/api/models" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -ne 200) {
            Write-Fail "model-mgr" "GET /api/models returned HTTP $($resp.StatusCode)"
            return
        }
        Write-Pass "model-mgr" "Model list endpoint returned HTTP 200"
    } catch {
        Write-Fail "model-mgr" "GET $CoreUrl/api/models failed: $_"
    }
}

# ── [scenario-lib] ────────────────────────────────────────────────────────────

function Invoke-SmokeScenarioLibrary {
    Write-Label "[scenario-lib] Scenario library API"

    if ($Mode -eq "ci") {
        $testFile = Join-Path $RepoRoot "services\convsim-core\tests\test_scenarios_api.py"
        if (-not (Test-Path $testFile)) {
            Write-Skip "scenario-lib" "test_scenarios_api.py not found"
            return
        }
        $pytestPath = Get-PytestPath
        if (-not $pytestPath) {
            Write-Skip "scenario-lib" "pytest not found"
            return
        }
        $prevLocation = Get-Location
        Set-Location (Join-Path $RepoRoot "services\convsim-core")
        try {
            $out = & $pytestPath tests/test_scenarios_api.py -v 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Fail "scenario-lib" "Scenario library API tests failed"
                Save-ArtifactText "scenario-lib-error.txt" ($out -join "`n")
                return
            }
        } finally {
            Set-Location $prevLocation
        }
        Write-Pass "scenario-lib" "Scenario library API tests passed"
        return
    }

    try {
        $resp = Invoke-WebRequest -Uri "$CoreUrl/api/scenarios" -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        if ($resp.StatusCode -ne 200) {
            Write-Fail "scenario-lib" "GET /api/scenarios returned HTTP $($resp.StatusCode)"
            return
        }
        Write-Pass "scenario-lib" "Scenario library endpoint returned HTTP 200"
    } catch {
        Write-Fail "scenario-lib" "GET $CoreUrl/api/scenarios failed: $_"
    }
}

# ── [text-session] ────────────────────────────────────────────────────────────

function Invoke-SmokeTextSession {
    Write-Label "[text-session] Text session (create session + one turn)"

    if ($Mode -eq "ci") {
        $testFiles = @("test_session_state.py", "test_turn_pipeline.py")
        foreach ($tf in $testFiles) {
            if (-not (Test-Path (Join-Path $RepoRoot "services\convsim-core\tests\$tf"))) {
                Write-Skip "text-session" "$tf not found"
                return
            }
        }
        $pytestPath = Get-PytestPath
        if (-not $pytestPath) {
            Write-Skip "text-session" "pytest not found"
            return
        }
        $prevLocation = Get-Location
        Set-Location (Join-Path $RepoRoot "services\convsim-core")
        try {
            $out = & $pytestPath tests/test_session_state.py tests/test_turn_pipeline.py -v 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Fail "text-session" "Text session unit tests failed"
                Save-ArtifactText "text-session-error.txt" ($out -join "`n")
                return
            }
        } finally {
            Set-Location $prevLocation
        }
        Write-Pass "text-session" "Text session unit tests passed (fake runtime)"
        return
    }

    Write-Info "text-session" "Creating session via $CoreUrl/api/sessions"
    try {
        # scenario_id is the bare registry id (not "pack/scenario"); player_role_name
        # is required by POST /api/sessions. See services/convsim-core routers/sessions.py.
        $createBody = '{"scenario_id":"behavioral_interview","player_role_name":"Smoke Tester","difficulty":"standard","language":"en","input_mode":"text-only","tts_enabled":false}'
        $createResp = Invoke-WebRequest -Uri "$CoreUrl/api/sessions" -Method POST `
            -ContentType "application/json" -Body $createBody -TimeoutSec 10 -UseBasicParsing -ErrorAction Stop
        if ($createResp.StatusCode -ne 201) {
            Write-Fail "text-session" "POST /api/sessions returned HTTP $($createResp.StatusCode)"
            return
        }
        $sessionData = $createResp.Content | ConvertFrom-Json
        $sessionId = $sessionData.session_id
        Write-Info "text-session" "Session created: $sessionId"

        # Start the session (moves it into PlayerTurnListening) before submitting a
        # turn — POST /turn rejects turns from any other state with HTTP 409.
        $startResp = Invoke-WebRequest -Uri "$CoreUrl/api/sessions/$sessionId/start" -Method POST `
            -TimeoutSec 30 -UseBasicParsing -ErrorAction Stop
        if ($startResp.StatusCode -ne 200) {
            Write-Fail "text-session" "POST /api/sessions/$sessionId/start returned HTTP $($startResp.StatusCode)"
            return
        }

        # Submit one player turn. Endpoint is /turn (singular); body field is "content".
        $turnBody = '{"content":"Hello, I am ready to start."}'
        $turnResp = Invoke-WebRequest -Uri "$CoreUrl/api/sessions/$sessionId/turn" -Method POST `
            -ContentType "application/json" -Body $turnBody -TimeoutSec 30 -UseBasicParsing -ErrorAction Stop
        if ($turnResp.StatusCode -ne 200) {
            Write-Fail "text-session" "POST /api/sessions/$sessionId/turn returned HTTP $($turnResp.StatusCode)"
            return
        }
        Write-Pass "text-session" "Session created, started, and one turn completed (session_id=$sessionId)"
    } catch {
        Write-Fail "text-session" "Text session failed: $_"
    }
}

# ── [debrief] ─────────────────────────────────────────────────────────────────

function Invoke-SmokeDebrief {
    Write-Label "[debrief] Debrief report generation"

    if ($Mode -eq "ci") {
        $testFile = Join-Path $RepoRoot "services\convsim-core\tests\test_debrief_engine.py"
        if (-not (Test-Path $testFile)) {
            Write-Skip "debrief" "test_debrief_engine.py not found"
            return
        }
        $pytestPath = Get-PytestPath
        if (-not $pytestPath) {
            Write-Skip "debrief" "pytest not found"
            return
        }
        $prevLocation = Get-Location
        Set-Location (Join-Path $RepoRoot "services\convsim-core")
        try {
            $out = & $pytestPath tests/test_debrief_engine.py -v 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Fail "debrief" "Debrief engine unit tests failed"
                Save-ArtifactText "debrief-error.txt" ($out -join "`n")
                return
            }
        } finally {
            Set-Location $prevLocation
        }
        Write-Pass "debrief" "Debrief engine unit tests passed"
        return
    }

    Write-Skip "debrief" "Full debrief smoke requires an active session — run manually per release-checklist.md"
}

# ── [offline] ─────────────────────────────────────────────────────────────────

function Invoke-SmokeOffline {
    Write-Label "[offline] Offline smoke (no outbound connections during play)"

    if ($Mode -eq "ci") {
        $testFile = Join-Path $RepoRoot "services\convsim-core\tests\test_network_policy.py"
        if (-not (Test-Path $testFile)) {
            Write-Skip "offline" "test_network_policy.py not found"
            return
        }
        $pytestPath = Get-PytestPath
        if (-not $pytestPath) {
            Write-Skip "offline" "pytest not found"
            return
        }
        $prevLocation = Get-Location
        Set-Location (Join-Path $RepoRoot "services\convsim-core")
        try {
            $out = & $pytestPath tests/test_network_policy.py -v 2>&1
            if ($LASTEXITCODE -ne 0) {
                Write-Fail "offline" "Network policy tests failed — backend may attempt outbound connections"
                Save-ArtifactText "offline-error.txt" ($out -join "`n")
                Copy-BackendLogs
                return
            }
        } finally {
            Set-Location $prevLocation
        }
        Write-Pass "offline" "Network policy tests passed — no outbound calls during fake-runtime play"
        return
    }

    $cliBin = Join-Path $RepoRoot "packages\convsim-cli\dist\index.js"
    if (Test-Path $cliBin) {
        Write-Info "offline" "Running CLI offline-smoke-test"
        $out = node $cliBin offline-smoke-test (Join-Path $RepoRoot "packs\official\job-interview-basic") 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "offline" "CLI offline-smoke-test exited $LASTEXITCODE"
            Save-ArtifactText "offline-error.txt" ($out -join "`n")
            Copy-BackendLogs
        } else {
            Write-Pass "offline" "CLI offline-smoke-test passed for job-interview-basic"
        }
    } else {
        Write-Skip "offline" "CLI not built — run: pnpm --filter @convsim/cli build then re-run with -Full"
    }
}

# ── [packaged-startup] ────────────────────────────────────────────────────────

function Invoke-SmokePackagedStartup {
    Write-Label "[packaged-startup] Packaged startup verification"

    $testFile = Join-Path $RepoRoot "services\convsim-core\tests\test_packaged_startup.py"
    if (-not (Test-Path $testFile)) {
        Write-Fail "packaged-startup" "test_packaged_startup.py not found"
        return
    }
    $pytestPath = Get-PytestPath
    if (-not $pytestPath) {
        Write-Skip "packaged-startup" "pytest not found — run setup.ps1 first"
        return
    }

    $prevLocation = Get-Location
    Set-Location (Join-Path $RepoRoot "services\convsim-core")
    try {
        $out = & $pytestPath tests/test_packaged_startup.py -v 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "packaged-startup" "Packaged startup unit tests failed"
            Save-ArtifactText "packaged-startup-error.txt" ($out -join "`n")
            return
        }
    } finally {
        Set-Location $prevLocation
    }
    Write-Pass "packaged-startup" "Packaged startup unit tests passed"

    # Check required build infrastructure files.
    $missing = 0
    $requiredBuildFiles = @(
        "services\convsim-core\convsim-core.spec",
        "scripts\build-core.sh",
        "scripts\build-core.ps1",
        "scripts\depot-audit.sh",
        "scripts\depot-audit.ps1",
        "apps\desktop\src-tauri\resources\bin\.gitkeep"
    )
    foreach ($f in $requiredBuildFiles) {
        if (-not (Test-Path -PathType Leaf (Join-Path $RepoRoot $f))) {
            Write-Fail "packaged-startup" "Missing required build file: $f"
            $missing++
        }
    }
    if ($missing -eq 0) {
        Write-Pass "packaged-startup" "All required packaging infrastructure files present"
    }

    if ($Mode -eq "full") {
        $builtBin  = Join-Path $RepoRoot "apps\desktop\src-tauri\resources\bin\convsim-core"
        $builtExe  = Join-Path $RepoRoot "apps\desktop\src-tauri\resources\bin\convsim-core.exe"
        if ((Test-Path $builtBin) -or (Test-Path $builtExe)) {
            Write-Info "packaged-startup" "convsim-core binary present — full launch test skipped (run manually)"
            Write-Pass "packaged-startup" "Packaged binary found in resources\bin"
        } else {
            Write-Skip "packaged-startup" "No packaged binary — run: .\scripts\build-core.ps1 first"
        }
    }
}

# ── [web] ─────────────────────────────────────────────────────────────────────

function Invoke-SmokeWeb {
    Write-Label "[web] Web frontend typecheck"

    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        Write-Skip "web" "node not found"
        return
    }
    if (-not (Test-Path (Join-Path $RepoRoot "node_modules"))) {
        Write-Skip "web" "node_modules not installed — run pnpm install first"
        return
    }
    if (-not (Test-Path (Join-Path $RepoRoot "apps\web\package.json"))) {
        Write-Fail "web" "apps\web\package.json not found"
        return
    }
    if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) {
        Write-Skip "web" "pnpm not found"
        return
    }

    $prevLocation = Get-Location
    Set-Location $RepoRoot
    try {
        $out = pnpm --filter "@convsim/web" typecheck 2>&1
        if ($LASTEXITCODE -ne 0) {
            Write-Fail "web" "Web frontend typecheck failed"
            Save-ArtifactText "web-error.txt" ($out -join "`n")
            return
        }
    } finally {
        Set-Location $prevLocation
    }
    Write-Pass "web" "Web frontend typecheck passed"

    if ($Mode -eq "full") {
        Write-Info "web" "Full mode: confirm http://127.0.0.1:7354 loads in browser (manual step)"
    }
}

# ── Summary ───────────────────────────────────────────────────────────────────

function Write-Summary {
    $arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
    Write-Host ""
    Write-Host "────────────────────────────────────────────────────────────────"
    Write-Host "Platform : Windows / $arch   Mode : $Mode"
    Write-Host "Passed   : $($script:Passed)   Failed : $($script:Errors)   Skipped : $($script:Skipped)"
    Write-Host "────────────────────────────────────────────────────────────────"

    if ($script:Errors -gt 0) {
        Write-Host "FAIL  $($script:Errors) subsystem(s) failed — see FAIL lines above." -ForegroundColor Red
        if ($script:ArtifactsWritten) {
            Write-Host "  Error details saved to: $ArtifactDir" -ForegroundColor Red
        }
        exit 1
    }

    if ($Mode -eq "ci") {
        Write-Host "PASS  CI smoke subset passed."
        Write-Host ""
        Write-Host "      Run with -Full against a live stack for the complete release gate."
        Write-Host "      See docs\release-checklist.md for manual steps."
    } else {
        Write-Host "PASS  Full release smoke passed."
    }
    Write-Host ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "Conversation Simulator — release smoke"
Write-Host "========================================"
Write-Host "Mode: $Mode   Platform: Windows/$([System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture)"
Write-Host ""

Initialize-Artifacts

Invoke-SmokSetup
Invoke-SmokePackValidation
Invoke-SmokeVoiceFallback
Invoke-SmokeBackendHealth
Invoke-SmokeModelManager
Invoke-SmokeScenarioLibrary
Invoke-SmokeTextSession
Invoke-SmokeDebrief
Invoke-SmokeOffline
Invoke-SmokePackagedStartup
Invoke-SmokeWeb

Write-Summary
