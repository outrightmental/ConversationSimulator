<!-- SPDX-License-Identifier: Apache-2.0 -->
# runtimes/llama_cpp

Integration layer for llama.cpp — the primary local LLM runtime.

**Status:** Not yet implemented. Planned in Milestone 1 (text-only simulator).

This directory will contain:
- Scripts to download platform-specific llama.cpp binaries
- Configuration helpers for llama-server startup
- The `ChatRuntime` adapter that speaks to llama-server's OpenAI-compatible API

The llama-server process runs at `http://127.0.0.1:7356` in dev mode.

## References

- llama.cpp: https://github.com/ggml-org/llama.cpp
- llama-server exposes an OpenAI-compatible chat completions endpoint
- GGUF model format is the target; models are downloaded by the user
