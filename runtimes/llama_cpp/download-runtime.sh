#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# download-runtime.sh — Download the pinned llama-server build for this platform.
#
# Usage:
#   ./runtimes/llama_cpp/download-runtime.sh [--variant cpu|vulkan] [--dest DIR]
#                                            [--version TAG --sha256 HEX]
#
# Options:
#   --variant NAME  build variant: cpu (default) or vulkan (Linux only)
#   --dest DIR      directory to install into (default: ~/.convsim/bin for cpu,
#                   ~/.convsim/bin/vulkan for vulkan)
#   --version TAG   llama.cpp release tag (default: the pin)
#   --sha256 HEX    expected SHA-256 of the archive; required for any tag other
#                   than the pinned one, which has its own digests
#
# Environment: LLAMA_CPP_VARIANT, LLAMA_CPP_DEST and LLAMA_CPP_VERSION set the
# same things as the flags (the flags win).
#
# The pin — one tag and one SHA-256 per archive — lives in
# runtimes/llama_cpp/pin.json, the single file this script, download-runtime.ps1,
# CI and the packaged core all read (issue #530). Upstream publishes no checksum
# file, so the pin is the only thing that verifies a download: an archive with
# no pinned digest, or one that does not match, is never installed. There is no
# unverified fallback.
#
# Supported platforms and variants (llama.cpp b9415 assets):
#   Linux  x86_64  — ubuntu-x64    cpu, vulkan (ubuntu-vulkan-x64)
#   Linux  aarch64 — ubuntu-arm64  cpu, vulkan (ubuntu-vulkan-arm64)
#   macOS  arm64   — macos-arm64   cpu only; this build runs on Metal
#   macOS  x86_64  — macos-x64     cpu only
#
# The Vulkan archive is the CPU archive plus the Vulkan backend library
# (libggml-vulkan.so). The two go in separate directories so that the CPU build
# never sits beside it: ggml loads every backend library it finds next to the
# executable, and a machine with a broken Vulkan driver must start the CPU
# build exactly as before. The app picks between them at each start (#531).
#
# Windows users: use runtimes/llama_cpp/download-runtime.ps1.
#
# Test hooks (not for players): LLAMA_CPP_PIN_FILE reads another pin file;
# LLAMA_CPP_DOWNLOAD_BASE replaces https://github.com/ggml-org/llama.cpp/releases/download;
# CONVSIM_LLAMA_CPP_PLATFORM (ubuntu-x64, ubuntu-arm64, macos-arm64, macos-x64)
# replaces platform detection.

set -euo pipefail

# ── Early --help / -h (platform-agnostic) ────────────────────────────────────

for _arg in "$@"; do
  if [[ "$_arg" == "--help" || "$_arg" == "-h" ]]; then
    sed -n '2,/^set /p' "$0" | grep '^#' | sed 's/^# \?//'
    exit 0
  fi
done

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="ggml-org/llama.cpp"
BINARY_NAME="llama-server"
DOWNLOAD_BASE="${LLAMA_CPP_DOWNLOAD_BASE:-https://github.com/${REPO}/releases/download}"
DOWNLOAD_BASE="${DOWNLOAD_BASE%/}"

# macOS deployment target (issue #469): upstream's prebuilt macOS binaries are
# only usable on the macOS versions they declare via LC_BUILD_VERSION. From
# b9428 onward the artifacts target macOS 26.0, so on any older macOS dyld
# kills llama-server the instant it launches ("Symbol not found:
# _OBJC_CLASS_$_MTLResidencySetDescriptor … built for macOS 26.0 which is
# newer than running OS") — which the setup wizard used to misreport as
# insufficient RAM. b9415 is the newest release targeting macOS 14.0. When
# moving the pin, the Darwin gate below (scripts/check-macho-minos.py) fails
# the download if the new artifacts raise the declared minimum; verify the
# candidate tag on every platform before raising the floor here.
#
# NOTE: no upstream prebuilt targets macOS 13 or older — every recent release
# targets 14.0+ — so the documented support floor in
# docs/QA_STEAM_PLATFORM_MATRIX.md is macOS 14 Sonoma (issue #472).
#
# Highest macOS minimum the bundled binaries may declare. Override with
# CONVSIM_MACOS_MINOS_FLOOR, or set CONVSIM_SKIP_MINOS_CHECK=1 to bypass the
# gate entirely (e.g. when deliberately building a newer-macOS-only depot).
MACOS_MINOS_FLOOR="${CONVSIM_MACOS_MINOS_FLOOR:-14.0}"

# ── The pin ───────────────────────────────────────────────────────────────────
# pin.json keeps one key per line (tests/test_llama_cpp_download.py checks it),
# so sed can read it without jq or python.

