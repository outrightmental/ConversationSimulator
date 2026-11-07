---
title: "Choosing how to run the AI"
description: "Compare the three ways to run local AI in Conversation Simulator — built-in engine, Ollama, and custom GGUF — and choose the right setup for your machine."
sidebar:
  order: 1
verified_against: v0.4.0
---
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Conversation Simulator runs AI inference on your computer. All three options work offline after the one-time setup, and no prompts or responses are sent to an external server, unless you point the app at an AI server on another computer yourself, with `CONVSIM_OLLAMA_BASE_URL` or `CONVSIM_LLAMA_CPP_BASE_URL` (see [Runtime environment variables](#runtime-environment-variables)). See [Privacy](/trust/privacy/) for the full data-handling policy.

---

## At a glance

| Option | Best for | What you supply |
|---|---|---|
| **Built-in engine** (default) | Everyone — no extra software required | Nothing; the app handles the download |
| **Ollama** | You already run Ollama; want GPU control; share models across apps | Ollama installed separately with at least one model pulled |
| **Custom GGUF file** | Air-gapped machines, private fine-tunes | A GGUF model file you obtained independently |

The Steam Next Fest demo offers only the built-in engine, with its one model.

---

## Built-in engine (default)

The built-in engine is the right choice for almost everyone. It is the
[llama.cpp](https://github.com/ggml-org/llama.cpp) inference runtime: the Steam
build ships it inside the app, and a build from source downloads it during
first-time setup. The app also downloads a model during that setup, then starts
and stops the engine itself. No external software to install.

**Who it's for:** anyone who wants to start playing without configuring anything.

### How to set it up

1. Open Conversation Simulator. On first launch the welcome screen appears.
2. The **Set me up** card shows the download size and license of the
   recommended model. That is the registry's starter model, Qwen3 4B Instruct
   Q4_K_M (2.5 GB, Apache-2.0), on every machine. Click **Set me up** to begin.
   The download starts right away, unless a quick system check finds something
   to fix first, such as too little free disk space; a **Getting things ready**
   screen then says what it is.
3. A progress screen, **Setting up your AI**, shows each installation stage.
   While the model downloads, it explains how to play and previews your first
   missions.
4. When every stage is done, the app opens the **Scenario Library**, where you
   pick your first conversation.

That is the complete process — no additional steps are required.

### Changing the model later

You can switch to a different model after first-time setup. Open **Settings**
and go to the **AI engine** section. Choose a **Provider** (**llama.cpp**,
**Ollama** or **Fake (Demo)**) and a **Model**, then click **Apply**. For
llama.cpp the model list shows the models the app downloaded; a GGUF file you
selected yourself is not listed there, so switch back to one with
**Open model manager →** and **Use a local GGUF file**. The demo edition has no
**AI engine** section.

A switch to **Ollama** or **Fake (Demo)** takes effect at once, although
Ollama may not answer with the model you picked (see
[How to select Ollama in the app](#how-to-select-ollama-in-the-app)). A switch to
another llama.cpp model or GGUF file does not, when the engine is already
running, which it is after **Set me up** and whenever the app starts with
llama.cpp selected. The app saves your choice: Settings reports **Provider and
model updated.** and the Home screen shows the new name. But the running engine
keeps the model it started with, and the new model is used only after you quit
and reopen the app. If the engine is not running, **Apply** starts it with the
model you chose.

### Hardware recommendations

The model registry lists four models. At this release the app's screens
install only the starter model: the larger ones are in the registry, but no
screen offers them. To use one, download its file yourself (the registry lists
the URL and SHA-256 checksum) and select it as a
[custom GGUF file](#custom-gguf-file). If the engine is already running, as it
is after **Set me up**, the new file is used after you quit and reopen the app;
see [Changing the model later](#changing-the-model-later).

| Tier | Model | Size | Download at 50 Mbps | Min VRAM | CPU fallback |
|---|---|---|---|---|---|
| Starter | Qwen3 4B Instruct Q4_K_M | 2.5 GB | ~7 min | 4 GB | Yes (slow) |
| Standard | Qwen3 8B Instruct Q4_K_M | 5.0 GB | ~13 min | 6 GB | Yes (very slow) |
| High-quality | Qwen3 14B Instruct Q4_K_M | 9.0 GB | ~24 min | 10 GB | Not practical |
| High-quality | Mistral Small 3.1 24B Instruct Q4_K_M | 14.3 GB | ~38 min | 16 GB | Not practical |

**Apple Silicon:** Metal acceleration works out of the box through llama.cpp.
Use the VRAM column as a guide for unified memory (M1/M2/M3/M4 chips share
CPU and GPU memory).

**No discrete GPU:** any model can run on CPU, but inference is significantly
slower — expect anywhere from 30 seconds to a few minutes per turn instead of
1–5 seconds, most of it spent reading the prompt back in. The app waits for a
slow turn rather than failing it; see
[Performance and hardware](/play/performance/#timeout-errors). The Qwen3 4B
starter model is the most practical choice for CPU-only machines.

**Partial VRAM fit:** if you have less VRAM than the minimum, llama.cpp can
still run the model with only part of it on the GPU. Inference will be slower
but may be acceptable. The app does not choose that split: it leaves the number
of GPU layers to the engine's own default. See
[Troubleshooting](/start/troubleshooting/#low-vram-or-slow-inference).

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
2. **You want direct GPU configuration control**: number of offloaded layers,
   VRAM limits, batch size, or custom server flags. The built-in engine starts
   with fixed settings chosen for one player in one conversation: one slot,
   the model's context size from the registry, and small prompt batches.
   **Settings → AI engine** has **Context length**, **GPU layers** and **CPU
   threads** fields under **Show advanced engine settings**, but at this
   release the engine the app starts does not use them.
3. **You run several AI applications** and prefer managing all model storage
   in one place with `ollama pull` / `ollama rm`.

If none of these apply, the built-in engine is simpler.

### Prerequisites

1. Install Ollama from [ollama.com](https://ollama.com/).
2. Pull a compatible model:
   ```bash
   ollama pull qwen3:8b
   ```
   Any model that supports system prompts and structured JSON output should
   work: the app sends Ollama the JSON schema each reply must follow. The
   models in the app's own registry come from the `qwen3` and `mistral`
   families.
3. Confirm Ollama is running:
   ```bash
   ollama list
   ```

### How to select Ollama in the app

1. Open Conversation Simulator. On the welcome screen, expand **Advanced: use
   Ollama or a local GGUF file** (below the **Set me up** card).
2. Click **Browse Ollama models**.
3. The app lists the models in your local Ollama installation. Click **Use
   this model** next to the one you want.
4. A short **Model benchmark** runs. Click **Continue to Home** when it is
   done.

If Ollama has more than one model, conversations may not use the one you
clicked. At this release the app passes your choice to the benchmark but not
to conversations and their debriefs, so Ollama answers those with the first
model it lists, the top line of `ollama list`. With a single model in Ollama,
that is the one every conversation uses.

If the list is empty (**No Ollama models detected.**), Ollama is either not
running or has no models. Start Ollama (`ollama serve`), pull a model
(`ollama pull qwen3:8b`), then open Conversation Simulator again.

### Changing the Ollama server address

The app connects to `http://127.0.0.1:11434` by default. Override this with
the `CONVSIM_OLLAMA_BASE_URL` environment variable if Ollama is listening on
a different address or port. If you point it at another computer, your
conversations' prompts and replies are sent to that computer.

### How to verify it worked

On the home screen, the **AI model** row of the **Status** list shows the name
of the Ollama model you selected. The row reads your saved choice and does not
ask Ollama, so it shows the name even when Ollama is not running. It says **Not
installed** only when no Ollama model is selected and Ollama does not answer.

A real problem shows up elsewhere: as an error on the Ollama step when you
click **Use this model**, as **Benchmark failed** on the **Model benchmark**
step, or as an AI engine error on your first turn in a conversation. If you see
one of those, confirm `ollama serve` is running and the model is still in
`ollama list`.

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

The GGUF path does not download the AI engine. The Steam build has it bundled.
A build from source needs it on the machine already: in `~/.convsim/bin/`, where
an earlier in-app model install put it, or as `llama-server` on your `PATH`.

### How to select a GGUF file in the app

1. Open Conversation Simulator. On the welcome screen, expand **Advanced: use
   Ollama or a local GGUF file**.
2. Click **Use a GGUF file**.
3. Enter the full path to the file, for example:
   - **macOS / Linux:** `/home/you/Downloads/my-model.gguf`
   - **Windows:** `C:\Users\you\Downloads\my-model.gguf`

   Type the whole path: a leading `~` is not expanded.
4. Click **Use this file**. The app uses the file where it is, without copying
   it, and loads it without checksum verification. Only registry-managed
   models have known checksums.
5. A short **Model benchmark** runs. Click **Continue to Home** when it is
   done.

On first launch the engine is not running yet, so it starts with your file
before the benchmark. You can also choose a file later, from **Settings → AI
engine → Open model manager →** and **Use a local GGUF file**. If the engine
is already running then, it keeps its current model: the benchmark measures
that model, and your file is used after you quit and reopen the app.

### How to verify it worked

On the home screen, the **AI model** row of the **Status** list shows the
name of the file you selected. The row reads your saved choice, not the
engine, so the name appears as soon as the file is selected, whether or not the
engine could load it. It says **Not installed** only when the selected file is
no longer at that path.

A file the engine cannot load shows up elsewhere: as an error on the GGUF step
when the engine starts with it, as **Benchmark failed** on the **Model
benchmark** step, or as an AI engine error on your first turn in a
conversation. If you see one of those, confirm the path is correct and the
file is a valid GGUF file compatible with the current llama.cpp version.

---

## Verifying a GGUF file's integrity manually

```bash
# macOS / Linux
shasum -a 256 /home/you/Downloads/my-model.gguf
```

```powershell
# Windows PowerShell
Get-FileHash "C:\Users\you\Downloads\my-model.gguf" -Algorithm SHA256
```

Compare the output against the checksum provided by the model author, or, for
a file from the model registry, against its `sha256` entry. Models the app
downloads itself are already checked; they are in the **Models** folder that
**Settings → Local folders** shows.

---

## Runtime environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CONVSIM_RUNTIME_ID` | `fake` | Runtime to start with: `llama_cpp`, `ollama`, or `fake`. Once a runtime is chosen in the app, that saved choice is used at startup instead |
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
