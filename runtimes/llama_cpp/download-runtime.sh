#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# download-runtime.sh — Download a pre-built llama-server binary for this platform.
#
# Usage:
#   ./runtimes/llama_cpp/download-runtime.sh [--version TAG] [--dest DIR]
#
# Options:
#   --version TAG   llama.cpp release tag to download (default: latest)
#   --dest DIR      directory to place the binary (default: ~/.convsim/bin)
#
# After the download, add the destination to PATH or pass its full path to
# POST /api/sidecar/start as the "executable" field.
#
# Supported platforms:
#   Linux  x86_64  — linux-x64
#   Linux  aarch64 — linux-arm64
#   macOS  arm64   — macos-arm64   (Apple Silicon)
#   macOS  x86_64  — macos-x64     (Intel Mac)
#
# Windows users: install via WSL2 (use the Linux binary) or build from source:
#   https://github.com/ggml-org/llama.cpp#build

set -euo pipefail

# ── Early --help / -h (platform-agnostic) ────────────────────────────────────

for _arg in "$@"; do
  if [[ "$_arg" == "--help" || "$_arg" == "-h" ]]; then
    sed -n '2,/^set /p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
  fi
done

# Pinned llama.cpp release. Keep this in sync with download-runtime.ps1.
#
# Pinned, not "latest", for two reasons:
#   1. Reproducibility — "latest" meant two releases built a day apart shipped
#      DIFFERENT inference engines, with nothing in the tag recording which.
#   2. Resolving "latest" hits api.github.com unauthenticated, which GitHub
#      rate-limits per IP. macOS runners share heavily-used IPs, so the release
#      build failed with `curl: (56) ... 403` while Linux got through.
#
# To upgrade: bump this, re-run the script on each platform, and confirm
# llama-server starts (`llama-server --version`) — that is what catches a
# renamed asset or a changed archive layout.
#
# macOS deployment target (issue #469): upstream's prebuilt macOS binaries are
# only usable on the macOS versions they declare via LC_BUILD_VERSION. From
# b9428 onward the artifacts target macOS 26.0, so on any older macOS dyld
# kills llama-server the instant it launches ("Symbol not found:
# _OBJC_CLASS_$_MTLResidencySetDescriptor … built for macOS 26.0 which is
# newer than running OS") — which the setup wizard used to misreport as
# insufficient RAM. b9415 is the newest release targeting macOS 14.0. When
# bumping the pin, the Darwin gate below (scripts/check-macho-minos.py) fails
# the download if the new artifacts raise the declared minimum; verify the
# candidate tag on every platform before raising the floor here.
#
# NOTE: no upstream prebuilt satisfies the documented macOS 13 (Ventura) floor
# in docs/QA_STEAM_PLATFORM_MATRIX.md — every recent release targets 14.0+.
# Supporting 13 requires building llama.cpp from source with
# MACOSX_DEPLOYMENT_TARGET=13 (tracked separately from #469).
LLAMA_CPP_PINNED_VERSION="b9415"

# Highest macOS minimum the bundled binaries may declare (see above). Override
# with CONVSIM_MACOS_MINOS_FLOOR, or set CONVSIM_SKIP_MINOS_CHECK=1 to bypass
# the gate entirely (e.g. when deliberately building a newer-macOS-only depot).
MACOS_MINOS_FLOOR="${CONVSIM_MACOS_MINOS_FLOOR:-14.0}"

# Pass --version latest (or LLAMA_CPP_VERSION=latest) to resolve the newest
# release instead of the pin.
RELEASE_TAG="${LLAMA_CPP_VERSION:-$LLAMA_CPP_PINNED_VERSION}"
DEST_DIR="${LLAMA_CPP_DEST:-$HOME/.convsim/bin}"
BINARY_NAME="llama-server"
REPO="ggml-org/llama.cpp"

# ── Platform detection ────────────────────────────────────────────────────────

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux)
    # Upstream names the Linux builds "ubuntu-*", not "linux-*". Asking for
    # linux-x64 yields a 404 on every release.
    case "$ARCH" in
      x86_64)  PLATFORM="ubuntu-x64" ;;
      aarch64) PLATFORM="ubuntu-arm64" ;;
      *)
        echo "Unsupported Linux architecture: $ARCH" >&2
        echo "Build from source: https://github.com/ggml-org/llama.cpp#build" >&2
        exit 1
        ;;
    esac
    ;;
  Darwin)
    case "$ARCH" in
      arm64)  PLATFORM="macos-arm64" ;;
      x86_64) PLATFORM="macos-x64" ;;
      *)
        echo "Unsupported macOS architecture: $ARCH" >&2
        exit 1
        ;;
    esac
    ;;
  *)
    echo "Unsupported OS: $OS" >&2
    echo "Windows users: use WSL2 (Linux binary) or build from source." >&2
    exit 1
    ;;
