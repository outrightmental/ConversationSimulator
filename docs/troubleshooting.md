<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Troubleshooting

Common problems and solutions. If your issue is not listed here, open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues).

---

## Setup issues

**`./scripts/setup.sh` fails with "Python 3.10+ is required"**

Install Python 3.10 or newer:

- macOS: `brew install python@3.11`
- Ubuntu/Debian: `sudo apt install python3.11 python3.11-venv`
- Windows: download from <https://www.python.org/downloads/>

If Python 3.10+ is already installed but the script still fails, check which binary is on your `PATH`:

```bash
which python3
python3 --version
```

If a system-managed Python is shadowing your installed version, use a version manager such as `pyenv` or `mise`.

**`./scripts/setup.sh` fails with "Node.js 18+ is required"**

Install Node.js 18 LTS or newer from <https://nodejs.org/>. Or use a version manager:

```bash
nvm install 18 && nvm use 18
```

**`pip install` fails during setup**

Try upgrading pip inside the virtual environment first:

```bash
services/convsim-core/.venv/bin/pip install --upgrade pip
./scripts/setup.sh
```

---

## Model load failure

**"No model loaded" banner on the home screen**

A model must be installed before conversations can start. Open **Settings → Models** and install a model from the registry. See [local-models.md](local-models.md) for hardware requirements and recommendations.

**"Model failed to load" error in the model manager**

Possible causes:

1. **Insufficient VRAM:** the model requires more GPU memory than is available. Try the starter model (Qwen3 4B, ~2.6 GB, 4 GB VRAM minimum). To force CPU-only mode and bypass the GPU entirely, set `CONVSIM_LLAMA_CPP_ARGS="-ngl 0"` before starting the dev server. Inference will be slower but the model will load.

2. **Corrupted download:** delete the file from `~/.convsim/models/` and re-download through the model manager.

