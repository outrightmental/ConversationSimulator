#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# download-runtime.sh — download a starter model and verify the whisper-cli binary.
#
# Usage:
#   bash runtimes/whisper_cpp/download-runtime.sh [model]
#
# Examples:
#   bash runtimes/whisper_cpp/download-runtime.sh          # downloads ggml-base.en
#   bash runtimes/whisper_cpp/download-runtime.sh tiny.en  # downloads ggml-tiny.en
#
# Supported models: tiny, tiny.en, base, base.en, small, small.en, medium, medium.en, large-v3
#
# The script does NOT build whisper.cpp from source. For GPU support or platform-specific
# optimisations, build from source — see runtimes/whisper_cpp/README.md.

set -euo pipefail

MODEL_NAME="${1:-base.en}"
MODEL_DIR="${HOME}/.convsim/models/stt"
MODEL_FILE="${MODEL_DIR}/ggml-${MODEL_NAME}.bin"
MODEL_URL="https://huggingface.co/ggml-org/whisper.cpp/resolve/main/ggml-${MODEL_NAME}.bin"

BINARY_NAME="whisper-cli"

# ---------------------------------------------------------------------------
# Detect platform
# ---------------------------------------------------------------------------

OS="$(uname -s)"
ARCH="$(uname -m)"

case "${OS}" in
  Darwin)
    PLATFORM="macos"
    ;;
  Linux)
    PLATFORM="linux"
    ;;
  MINGW*|MSYS*|CYGWIN*)
    PLATFORM="windows"
    ;;
  *)
    echo "ERROR: Unsupported OS: ${OS}" >&2
    echo "       Build whisper.cpp from source — see README.md." >&2
    exit 1
    ;;
esac

# ---------------------------------------------------------------------------
# Download model
# ---------------------------------------------------------------------------

mkdir -p "${MODEL_DIR}"

if [[ -f "${MODEL_FILE}" ]]; then
  echo "Model already present: ${MODEL_FILE}"
else
  echo "Downloading model ggml-${MODEL_NAME} …"
  if command -v curl &>/dev/null; then
    curl -L --progress-bar -o "${MODEL_FILE}" "${MODEL_URL}"
  elif command -v wget &>/dev/null; then
    wget -q --show-progress -O "${MODEL_FILE}" "${MODEL_URL}"
  else
    echo "ERROR: neither curl nor wget found. Install one and retry." >&2
    exit 1
  fi
  echo "Model saved to ${MODEL_FILE}"
fi

# ---------------------------------------------------------------------------
# Install binary (Linux/macOS only — Windows users should build from source)
# ---------------------------------------------------------------------------

if [[ "${PLATFORM}" == "windows" ]]; then
  cat <<'EOF'
NOTE: Automatic binary download is not supported on Windows.
Build whisper.cpp from source:
  git clone https://github.com/ggml-org/whisper.cpp
  cd whisper.cpp
  cmake -B build && cmake --build build --config Release
Then add the build/bin directory to your PATH, or set:
  CONVSIM_WHISPER_CPP_BINARY_PATH=C:\path\to\whisper-cli.exe
EOF
  exit 0
fi

if command -v "${BINARY_NAME}" &>/dev/null; then
  EXISTING="$(command -v "${BINARY_NAME}")"
  echo "whisper-cli already on PATH: ${EXISTING}"
else
  echo ""
  echo "whisper-cli not found on PATH."
  echo ""
  echo "To install, build from source:"
  echo ""
  echo "  git clone https://github.com/ggml-org/whisper.cpp"
  echo "  cd whisper.cpp"

  if [[ "${PLATFORM}" == "macos" && "${ARCH}" == "arm64" ]]; then
    echo "  cmake -B build -DWHISPER_METAL=ON && cmake --build build --config Release"
  else
    echo "  cmake -B build && cmake --build build --config Release"
  fi

  echo "  sudo cp build/bin/whisper-cli /usr/local/bin/"
  echo ""
  echo "Or set CONVSIM_WHISPER_CPP_BINARY_PATH to point to the binary."
  echo ""
  echo "Model is ready at: ${MODEL_FILE}"
  echo "Set CONVSIM_WHISPER_CPP_MODEL_PATH=${MODEL_FILE} if it differs from the default."
  exit 0
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

echo ""
echo "whisper.cpp runtime ready:"
echo "  Binary : $(command -v ${BINARY_NAME})"
echo "  Model  : ${MODEL_FILE}"
echo ""
echo "Start convsim-core and the STT status badge should show 'Ready'."
