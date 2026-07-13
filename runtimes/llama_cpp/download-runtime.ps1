# SPDX-License-Identifier: Apache-2.0
# download-runtime.ps1 — Download a pre-built llama-server binary for Windows.
#
# Usage:
#   .\runtimes\llama_cpp\download-runtime.ps1 [[-Version] <tag>] [[-Dest] <dir>] [-Variant <cpu|vulkan>]
#
# Options:
#   -Version <tag>      llama.cpp release tag to download (default: latest)
#   -Dest    <dir>      directory to place the binary (default: $HOME\.convsim\bin)
#   -Variant <name>     build variant: cpu (default), vulkan
#
# After the download, add the destination to PATH or pass its full path to
# POST /api/sidecar/start as the "executable" field.
#
# Supported platforms:
#   Windows x86_64 — win-x64  (cpu / vulkan variants)
#   Windows arm64  — win-arm64 (cpu variant)
#
# Variant selection:
#   cpu    — universally safe, works on every Windows machine (default)
#   vulkan — GPU acceleration via Vulkan; works on NVIDIA, AMD, Intel
#
# CUDA builds are intentionally not offered: llama.cpp publishes them per CUDA
# toolkit version (win-cuda-12.4-x64, win-cuda-13.3-x64, …) plus a separate
# cudart runtime archive, so there is no single "cuda" asset to fetch. Vulkan
# accelerates on NVIDIA too (the driver ships the Vulkan runtime).
#
# For Linux / macOS use runtimes/llama_cpp/download-runtime.sh instead.

[CmdletBinding()]
param(
    [string]$Version = "",
    [string]$Dest    = (Join-Path (Join-Path $HOME ".convsim") "bin"),
    [ValidateSet("cpu", "vulkan")]
    [string]$Variant = "cpu"
)

$ErrorActionPreference = "Stop"

$REPO  = "ggml-org/llama.cpp"

# ── Platform detection ────────────────────────────────────────────────────────

$arch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture
switch ($arch) {
    "X64"   { $PLATFORM = "win-x64" }
    "Arm64" { $PLATFORM = "win-arm64" }
    default {
        Write-Error "Unsupported Windows architecture: $arch"
        Write-Error "Build from source: https://github.com/ggml-org/llama.cpp#build"
        exit 1
    }
}

# ── Resolve latest tag if not specified ───────────────────────────────────────

if (-not $Version) {
    Write-Host "Fetching latest llama.cpp release tag..."
    try {
        $apiUrl = "https://api.github.com/repos/$REPO/releases/latest"
        $resp   = Invoke-RestMethod -Uri $apiUrl -UseBasicParsing -ErrorAction Stop
        $Version = $resp.tag_name
        if (-not $Version) { throw "tag_name is empty" }
    } catch {
        Write-Error "Failed to fetch latest release from GitHub: $_"
        Write-Error "Check your internet connection. Engine download requires a network connection (~5 MB)."
        exit 1
    }
    Write-Host "Latest release: $Version"
}

# ── Build asset name ──────────────────────────────────────────────────────────
# Windows naming convention: llama-{tag}-bin-win-{variant}-{arch}.zip
# e.g. llama-b5140-bin-win-cpu-x64.zip

$archSuffix = $PLATFORM -replace "^win-", ""   # "x64" or "arm64"
$ASSET_NAME = "llama-$Version-bin-win-$Variant-$archSuffix.zip"
$DOWNLOAD_URL = "https://github.com/$REPO/releases/download/$Version/$ASSET_NAME"
$SHA256_URL   = "https://github.com/$REPO/releases/download/$Version/sha256sum.txt"

Write-Host ""
Write-Host "Platform : $PLATFORM"
Write-Host "Version  : $Version"
Write-Host "Variant  : $Variant"
Write-Host "Asset    : $ASSET_NAME"
Write-Host "Dest     : $Dest"
Write-Host ""

# ── Download ──────────────────────────────────────────────────────────────────

$null = New-Item -ItemType Directory -Path $Dest -Force

$tmpDir  = Join-Path ([System.IO.Path]::GetTempPath()) ([System.IO.Path]::GetRandomFileName())
$null    = New-Item -ItemType Directory -Path $tmpDir -Force

$zipPath = Join-Path $tmpDir $ASSET_NAME

