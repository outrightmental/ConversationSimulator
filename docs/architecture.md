<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Architecture

> **Status:** Placeholder. Will be expanded in Milestone 1 (text-only simulator).

For the full technical specification, see [SPEC.md](SPEC.md) — sections 5 and 16
cover the high-level architecture and recommended repository layout.

## Overview

```
Browser UI (React/TypeScript/Vite)
        │ localhost WebSocket/HTTP
        ▼
convsim-core (Python FastAPI)
        │
        ├── LLM runtime (llama.cpp / Ollama)  :7356
        ├── STT runtime (whisper.cpp)          :7357
        ├── TTS runtime (Kokoro / sherpa-onnx) :7358
        └── SQLite database
```

## Service ports

| Service       | Port | Responsibility                          |
| ------------- | ---- | --------------------------------------- |
| convsim-ui    | 7354 | Browser UI (dev mode)                   |
| convsim-core  | 7355 | Main server, scenario engine, WebSocket |
| convsim-llm   | 7356 | Local LLM server (llama-server)         |
| convsim-stt   | 7357 | Speech-to-text worker                   |
| convsim-tts   | 7358 | Text-to-speech worker                   |

All services bind to `127.0.0.1` only. LAN access is an opt-in advanced setting.

## Key design principles

- The scenario engine speaks to a `ChatRuntime` abstraction, not directly to
  any one LLM provider. New runtimes (Ollama, llama.cpp, future providers)
  implement the same interface.
- Scenario packs are declarative data (YAML/JSON), never executable code.
- All inference, transcription, and synthesis runs locally on the user's machine.
- SQLite stores all session state, transcripts, and installed pack metadata.
