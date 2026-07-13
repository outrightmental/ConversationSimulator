<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Local models

Conversation Simulator requires a local language model to run NPC dialogue. No model weights are bundled with the application — you download exactly what you need after reading and accepting the model's license.

All inference happens on your computer. No prompts, transcripts, or model outputs are sent to any external server during play. See [privacy.md](privacy.md) for the full data-handling policy and [network-security.md](network-security.md) for how the local-only guarantee is enforced.

---

## How the model manager works

During first-run setup, click **Set me up** on the welcome screen. After
first-run setup completes you can change the model from **Settings → AI Engine**.

The model manager shows curated models from the registry (`model-registry/registry.yaml`). For each model it displays:

- Full name, model family, and quantization level
- File size and approximate download time
- License name with a link to the full license text
- VRAM requirement and CPU-fallback note
- SHA-256 checksum (verified after download)

You must accept the license before a download begins. After downloading, the app verifies the SHA-256 checksum before loading the file. If the checksum does not match, the file is discarded and an error is shown — the app never loads a file whose integrity cannot be confirmed.

Downloaded models are stored in `~/.convsim/models/llm/`.

---

## Hardware tiers

| Tier | Model | Size | Download at 50 Mbps | Min VRAM | CPU fallback |
|---|---|---|---|---|---|
| Starter | Qwen3 4B Instruct Q4_K_M | 2.5 GB | ~7 min | 4 GB | Yes (slow) |
| Standard | Qwen3 8B Instruct Q4_K_M | 5.0 GB | ~14 min | 6 GB | Yes (very slow) |
| High-quality | Qwen3 14B Instruct Q4_K_M | 9.0 GB | ~25 min | 10 GB | Not practical |
| High-quality | Mistral Small 3.1 24B Q4_K_M | 14.3 GB | ~39 min | 16 GB | Not practical |
| User-supplied | Any GGUF | varies | varies | varies | Depends on model |

**Apple Silicon:** Metal acceleration works out of the box through llama.cpp. Use the VRAM column as a guide for unified memory (M1/M2/M3/M4 chips share CPU and GPU memory).

**CPU fallback:** any model can run on CPU without a GPU, but inference is significantly slower — expect 15–60 seconds per turn instead of 1–5 seconds. The Qwen3 4B starter model is the only practical choice for CPU-only machines.

**Partial VRAM fit:** if you have less VRAM than the minimum, the model can still load with a reduced number of GPU-offloaded layers. Inference will be slower but may be acceptable. See [troubleshooting](troubleshooting.md#low-vram-or-slow-inference).

---

## Recommended models

### Qwen3 4B Instruct Q4_K_M — starter

- **License:** Apache-2.0
- **Size:** 2.5 GB — about 7 minutes on a 50 Mbps connection
- **Best for:** machines with 4–6 GB VRAM, or CPU-only installs
- **Context length:** 8 192 tokens
- **Notes:** Fastest model in the registry. Suitable for all text-only scenarios. NPC responses may be shorter and less contextually rich than larger models.

### Qwen3 8B Instruct Q4_K_M — standard (recommended for most users)

- **License:** Apache-2.0
- **Size:** 5.0 GB — about 14 minutes on a 50 Mbps connection
- **Best for:** machines with 6–8 GB VRAM
- **Context length:** 8 192 tokens
- **Notes:** Good balance of quality and speed. Handles complex multi-turn conversations well.

### Qwen3 14B Instruct Q4_K_M — high-quality

- **License:** Apache-2.0
- **Size:** 9.0 GB — about 25 minutes on a 50 Mbps connection
- **Best for:** machines with 10–12 GB VRAM
- **Context length:** 8 192 tokens
- **Notes:** Noticeably more coherent NPC behaviour in emotionally complex scenarios.

### Mistral Small 3.1 24B Instruct Q4_K_M — high-quality

- **License:** Apache-2.0
- **Size:** 14.3 GB — about 39 minutes on a 50 Mbps connection
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

Any Ollama model that supports system prompts and structured JSON output should work. The qwen3 and mistral families are tested.

### 3. Select the Ollama runtime

On the welcome screen, expand **Advanced options** and click the **Use
Ollama** button. The app lists detected Ollama models — click **Use this
model** next to the one you want. The app connects to
`http://127.0.0.1:11434` by default.

Or set the runtime before starting the dev server:

```bash
CONVSIM_RUNTIME_ID=ollama ./scripts/dev.sh
```

Override the Ollama server URL with `CONVSIM_OLLAMA_BASE_URL` if Ollama is listening on a different address.

---

## GGUF format

All registry models use the GGUF format — the standard container for quantized models compatible with llama.cpp. A GGUF file is self-contained: weights and metadata are stored in a single file.

### Quantization

The registry uses Q4_K_M quantization for all curated models. This offers a good balance of model quality and file size. Other quantization levels (Q2_K, Q5_K_M, Q8_0, F16) are available from model providers if you want to trade quality for smaller size or more precision.

### Verifying a GGUF file manually

```bash
# macOS / Linux
shasum -a 256 ~/.convsim/models/llm/qwen3-4b-instruct-q4_k_m.gguf
```

```powershell
# Windows PowerShell
Get-FileHash "$env:USERPROFILE\.convsim\models\llm\qwen3-4b-instruct-q4_k_m.gguf" -Algorithm SHA256
```

Compare the output against the checksum in `model-registry/registry.yaml`.

---

## Using a custom GGUF model

To use a GGUF file you obtained independently:

1. On the welcome screen, expand **Advanced options** and click **Use custom
   GGUF**.
2. Enter the full path to the file (e.g., `~/.convsim/models/llm/my-model.gguf`).

The app loads the file without checksum verification — only registry-managed models have known checksums. Ensure you have the right to use the model under its license; the application cannot verify the license of a user-supplied file.

---

## Licenses

All models in the curated registry are released under Apache-2.0. Model weights are never bundled with the application installer — they are downloaded separately, and the license is shown in full before any download begins.

If you supply your own GGUF file, you are responsible for complying with its license.

---

## Updating and removing models

**Update:** re-download the model from the model manager. The old file is replaced only after the new download and checksum verification succeed.

**Remove:** delete the file from `~/.convsim/models/llm/` and select a different model in the model manager.

---

## Runtime environment variables

| Variable | Default | Purpose |
|---|---|---|
| `CONVSIM_RUNTIME_ID` | `fake` | Select runtime: `llama_cpp`, `ollama`, or `fake`. Set to `llama_cpp` to use a downloaded local model. |
| `CONVSIM_LLAMA_CPP_BASE_URL` | `http://127.0.0.1:7356` | llama-server URL |
| `CONVSIM_OLLAMA_BASE_URL` | `http://127.0.0.1:11434` | Ollama server URL |

The `fake` runtime returns scripted responses and requires no model file. It is used for offline smoke tests and CI.

---

## Next steps

- [Quickstart](quickstart.md) — run your first conversation
- [Troubleshooting](troubleshooting.md) — model load failures, slow inference, low VRAM
- [runtime-adapters.md](runtime-adapters.md) — technical detail on the LLM runtime abstraction
- [model-registry/registry.yaml](../model-registry/registry.yaml) — full list of registry entries with checksums
