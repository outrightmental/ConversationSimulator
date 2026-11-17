# SPDX-License-Identifier: Apache-2.0
# download-runtime.ps1 — Download the pinned llama-server build for Windows.
#
# Usage:
#   .\runtimes\llama_cpp\download-runtime.ps1 [-Variant <cpu|vulkan>] [-Dest <dir>] [-Version <tag> -Sha256 <hex>]
#
# Options:
#   -Variant <name>     build variant: cpu (default) or vulkan
#   -Dest    <dir>      directory to install into
#                       (default: $HOME\.convsim\bin for cpu,
#                                 $HOME\.convsim\bin\vulkan for vulkan)
#   -Version <tag>      llama.cpp release tag (default: the pin)
#   -Sha256  <hex>      expected SHA-256 of the archive; required for any tag
#                       other than the pinned one, which has its own digests
#
# The pin — one tag and one SHA-256 per archive — lives in
# runtimes/llama_cpp/pin.json, the single file this script, download-runtime.sh,
# CI and the packaged core all read (issue #530). Upstream publishes no
# checksum file, so the pin is the only thing that verifies a download: an
# archive with no pinned digest, or one that does not match, is never
# installed. There is no unverified fallback.
#
# Variants (llama.cpp b9415 assets):
#   cpu    — llama-<tag>-bin-win-cpu-<arch>.zip. Works on every Windows machine.
#   vulkan — llama-<tag>-bin-win-vulkan-x64.zip. The CPU archive plus the
#            Vulkan backend library (ggml-vulkan.dll); runs on NVIDIA, AMD and
#            Intel graphics through the driver's Vulkan runtime. x64 only.
#
# The two variants go in separate directories so that the CPU build never sits
# beside ggml-vulkan.dll: ggml loads every backend library it finds next to the
# executable, and a machine with a broken Vulkan driver must start the CPU
# build exactly as before. The app picks between them at each start (#531).
#
# CUDA builds are intentionally not offered: llama.cpp publishes them per CUDA
# toolkit version (win-cuda-12.4-x64, win-cuda-13.3-x64, …) plus a separate
# cudart runtime archive, and Vulkan accelerates NVIDIA cards too.
#
# Test hooks (not for players): LLAMA_CPP_PIN_FILE reads another pin file;
# LLAMA_CPP_DOWNLOAD_BASE replaces https://github.com/ggml-org/llama.cpp/releases/download.
#
# For Linux / macOS use runtimes/llama_cpp/download-runtime.sh instead.

[CmdletBinding()]
param(
    [ValidateSet("cpu", "vulkan")]
    [string]$Variant = "cpu",
    [string]$Dest    = "",
    [string]$Version = "",
    [string]$Sha256  = ""
)

$ErrorActionPreference = "Stop"
# Windows PowerShell 5.1 renders a progress bar per received chunk, which makes
# a 30 MB download take minutes.
$ProgressPreference = "SilentlyContinue"

function Fail([string]$Message) {
    [Console]::Error.WriteLine("ERROR: $Message")
    exit 1
}

$REPO = "ggml-org/llama.cpp"
$DownloadBase = if ($env:LLAMA_CPP_DOWNLOAD_BASE) { $env:LLAMA_CPP_DOWNLOAD_BASE.TrimEnd("/") } else { "https://github.com/$REPO/releases/download" }

# ── The pin ───────────────────────────────────────────────────────────────────

$PinFile = if ($env:LLAMA_CPP_PIN_FILE) { $env:LLAMA_CPP_PIN_FILE } else { Join-Path $PSScriptRoot "pin.json" }
if (-not (Test-Path $PinFile)) {
    Fail "Cannot find the llama.cpp pin at $PinFile. Run this script from the repository (runtimes/llama_cpp/pin.json)."
}
try {
    $Pin = Get-Content -Raw -Path $PinFile | ConvertFrom-Json
} catch {
    Fail "The llama.cpp pin at $PinFile is not valid JSON: $_"
}
if (-not $Pin.tag) { Fail "The llama.cpp pin at $PinFile has no tag." }

if (-not $Version) { $Version = $Pin.tag }

# ── Platform detection ────────────────────────────────────────────────────────

$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
switch ($arch) {
    "X64"   { $archSuffix = "x64" }
    "Arm64" { $archSuffix = "arm64" }
    default { Fail "Unsupported Windows architecture: $arch. Build from source: https://github.com/ggml-org/llama.cpp#build" }
}
if ($Variant -eq "vulkan" -and $archSuffix -ne "x64") {
    Fail "llama.cpp publishes no Vulkan build for Windows $archSuffix. Use -Variant cpu."
}

if (-not $Dest) {
    $Dest = Join-Path (Join-Path $HOME ".convsim") "bin"
    if ($Variant -eq "vulkan") { $Dest = Join-Path $Dest "vulkan" }
}

# ── Asset and expected digest ─────────────────────────────────────────────────
# Windows naming convention: llama-{tag}-bin-win-{cpu|vulkan}-{arch}.zip

