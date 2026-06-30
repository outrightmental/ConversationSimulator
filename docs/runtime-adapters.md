<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Runtime adapters

> **Status:** Placeholder. Will be completed in Milestone 1 (text-only simulator).

This document will cover:

- The `ChatRuntime` abstraction interface
- llama.cpp adapter (primary runtime via llama-server)
- Ollama adapter (alternative runtime)
- How to add a new runtime adapter
- Runtime selection and fallback logic
- Structured output / JSON schema enforcement per runtime

For the runtime directory, see [runtimes/](../runtimes/).
For the architecture overview, see [architecture.md](architecture.md).
