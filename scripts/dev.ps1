# SPDX-License-Identifier: Apache-2.0
# Start all Conversation Simulator local dev services (Windows PowerShell version).
# Services are not yet implemented; this script prints the intended ports
# and exits cleanly until Milestone 1 is complete.

Write-Host ""
Write-Host "Conversation Simulator — local dev"
Write-Host "===================================="
Write-Host ""
Write-Host "Intended local service ports:"
Write-Host ""
Write-Host "  convsim-ui    http://127.0.0.1:7354  (browser UI, dev mode)"
Write-Host "  convsim-core  http://127.0.0.1:7355  (main server, WebSocket, API)"
Write-Host "  convsim-llm   http://127.0.0.1:7356  (local LLM server)"
Write-Host "  convsim-stt   http://127.0.0.1:7357  (speech-to-text worker)"
Write-Host "  convsim-tts   http://127.0.0.1:7358  (text-to-speech worker)"
Write-Host ""
Write-Host "All services bind to 127.0.0.1 only (localhost)."
Write-Host ""
Write-Host "Status:"
Write-Host "  Services are not yet implemented."
Write-Host "  This script will launch all processes once Milestone 1 is complete."
Write-Host ""
Write-Host "Milestones:"
Write-Host "  Milestone 0: repo skeleton and local dev setup   [COMPLETE]"
Write-Host "  Milestone 1: text-only conversation simulator    [TODO]"
Write-Host "  Milestone 2: scenario pack system                [TODO]"
Write-Host "  Milestone 3: local voice input                   [TODO]"
Write-Host "  Milestone 4: local voice output                  [TODO]"
Write-Host "  Milestone 5: polished playable alpha             [TODO]"
Write-Host ""
Write-Host "Track progress: https://github.com/outrightmental/ConversationSimulator/milestones"
Write-Host ""
exit 0