PIN_FILE="${LLAMA_CPP_PIN_FILE:-${SCRIPT_DIR}/pin.json}"
[[ -f "$PIN_FILE" ]] || fail "Cannot find the llama.cpp pin at ${PIN_FILE}. Run this script from the repository (runtimes/llama_cpp/pin.json)."
PINNED_TAG="$(sed -n 's/^[[:space:]]*"tag":[[:space:]]*"\([^"]*\)".*/\1/p' "$PIN_FILE" | head -1)"
[[ -n "$PINNED_TAG" ]] || fail "The llama.cpp pin at ${PIN_FILE} has no tag."

pinned_digest() {
  # The digest on the line that names the asset, or nothing. (grep finding no
  # line is an answer here, not an error for pipefail.)
  { grep -F "\"$1\":" "$PIN_FILE" || true; } | head -1 |
    sed -n 's/.*":[[:space:]]*"\([0-9a-f]\{64\}\)".*/\1/p'
}

# ── Argument parsing ──────────────────────────────────────────────────────────

VARIANT="${LLAMA_CPP_VARIANT:-cpu}"
DEST_DIR="${LLAMA_CPP_DEST:-}"
RELEASE_TAG="${LLAMA_CPP_VERSION:-}"
EXPECTED_SHA256=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --variant) VARIANT="$2"; shift 2 ;;
    --dest)    DEST_DIR="$2"; shift 2 ;;
    --version) RELEASE_TAG="$2"; shift 2 ;;
    --sha256)  EXPECTED_SHA256="$2"; shift 2 ;;
    *) fail "Unknown option: $1 (see --help)" ;;
  esac
done

case "$VARIANT" in
  cpu|vulkan) ;;
  *) fail "Unknown variant: ${VARIANT} (expected cpu or vulkan)" ;;
esac
[[ -n "$RELEASE_TAG" ]] || RELEASE_TAG="$PINNED_TAG"
if [[ -z "$DEST_DIR" ]]; then
  DEST_DIR="$HOME/.convsim/bin"
  if [[ "$VARIANT" == "vulkan" ]]; then
    DEST_DIR="${DEST_DIR}/vulkan"
  fi
fi

# ── Platform detection ────────────────────────────────────────────────────────
# Upstream names the Linux builds "ubuntu-*", not "linux-*": asking for
# linux-x64 yields a 404 on every release.

PLATFORM="${CONVSIM_LLAMA_CPP_PLATFORM:-}"
if [[ -z "$PLATFORM" ]]; then
  OS="$(uname -s)"
  ARCH="$(uname -m)"
  case "$OS" in
    Linux)
      case "$ARCH" in
        x86_64)  PLATFORM="ubuntu-x64" ;;
        aarch64) PLATFORM="ubuntu-arm64" ;;
        *) fail "Unsupported Linux architecture: $ARCH. Build from source: https://github.com/ggml-org/llama.cpp#build" ;;
      esac
      ;;
    Darwin)
      case "$ARCH" in
        arm64)  PLATFORM="macos-arm64" ;;
        x86_64) PLATFORM="macos-x64" ;;
        *) fail "Unsupported macOS architecture: $ARCH" ;;
      esac
      ;;
    *)
      fail "Unsupported OS: $OS. Windows users: runtimes/llama_cpp/download-runtime.ps1."
      ;;
  esac
fi
PLATFORM_OS="${PLATFORM%%-*}"
PLATFORM_ARCH="${PLATFORM#*-}"

# ── Asset name and expected digest ───────────────────────────────────────────
# llama.cpp names its Linux and macOS assets:
#   llama-{tag}-bin-ubuntu-{arch}.tar.gz          (CPU)
#   llama-{tag}-bin-ubuntu-vulkan-{arch}.tar.gz   (Vulkan)
#   llama-{tag}-bin-macos-{arch}.tar.gz           (Metal)
# (Windows uses llama-{tag}-bin-win-{cpu|vulkan}-{arch}.zip — see the .ps1.)

case "${PLATFORM_OS}:${VARIANT}" in
  ubuntu:cpu)    SEGMENT="ubuntu-${PLATFORM_ARCH}" ;;
  ubuntu:vulkan) SEGMENT="ubuntu-vulkan-${PLATFORM_ARCH}" ;;
  macos:cpu)     SEGMENT="macos-${PLATFORM_ARCH}" ;;
  macos:vulkan)  fail "llama.cpp publishes no Vulkan build for macOS; the default build runs on Metal. Use --variant cpu." ;;
  *) fail "Unknown platform: ${PLATFORM}" ;;
esac
ASSET_NAME="llama-${RELEASE_TAG}-bin-${SEGMENT}.tar.gz"
DOWNLOAD_URL="${DOWNLOAD_BASE}/${RELEASE_TAG}/${ASSET_NAME}"

EXPECTED_SHA256="$(printf '%s' "$EXPECTED_SHA256" | tr 'A-F' 'a-f')"
if [[ -z "$EXPECTED_SHA256" ]]; then
  if [[ "$RELEASE_TAG" != "$PINNED_TAG" ]]; then
    fail "llama.cpp ${RELEASE_TAG} is not the pinned release (${PINNED_TAG}), so there is no pinned SHA-256 for ${ASSET_NAME}. Pass --sha256 (gh api repos/${REPO}/releases/tags/${RELEASE_TAG} shows each asset's digest)."
  fi
  EXPECTED_SHA256="$(pinned_digest "$ASSET_NAME")"
  [[ -n "$EXPECTED_SHA256" ]] || fail "No pinned SHA-256 for ${ASSET_NAME} in ${PIN_FILE}. Every engine download is verified; add the asset's digest to the pin."
