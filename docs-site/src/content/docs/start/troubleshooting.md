---
title: "Troubleshooting"
description: "Solutions for common Conversation Simulator problems, including engine startup failures, model load errors, slow inference, port conflicts, and offline mode."
sidebar:
  order: 3
verified_against: v0.2.2
---
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Common problems and solutions. If your issue is not listed here, open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues).

---

## Engine startup failure {#engine-startup-failure}

**"The conversation engine didn't start"**

The app could not start its background conversation engine (`convsim-core`). Common causes:

- **Port conflict:** another application is using port 7355. See [Port conflicts](#port-conflicts) below.
- **Binary not found:** the `convsim-core` executable is missing. Reinstall the app.
- **Crash on startup:** check the logs at `~/.convsim/logs/app.log` for the specific error.

**Recovery steps:**

1. Close other applications that might be using port 7355.
2. Restart Conversation Simulator from Steam or your installation.
3. If the problem persists, collect logs from `~/.convsim/logs/` and open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues).

**"The conversation engine stopped"**

The engine started but stopped during a session. This can happen if the AI model crashes the engine or the engine runs out of memory.

1. Click **Restart conversation engine** in the status card on the home screen.
2. If the problem repeats, try a lighter model — run setup again from the home screen and choose a smaller model.
3. Check `~/.convsim/logs/app.log` for crash details.

---

## First-run setup problems {#llm-present}

**No model is installed yet**

You need a local AI model before conversations can start. On the home screen,
click **Set me up** to install one. See
[Choosing how to run the AI](/play/ai-engine/) for model options and hardware
recommendations.

**Setup did not complete — came back to the welcome screen**

If setup was interrupted, click **Set me up** again. The process is
resumable — stages that already completed are skipped.

---

## AI engine binary {#llama-cpp-binary}

**"AI engine not found" on the setup screen**

The llama.cpp inference binary that Conversation Simulator needs is missing.
This usually means the installation was incomplete.

1. Reinstall the application from the [releases page](https://github.com/outrightmental/ConversationSimulator/releases).
2. If the error persists after reinstall, open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues) with your platform and OS version.

---

## Disk space {#disk-space}

**"Not enough disk space" during setup**

Model downloads require 2.5–14 GB of free disk space depending on the model.
The setup screen shows the exact size before any download begins.

1. Free up space on your drive — the setup screen shows the minimum required.
2. If you cannot free enough space, choose a smaller model: expand
   **Advanced options** on the welcome screen and pick a lighter option.

**Check available space:**

```bash
# macOS / Linux
df -h ~
```

```powershell
# Windows PowerShell
Get-PSDrive C
```

---

## Data directory {#data-dir-writable}

**"Cannot write to data directory"**

The app cannot write to `~/.convsim/`. Common causes:

- The directory is owned by another user (e.g. created by a previous `sudo` run).
- A permissions change removed write access.

Fix:

```bash
# macOS / Linux
sudo chown -R "$USER" ~/.convsim/
chmod -R u+rwX ~/.convsim/
```

---

## Model load failure {#model-load-failure}

**"Model failed to load" error after setup**

Possible causes:

1. **Insufficient VRAM:** the model requires more GPU memory than is available.
   Try the starter model (Qwen3 4B, ~2.5 GB, 4 GB VRAM minimum). To force
   CPU-only mode, open **Settings → Advanced**, set GPU layers
   (`n_gpu_layers`) to 0, and reload the model. Inference will be slower.

2. **Corrupted download:** delete the file from `~/.convsim/models/llm/` and
   re-run setup to download a fresh copy.

