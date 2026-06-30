# SPDX-License-Identifier: Apache-2.0
# Start the Conversation Simulator local dev services (Windows PowerShell).
# Currently launches convsim-core; remaining services are TODO for later milestones.

$RepoRoot = (Resolve-Path "$PSScriptRoot\..").Path
$CoreDir = Join-Path $RepoRoot "services\convsim-core"

Write-Host ""
Write-Host "Conversation Simulator — local dev"
Write-Host "===================================="
Write-Host ""
Write-Host "Local service ports:"
Write-Host ""
Write-Host "  convsim-ui    http://127.0.0.1:7354  (browser UI — TODO Milestone 1)"
Write-Host "  convsim-core  http://127.0.0.1:7355  (main server, WebSocket, API)"
Write-Host "  convsim-llm   http://127.0.0.1:7356  (local LLM server — TODO)"
Write-Host "  convsim-stt   http://127.0.0.1:7357  (speech-to-text worker — TODO)"
Write-Host "  convsim-tts   http://127.0.0.1:7358  (text-to-speech worker — TODO)"
Write-Host ""
Write-Host "All services bind to 127.0.0.1 only."
Write-Host ""

Set-Location $CoreDir

$VenvUvicorn = Join-Path $CoreDir ".venv\Scripts\uvicorn.exe"
if (Test-Path $VenvUvicorn) {
    $Uvicorn = $VenvUvicorn
} elseif (Get-Command uvicorn -ErrorAction SilentlyContinue) {
    $Uvicorn = "uvicorn"
} else {
    Write-Host "ERROR: uvicorn not found."
    Write-Host "Set up the virtual environment first:"
    Write-Host "  cd services\convsim-core"
    Write-Host "  python -m venv .venv"
    Write-Host "  .venv\Scripts\pip install -e '.[dev]'"
    exit 1
}

Write-Host "Starting convsim-core ..."
Write-Host ""
& $Uvicorn convsim_core.main:app --host 127.0.0.1 --port 7355 --reload
