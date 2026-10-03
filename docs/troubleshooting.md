<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Troubleshooting

Common problems and solutions. If your issue is not listed here, open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues).

---

## Engine startup failure {#engine-startup-failure}

**"The conversation engine didn't start"**

The app could not start its background conversation engine (`convsim-core`). Common causes:

- **Port conflict:** another program is holding port 7355. See [Port conflicts](#port-conflicts) below. The app asks whatever is on the port whether it is a conversation engine, and gives it 30 seconds to answer before reporting a conflict — so an engine that is busy or restarting is not mistaken for an unrelated program.
- **Another edition is running:** the demo and the full app share port 7355. Close the one you are not using, then start the other.
- **The app is already running:** you launched a second copy while the first was still starting. Switch to the window that opened — do **not** close the program holding port 7355, because that is the conversation engine the working window is using.
- **Binary not found:** the `convsim-core` executable is missing. Reinstall the app or run `./scripts/setup.sh`.
- **Crash on startup:** open the logs folder (the recovery card shows an **Open logs folder** button) and check `app.log` for the specific error.

**Where are the logs?**

The packaged app writes logs to the platform-specific application data directory:

| Platform | Log directory |
|---|---|
| Windows | `%LOCALAPPDATA%\com.outrightmental.convsim\logs\` |
| macOS | `~/Library/Application Support/com.outrightmental.convsim/logs/` |
| Linux / Steam Deck | `~/.local/share/com.outrightmental.convsim/logs/` (or `$XDG_DATA_HOME/com.outrightmental.convsim/logs/`) |

The recovery card shows the exact path for your machine and includes an **Open logs folder** button. In developer mode (running without Tauri), the `./scripts/dev.sh` and `./scripts/dev-desktop.sh` helpers set `CONVSIM_LOG_DIR=~/.convsim/logs`, so logs go there. Running `convsim-core` directly without `CONVSIM_LOG_DIR` writes to the platform-specific directory above (or `<CONVSIM_DATA_ROOT>/logs` when `CONVSIM_DATA_ROOT` is set).

> **Legacy `~/.convsim` directory:** versions before v0.2.0 stored all app data under `~/.convsim/`. The packaged app no longer writes there. On first launch it runs a one-time migration that **copies** (never moves) `db/`, `packs/`, and other data into the platform-specific directory above — but only when that directory is still empty. If the new location already had data, migration is skipped and your `~/.convsim/` files are left untouched. Because the originals are only ever copied, `~/.convsim/` is safe to keep as a backup. Before deleting it, open the platform-specific directory above and confirm your `db/` and `packs/` folders are present there; a `.convsim_migrated_to_platform_dir` marker file inside `~/.convsim/` indicates a completed migration.

**Recovery steps:**

1. Close other applications that might be using port 7355.
2. Restart Conversation Simulator from Steam or your installation.
3. If the problem persists, open the logs folder using the **Open logs folder** button on the recovery card, collect `app.log`, and open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues).

**"The conversation engine stopped"**

The engine started but stopped during a session. This can happen if the AI model crashes the engine or the engine runs out of memory.

The app notices and restarts the engine itself, up to three times, showing
*The conversation engine stopped unexpectedly. Restarting…* while it does, then
reloads when the replacement is ready.

A conversation in progress is **not** lost. Every turn, the flow state and the
state variables are written to the local database as they happen, so the
replacement engine picks the session up exactly where it stopped and your
transcript reappears. Two things do not survive: the single turn that was in
flight when the engine stopped (send it again), and the state meters, which read
blank until the next reply refills them. After three failed restarts the app
stops trying and shows the recovery card instead.

1. If a restart succeeded, carry on where you left off — your transcript, packs, models, and past sessions are all intact.
2. If **Settings** reports that a required port is in use, the engine that crashed left its own AI-model process
   (`llama-server`, port 7356) behind. Replies usually keep working, because the app reaches that process over the
   port it is still serving — but the new engine does not own it, so anything that has to restart it (switching
   models, for instance) keeps failing. Quitting the app does **not** clear it: it is no longer a child of anything
   the app owns. End it by hand (see [Port conflicts](#port-conflicts)) or restart your computer, then start the app
   again.
3. If the problem repeats, try a lighter model — open the model manager (**Settings → Runtime → Open model manager**) and choose a smaller model.
4. Check `app.log` in the logs folder (see table above) for crash details.

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

**"No model configured" — no AI is configured yet**

A model must be installed before conversations can start. On first launch,
click **Set me up** on the welcome screen. Afterward, the home screen's **No
model configured** section (**Install a GGUF model** / **Connect Ollama**) opens
the model manager, where **Install recommended model** downloads the default;
you can also reach it from **Settings → Runtime → Open model manager**. See
[local-models.md](local-models.md) for hardware requirements and model
recommendations.

**"Model failed to load" error in the model manager**

Possible causes:

1. **Insufficient VRAM:** the model requires more GPU memory than is available. Try the starter model (Qwen3 4B, ~2.6 GB, 4 GB VRAM minimum). To force CPU-only mode and bypass the GPU entirely, open **Settings → Advanced**, set GPU layers (`n_gpu_layers`) to 0, and reload the model. Inference will be slower but the model will load.

2. **Corrupted download:** delete the file from the `models/llm/` subfolder of the application data directory (the parent of the `logs/` folder shown in [Where are the logs?](#engine-startup-failure) above — e.g. `%LOCALAPPDATA%\com.outrightmental.convsim\models\llm\` on Windows) and re-download through the model manager.

3. **llama-server binary not found:** the llama.cpp binary must be present before the LLM runtime can start. Run `./runtimes/llama_cpp/download-runtime.sh` to fetch the binary for your platform. If that script is not yet available, check the [GitHub releases](https://github.com/outrightmental/ConversationSimulator/releases) page for pre-built binaries.

**"Checksum mismatch" during model download**

The downloaded file does not match the expected SHA-256 checksum. The file has been discarded automatically. Try downloading again — the most common cause is a partial or interrupted download. If the error repeats, open a GitHub issue; the registry entry may need updating.

**Model loads but NPC responses are empty or malformed**

The model is loaded but producing unexpected output. Try:

1. Switching to a larger model from the registry.
2. Reducing context length: open **Settings → Advanced**, lower the context length to 4 096, and restart the app.
3. Checking the logs folder (see [Where are the logs?](#engine-startup-failure) for the platform-specific path) for errors from convsim-core or the LLM runtime.

---

## Low VRAM or slow inference

**Inference is very slow (30+ seconds per turn)**

The model is likely running entirely on CPU. This is expected on machines without a discrete GPU or with insufficient VRAM. Options, easiest first:

- **Set reply speed to Quick replies:** open **Settings → Reply speed** and choose **Quick replies**. A local model emits one token at a time, so most of the wait is the length of the reply — asking for shorter replies is the one lever that needs no hardware knowledge and no restart. It applies to your very next message, so you can change it mid-conversation and go straight back to it. ("Balanced" is the default and matches how the app behaved before this setting existed; "Fuller replies" trades speed for length.)
- **Switch to the starter model:** Qwen3 4B (~2.6 GB, 4 GB VRAM minimum) is the most practical choice for CPU-only or low-VRAM machines. On slow hardware a smaller model is a bigger win than any reply-speed setting.
- **Reduce GPU layers:** if you have some VRAM but not enough for the full model, lower `n_gpu_layers` in **Settings → Advanced**. Partial GPU offload is faster than full CPU.
- **Reduce context length:** a shorter context (`n_ctx=4096`) uses less memory and allows more model layers to fit on the GPU.

**"Out of memory" error when loading model**

Not enough VRAM, or insufficient system RAM for CPU mode. Recommended model by available memory:

| Available VRAM / RAM | Recommendation |
|---|---|
| < 4 GB VRAM, ≥ 8 GB RAM | Qwen3 4B on CPU (GPU layers = 0) |
| 4–6 GB VRAM | Qwen3 4B (starter) |
| 6–8 GB VRAM | Qwen3 8B (standard) |
| 10–12 GB VRAM | Qwen3 14B (high-quality) |
| 16+ GB VRAM | Mistral Small 3.1 24B or Qwen3 14B |

For Apple Silicon, unified memory acts as VRAM — treat the total RAM figure as available VRAM.

---

## Port conflicts {#port-conflicts}

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

**The packaged app reports "Port 7355 is already in use by another program"**

The desktop app asks whatever is on port 7355 for `GET /api/health`. If the
answer is a Conversation Simulator engine it attaches to it instead of starting
a second one; this message means the answer was something else. Close that
program (`lsof -i :7355` on macOS / Linux, `Get-NetTCPConnection -LocalPort 7355`
on Windows) and start the app again.

> Note: custom port numbers via environment variable are not yet implemented in the dev scripts. Stopping the conflicting process is the current workaround.

---

## STT / TTS unavailable

**"Speech input unavailable" on the conversation screen**

Speech-to-text (STT) requires the whisper.cpp runtime. In the first milestone (text-only simulator), STT is not yet implemented. The conversation screen falls back to text input automatically — no action is needed.

When STT is available, a microphone icon will appear in the conversation input. If it is greyed out:

1. Check that your browser has microphone permission for `127.0.0.1`.
2. Confirm convsim-stt is running on port 7357 — look for it in the `./scripts/dev.sh` output.
3. Check the logs folder (see [Where are the logs?](#engine-startup-failure) for the platform-specific path) for errors from the STT service.

**"Voice output unavailable" on the conversation screen**

Text-to-speech (TTS) requires the Kokoro TTS runtime. In the first milestone, TTS is not yet implemented. The conversation screen shows NPC dialogue as text automatically.

When TTS is available, a speaker icon will appear in the conversation settings. If it is greyed out, confirm convsim-tts is running on port 7358.

---

## Offline mode

Conversation Simulator is designed to work fully offline after initial setup and model download.

If the home screen shows a network error:

1. **Model not downloaded:** install a model through the model manager while connected to the internet. After that, play is fully offline.
2. **Pack metadata:** packs are bundled with the application and do not require a network connection. If pack loading fails, this is a bug — open a GitHub issue.
3. **Stale browser cache:** a hard reload (`Ctrl+Shift+R` / `Cmd+Shift+R`) clears any stale service worker state.

To verify that play is truly offline, run the built-in smoke test. It ships as the `convsim` CLI (`@convsim/cli`); build it once first if you have not already:

```bash
pnpm --filter @convsim/cli build
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

## The engine keeps running after I quit {#engine-wont-exit}

**Steam still shows Conversation Simulator as running after the window closes**,
or `convsim-core` / `convsim-core.exe` is still in the task list.

Quitting the app shuts the engine down and waits for it, so this should not
happen. If it does:

```bash
# macOS / Linux
pkill -f convsim-core
# The engine stops llama-server and the TTS sidecar on its way out, so normally
# that is all. If it was too wedged to do that, a stray llama-server keeps port
# 7356 — which stops the next launch from loading a model — so clear it too.
# (This also matches a llama-server you started yourself; skip it if you did.)
pkill -f llama-server
```

```powershell
# Windows PowerShell — /T also takes out llama-server and the TTS sidecar
taskkill /IM convsim-core.exe /T /F
```

Nothing is lost by doing this: conversations are written to SQLite as they
happen, and an interrupted model download resumes from where it stopped.

Then please [open an issue](https://github.com/outrightmental/ConversationSimulator/issues)
and attach `app.log` and `runtime.log` from the logs folder (Settings →
**Open logs folder**). A clean shutdown ends `app.log` with
`Launcher closed our stdin pipe; shutting down.` followed by uvicorn's
`Application shutdown complete.` — which of those two lines is missing says
whether the engine never heard the request or heard it and got stuck, and
`runtime.log` says the same for `llama-server`.

---

## Where to get help

- Open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues) for bugs or missing documentation.
- See [install.md](install.md) for installation steps.
- See [quickstart.md](quickstart.md) for first-run instructions.
- See [local-models.md](local-models.md) for model selection and hardware guidance.
