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
# License and privacy disclosure
# ---------------------------------------------------------------------------

cat <<'DISCLOSURE'
──────────────────────────────────────────────────────────────────────────────
  LICENSE NOTICE
  whisper.cpp is released under the MIT License.
  The OpenAI Whisper model weights are released under the MIT License.
  Source: https://github.com/ggml-org/whisper.cpp/blob/master/LICENSE
          https://github.com/openai/whisper/blob/main/LICENSE

  PRIVACY NOTICE
  Model files are downloaded from HuggingFace (huggingface.co). No audio,
  transcript, or personal data is transmitted. All speech recognition runs
  entirely on your device after this one-time download.
──────────────────────────────────────────────────────────────────────────────
DISCLOSURE

# ---------------------------------------------------------------------------
# Approximate model sizes (for user awareness before download)
# ---------------------------------------------------------------------------

declare -A MODEL_SIZES=(
  ["tiny"]="~77 MB"
  ["tiny.en"]="~77 MB"
  ["base"]="~148 MB"
  ["base.en"]="~147 MB"
  ["small"]="~488 MB"
  ["small.en"]="~488 MB"
  ["medium"]="~1.5 GB"
  ["medium.en"]="~1.5 GB"
  ["large-v3"]="~3.1 GB"
)

APPROX_SIZE="${MODEL_SIZES[$MODEL_NAME]:-unknown size}"
echo "Model   : ggml-${MODEL_NAME}"
echo "Size    : ${APPROX_SIZE} (approximate)"
echo "Dest    : ${MODEL_FILE}"
echo ""

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
  echo "Downloading model ggml-${MODEL_NAME} (${APPROX_SIZE}) …"
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
# Checksum — display SHA256 of the downloaded file
# ---------------------------------------------------------------------------

echo ""
echo "Computing SHA256 checksum …"
if command -v sha256sum &>/dev/null; then
  FILE_SHA256="$(sha256sum "${MODEL_FILE}" | awk '{print $1}')"
elif command -v shasum &>/dev/null; then
  FILE_SHA256="$(shasum -a 256 "${MODEL_FILE}" | awk '{print $1}')"
else
  echo "WARNING: sha256sum / shasum not available — cannot verify checksum." >&2
  FILE_SHA256="(unavailable)"
fi

echo "SHA256  : ${FILE_SHA256}"
echo ""
echo "To verify independently, compare the above against the value listed on:"
echo "  https://huggingface.co/ggml-org/whisper.cpp/blob/main/ggml-${MODEL_NAME}.bin"
echo ""

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
echo "  SHA256 : ${FILE_SHA256}"
echo ""
echo "Start convsim-core and the STT status badge should show 'Ready'."
