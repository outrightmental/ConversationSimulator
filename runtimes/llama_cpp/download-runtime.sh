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

RELEASE_TAG="${LLAMA_CPP_VERSION:-}"  # empty = auto-detect latest
DEST_DIR="${LLAMA_CPP_DEST:-$HOME/.convsim/bin}"
BINARY_NAME="llama-server"
REPO="ggml-org/llama.cpp"

# ── Platform detection ────────────────────────────────────────────────────────

OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
  Linux)
    case "$ARCH" in
      x86_64)  PLATFORM="linux-x64" ;;
      aarch64) PLATFORM="linux-arm64" ;;
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

# ── Resolve latest tag if not specified ───────────────────────────────────────

if [[ -z "$RELEASE_TAG" ]]; then
  echo "Fetching latest llama.cpp release tag..."
  if command -v curl &>/dev/null; then
    RELEASE_TAG="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
      | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')"
  elif command -v wget &>/dev/null; then
    RELEASE_TAG="$(wget -qO- "https://api.github.com/repos/${REPO}/releases/latest" \
      | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')"
  else
    echo "curl or wget is required to fetch the latest release." >&2
    exit 1
  fi
  echo "Latest release: ${RELEASE_TAG}"
fi

# ── Build download URL ────────────────────────────────────────────────────────
# llama.cpp release assets follow this naming convention:
#   llama-{tag}-bin-{platform}-{cuda/metal/cpu}.zip
# We prefer the plain CPU build for portability.

ASSET_NAME="llama-${RELEASE_TAG}-bin-${PLATFORM}-cpu.zip"
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
if command -v curl &>/dev/null; then
  curl -fL --progress-bar -o "$ZIP_PATH" "$DOWNLOAD_URL" || {
    echo "" >&2
    echo "Download failed. Check that ${RELEASE_TAG} has a ${ASSET_NAME} asset." >&2
    echo "Browse releases: https://github.com/${REPO}/releases" >&2
    exit 1
  }
elif command -v wget &>/dev/null; then
  wget -q --show-progress -O "$ZIP_PATH" "$DOWNLOAD_URL" || {
    echo "Download failed." >&2
    exit 1
  }
fi

echo "Extracting..."
unzip -q "$ZIP_PATH" -d "$TMP_DIR/extracted"

# The binary may be at the root or in a subdirectory
EXTRACTED_BIN="$(find "$TMP_DIR/extracted" \( -name "llama-server" -o -name "llama-server.exe" \) -type f | head -1)"
if [[ -z "$EXTRACTED_BIN" ]]; then
  echo "llama-server binary not found in archive. Contents:" >&2
  find "$TMP_DIR/extracted" -type f >&2
  exit 1
fi

cp "$EXTRACTED_BIN" "${DEST_DIR}/${BINARY_NAME}"
chmod +x "${DEST_DIR}/${BINARY_NAME}"

echo ""
echo "Installed: ${DEST_DIR}/${BINARY_NAME}"
echo ""
echo "Add to PATH (add this to ~/.bashrc or ~/.zshrc):"
echo "  export PATH=\"${DEST_DIR}:\$PATH\""
echo ""
echo "Or pass the full path to the sidecar API:"
echo "  POST /api/sidecar/start  { \"executable\": \"${DEST_DIR}/${BINARY_NAME}\", ... }"