3. **AI engine binary not found:** see [AI engine binary](#llama-cpp-binary).

**"Checksum mismatch" during model download**

The downloaded file does not match the expected SHA-256 checksum. The file
has been discarded automatically. Try downloading again — the most common
cause is a partial or interrupted download. If the error repeats, open a
GitHub issue; the registry entry may need updating.

**Model loads but NPC responses are empty or malformed**

The model is loaded but producing unexpected output. Try:

1. Switching to a larger model from the setup flow.
2. Reducing context length: open **Settings → Advanced**, lower the context
   length to 4 096, and restart the app.
3. Checking `~/.convsim/logs/` for errors from convsim-core or the LLM runtime.

---

## Low VRAM or slow inference {#low-vram-or-slow-inference}

**Inference is very slow (30+ seconds per turn)**

The model is likely running entirely on CPU. This is expected on machines
without a discrete GPU or with insufficient VRAM. Options:

- **Switch to the starter model:** Qwen3 4B (~2.5 GB, 4 GB VRAM minimum) is
  the most practical choice for CPU-only or low-VRAM machines.
- **Reduce GPU layers:** if you have some VRAM but not enough for the full
  model, lower `n_gpu_layers` in **Settings → Advanced**. Partial GPU offload
  is faster than full CPU.
- **Reduce context length:** a shorter context (`n_ctx=4096`) uses less memory
  and allows more model layers to fit on the GPU.

**"Out of memory" error when loading model**

Not enough VRAM, or insufficient system RAM for CPU mode. Recommended model
by available memory:

| Available VRAM / RAM | Recommendation |
|---|---|
| < 4 GB VRAM, ≥ 8 GB RAM | Qwen3 4B on CPU (GPU layers = 0) |
| 4–6 GB VRAM | Qwen3 4B (starter) |
| 6–8 GB VRAM | Qwen3 8B (standard) |
| 10–12 GB VRAM | Qwen3 14B (high-quality) |
| 16+ GB VRAM | Mistral Small 3.1 24B or Qwen3 14B |

For Apple Silicon, unified memory acts as VRAM — treat the total RAM figure
as available VRAM.

---

## Port conflicts {#port-conflicts}

**"Port XXXX is already in use"**

The app reports exactly which process is blocking the port. Stop that process
and restart the app.

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

Common culprits: a previous instance of the app that was not stopped cleanly,
or another application using ports in the 7354–7358 range.

---

## Voice unavailable {#voice-ready}

**"Speech input unavailable"**

Speech-to-text (STT) requires the whisper.cpp runtime. In the current release
the conversation screen falls back to text input automatically — no action
needed.

When STT is available, a microphone icon will appear in the conversation input.
If it is greyed out:

1. Check that your device has microphone permission for the app.
2. Check `~/.convsim/logs/` for errors from the STT service.

**"Voice output unavailable"**

Text-to-speech (TTS) requires the Kokoro TTS runtime. In the current release
the conversation screen shows NPC dialogue as text automatically.

---

## Offline mode {#offline-mode}

Conversation Simulator is designed to work fully offline after initial setup
and model download.

If the home screen shows a network error:

1. **Model not downloaded:** complete first-run setup while connected to the
   internet. After that, play is fully offline.
2. **Pack metadata:** packs are bundled with the application and do not require
   a network connection. If pack loading fails, this is a bug — open a GitHub
   issue.
3. **Stale browser cache:** a hard reload (`Ctrl+Shift+R` / `Cmd+Shift+R`)
   clears any stale service worker state.

---

## Developer debug drawer

The conversation screen includes a collapsible debug drawer for diagnosing
model drift or unexpected NPC behaviour. It is never shown during normal play.

**How to enable:**

- **Build-time flag:** set `VITE_DEV_TOOLS=true` in `.env.local` before
  running `pnpm dev`. The drawer appears for all sessions in that build.
- **Per-device toggle:** open **Settings → Advanced → Developer debug mode**.
  Takes effect after reloading the conversation screen.

**What the drawer shows per turn:**

- Raw model JSON payload (the full event payload as returned by the backend).
- Applied state delta committed to tracked NPC state variables for that turn.
- Rejected state delta — changes the model requested for variables the
  simulator does not track; these are dropped and never applied.
- Amber `agenda` badge when the payload contains hidden NPC fields.

**Security note:** the drawer is not mounted in the DOM in normal mode. Disable
developer debug mode before sharing your screen or recording a session.

---

## Where to get help

- Open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues) for bugs or missing documentation.
- See [Installation](/start/install/) for installation steps.
- See [Quickstart](/start/quickstart/) for first-run instructions.
- See [Choosing how to run the AI](/play/ai-engine/) for model selection and hardware guidance.