esac

# ── Argument parsing ──────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      RELEASE_TAG="$2"
      shift 2
      ;;
    --dest)
      DEST_DIR="$2"
      shift 2
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

# ── Resolve "latest" only when explicitly requested ───────────────────────────
# Send the token when one is available: this endpoint is rate-limited per IP for
# unauthenticated callers, and shared CI IPs hit that limit (403) routinely.

if [[ -z "$RELEASE_TAG" || "$RELEASE_TAG" == "latest" ]]; then
  echo "Fetching latest llama.cpp release tag..."
  _API_URL="https://api.github.com/repos/${REPO}/releases/latest"
  _TOKEN="${GITHUB_TOKEN:-${GH_TOKEN:-}}"
  if command -v curl &>/dev/null; then
    if [[ -n "$_TOKEN" ]]; then
      _RESP="$(curl -fsSL -H "Authorization: Bearer ${_TOKEN}" "$_API_URL")"
    else
      _RESP="$(curl -fsSL "$_API_URL")"
    fi
  elif command -v wget &>/dev/null; then
    _RESP="$(wget -qO- "$_API_URL")"
  else
    echo "curl or wget is required to fetch the latest release." >&2
    exit 1
  fi
  RELEASE_TAG="$(printf '%s' "$_RESP" | grep '"tag_name"' | head -1 |
                 sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')"
  if [[ -z "$RELEASE_TAG" ]]; then
    echo "Could not resolve the latest llama.cpp release (rate-limited?)." >&2
    echo "Pass --version <tag> to pin one explicitly." >&2
    exit 1
  fi
  echo "Latest release: ${RELEASE_TAG}"
fi

# ── Build download URL ────────────────────────────────────────────────────────
# llama.cpp names its Linux and macOS assets:
#   llama-{tag}-bin-{ubuntu|macos}-{arch}.tar.gz
# e.g. llama-b9996-bin-ubuntu-x64.tar.gz, llama-b9996-bin-macos-arm64.tar.gz
#
# NOT llama-{tag}-bin-{platform}-cpu.zip, which this script used to request: there
# is no "-cpu" variant and no .zip outside Windows, so every Linux/macOS download
# 404'd. (Windows keeps the -{variant}-.zip form — see download-runtime.ps1.)
# There is no separate CPU build to prefer here; the plain archive is the CPU one.

ASSET_NAME="llama-${RELEASE_TAG}-bin-${PLATFORM}.tar.gz"
DOWNLOAD_URL="https://github.com/${REPO}/releases/download/${RELEASE_TAG}/${ASSET_NAME}"

echo ""
echo "Platform : ${PLATFORM}"
echo "Version  : ${RELEASE_TAG}"
echo "Asset    : ${ASSET_NAME}"
echo "Dest     : ${DEST_DIR}"
echo ""

# ── Download and extract ──────────────────────────────────────────────────────

mkdir -p "$DEST_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

ZIP_PATH="${TMP_DIR}/${ASSET_NAME}"

echo "Downloading ${DOWNLOAD_URL} ..."
_DOWNLOAD_FAILED_MSG() {
  echo "" >&2
  echo "Download failed. Check that ${RELEASE_TAG} has a ${ASSET_NAME} asset." >&2
  echo "Browse releases: https://github.com/${REPO}/releases" >&2
}
if command -v curl &>/dev/null; then
  curl -fL --progress-bar -o "$ZIP_PATH" "$DOWNLOAD_URL" || { _DOWNLOAD_FAILED_MSG; exit 1; }
elif command -v wget &>/dev/null; then
  wget -q --show-progress -O "$ZIP_PATH" "$DOWNLOAD_URL" || { _DOWNLOAD_FAILED_MSG; exit 1; }
else
  echo "curl or wget is required to download the binary." >&2
  exit 1
fi

echo "Extracting..."
mkdir -p "$TMP_DIR/extracted"
tar -xzf "$ZIP_PATH" -C "$TMP_DIR/extracted"

