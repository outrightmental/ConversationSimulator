# SPDX-License-Identifier: Apache-2.0
# depot-audit.ps1 — Audit a directory for files that must not ship in a
# Steam depot or release artifact (Windows PowerShell).
#
# Usage:
#   .\scripts\depot-audit.ps1 <depot-dir> [-WarnOnly] [-Help]
#
# Arguments:
#   <depot-dir>   Path to the directory containing the release content to audit.
#
# Options:
#   -WarnOnly     Print violations but exit 0 (useful for pre-flight checks).
#   -Help         Print this help and exit.
#
# Audit categories (all cause exit 1 unless -WarnOnly):
#
#   [weights]   Large model weight files (.gguf, .safetensors, .bin, .pt, .pth,
#               .ckpt) — compliance rule MD-04.
#               See publishing\STEAM_DEPOT_CONTENTS.md for the approved binary
#               payload list and docs\model-download-policy.md for download rules.
#
#   [unapproved-binaries]  Serialised model payloads in less common formats:
#               *.pkl / *.pickle > 10 MB (serialised PyTorch / scikit-learn),
#               *.npz / *.npy > 10 MB (NumPy array formats), any models\
#               directory (must never appear in a depot), *.onnx > 50 MB
#               (large ONNX exports indicate a bundled LLM).
#
#   [devfiles]  Developer-only artefacts: .env, .venv\, __pycache__\, *.py[cod],
#               tests\, .git\, pytest config, coverage files, *.spec.
#
#   [secrets]   Common secret file patterns: *.key, *.pem, *.pfx, *.p12,
#               api_keys.*, credentials.*, config.vdf.
#
#   [fixtures]  Test fixture files: fixtures\, testdata\, *.fixture.*.

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$DepotDir,
    [switch]$WarnOnly,
    [switch]$Help
)

if ($Help) {
    Get-Content $MyInvocation.MyCommand.Path |
        Where-Object { $_ -match "^#" } |
        ForEach-Object { $_ -replace "^# ?", "" }
    exit 0
}

if (-not $DepotDir) {
    Write-Error "Usage: .\depot-audit.ps1 <depot-dir> [-WarnOnly]"
    exit 1
}

if (-not (Test-Path -PathType Container $DepotDir)) {
    Write-Error "Depot directory not found: $DepotDir"
    exit 1
}

$violations = 0

function Write-Violation {
    param([string]$Category, [string]$Path)
    Write-Host "  VIOLATION  [$Category]  $Path" -ForegroundColor Red
    $script:violations++
}

function Write-Section { param([string]$Title) Write-Host ""; Write-Host "── $Title ──" }

# ── [weights] Model weight files ───────────────────────────────────────────────

Write-Section "[weights] Model weight files (compliance rule MD-04)"

$weightExts = @('*.gguf', '*.safetensors', '*.pt', '*.pth', '*.ckpt')
foreach ($ext in $weightExts) {
    Get-ChildItem -Recurse -File -Path $DepotDir -Filter $ext -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Violation "weights" $_.FullName }
}

# .bin — flag only files > 1 MB that are not PE executables (MZ header).
Get-ChildItem -Recurse -File -Path $DepotDir -Filter '*.bin' -ErrorAction SilentlyContinue |
    Where-Object { $_.Length -gt 1MB } |
    ForEach-Object {
        # Read only the first two bytes; weight .bin files can be many GB, so
        # loading the whole file into memory (ReadAllBytes) would exhaust RAM on
        # exactly the files this audit exists to catch.
        $fs = [System.IO.File]::OpenRead($_.FullName)
        try {
            $b0 = $fs.ReadByte()
            $b1 = $fs.ReadByte()
        } finally {
            $fs.Dispose()
        }
        $isPE = ($b0 -eq 0x4D -and $b1 -eq 0x5A)
        if (-not $isPE) { Write-Violation "weights" $_.FullName }
    }

# ── [unapproved-binaries] Serialised model payloads ───────────────────────────

Write-Section "[unapproved-binaries] Serialised model payloads"

# Pickle files > 10 MB — may be serialised PyTorch or scikit-learn models.
foreach ($ext in @('*.pkl', '*.pickle')) {
    Get-ChildItem -Recurse -File -Path $DepotDir -Filter $ext -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -gt 10MB } |
        ForEach-Object { Write-Violation "unapproved-binaries" $_.FullName }
}

