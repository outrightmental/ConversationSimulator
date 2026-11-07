<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Local models

Conversation Simulator requires a local language model to run NPC dialogue. No model weights are bundled with the application. You download exactly what you need, after the app has shown you the model's size and license.

Inference happens on your computer, and no prompts, transcripts, or model outputs are sent to any external server during play, unless you point the app at an AI server on another computer yourself: `CONVSIM_OLLAMA_BASE_URL` for Ollama, or `CONVSIM_LLAMA_CPP_BASE_URL` for a llama.cpp server (see [Runtime environment variables](#runtime-environment-variables)). See [privacy.md](privacy.md) for the full data-handling policy and [network-security.md](network-security.md) for how the local-only guarantee is enforced.

---

## How the model manager works

During first-run setup, click **Set me up** on the welcome screen. The card
shows the recommended model's size and license, and the download starts as soon
as you click. The recommended model is the registry's `role: starter` entry
(Qwen3 4B Instruct Q4_K_M) on every machine; it is not chosen by hardware.

After first-run setup you can switch model in the **AI engine** section of
**Settings** (Provider and Model, then **Apply**). Its llama.cpp model list
shows only models the app downloaded (install status `ready`); a GGUF file you
registered yourself is stored as `complete` and is not listed. The section's
**Open model manager →** link opens the model manager (**Set up your model**).

A switch to another llama.cpp model or GGUF file does not reach an engine that
is already running, which it is after **Set me up** and whenever the app starts
with llama.cpp selected. `POST /api/models/use` starts the engine only when it
is not answering, and the GGUF path's engine start treats the engine's "already
running" answer as success. The choice is saved: Settings reports **Provider
and model updated.** and the Home screen shows the new name. But the engine
keeps the model it started with, and on the GGUF path the **Model benchmark**
measures that model too. The new model is used after you quit and reopen the
app, because the startup autostart tries the saved selection first. If the
engine is not running, **Apply** starts it with the model you chose.

The model manager offers the same three choices as first-run setup: the
recommended model, **Use existing Ollama model**, and **Use a local GGUF file**.
It reads the registry (`model-registry/registry.yaml`) but offers only the
starter model from it; no screen installs the other models at this release. The
recommended model's card shows its name, size, license and minimum VRAM. Its
**Confirm model install** step adds the recommended VRAM, the SHA-256 checksum,
a link to the license and, in the model manager, the source (**Official
registry**). Nothing downloads until you click **Confirm & install**. There is
no separate license acceptance step.

After downloading, the app verifies the SHA-256 checksum before the file is
used. If the checksum does not match, the file is deleted and downloaded once
more; if the second copy also fails, setup stops with an error. The app never
loads a registry download whose checksum does not match. See
[model-download-policy.md](model-download-policy.md) for the details.

Downloaded models are stored in `models/llm/` under the app's data folder, which
depends on the platform; **Settings → Local folders** shows the path as
**Models**. The confirmation step's **Saves to** row (**Storage path** in the
model manager) still shows a `~/.convsim/models/llm/` prefix, which is out of
date; only the filename on it is right.

---

## Hardware tiers

| Tier | Model | Size | Download at 50 Mbps | Min VRAM | CPU fallback |
|---|---|---|---|---|---|
| Starter | Qwen3 4B Instruct Q4_K_M | 2.5 GB | ~7 min | 4 GB | Yes (slow) |
| Standard | Qwen3 8B Instruct Q4_K_M | 5.0 GB | ~13 min | 6 GB | Yes (very slow) |
| High-quality | Qwen3 14B Instruct Q4_K_M | 9.0 GB | ~24 min | 10 GB | Not practical |
| High-quality | Mistral Small 3.1 24B Instruct Q4_K_M | 14.3 GB | ~38 min | 16 GB | Not practical |
| User-supplied | Any GGUF | varies | varies | varies | Depends on model |

**Apple Silicon:** Metal acceleration works out of the box through llama.cpp. Use the VRAM column as a guide for unified memory (M1/M2/M3/M4 chips share CPU and GPU memory).

**CPU fallback:** any model can run on CPU without a GPU, but inference is significantly slower — expect anywhere from 30 seconds to a few minutes per turn instead of 1–5 seconds, most of it spent reading the prompt back in. The app waits for a slow turn rather than failing it; see [performance](performance.md#timeout-errors). The Qwen3 4B starter model is the only practical choice for CPU-only machines.

**Partial VRAM fit:** if you have less VRAM than the minimum, llama.cpp can still run the model with a reduced number of GPU-offloaded layers. Inference will be slower but may be acceptable. The app passes no `--n-gpu-layers` to the engine it starts, so the engine's own default decides the split; the **GPU layers** field in **Settings → AI engine** (under **Show advanced engine settings**) is saved but not applied to that engine at this release. See [troubleshooting](troubleshooting.md#low-vram-or-slow-inference).

The engine the app starts runs with one slot, the context size from the model's registry entry (8 192 tokens unless the entry says otherwise), a 256-token batch and a 1 GiB prompt cache. See [runtime-adapters.md](runtime-adapters.md) for how those settings are passed and overridden.

---

## Recommended models

The app's screens install only the starter model. The other three are in the registry, but to use one at this release you download its file yourself (the registry lists the pinned URL and SHA-256) and select it as a [custom GGUF model](#using-a-custom-gguf-model). A file selected that way is not matched to its registry entry, so the engine starts it with the default 8 192-token context, not the context length listed below. If the engine is already running, as it is after **Set me up**, the new file is used after you quit and reopen the app (see [How the model manager works](#how-the-model-manager-works)).

### Qwen3 4B Instruct Q4_K_M — starter

- **License:** Apache-2.0
- **Size:** 2.5 GB — about 7 minutes on a 50 Mbps connection
- **Best for:** machines with 4–6 GB VRAM, or CPU-only installs
- **Context length:** 8 192 tokens
- **Notes:** Fastest model in the registry. Suitable for all text-only scenarios. NPC responses may be shorter and less contextually rich than larger models.

### Qwen3 8B Instruct Q4_K_M — standard

- **License:** Apache-2.0
- **Size:** 5.0 GB — about 13 minutes on a 50 Mbps connection
- **Best for:** machines with 6–8 GB VRAM
- **Context length:** 8 192 tokens
- **Notes:** Good balance of quality and speed. Handles complex multi-turn conversations well.

### Qwen3 14B Instruct Q4_K_M — high-quality

- **License:** Apache-2.0
- **Size:** 9.0 GB — about 24 minutes on a 50 Mbps connection
- **Best for:** machines with 10–12 GB VRAM
- **Context length:** 8 192 tokens
- **Notes:** Noticeably more coherent NPC behaviour in emotionally complex scenarios.

### Mistral Small 3.1 24B Instruct Q4_K_M — high-quality

- **License:** Apache-2.0
- **Size:** 14.3 GB — about 38 minutes on a 50 Mbps connection
- **Best for:** machines with 16–24 GB VRAM
- **Context length:** 32 768 tokens
- **Notes:** Longest context window in the registry. Best for long negotiations or scenarios with many tracked state variables.

---

## Using Ollama

If you already have [Ollama](https://ollama.com/) installed with a compatible model, you can use it as the LLM runtime instead of the built-in llama.cpp server.

### 1. Start Ollama

```bash
ollama serve
```

### 2. Pull a compatible model

```bash
ollama pull qwen3:8b
```

Any Ollama model that supports system prompts and structured JSON output should work: the adapter sends the reply's JSON schema as Ollama's `format`. The models in the app's own registry come from the qwen3 and mistral families.

### 3. Select the Ollama runtime

On the welcome screen, expand **Advanced: use Ollama or a local GGUF file** and
click **Browse Ollama models**. The app lists detected Ollama models; click
**Use this model** next to the one you want, and a short **Model benchmark**
runs before **Continue to Home**. The app connects to `http://127.0.0.1:11434`
by default.

Or set the runtime before starting the dev server:

```bash
CONVSIM_RUNTIME_ID=ollama ./scripts/dev.sh
```

This only applies while no runtime has been chosen in the app: a saved choice
wins at startup.

Conversations and debriefs use the first model Ollama lists (the top line of
`ollama list`), whether or not you chose another one. The turn pipeline and the
debrief engine build their `ChatRequest` without a `model_id`, and the Ollama
adapter falls back to the first entry of `/api/tags` when none is given. Only
the **Model benchmark** passes the chosen model, and the Home screen shows it.
With a single model in Ollama, that is the one every conversation uses.

Override the Ollama server URL with `CONVSIM_OLLAMA_BASE_URL` if Ollama is listening on a different address.

---

## GGUF format

All registry models use the GGUF format — the standard container for quantized models compatible with llama.cpp. A GGUF file is self-contained: weights and metadata are stored in a single file.

### Quantization

The registry uses Q4_K_M quantization for all curated models. This offers a good balance of model quality and file size. Other quantization levels (Q2_K, Q5_K_M, Q8_0, F16) are available from model providers if you want to trade quality for smaller size or more precision.

### Verifying a GGUF file manually

Registry downloads are named after the model ID and stored in the **Models**
folder that **Settings → Local folders** shows. On Linux, for example:

```bash
# macOS / Linux
shasum -a 256 ~/.local/share/com.outrightmental.convsim/models/llm/qwen3-4b-instruct-q4_k_m.gguf
```

```powershell
# Windows PowerShell
Get-FileHash "$env:LOCALAPPDATA\com.outrightmental.convsim\models\llm\qwen3-4b-instruct-q4_k_m.gguf" -Algorithm SHA256
```

On macOS the folder is `~/Library/Application Support/com.outrightmental.convsim/models/llm/`.
These are the desktop app's folders; convsim-core run from source without the
desktop shell uses different ones on Linux and Windows (see
[model-download-policy.md](model-download-policy.md#destination-directory)).

Compare the output against the checksum in `model-registry/registry.yaml`.

---

## Using a custom GGUF model

To use a GGUF file you obtained independently:

1. On the welcome screen, expand **Advanced: use Ollama or a local GGUF file**
   and click **Use a GGUF file**.
2. Enter the full path to the file (e.g., `/home/you/Downloads/my-model.gguf`).
   A leading `~` is not expanded.
3. Click **Use this file**. A short **Model benchmark** runs before **Continue to Home**.

On first launch the engine is not running yet, so it starts with your file before the benchmark. You can also choose a file later from the model manager (**Settings → AI engine → Open model manager →**, then **Use a local GGUF file**). If the engine is already running then, it keeps its current model, the benchmark measures that model, and your file is used after you quit and reopen the app.

The app stores the path and uses the file where it is; it does not copy it. It loads the file without checksum verification, because only registry-managed models have known checksums. Ensure you have the right to use the model under its license; the application cannot verify the license of a user-supplied file.

This path does not download the engine. The Steam build bundles `llama-server`; a build from source needs it already present, in `~/.convsim/bin/` from an earlier in-app model install or on your `PATH`.

---

## Licenses

All models in the curated registry are released under Apache-2.0. Model weights are never bundled with the application installer. They are downloaded separately, and the license name is shown before any download begins: on the **Set me up** card, and with a link to the full license text on the **Confirm model install** step.

If you supply your own GGUF file, you are responsible for complying with its license.

---

## Updating and removing models

**Update:** each registry entry is pinned to one file revision, so an installed model has nothing to update. Installing a model that is already recorded as installed skips the download and checksum stages.

**Remove:** the app has no remove button. Delete the file from the **Models** folder (**Settings → Local folders** shows where it is) and select a different model. The install record stays, so if you later install the same model again, setup skips the download and then fails when it tries to start the missing file.

---

## Runtime environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CONVSIM_RUNTIME_ID` | `fake` | Runtime to start with: `llama_cpp`, `ollama`, or `fake`. Set to `llama_cpp` to use a downloaded local model. A runtime chosen in the app is saved and wins at startup. |
| `CONVSIM_LLAMA_CPP_BASE_URL` | `http://127.0.0.1:7356` | llama-server URL |
| `CONVSIM_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama server URL |

The `fake` runtime returns scripted responses and requires no model file. It is used for offline smoke tests and CI.

---

## Next steps

- [Quickstart](quickstart.md) — run your first conversation
- [Troubleshooting](troubleshooting.md) — model load failures, slow inference, low VRAM
- [runtime-adapters.md](runtime-adapters.md) — technical detail on the LLM runtime abstraction
- [model-registry/registry.yaml](../model-registry/registry.yaml) — full list of registry entries with checksums