# The binary sits under an archive-root directory (llama-{tag}/llama-server).
EXTRACTED_BIN="$(find "$TMP_DIR/extracted" -name "llama-server" -type f | head -1)"
if [[ -z "$EXTRACTED_BIN" ]]; then
  echo "llama-server binary not found in archive. Contents:" >&2
  find "$TMP_DIR/extracted" -type f >&2
  exit 1
fi
SRC_DIR="$(dirname "$EXTRACTED_BIN")"

# llama-server is dynamically linked against sibling shared libraries shipped in
# the same archive directory (@rpath/libllama.0.dylib, libggml-cpu.so, …). Copying
# only the executable — which this script used to do — produces a binary that
# cannot start: "image not found" on macOS, "cannot open shared object file" on
# Linux. download-runtime.ps1 has always copied the sibling DLLs on Windows; this
# is the same requirement.
#
# Install the libraries FIRST so the executable never resolves before its
# dependencies are in place, then move the binary into position atomically.
#
# `-type l` and `cp -a` are both load-bearing. llama.cpp ships the usual versioned
# chain — libllama-common.dylib -> libllama-common.0.dylib ->
# libllama-common.0.0.9996.dylib — and llama-server links against the SYMLINK name
# (@rpath/libllama-common.0.dylib). Copying only regular files drops all 18
# symlinks and the binary still refuses to start; `cp -a` preserves them as links
# rather than duplicating ~24 MB of libraries into the depot.
# ── macOS deployment-target gate (issue #469) ─────────────────────────────────
# Refuse to install binaries that declare a macOS minimum above the supported
# floor: they would pass every download/extract step and then crash on launch
# for every player below that version. Runs BEFORE anything is copied into
# DEST_DIR so a failing gate can never clobber a working installation. The
# checker is stdlib-only Python and lives in the repo; when it (or python3) is
# unavailable — e.g. the script was copied out of the repo — warn instead of
# failing the install.
if [[ "$OS" == "Darwin" && "${CONVSIM_SKIP_MINOS_CHECK:-0}" != "1" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  MINOS_CHECKER="${SCRIPT_DIR}/../../scripts/check-macho-minos.py"
  if [[ -f "$MINOS_CHECKER" ]] && command -v python3 &>/dev/null; then
    echo "Checking macOS deployment target (floor: ${MACOS_MINOS_FLOOR})..."
    if ! python3 "$MINOS_CHECKER" --max "$MACOS_MINOS_FLOOR" "$SRC_DIR" > "$TMP_DIR/minos.log" 2>&1; then
      grep '^FAIL' "$TMP_DIR/minos.log" >&2 || cat "$TMP_DIR/minos.log" >&2
      echo "" >&2
      echo "Release ${RELEASE_TAG} targets a macOS newer than ${MACOS_MINOS_FLOOR}," >&2
      echo "so llama-server would be killed by dyld on supported systems (issue #469)." >&2
      echo "Pick an older tag (--version), or set CONVSIM_SKIP_MINOS_CHECK=1 to force." >&2
      exit 1
    fi
  else
    echo "WARN: skipping macOS deployment-target check (checker or python3 unavailable)." >&2
  fi
fi

echo "Installing shared libraries..."
find "$SRC_DIR" -maxdepth 1 \( -type f -o -type l \) \
  \( -name '*.so' -o -name '*.so.*' -o -name '*.dylib' \) \
  -exec cp -a {} "$DEST_DIR/" \;

# llama.cpp is MIT-licensed; ship its licence with the binaries we redistribute.
if [[ -f "$SRC_DIR/LICENSE" ]]; then
  cp -f "$SRC_DIR/LICENSE" "${DEST_DIR}/LICENSE-llama.cpp.txt"
fi

cp -f "$EXTRACTED_BIN" "${DEST_DIR}/${BINARY_NAME}.part"
chmod +x "${DEST_DIR}/${BINARY_NAME}.part"
mv -f "${DEST_DIR}/${BINARY_NAME}.part" "${DEST_DIR}/${BINARY_NAME}"

echo ""
echo "Installed: ${DEST_DIR}/${BINARY_NAME}"
echo ""
echo "Add to PATH (add this to ~/.bashrc or ~/.zshrc):"
echo "  export PATH=\"${DEST_DIR}:\$PATH\""
echo ""
echo "Or pass the full path to the sidecar API:"
echo "  POST /api/sidecar/start  { \"executable\": \"${DEST_DIR}/${BINARY_NAME}\", ... }"