# NumPy array files > 10 MB — used by some lightweight model quantisation formats.
foreach ($ext in @('*.npz', '*.npy')) {
    Get-ChildItem -Recurse -File -Path $DepotDir -Filter $ext -ErrorAction SilentlyContinue |
        Where-Object { $_.Length -gt 10MB } |
        ForEach-Object { Write-Violation "unapproved-binaries" $_.FullName }
}

# Any models\ subdirectory — model files must never appear in a depot; they live
# in ~/.convsim/models/ on the player's machine after an explicit download.
Get-ChildItem -Recurse -Directory -Path $DepotDir -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -eq 'models' } |
    ForEach-Object { Write-Violation "unapproved-binaries" ($_.FullName + '\') }

# ONNX files > 50 MB — small ONNX files are legitimate sidecar dependencies
# (VAD model, TTS voice files); large ONNX files indicate a bundled LLM export.
Get-ChildItem -Recurse -File -Path $DepotDir -Filter '*.onnx' -ErrorAction SilentlyContinue |
    Where-Object { $_.Length -gt 50MB } |
    ForEach-Object { Write-Violation "unapproved-binaries" $_.FullName }

# ── [devfiles] Developer-only artefacts ───────────────────────────────────────

Write-Section "[devfiles] Developer-only artefacts"

$devFileFilters = @(
    '.env', '.env.*',
    '*.pyc', '*.pyo', '*.pyd',
    'pytest.ini', 'setup.cfg', 'tox.ini',
    '.coverage', 'coverage.xml',
    'convsim-core.spec'
)
foreach ($f in $devFileFilters) {
    Get-ChildItem -Recurse -File -Path $DepotDir -Filter $f -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Violation "devfiles" $_.FullName }
}

$devDirNames = @('__pycache__', '.venv', 'venv', '.git', '.pytest_cache',
                  '.mypy_cache', 'htmlcov', 'tests')
Get-ChildItem -Recurse -Directory -Path $DepotDir -ErrorAction SilentlyContinue |
    Where-Object { $devDirNames -contains $_.Name -or $_.Name -like '*.egg-info' } |
    ForEach-Object { Write-Violation "devfiles" ($_.FullName + '\') }

# ── [secrets] Secret / credential files ───────────────────────────────────────

Write-Section "[secrets] Secret / credential files"

$secretFilters = @(
    '*.key', '*.pem', '*.pfx', '*.p12',
    '*_rsa', '*_dsa', '*_ecdsa', '*_ed25519',
    'known_hosts', 'api_keys.*', 'credentials.*', 'config.vdf'
)
foreach ($f in $secretFilters) {
    Get-ChildItem -Recurse -File -Path $DepotDir -Filter $f -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Violation "secrets" $_.FullName }
}

# ── [fixtures] Test fixture files ──────────────────────────────────────────────

Write-Section "[fixtures] Test fixture files"

$fixtureDirNames = @('fixtures', 'testdata', 'test_data')
Get-ChildItem -Recurse -Directory -Path $DepotDir -ErrorAction SilentlyContinue |
    Where-Object { $fixtureDirNames -contains $_.Name } |
    ForEach-Object { Write-Violation "fixtures" ($_.FullName + '\') }

$fixtureFilters = @('*.fixture.*', '*_fixture.*', '*.testdata.*')
foreach ($f in $fixtureFilters) {
    Get-ChildItem -Recurse -File -Path $DepotDir -Filter $f -ErrorAction SilentlyContinue |
        ForEach-Object { Write-Violation "fixtures" $_.FullName }
}

# ── Summary ────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "────────────────────────────────────────────────────────────────"

if ($violations -eq 0) {
    Write-Host "PASS  Depot audit passed — no prohibited files detected."
    Write-Host "      Directory: $DepotDir"
    Write-Host ""
    exit 0
}

Write-Host "VIOLATIONS  $violations prohibited file(s) found in: $DepotDir" -ForegroundColor Red
Write-Host ""

if ($WarnOnly) {
    Write-Host "  -WarnOnly is set; exiting 0 despite violations."
    Write-Host ""
    exit 0
}

exit 1
