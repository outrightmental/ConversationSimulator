#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Start the Conversation Simulator local dev services.
# Currently launches convsim-core; remaining services are TODO for later milestones.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORE_DIR="$SCRIPT_DIR/../services/convsim-core"

echo ""
echo "Conversation Simulator — local dev"
echo "===================================="
echo ""
echo "Local service ports:"
echo ""
echo "  convsim-ui    http://127.0.0.1:7354  (browser UI — TODO Milestone 1)"
echo "  convsim-core  http://127.0.0.1:7355  (main server, WebSocket, API)"
echo "  convsim-llm   http://127.0.0.1:7356  (local LLM server — TODO)"
echo "  convsim-stt   http://127.0.0.1:7357  (speech-to-text worker — TODO)"
echo "  convsim-tts   http://127.0.0.1:7358  (text-to-speech worker — TODO)"
echo ""
echo "All services bind to 127.0.0.1 only."
echo ""

cd "$CORE_DIR"

if [ -f ".venv/bin/uvicorn" ]; then
    UVICORN=".venv/bin/uvicorn"
elif command -v uvicorn &>/dev/null; then
    UVICORN="uvicorn"
else
    echo "ERROR: uvicorn not found."
    echo "Set up the virtual environment first:"
    echo "  cd services/convsim-core"
    echo "  python -m venv .venv"
    echo "  .venv/bin/pip install -e '.[dev]'"
    exit 1
fi

echo "Starting convsim-core ..."
echo ""
exec "$UVICORN" convsim_core.main:app --host 127.0.0.1 --port 7355 --reload