$ASSET_NAME   = "llama-$Version-bin-win-$Variant-$archSuffix.zip"
$DOWNLOAD_URL = "$DownloadBase/$Version/$ASSET_NAME"

$Expected = $Sha256.Trim().ToLower()
if (-not $Expected) {
    if ($Version -ne $Pin.tag) {
        Fail "llama.cpp $Version is not the pinned release ($($Pin.tag)), so there is no pinned SHA-256 for $ASSET_NAME. Pass -Sha256 (gh api repos/$REPO/releases/tags/$Version shows each asset's digest)."
    }
    $prop = $Pin.sha256.PSObject.Properties[$ASSET_NAME]
    if (-not $prop -or -not $prop.Value) {
        Fail "No pinned SHA-256 for $ASSET_NAME in $PinFile. Every engine download is verified; add the asset's digest to the pin."
    }
    $Expected = ([string]$prop.Value).ToLower()
}
if ($Expected -notmatch '^[0-9a-f]{64}$') {
    Fail "The expected SHA-256 for $ASSET_NAME is not 64 hex digits: $Expected"
}

Write-Host ""
Write-Host "Platform : win-$archSuffix"
Write-Host "Version  : $Version"
Write-Host "Variant  : $Variant"
Write-Host "Asset    : $ASSET_NAME"
Write-Host "SHA-256  : $Expected"
Write-Host "Dest     : $Dest"
Write-Host ""

# ── Download ──────────────────────────────────────────────────────────────────

$tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
$null   = New-Item -ItemType Directory -Path $tmpDir -Force
$zipPath = Join-Path $tmpDir $ASSET_NAME

try {
    Write-Host "Downloading $DOWNLOAD_URL ..."
    try {
        Invoke-WebRequest -Uri $DOWNLOAD_URL -OutFile $zipPath -UseBasicParsing -ErrorAction Stop
    } catch {
        Fail "Download failed: $_. Check that release $Version has asset $ASSET_NAME (https://github.com/$REPO/releases)."
    }

    # ── SHA-256 verification (never skipped) ─────────────────────────────────
    Write-Host "Verifying SHA-256 checksum..."
    $actual = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToLower()
    if ($actual -ne $Expected) {
        Fail "SHA-256 checksum mismatch for $ASSET_NAME. Expected $Expected, got $actual. The download may be corrupted or tampered with; nothing was installed."
    }
    Write-Host "  OK: checksum verified"

    # ── Extract ───────────────────────────────────────────────────────────────
    Write-Host "Extracting..."
    $extractDir = Join-Path $tmpDir "extracted"
    Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

    $extractedBin = Get-ChildItem -Recurse -Path $extractDir -Filter "llama-server.exe" | Select-Object -First 1
    if (-not $extractedBin) {
        Get-ChildItem -Recurse -Path $extractDir | Select-Object FullName | Out-String | Write-Host
        Fail "llama-server.exe not found in $ASSET_NAME."
    }

    # ── Install (atomic replace) ──────────────────────────────────────────────
    # llama-server.exe is dynamically linked against sibling DLLs (ggml*.dll,
    # llama.dll, …) shipped in the same archive directory; copy them alongside
    # the exe or it cannot start ("ggml.dll was not found"). Install the DLLs
    # first so the executable never resolves before its dependencies are in
    # place.
    $null     = New-Item -ItemType Directory -Path $Dest -Force
    $destBin  = Join-Path $Dest "llama-server.exe"
    $partPath = Join-Path $Dest "llama-server.exe.part"
    $srcDir   = $extractedBin.Directory.FullName
    try {
        Get-ChildItem -Path $srcDir -File |
            Where-Object { $_.Name -ne "llama-server.exe" } |
            ForEach-Object { Copy-Item -Path $_.FullName -Destination (Join-Path $Dest $_.Name) -Force }
        Copy-Item -Path $extractedBin.FullName -Destination $partPath -Force
        # Move-Item -Force is the closest atomic replace available on Windows.
        # A running llama-server.exe fails it with a sharing violation.
        Move-Item -Path $partPath -Destination $destBin -Force
    } catch {
        Remove-Item -Path $partPath -Force -ErrorAction SilentlyContinue
        Fail "Cannot replace $destBin : the file may be in use. Stop the running inference engine before upgrading."
    }
} finally {
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
}

# The CPU build must never sit beside the Vulkan backend library.
if ($Variant -eq "cpu" -and (Test-Path (Join-Path $Dest "ggml-vulkan.dll"))) {
    Fail "$Dest contains ggml-vulkan.dll, so the CPU build there would load the Vulkan backend. Install the Vulkan build into its own directory (the default for -Variant vulkan)."
}

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "Installed: $destBin"
Write-Host ""
if ($Variant -eq "cpu") {
    Write-Host "Add to PATH (add this to your PowerShell profile or System environment):"
    Write-Host "  `$env:PATH = `"$Dest;`$env:PATH`""
    Write-Host ""
}
Write-Host "The app finds $HOME\.convsim\bin\llama-server.exe and $HOME\.convsim\bin\vulkan\llama-server.exe by itself."
