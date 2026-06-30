<!-- SPDX-License-Identifier: Apache-2.0 -->
# services/convsim-core

Python FastAPI server — the main backend for Conversation Simulator.

**Status:** Not yet implemented. Planned in Milestone 1 (text-only simulator).

Responsibilities:
- Scenario engine (load, validate, run scenarios)
- HTTP API and WebSocket events for the UI
- LLM runtime abstraction (llama.cpp / Ollama)
- Safety gate (input/output validation)
- Debrief generation
- SQLite storage (sessions, transcripts, installed packs)

Runs at `http://127.0.0.1:7355` in dev mode.

## Requirements

- Python 3.10+

## Setup (once implemented)

```bash
cd services/convsim-core
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
uvicorn convsim.main:app --host 127.0.0.1 --port 7355 --reload
```
