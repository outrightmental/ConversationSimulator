#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Download the Silero VAD ONNX model to ~/.convsim/models/vad/
set -euo pipefail

MODEL_DIR="${HOME}/.convsim/models/vad"
MODEL_FILE="${MODEL_DIR}/silero_vad.onnx"
MODEL_URL="https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"

mkdir -p "${MODEL_DIR}"

if [[ -f "${MODEL_FILE}" ]]; then
    echo "Silero VAD model already present at ${MODEL_FILE}"
    exit 0
fi

echo "Downloading Silero VAD ONNX model to ${MODEL_FILE} ..."

if command -v curl &>/dev/null; then
    curl -fsSL -o "${MODEL_FILE}" "${MODEL_URL}"
elif command -v wget &>/dev/null; then
    wget -q -O "${MODEL_FILE}" "${MODEL_URL}"
else
    echo "ERROR: neither curl nor wget found. Install one and retry." >&2
    exit 1
fi

echo "Done. Model saved to ${MODEL_FILE}"
echo ""
echo "Also install onnxruntime if not already present:"
echo "  pip install onnxruntime"