fi
[[ "$EXPECTED_SHA256" =~ ^[0-9a-f]{64}$ ]] || fail "The expected SHA-256 for ${ASSET_NAME} is not 64 hex digits: ${EXPECTED_SHA256}"

echo ""
echo "Platform : ${PLATFORM}"
echo "Version  : ${RELEASE_TAG}"
echo "Variant  : ${VARIANT}"
echo "Asset    : ${ASSET_NAME}"
echo "SHA-256  : ${EXPECTED_SHA256}"
echo "Dest     : ${DEST_DIR}"
echo ""

# ── Download ──────────────────────────────────────────────────────────────────

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
ARCHIVE="${TMP_DIR}/${ASSET_NAME}"

echo "Downloading ${DOWNLOAD_URL} ..."
_download_failed() {
  fail "Download failed. Check that ${RELEASE_TAG} has a ${ASSET_NAME} asset (https://github.com/${REPO}/releases)."
}
if command -v curl &>/dev/null; then
  curl -fL --retry 3 --progress-bar -o "$ARCHIVE" "$DOWNLOAD_URL" || _download_failed
elif command -v wget &>/dev/null; then
  wget -q --show-progress -O "$ARCHIVE" "$DOWNLOAD_URL" || _download_failed
else
  fail "curl or wget is required to download the binary."
fi

# ── SHA-256 verification (never skipped) ─────────────────────────────────────

echo "Verifying SHA-256 checksum..."
if command -v sha256sum &>/dev/null; then
  ACTUAL_SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
elif command -v shasum &>/dev/null; then
  ACTUAL_SHA256="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
else
  fail "sha256sum or shasum is required to verify the download."
fi
if [[ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]]; then
  fail "SHA-256 checksum mismatch for ${ASSET_NAME}. Expected ${EXPECTED_SHA256}, got ${ACTUAL_SHA256}. The download may be corrupted or tampered with; nothing was installed."
fi
echo "  OK: checksum verified"

# ── Extract ───────────────────────────────────────────────────────────────────

echo "Extracting..."
mkdir -p "$TMP_DIR/extracted"
tar -xzf "$ARCHIVE" -C "$TMP_DIR/extracted"

# The binary sits under an archive-root directory (llama-{tag}/llama-server).
EXTRACTED_BIN="$(find "$TMP_DIR/extracted" -name "$BINARY_NAME" -type f | head -1)"
if [[ -z "$EXTRACTED_BIN" ]]; then
  echo "llama-server binary not found in archive. Contents:" >&2
  find "$TMP_DIR/extracted" >&2
  exit 1
fi
SRC_DIR="$(dirname "$EXTRACTED_BIN")"

# ── macOS deployment-target gate (issue #469) ─────────────────────────────────
# Refuse to install binaries that declare a macOS minimum above the supported
# floor: they would pass every download/extract step and then crash on launch
# for every player below that version. Runs BEFORE anything is copied into
# DEST_DIR so a failing gate can never clobber a working installation. The
# checker is stdlib-only Python and lives in the repo; when it (or python3) is
# unavailable — e.g. the script was copied out of the repo — warn instead of
# failing the install.
if [[ "$PLATFORM_OS" == "macos" && "${CONVSIM_SKIP_MINOS_CHECK:-0}" != "1" ]]; then
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

# ── Install ───────────────────────────────────────────────────────────────────
# llama-server is dynamically linked against sibling shared libraries shipped in
# the same archive directory (@rpath/libllama.0.dylib, libggml-cpu.so, …), so
# they are installed with it; the other command-line tools are not needed.
#
# `-type l` and `cp -a` are both load-bearing. llama.cpp ships the usual versioned
# chain — libllama-common.so -> libllama-common.so.0 -> libllama-common.so.0.0.9415
# — and llama-server links against the SYMLINK name. Copying only regular files
# drops the links and the binary refuses to start; `cp -a` preserves them as
# links rather than duplicating the libraries into the depot.
#
# Libraries go in FIRST so the executable never resolves before its dependencies
# are in place; then the binary is moved into position atomically.

mkdir -p "$DEST_DIR"
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

# The CPU build must never sit beside the Vulkan backend library.
if [[ "$VARIANT" == "cpu" ]] && compgen -G "${DEST_DIR}/libggml-vulkan*" > /dev/null; then
  fail "${DEST_DIR} contains libggml-vulkan, so the CPU build there would load the Vulkan backend. Install the Vulkan build into its own directory (the default for --variant vulkan)."
fi

echo ""
echo "Installed: ${DEST_DIR}/${BINARY_NAME}"
echo ""
if [[ "$VARIANT" == "cpu" ]]; then
  echo "Add to PATH (add this to ~/.bashrc or ~/.zshrc):"
  echo "  export PATH=\"${DEST_DIR}:\$PATH\""
  echo ""
fi
echo "The app finds ~/.convsim/bin/llama-server and ~/.convsim/bin/vulkan/llama-server by itself."
