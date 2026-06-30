<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Quickstart

> **Status:** Placeholder. Will be completed in Milestone 1 (text-only simulator).

## Current state

The repository contains the monorepo skeleton. Services are not yet implemented.
You can check your environment setup with:

```bash
./scripts/setup.sh
```

This prints the next dependency to install or confirms that your environment
meets the requirements.

## Once Milestone 1 is complete

```bash
git clone https://github.com/outrightmental/ConversationSimulator
cd ConversationSimulator
./scripts/setup.sh
./scripts/dev.sh
```

Then open `http://127.0.0.1:7354` in your browser.

The first run will prompt you to install a local LLM. The recommended starter
is Qwen3 8B Instruct Q4_K_M (approximately 5 GB, Apache-2.0 licensed).
