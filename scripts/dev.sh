#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Start all Conversation Simulator local dev services.
# Services are not yet implemented; this script prints the intended ports
# and exits cleanly until Milestone 1 is complete.
set -euo pipefail

echo ""
echo "Conversation Simulator — local dev"
echo "===================================="
echo ""
echo "Intended local service ports:"
echo ""
echo "  convsim-ui    http://127.0.0.1:7354  (browser UI, dev mode)"
echo "  convsim-core  http://127.0.0.1:7355  (main server, WebSocket, API)"
echo "  convsim-llm   http://127.0.0.1:7356  (local LLM server)"
echo "  convsim-stt   http://127.0.0.1:7357  (speech-to-text worker)"
echo "  convsim-tts   http://127.0.0.1:7358  (text-to-speech worker)"
echo ""
echo "All services bind to 127.0.0.1 only (localhost)."
echo ""
echo "Status:"
echo "  Services are not yet implemented."
echo "  This script will launch all processes once Milestone 1 is complete."
echo ""
echo "Starting:"
echo "  Web UI  →  pnpm --filter @convsim/web dev"
echo "  (opens http://127.0.0.1:7354 — starts without the backend)"
echo ""
echo "Milestones:"
echo "  Milestone 0: repo skeleton and local dev setup   [COMPLETE]"
echo "  Milestone 1: text-only conversation simulator    [IN PROGRESS]"
echo "  Milestone 2: scenario pack system                [TODO]"
echo "  Milestone 3: local voice input                   [TODO]"
echo "  Milestone 4: local voice output                  [TODO]"
echo "  Milestone 5: polished playable alpha             [TODO]"
echo ""
echo "Track progress: https://github.com/outrightmental/ConversationSimulator/milestones"
echo ""
exit 0