Write-Host "Downloading $DOWNLOAD_URL ..."
try {
    Invoke-WebRequest -Uri $DOWNLOAD_URL -OutFile $zipPath -UseBasicParsing -ErrorAction Stop
} catch {
    Write-Host ""
    Write-Error "Download failed: $_"
    Write-Error "Check that release $Version has asset $ASSET_NAME."
    Write-Error "Browse releases: https://github.com/$REPO/releases"
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
    exit 1
}

# ── SHA-256 verification ──────────────────────────────────────────────────────

Write-Host "Verifying SHA-256 checksum..."
try {
    $sha256resp = Invoke-WebRequest -Uri $SHA256_URL -UseBasicParsing -ErrorAction Stop
    $sha256text = $sha256resp.Content

    $expectedHash = $null
    foreach ($line in ($sha256text -split "`n")) {
        $parts = $line.Trim() -split "\s+", 2
        if ($parts.Count -eq 2) {
            $digest = $parts[0].ToLower()
            $name   = $parts[1].TrimStart("*")
            if ($name -eq $ASSET_NAME) {
                $expectedHash = $digest
                break
            }
        }
    }

    if ($expectedHash) {
        $actualHash = (Get-FileHash -Path $zipPath -Algorithm SHA256).Hash.ToLower()
        if ($actualHash -ne $expectedHash) {
            Write-Error "SHA-256 checksum mismatch for $ASSET_NAME."
            Write-Error "Expected : $expectedHash"
            Write-Error "Got      : $actualHash"
            Write-Error "The downloaded file may be corrupted. Try again."
            Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
            exit 1
        }
        Write-Host "  OK: checksum verified"
    } else {
        Write-Host "  WARN: $ASSET_NAME not listed in sha256sum.txt — skipping verification"
    }
} catch {
    Write-Host "  WARN: Could not fetch sha256sum.txt ($($_)) — skipping verification"
}

# ── Extract ───────────────────────────────────────────────────────────────────

Write-Host "Extracting..."
$extractDir = Join-Path $tmpDir "extracted"
Expand-Archive -Path $zipPath -DestinationPath $extractDir -Force

$extractedBin = Get-ChildItem -Recurse -Path $extractDir -Filter "llama-server.exe" |
    Select-Object -First 1

if (-not $extractedBin) {
    Write-Error "llama-server.exe not found in archive."
    Get-ChildItem -Recurse -Path $extractDir | Select-Object FullName
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
    exit 1
}

# ── Install (atomic replace) ──────────────────────────────────────────────────
# llama-server.exe is dynamically linked against sibling DLLs (ggml*.dll,
# llama.dll, …) shipped in the same archive directory; copy them alongside the
# exe or it cannot start ("ggml.dll was not found"). Install the DLLs first so
# the executable never resolves before its dependencies are in place.

$destBin  = Join-Path $Dest "llama-server.exe"
$partPath = Join-Path $Dest "llama-server.exe.part"
$srcDir   = $extractedBin.Directory.FullName

try {
    Get-ChildItem -Path $srcDir -File |
        Where-Object { $_.Name -ne "llama-server.exe" } |
        ForEach-Object {
            Copy-Item -Path $_.FullName -Destination (Join-Path $Dest $_.Name) -Force
        }
    Copy-Item -Path $extractedBin.FullName -Destination $partPath -Force
    # Move-Item with -Force is the closest atomic replace available on Windows.
    # If llama-server.exe is currently running this will fail with a sharing
    # violation; the .part file is cleaned up and an actionable error is shown.
    Move-Item -Path $partPath -Destination $destBin -Force
} catch {
    Remove-Item -Path $partPath -Force -ErrorAction SilentlyContinue
    Write-Error "Cannot replace $destBin : the file may be in use."
    Write-Error "Stop the running inference engine before upgrading."
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
    exit 1
} finally {
    Remove-Item -Recurse -Force $tmpDir -ErrorAction SilentlyContinue
}

# ── Done ──────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "Installed: $destBin"
Write-Host ""
Write-Host "Add to PATH (add this to your PowerShell profile or System environment):"
Write-Host "  `$env:PATH = `"$Dest;`$env:PATH`""
Write-Host ""
Write-Host "Or pass the full path to the sidecar API:"
Write-Host "  POST /api/sidecar/start  { `"executable`": `"$destBin`", ... }"