3. **llama-server binary not found:** the llama.cpp binary must be present before the LLM runtime can start. Run `./runtimes/llama_cpp/download-runtime.sh` to fetch the binary for your platform. If that script is not yet available, check the [GitHub releases](https://github.com/outrightmental/ConversationSimulator/releases) page for pre-built binaries.

**"Checksum mismatch" during model download**

The downloaded file does not match the expected SHA-256 checksum. The file has been discarded automatically. Try downloading again — the most common cause is a partial or interrupted download. If the error repeats, open a GitHub issue; the registry entry may need updating.

**Model loads but NPC responses are empty or malformed**

The model is loaded but producing unexpected output. Try:

1. Switching to a larger model from the registry.
2. Reducing context length: open **Settings → Advanced**, lower the context length to 4 096, and restart the app.
3. Checking `~/.convsim/logs/` for errors from convsim-core or the LLM runtime.

---

## Low VRAM or slow inference

**Inference is very slow (30+ seconds per turn)**

The model is likely running entirely on CPU. This is expected on machines without a discrete GPU or with insufficient VRAM. Options:

- **Switch to the starter model:** Qwen3 4B (~2.6 GB, 4 GB VRAM minimum) is the most practical choice for CPU-only or low-VRAM machines.
- **Reduce GPU layers:** if you have some VRAM but not enough for the full model, lower `n_gpu_layers` in **Settings → Advanced**. Partial GPU offload is faster than full CPU.
- **Reduce context length:** a shorter context (`n_ctx=4096`) uses less memory and allows more model layers to fit on the GPU.

**"Out of memory" error when loading model**

Not enough VRAM, or insufficient system RAM for CPU mode. Recommended model by available memory:

| Available VRAM / RAM | Recommendation |
|---|---|
| < 4 GB VRAM, ≥ 8 GB RAM | Qwen3 4B on CPU (`-ngl 0`) |
| 4–6 GB VRAM | Qwen3 4B (starter) |
| 6–8 GB VRAM | Qwen3 8B (standard) |
| 10–12 GB VRAM | Qwen3 14B (high-quality) |
| 16+ GB VRAM | Mistral Small 3.1 24B or Qwen3 14B |

For Apple Silicon, unified memory acts as VRAM — treat the total RAM figure as available VRAM.

---

## Port conflicts

**`./scripts/dev.sh` fails with "Port XXXX is already in use by PID YYYY (process-name)"**

The script reports exactly which process is blocking the port. Stop that process and try again.

```bash
# macOS / Linux — find and kill the blocking process
lsof -i :7354
lsof -i :7355
kill <PID>
```

```powershell
# Windows PowerShell
Get-NetTCPConnection -LocalPort 7354 | Select-Object OwningProcess
Stop-Process -Id <PID>
```

Common culprits:

- A previous `./scripts/dev.sh` that was not stopped cleanly — run `pkill -f uvicorn` and `pkill -f vite` to clean up.
- Another application using ports in the 7354–7358 range.

> Note: custom port numbers via environment variable are not yet implemented in the dev scripts. Stopping the conflicting process is the current workaround.

---

## STT / TTS unavailable

**"Speech input unavailable" on the conversation screen**

Speech-to-text (STT) requires the whisper.cpp runtime. In the first milestone (text-only simulator), STT is not yet implemented. The conversation screen falls back to text input automatically — no action is needed.

When STT is available, a microphone icon will appear in the conversation input. If it is greyed out:

1. Check that your browser has microphone permission for `127.0.0.1`.
2. Confirm convsim-stt is running on port 7357 — look for it in the `./scripts/dev.sh` output.
3. Check `~/.convsim/logs/` for errors from the STT service.

**"Voice output unavailable" on the conversation screen**

Text-to-speech (TTS) requires the Silero TTS runtime. In the first milestone, TTS is not yet implemented. The conversation screen shows NPC dialogue as text automatically.

When TTS is available, a speaker icon will appear in the conversation settings. If it is greyed out, confirm convsim-tts is running on port 7358.

---

## Offline mode

Conversation Simulator is designed to work fully offline after initial setup and model download.

If the home screen shows a network error:

1. **Model not downloaded:** install a model through the model manager while connected to the internet. After that, play is fully offline.
2. **Pack metadata:** packs are bundled with the application and do not require a network connection. If pack loading fails, this is a bug — open a GitHub issue.
3. **Stale browser cache:** a hard reload (`Ctrl+Shift+R` / `Cmd+Shift+R`) clears any stale service worker state.

To verify that play is truly offline, run the built-in smoke test:

```bash
npx convsim offline-smoke-test packs/official/job-interview-basic
```

This runs a scripted conversation with the fake runtime and confirms that no outbound TCP connection was attempted during play. The command exits nonzero with a specific error message if any subsystem (LLM inference, STT, TTS, telemetry, asset fetch) attempted to reach an external host.

---

## Developer debug drawer

The conversation screen includes a collapsible debug drawer for diagnosing model drift or unexpected NPC behaviour. It is never shown during normal play.

**How to enable:**

- **Build-time flag:** set `VITE_DEV_TOOLS=true` in `.env.local` before running `pnpm dev`. The drawer appears for all sessions in that build.
- **Per-device toggle:** open **Settings → Advanced → Developer debug mode**. Takes effect after reloading the conversation screen.

**What the drawer shows per turn:**

- Raw model JSON payload (the full `npc_opening` / `npc_turn` event payload as returned by the backend).
- Applied state delta committed to tracked NPC state variables for that turn.
- Rejected state delta (red `⊘ rejected` badge) — changes the model requested for variables the simulator does not track; these are dropped and never applied. This is a common model-drift signal.
- Amber `agenda` badge when the payload contains hidden NPC fields (`agenda`, `hidden_state`, `prompt_metadata`).

**Copy to clipboard:** raw audio fields (`audio`, `audio_data`, `tts_audio`, `raw_audio`) and `secret` fields are redacted before copying. A persistent warning label marks the redaction.

**Security note:** the drawer is not mounted in the DOM in normal mode — hidden NPC fields cannot be read through browser developer tools when the setting is off. Disable developer debug mode before sharing your screen or recording a session.

---

## Where to get help

- Open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues) for bugs or missing documentation.
- See [install.md](install.md) for installation steps.
- See [quickstart.md](quickstart.md) for first-run instructions.
- See [local-models.md](local-models.md) for model selection and hardware guidance.
