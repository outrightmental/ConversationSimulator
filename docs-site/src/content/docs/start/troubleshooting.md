---
title: "Troubleshooting"
description: "Solutions for common Conversation Simulator problems, including engine startup failures, model load errors, slow inference, port conflicts, and offline mode."
sidebar:
  order: 3
verified_against: v0.2.3
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
2. If the problem repeats, try a lighter model — open the model manager (**Settings → Runtime → Open model manager**) and choose a smaller model.
3. Check `~/.convsim/logs/app.log` for crash details.

---

## First-run setup problems {#llm-present}

**No model is installed yet**

You need a local AI model before conversations can start. On first launch,
click **Set me up** on the welcome screen. If you have already been to the
home screen, the **No model configured** section there offers **Install a GGUF
model**, **Connect Ollama**, and **Try text-only demo** — the first two open
the model manager, where **Install recommended model** downloads the default.
You can also reach it from **Settings → Runtime → Open model manager**. See
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
2. If you cannot free enough space, choose a lighter option: when the download
   fails, click **Choose a different option** and use a smaller Ollama model or
   a compact GGUF file instead. On first launch these are also under
   **Advanced: use Ollama or a local GGUF file** on the welcome screen.

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

Common culprits: a previous instance of the app that was not stopped cleanly
(see [The engine keeps running after I quit](#engine-wont-exit)), or another
application using ports in the 7354–7358 range.

---

## The engine keeps running after I quit {#engine-wont-exit}

**Steam still shows Conversation Simulator as running after the window closes**,
or `convsim-core` is still listed in Task Manager / Activity Monitor.

Quitting the app shuts the conversation engine down and waits for it, so this
should not happen. If it does, the leftover process also holds port 7355, which
stops the next launch. Clear it:

```bash
# macOS / Linux
pkill -f convsim-core
# The engine normally stops the AI engine and the voice process on its way out.
# If it was too wedged to do that, a stray llama-server holds port 7356 and the
# next launch cannot load a model — so clear that too. (Skip this line if you
# started llama-server yourself.)
pkill -f llama-server
```

```powershell
# Windows PowerShell — /T also clears the AI engine and the voice process
taskkill /IM convsim-core.exe /T /F
```

Nothing is lost by doing this: conversations are saved as they happen, and an
interrupted model download resumes from where it stopped.

Then please [open an issue](https://github.com/outrightmental/ConversationSimulator/issues)
and attach `app.log` and `runtime.log` from `~/.convsim/logs/`. The last lines of
`app.log` say how far the shutdown got, which is the one thing we cannot work
out from the outside.

---

## Voice unavailable {#voice-ready}

Voice is optional. Without it the conversation screen falls back to text input
and on-screen NPC dialogue automatically — nothing breaks.

**To turn it on, open Settings → Voice readiness → Set up voice.** That screen
lists every piece voice needs, downloads the model files for you (each one
checksum-verified before it is installed), and shows the exact one-line command
for the two engines it will not download on your behalf. Once speech-to-text is
in place it also offers **Record a test phrase**, which runs one real
transcription and repeats back what it heard — the quickest way to tell a
broken chain from a quiet microphone. Full walkthrough:
[Speaking and listening](/play/voice/).

**"Speech input unavailable"**

Speech-to-text needs both the whisper.cpp program and a speech model. The setup
screen says which is missing. If both are present and the microphone button is
still greyed out:

1. Check that your device has microphone permission for the app. The setup
   screen asks for it directly and reports when the browser is blocking it.
2. Install `ffmpeg` — some recordings cannot be decoded without it. The setup
   screen flags this as its own row.
3. Check the logs folder for errors from the speech worker.

**"Voice output unavailable"**

The NPC voice runs in a small local server. If it is installed but not running,
the setup screen offers a **Start the voice server** button.

**Hands-free mode unavailable**

Hands-free turn-taking also needs the voice-activity model and `onnxruntime`;
both appear as their own rows on the setup screen. Push-to-talk works without
them.

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
