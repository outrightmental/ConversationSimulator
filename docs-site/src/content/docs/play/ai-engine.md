---
title: "Choosing how to run the AI"
description: "Compare the three ways to run local AI in Conversation Simulator — built-in engine, Ollama, and custom GGUF — and choose the right setup for your machine."
sidebar:
  order: 1
verified_against: v0.2.2
---
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Conversation Simulator runs AI inference entirely on your computer. All three options work offline after the one-time setup; no prompts or responses are ever sent to an external server. See [Privacy](/trust/privacy/) for the full data-handling policy.

---

## At a glance

| Option | Best for | What you supply |
|---|---|---|
| **Built-in engine** (default) | Everyone — no extra software required | Nothing; the app handles the download |
| **Ollama** | You already run Ollama; want GPU control; share models across apps | Ollama installed separately with at least one model pulled |
| **Custom GGUF file** | Air-gapped machines, private fine-tunes | A GGUF model file you obtained independently |

---

## Built-in engine (default)

The built-in engine is the right choice for almost everyone. The app bundles
the [llama.cpp](https://github.com/ggml-org/llama.cpp) inference runtime,
downloads a model during first-time setup, and manages everything automatically.
No external software to install.

**Who it's for:** anyone who wants to start playing without configuring anything.

### How to set it up

1. Open Conversation Simulator. On first launch the welcome screen appears.
2. The **Set me up** card names the recommended model for your hardware and
   shows its download size and license. Click **Set me up** to begin — the
   download starts right away.
3. A progress screen shows each installation stage. While it downloads, the
   **Have your first conversation** card offers a **Start now** button — click
   it to try the simulator immediately with a scripted (non-AI) tutorial.
4. When all stages complete, click **Continue to Home** to start playing.

That is the complete process — no additional steps are required.

### Changing the model later

You can switch to a different model after first-time setup. From the home screen
open **Settings**, find the **Runtime** section, and choose a different provider
and model from the dropdowns.

### Hardware recommendations

| Tier | Model | Size | Download at 50 Mbps | Min VRAM | CPU fallback |
|---|---|---|---|---|---|
| Starter | Qwen3 4B Instruct Q4_K_M | 2.5 GB | ~7 min | 4 GB | Yes (slow) |
| Standard | Qwen3 8B Instruct Q4_K_M | 5.0 GB | ~14 min | 6 GB | Yes (very slow) |
| High-quality | Qwen3 14B Instruct Q4_K_M | 9.0 GB | ~25 min | 10 GB | Not practical |
| High-quality | Mistral Small 3.1 24B Q4_K_M | 14.3 GB | ~39 min | 16 GB | Not practical |

**Apple Silicon:** Metal acceleration works out of the box through llama.cpp.
Use the VRAM column as a guide for unified memory (M1/M2/M3/M4 chips share
CPU and GPU memory).

**No discrete GPU:** any model can run on CPU, but inference is significantly
slower — expect 15–60 seconds per turn instead of 1–5 seconds. The Qwen3 4B
starter model is the most practical choice for CPU-only machines.

**Partial VRAM fit:** if you have less VRAM than the minimum, the model can
still load with fewer GPU-offloaded layers. Inference will be slower but may
be acceptable. See [Troubleshooting](/start/troubleshooting/#low-vram-or-slow-inference).

---

## Ollama

**What Ollama is:** [Ollama](https://ollama.com/) is a free, open-source tool
that downloads and runs local language models on your computer. It exposes a
standard API (`http://127.0.0.1:11434`) that Conversation Simulator can use
instead of its own built-in inference engine. You install Ollama once, pull
models with a single command, and any compatible application on your machine
can share those model files without a second download.

**Choose Ollama if any of these apply to you:**

1. **You already have Ollama installed** with models you want to reuse — no
   second download of the same weights.
2. **You want direct GPU configuration control** — number of offloaded layers,
   VRAM limits, batch size, or custom server flags that the built-in engine
   does not expose.
3. **You run several AI applications** and prefer managing all model storage
   in one place with `ollama pull` / `ollama rm`.

If none of these apply, the built-in engine is simpler.

### Prerequisites

1. Install Ollama from [ollama.com](https://ollama.com/).
2. Pull a compatible model:
   ```bash
   ollama pull qwen3:8b
   ```
   Any model that supports system prompts and structured JSON output works.
   The `qwen3` and `mistral` families are tested.
3. Confirm Ollama is running:
   ```bash
   ollama list
   ```

### How to select Ollama in the app

1. Open Conversation Simulator. On the welcome screen, expand **Advanced: use
   Ollama or a local GGUF file** (the disclosure below the two main cards).
2. Click **Browse Ollama models**.
3. The app lists all models detected in your local Ollama installation.
   Click **Use this model** next to the one you want.

If the list is empty, Ollama is either not running or has no models. Start
Ollama (`ollama serve`), pull a model (`ollama pull qwen3:8b`), then open
Conversation Simulator again.

### Changing the Ollama server address

The app connects to `http://127.0.0.1:11434` by default. Override this with
the `CONVSIM_OLLAMA_BASE_URL` environment variable if Ollama is listening on
a different address or port.

### How to verify it worked

On the home screen the AI status indicator should turn green and show your
selected Ollama model. If it shows an error, confirm `ollama serve` is running
and the selected model name is still valid (`ollama list` shows what is
available).

---

## Custom GGUF file

**Choose a custom GGUF file if:**

- You are on an air-gapped machine with no internet access during setup.
- You have a private fine-tune or a model not in the Conversation Simulator
  registry.

If you obtained a GGUF file from a public model hub, review the model's
license before use. The app cannot verify the license of a user-supplied file.

### What GGUF is

GGUF (GPT-Generated Unified Format) is the standard file format for quantized
language models compatible with llama.cpp. A GGUF file is self-contained:
model weights and metadata are stored in a single file.

### Prerequisites

A GGUF-format model file compatible with llama.cpp. Check the model's page
for minimum VRAM requirements — the hardware tier table in the built-in engine
section above is a useful reference for Q4_K_M-quantized models of similar size.

### How to select a GGUF file in the app

1. Open Conversation Simulator. On the welcome screen, expand **Advanced: use
   Ollama or a local GGUF file**.
2. Click **Use a GGUF file**.
3. Enter the full path to the file, for example:
   - **macOS / Linux:** `/home/you/Downloads/my-model.gguf`
   - **Windows:** `C:\Users\you\Downloads\my-model.gguf`
4. Click **Use this file**. The app loads the model without checksum
   verification — only registry-managed models have known checksums.

### How to verify it worked

On the home screen the runtime status indicator should show the model loaded
in green. If you see an error, confirm the path is correct and the file is
a valid GGUF file compatible with the current llama.cpp version.

---

## Verifying a GGUF file's integrity manually

```bash
# macOS / Linux
shasum -a 256 ~/.convsim/models/llm/my-model.gguf
```

```powershell
# Windows PowerShell
Get-FileHash "$env:USERPROFILE\.convsim\models\llm\my-model.gguf" -Algorithm SHA256
```

Compare the output against the checksum provided by the model author.

---

## Runtime environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CONVSIM_RUNTIME_ID` | `fake` | Select runtime: `llama_cpp`, `ollama`, or `fake` |
| `CONVSIM_LLAMA_CPP_BASE_URL` | `http://127.0.0.1:7356` | llama-server URL (built-in engine) |
| `CONVSIM_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama server URL |

The `fake` runtime returns scripted responses and requires no model file. It is
used for offline smoke tests and CI.

---

## Next steps

- [Quickstart](/start/quickstart/) — run your first conversation
- [Troubleshooting](/start/troubleshooting/) — model load failures, slow inference, VRAM errors
- [runtime-adapters.md](/reference/runtime-adapters/) — technical detail on the LLM runtime abstraction
- [model-registry/registry.yaml](https://github.com/outrightmental/ConversationSimulator/blob/main/model-registry/registry.yaml) — full list of registry entries with checksums
