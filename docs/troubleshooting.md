<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Troubleshooting

Common problems and solutions. If your issue is not listed here, open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues).

Two things help with almost every problem below. The [logs](#logs) say what went wrong, and every error card in the app has a **Copy diagnostics** button that puts the error and the relevant log lines on your clipboard, ready to paste into an issue (see [Copy diagnostics](#copy-diagnostics)).

---

## Engine startup failure

The desktop app starts its background conversation engine (`convsim-core`) when it opens. If that fails, the window shows a recovery card instead of the app. Every card has the same parts: the app's own explanation under the title, a **Logs folder** line with the path on your machine, and **Restart the app**, **Open logs folder**, **Report a problem**, **Copy diagnostics** and a **Troubleshooting guide** link. The title says which problem it is:

- **Another app is using a required port.** A program that is not the conversation engine holds port 7355. Before saying so, the app asks whatever is on the port whether it is a conversation engine and gives it 30 seconds to answer, so an engine that is busy or restarting is not mistaken for an unrelated program. See [Port conflicts](#port-conflicts).
- **Another edition of Conversation Simulator is running.** The demo and the full version share port 7355 and one conversation engine, so they cannot run at the same time. Close the one you are not using, then start the other again. (A dev build of the shell skips this check and uses whichever engine is running.)
- **Conversation Simulator is already running.** You launched a second copy while the first was still starting. Switch to the window that opened. Do **not** close the program holding port 7355: it is the conversation engine that window is using.
- **The conversation engine couldn't be found.** The `convsim-core` executable is missing. Reinstall the app; in a source build, run `./scripts/setup.sh` (the shell looks for `convsim-core` on `PATH` or in the activated virtual environment).
- **The conversation engine keeps stopping.** The engine started, but stopped again after each of three restarts, so the app stopped restarting it. A lighter model often fixes this; see [The conversation engine stopped](#the-conversation-engine-stopped) below.
- **The conversation engine didn't start.** Anything else, including an engine that started but did not answer within 120 seconds. Open the logs folder and read the last lines of `app.log`.

**Recovery steps:**

1. Close other applications that might be using port 7355.
2. Restart Conversation Simulator from Steam or your installation.
3. If the problem persists, click **Copy diagnostics** on the card and paste the report into a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues), or attach `app.log` from the logs folder.

If the Home screen says **The conversation engine is not responding**, the app cannot reach the engine at all. Click **Restart the app**; in a source build, check that `./scripts/dev.sh` is still running.

### The conversation engine stopped

When the engine stops while the app is open, for example because the AI model crashed it or it ran out of memory, the app restarts it itself, up to three times, showing *The conversation engine stopped unexpectedly. Restarting… (attempt 1 of 3)* while it does, then reloads when the replacement is ready. An engine that then runs for five minutes without stopping starts the count again.

A conversation in progress is **not** lost. The flow state, the meters and the transcript are written to the local database as each turn happens, so the replacement engine picks the session up where it stopped and the conversation screen shows your meters and turn count again, and your transcript if transcript saving is on. The one thing that does not survive is the turn that was in flight when the engine stopped: send that message again. After the third failed restart the app stops trying and shows **The conversation engine keeps stopping**.

1. If a restart succeeded, carry on where you left off. Your transcript, packs, models and past sessions are intact.
2. If the problem repeats, try a lighter model: open the model manager (**Settings → AI engine → Open model manager →**) and choose a smaller one. The new model is used after you quit and reopen the app. The demo has one model; close other applications instead.
3. If a model switch never takes effect, even after you quit and reopen the app, the engine that stopped may have left its AI model process (`llama-server`, port 7356) running. Replies keep working, because the new engine reaches that process over the port, but the new engine does not own it and cannot replace it; `app.log` then records `llama-server autostart failed: Port 7356 on 127.0.0.1 is already in use`. Quitting the app does **not** end that process, because it is no longer a child of anything the app owns. End it by hand (see [The engine keeps running after I quit](#the-engine-keeps-running-after-i-quit)) or restart your computer, then start the app again.
4. Check `app.log` in the [logs folder](#logs) for the reason the engine stopped.

---

## Port conflicts

**"Another app is using a required port"**

The desktop app needs port 7355 on 127.0.0.1 for its conversation engine. When it starts, it asks whatever is already on that port for `GET /api/health`. If the answer comes from a Conversation Simulator engine of the same edition, the app uses that engine instead of starting a second one. If nothing answers as an engine within 30 seconds, the app reports *Port 7355 is already in use by another program.* Find that program, close it, and start the app again:

```bash
# macOS / Linux: find and stop the program on the port
lsof -i :7355
kill <PID>
```

```powershell
# Windows PowerShell
Get-NetTCPConnection -LocalPort 7355 | Select-Object OwningProcess
Stop-Process -Id <PID>
```

The app also uses port 7356 for its AI model process (`llama-server`) and 7358 for the voice output server; a build from source serves the web UI on 7354. If another program holds 7356, the engine cannot start the AI model.

A conversation engine left over from an earlier run is not a conflict as long as it still answers: the app uses it. One that is stuck and does not answer is reported as above; see [The engine keeps running after I quit](#the-engine-keeps-running-after-i-quit) to clear it.

**`./scripts/dev.sh` fails with "Port XXXX is already in use by PID YYYY (process-name)"**

The script checks ports 7355 (convsim-core) and 7354 (the web UI) before it starts anything, and names the process holding the port. Stop that process and try again:

```bash
# macOS / Linux: find and stop the blocking process
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

- A previous `./scripts/dev.sh` that was not stopped cleanly: run `pkill -f uvicorn` and `pkill -f vite` to clean up.
- The desktop app, or another copy of convsim-core, already running on 7355.

> Note: the dev scripts use fixed ports; there is no environment variable to change them. Stopping the conflicting process is the workaround.

---

## The engine keeps running after I quit

**Steam still shows Conversation Simulator as running after the window closes**,
or `convsim-core` / `convsim-core.exe` is still in the task list.

Quitting the app asks the conversation engine to shut down and waits for it. Two things can still leave it running: an engine too stuck to stop, and an engine the app found already running when it started and used, which quitting does not stop because the app did not start it. A leftover engine is used by the next launch if it still answers, and reported as a port conflict if it does not. Clear it:

```bash
# macOS / Linux
pkill -f convsim-core
# The engine stops llama-server and the TTS sidecar on its way out, so normally
# that is all. If it was too stuck to do that, a stray llama-server keeps port
# 7356, which stops the next launch from loading a model, so clear it too.
# (This also matches a llama-server you started yourself; skip it if you did.)
pkill -f llama-server
```

```powershell
# Windows PowerShell: /T also takes out llama-server and the TTS sidecar
taskkill /IM convsim-core.exe /T /F
```

Nothing is lost by doing this: conversations are written to SQLite as they happen, and an interrupted model download resumes from where it stopped.

Then please [open an issue](https://github.com/outrightmental/ConversationSimulator/issues) and attach `app.log` and `runtime.log` from the [logs folder](#logs). A clean shutdown ends `app.log` with `Launcher closed our stdin pipe; shutting down.` followed by uvicorn's `Application shutdown complete.` Which of those two lines is missing says whether the engine never heard the request or heard it and got stuck, and `runtime.log` says the same for `llama-server`.

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

The script accepts Node.js 18 or newer, but the locked dependencies need Node.js 20 or newer, and Node 22 or 24 install `better-sqlite3` from a prebuilt binary instead of compiling it (see [install.md](install.md)). Install it from <https://nodejs.org/>, or use a version manager:

```bash
nvm install 24 && nvm use 24
```

**`pip install` fails during setup**

`setup.sh` upgrades pip in `services/convsim-core/.venv` and installs quietly (`-q`), so the error it stops on can be terse. Run the two installs yourself to see the whole message:

```bash
services/convsim-core/.venv/bin/pip install -e packages/prompt-composer
services/convsim-core/.venv/bin/pip install -e "services/convsim-core[dev]"
```

---

## First-run setup problems

**No model is installed yet**

You need a local AI model before conversations can start. On first launch, click **Set me up** on the welcome screen. If you are already past the welcome screen, the **No model configured** section on the Home screen offers **Install a GGUF model →** and **Connect Ollama →**; both open the model manager, where **Install recommended model** downloads the default. You can also reach the model manager from **Settings → AI engine → Open model manager →**. In the demo, the Home screen says **One download and you're in** and offers **Install the demo model →**. See [local-models.md](local-models.md) for hardware requirements and model recommendations.

**Setup did not finish**

If the app closed during first-time setup, it opens on the **Setting up your AI** screen next time and carries on; a model download that was cut off continues from the part already on disk. If you land on the welcome screen instead, click **Set me up** again: an AI engine and a model that are already installed are not downloaded again. If setup stopped with an error, see [Download failures](#download-failures).

---

## Download failures

The **Setting up your AI** screen lists the installation stages: **Getting the AI engine**, **Downloading** followed by the model's name, **Verifying (SHA-256)**, **First launch of the model** and **Preparing scenarios**. When a stage fails, the screen shows a card for the cause, each with **Copy diagnostics**. The engine records a code with each failed download (`NETWORK`, `HTTP`, `CHECKSUM` or `UNKNOWN`), and the screen uses it to recognise a lost connection; a failure recorded before codes existed is recognised from its text:

- **Network connection lost** (`NETWORK`). The connection to the download server failed: it could not connect, timed out, or dropped. Check your internet connection and click **Retry**, which goes back to **Confirm model install**; click **Confirm & install** and the download starts again from the beginning. **Choose a different option** offers an Ollama model or a GGUF file you already have, which need no download. The demo offers **Retry** only.
- **Not enough disk space.** See [Disk space](#disk-space).
- **Model loaded but could not start.** See [Model load failure](#model-load-failure).
- **Any other failure** shows the error itself, with **Try again** and **Choose a different option** (**Try again** only, in the demo). Two you may see:
  - *SHA-256 checksum mismatch. The downloaded file has been deleted.* (`CHECKSUM`) The file that arrived does not match the checksum in the model registry. The app has already downloaded it a second time on its own before showing this. It never uses a file that fails the check. Try again later; if it repeats, open a GitHub issue, because the registry entry may need updating.
  - *The download server answered with HTTP* and a status code (`HTTP`). The server refused the file. Try again later; if it repeats, open a GitHub issue.

In the model manager, a failed install goes back to **Confirm model install** and shows the error there.

---

## AI engine binary

**The AI engine is not installed**

The Steam build ships the AI engine (llama.cpp's `llama-server`) inside the app. A build from source downloads it during setup, as the **Getting the AI engine** stage, into `~/.convsim/bin/`; the stage shows as skipped when the engine is already there. If that download fails, the screen shows the same cards as a model download (see [Download failures](#download-failures)).

When the engine is missing, **Settings → System health → Run system check** lists *AI engine: The AI engine is not installed. It will be set up automatically.*, and choosing a model in **Settings → AI engine** reports *The AI engine isn't installed yet. Use “Set me up” on the Welcome screen to install it.* **Set me up**, and **Install recommended model** in the model manager, both run the **Getting the AI engine** stage.

In a source build you can also fetch the binary by hand with `./runtimes/llama_cpp/download-runtime.sh` (macOS and Linux; it saves to `~/.convsim/bin/` by default, where the engine looks before `PATH`) or `runtimes/llama_cpp/download-runtime.ps1` on Windows.

If the Steam build reports the engine missing, the installation is incomplete. Reinstall the app; if the error persists, open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues) with your platform and OS version.

---

## Disk space

**"Not enough disk space"**

Two checks can stop setup before the model download starts:

- When you click **Set me up**, the app checks the drive that holds the models folder. With less free space than the model's size, setup stops on a **Getting things ready** screen with a **Not enough disk space** card: *The AI model needs 2.5 GB and this disk has … GB free.*
- The download itself needs about 2.2 times the model's size free, room for the partial file and the finished one: about 5.5 GB for the 2.5 GB starter model. With less, the **Setting up your AI** screen shows **Not enough disk space**. The card names the model's size; the check wants the larger figure. The full figures (available, needed and short) are in the report **Copy diagnostics** copies.

To fix it:

1. Free up space on that drive. **Settings → Local folders** shows where the **Models** folder is. Then click **Try again**, or **Set me up** again.
2. Or choose an option that downloads nothing: **Choose a different option** offers an Ollama model you already have or a GGUF file already on disk. On first launch these are also under **Advanced: use Ollama or a local GGUF file** on the welcome screen. The demo has only its own model.

The **Choose another location** button on the **Getting things ready** card opens Settings, which shows the models folder but cannot move it. To keep models on another drive, set `CONVSIM_MODELS_DIR` (see [install.md](install.md#data-locations)).

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

## Data directory

**"Data folder: The app can't write to its data folder."**

Setup checks that it can write to the `data/` folder inside the app's data folder, and stops on a **Getting things ready** screen if it cannot. The card's **Open Settings** button opens Settings, where **Local folders** shows the exact paths. Common causes:

- The folder is owned by another user (for example, created by running the app or a script with `sudo`).
- A permissions change removed write access.

Fix on macOS and Linux by giving your account the whole data folder (see [install.md](install.md#data-locations) for each platform's path):

```bash
# macOS
sudo chown -R "$USER" ~/Library/Application\ Support/com.outrightmental.convsim/
chmod -R u+rwX ~/Library/Application\ Support/com.outrightmental.convsim/

# Linux / Steam Deck
sudo chown -R "$USER" ~/.local/share/com.outrightmental.convsim/
chmod -R u+rwX ~/.local/share/com.outrightmental.convsim/
```

On Windows, make sure your account can write to `%LOCALAPPDATA%\com.outrightmental.convsim\`. convsim-core run without the desktop shell uses a different folder; see [install.md](install.md#data-locations).

**Sessions from an older build are missing**

Older builds kept everything under `~/.convsim/`. On startup, convsim-core copies (never moves) `data/`, `db/`, `packs/`, `logs/`, `exports/`, `cache/` and `crashes/` from there into the new data folder, and writes a `.convsim_migrated_to_platform_dir` marker into `~/.convsim/` when it has. It does this only when the new folder is still empty when it starts. The desktop shell creates `logs/` in the new folder before it starts convsim-core, so in the desktop app the copy does not happen. To bring your old sessions across, quit the app and copy `~/.convsim/db/` over the `db/` folder in the data folder; this replaces whatever the new installation has saved, and the engine upgrades the database when it opens it. Model files are never copied.

Keep `~/.convsim/` until you have checked that your sessions are back. A few things still live there in any case: the AI engine a source build downloads (`bin/`), the voice input and voice activity models (`models/stt/`, `models/vad/`) and the voice synthesis cache (`tts_cache/`); see [install.md](install.md#data-locations).

---

## Model load failure

**"Model loaded but could not start"**

Setup downloaded the model and checked its SHA-256 checksum, in this run or when it first installed it, but the AI engine could not start it. Only a model from the app's own list reaches this card, through a setup-install job (`services/convsim-core/convsim_core/routers/setup_install.py`). A GGUF file you choose yourself fails on its own step instead (see the next heading). Possible causes:

1. **Not enough memory.** The card says this usually means the machine is short on memory for the model. Close other applications and install again: the demo's card has **Try again**, and in the full version **Choose a smaller model** goes back to the options. The starter model, Qwen3 4B Instruct Q4_K_M (2.5 GB, 4 GB of video memory minimum), is the smallest the app installs, so if it does not fit, an Ollama model or a smaller GGUF file is the way out.
2. **The model file changed after it was installed.** Setup checks the checksum only when it downloads. When the model is already installed, setup skips the download and the check and starts the file on disk, so a file damaged or deleted since then fails here. Do not delete a model the app downloaded to make it download again: its install record stays, and setup then skips the download and fails to start the missing file.
3. **An AI engine that will not run.** Setup installs a missing engine in the **Getting the AI engine** stage before this one, so here the engine is present but stopped before it loaded the model. See [AI engine binary](#ai-engine-binary).

`runtime.log` in the [logs folder](#logs) holds the AI engine's own output from its last start, which usually names the reason; **Copy diagnostics** includes that part.

**"SIDECAR_START_FAILED: llama-server exited early" after choosing a GGUF file**

A GGUF file you choose yourself (full version only) does not go through setup's install stages. When you click **Use this file**, the app registers the file (`POST /api/models/register-gguf`) and starts the AI engine on it (`POST /api/sidecar/start`); if the engine is already running, that call answers 409 and nothing is started at this point. If the engine cannot start the file, the error appears under the file path with a **Copy diagnostics** button, for example *SIDECAR_START_FAILED: llama-server exited early (code …). Check log: …* (503). In the model manager it appears on a **Request failed** card. The app does not check a file you choose against a checksum, so a damaged or truncated download fails here: download it again from its source and choose it again. Not enough memory for the model can end the same way. Other messages after **SIDECAR_START_FAILED** name their own cause: *llama-server executable not found in PATH* means the AI engine is not installed (see [AI engine binary](#ai-engine-binary)), *Port 7356 on 127.0.0.1 is already in use* means another program holds the AI model's port (see [Port conflicts](#port-conflicts)), and *llama-server did not become ready within 120.0s* means the engine did not report itself ready in the 120 seconds the app waits for it.

**"The AI engine couldn't start"**

When you choose a model in **Settings → AI engine** and the engine cannot start it, the error reads *The AI engine couldn't start. Restart the app and try again; if it keeps happening, open the logs folder from the Support screen.* The causes above apply, a damaged GGUF file you chose yourself included. The Support screen has no logs button at this release: open the logs folder from **Settings → Local folders** (**Open** beside **Logs**).

**The character keeps saying "I'm not sure what to say right now. Could you repeat that?"**

That is the line the app uses when the model's reply could not be read at all, and `app.log` records *Turn output fell back to safe utterance* for that turn. If it happens often, the model is struggling with the structured replies the app asks for. Use the starter model or a larger one (see [local-models.md](local-models.md#hardware-tiers)).

---

## Low VRAM or slow inference

**A turn takes 30 seconds or more**

The model is most likely running on the processor rather than a graphics card: the machine has no discrete GPU, or the model does not fit in its video memory. Most of the wait then goes to reading the conversation back in before the reply starts. That is expected on such machines, and the app waits for it: a slow turn is not a failed turn. While you wait, the panel under the transcript says what the turn is doing, with the character's name (for example *Dana is thinking…* while the conversation is read and *Dana is replying…* while the words arrive) and, once this machine has timed a turn, when the reply should start. After five seconds it adds *Once this reply arrives, you can shorten the next ones under Reply speed, in Settings.* See [How long a turn will take](performance.md#how-long-a-turn-will-take) for every part of the panel, and [Timeout errors](performance.md#timeout-errors) for the limits that can still end a turn.

What helps, easiest first:

- **Choose Quick replies.** Open **Settings → Reply speed** and choose **Quick replies**. The model writes its reply one piece at a time, so a shorter reply arrives sooner. It takes effect on your next message with nothing to restart, so you can change it mid-conversation. It does not shorten the reading before the reply starts. **Balanced** is the default and matches how the app behaved before this setting existed; **Fuller replies** trades speed for length.
- **Use a smaller model** (full version). The starter model, Qwen3 4B Instruct Q4_K_M (2.5 GB, 4 GB of video memory minimum), is the most practical choice for processor-only or low-memory machines and the smallest the app installs. Anything smaller is a GGUF file you choose yourself (**Settings → AI engine → Open model manager →**, then **Use a local GGUF file**). If the engine is running, the new model is used after you quit and reopen the app. See [Using a custom GGUF model](local-models.md#using-a-custom-gguf-model).
- **Close other applications**, so the engine has the processor and memory to itself. The demo's panel suggests this, because its model is fixed.
- **GPU layers and context length do not help at this release.** **Settings → AI engine** has **Context length** and **GPU layers** fields under **Show advanced engine settings**, but the engine the app starts does not use them: the app passes no `--n-gpu-layers`, so the split between processor and graphics card is the engine's own default, and the context size comes from the model registry. For control over GPU offload, use [Ollama](local-models.md#using-ollama).

**The reply appears all at once instead of word by word**

The character's words reach the screen sentence by sentence over a live connection to the engine, the session socket (`/ws/session/<id>`). Without it the turn still works: the reply appears in one piece when the turn is saved, and the panel falls back to the clock and an estimate from this machine's recent turns, without the stages. The engine accepts the socket only from the desktop app (`tauri://localhost`, `http://tauri.localhost`, `https://tauri.localhost`) and from the development web UI on port 7354 (`http://127.0.0.1:7354` or `http://localhost:7354`), plus clients that send no `Origin` header. A page served from anywhere else is answered with HTTP 403, and `app.log` records `session socket refused: origin … is not a local UI`. If the socket drops, the screen reconnects once. The list lives in `services/convsim-core/convsim_core/origins.py`.

**Not enough memory for the model**

The engine starts each model with one conversation slot, the context size the model registry lists (8 192 tokens for the Qwen3 models, 32 768 for Mistral Small 3.1 24B, and 8 192 for a GGUF file you choose), prompt batches of 256 tokens and a prompt cache of at most 1 GiB. The context size goes on the command line as `--ctx-size`; the rest are passed as `LLAMA_ARG_N_PARALLEL`, `LLAMA_ARG_BATCH` and `LLAMA_ARG_CACHE_RAM`. Any `LLAMA_ARG_*` already set in the environment the app starts with wins, and a `LLAMA_ARG_CTX_SIZE` there keeps `--ctx-size` off the command line. Recommended models by available memory:

| Available VRAM / RAM | Recommendation |
|---|---|
| < 4 GB VRAM, ≥ 8 GB RAM | Qwen3 4B (starter); expect slow turns |
| 4–6 GB VRAM | Qwen3 4B (starter) |
| 6–8 GB VRAM | Qwen3 8B (standard) |
| 10–12 GB VRAM | Qwen3 14B (high-quality) |
| 16+ GB VRAM | Mistral Small 3.1 24B or Qwen3 14B |

The app's screens install only the starter model. The larger ones are files you download yourself and choose as a GGUF file; see [local-models.md](local-models.md#recommended-models).

For Apple Silicon, unified memory acts as VRAM: treat the total RAM figure as available VRAM.

---

## Error messages

An error during a conversation appears on the conversation screen as a **Request failed** card that shows the engine's message after its code, with a **Copy diagnostics** button. The message you sent is taken off the transcript so you can send it again; the session is not ended.

- **TURN_TIMEOUT: The AI engine stopped responding partway through its reply. Your turn was not recorded, so try again. If this keeps happening, choose Quick replies under Reply speed in Settings, or try a smaller model.** (504) The engine sent nothing for 180 seconds (`CONVSIM_LLAMA_CPP_CHAT_TIMEOUT` for the built-in engine) while it was reading or writing. Send the message again. If it keeps happening, follow the message: see [Low VRAM or slow inference](#low-vram-or-slow-inference). The demo's message stops after Reply speed, because its model is fixed.
- **Request timed out** (*The service did not respond in time. It may be busy starting up — wait a moment and try again.*). The screen heard nothing from the engine for 5 minutes, checked every 15 seconds whether the reply had been saved anyway, and gave up 10 minutes after you sent the message. Send it again; if this repeats, the engine is stuck, so restart the app.
- **RUNTIME_UNAVAILABLE: The AI engine is not responding. Check the runtime in Settings, then try the same turn again — it was not recorded.** (503) The conversation engine could not reach the AI model at all: the built-in engine's `llama-server`, or Ollama if you chose it. With Ollama, check that it is running (`ollama list`). With the built-in engine, **Settings → AI engine** shows its status, and quitting and reopening the app starts it again. Then send the message again.
- **TURN_IN_PROGRESS: A reply is already being written for this conversation. Wait for it to arrive before sending another message.** (409) The engine writes one reply at a time per conversation and is still writing the last one, for example because the same conversation is open in a second window. Nothing new is generated. Wait for that reply, then send. A message you type on this screen while the reply is being saved is not refused: it waits and is sent when the turn is saved.

On any screen, a **Request failed** card that reads **VALIDATION_ERROR: Request validation failed —** followed by a field name and a reason (for example `tts_voice_id: Input should be a valid string`) means the engine rejected a request the app built (422). The message names each field it rejected and why, up to five, and never repeats the rejected value; `app.log` records the request's path and the failing fields. This is a bug: click **Copy diagnostics** and paste the report into a GitHub issue.

---

## Voice unavailable

Voice is optional, and text works without it. Voice input uses whisper.cpp and voice output a local Kokoro speech server; the app does not download either of them at this release. **Set up voice** on the debrief screen opens Settings, which shows where voice stands but installs nothing. [`runtimes/whisper_cpp/README.md`](../runtimes/whisper_cpp/README.md) and [`runtimes/kokoro/README.md`](../runtimes/kokoro/README.md) describe the setup. Voice input runs `whisper-cli` as a subprocess, not a server, so nothing listens on a port for it; voice output expects the Kokoro server on port 7358.

Where the app shows that voice is not ready:

- The Home screen's **Voice input** and **Voice output** rows read **Not installed**.
- On the Conversation Brief, **Push-to-talk voice** and **Hands-free voice (VAD)** are marked **STT not loaded** and cannot be chosen, and **NPC voice (TTS)** reads **— not loaded**, with *Text-only is always available. Install a TTS model to enable voice output.*
- **Settings → Voice output** lists **Voice readiness** for the microphone, STT, VAD and TTS, each with what is missing.

If the microphone is the problem, **Voice readiness** shows *permission denied* with *Allow microphone access in your browser or OS settings to use voice input.* See [platform-notes.md](platform-notes.md) for each system's microphone permission. Errors from voice input and output are in `app.log`. The demo has no voice.

---

## Offline mode

Conversation Simulator works fully offline after setup. Only the one-time downloads need the internet: the model, and in a build from source the AI engine. The Home screen's **Network required to play** row reads **No**.

A **Connection failed** card or **The conversation engine is not responding** is about the engine on your own computer, not the internet; see [Engine startup failure](#engine-startup-failure).

Packs are bundled with the app and need no network. If the Home screen says **No scenario packs installed**, click **Restore official packs**. If that fails, it is a bug: open a GitHub issue.

To check that a pack plays with no outbound network access, run the offline smoke test. It ships as the `convsim` CLI (`@convsim/cli`); build it once, together with the pack loader it depends on, then run it with `node`:

```bash
pnpm --filter @convsim/pack-loader build
pnpm --filter @convsim/cli build
node packages/convsim-cli/dist/index.js offline-smoke-test packs/official/job-interview-basic
```

Everything happens inside the CLI's own process. It blocks every outbound TCP connection that process opens to anything other than localhost, loads the pack and plays a short scripted session with the CLI's built-in fake runtime; convsim-core is not contacted. It exits 0 when nothing tried to connect out, and 1 if a connection was blocked (naming the subsystem and address) or the pack failed to load. See [offline-smoke-tests.md](offline-smoke-tests.md) for the test against the live engine.

---

## Logs

The desktop app writes its logs to the `logs/` folder in its data folder. The demo uses the same folder as the full version.

| Platform | Logs folder |
|---|---|
| macOS | `~/Library/Application Support/com.outrightmental.convsim/logs/` |
| Windows | `%LOCALAPPDATA%\com.outrightmental.convsim\logs\` |
| Linux / Steam Deck | `~/.local/share/com.outrightmental.convsim/logs/` (or `$XDG_DATA_HOME/com.outrightmental.convsim/logs/`) |

The startup recovery card shows the exact path and an **Open logs folder** button. Once the app is running, **Settings → Local folders** shows the path beside **Logs**, with **Copy** and **Open**. The **Help** box on the Home screen says `~/.convsim/logs`: that is where a source build run with the development scripts writes, not the desktop app.

- `app.log`: everything convsim-core logs, one JSON object per line. The last lines say what failed and, after you quit, how far the shutdown got.
- `runtime.log`: the AI engine's own output, and the runtime adapters' log lines. Each start begins with a `--- llama-server start` line, followed by the command line it was started with and the `LLAMA_ARG_*` settings it was given.
- `kokoro.log`: the voice output server's output, when convsim-core started one.

`app.log` rotates at 5 MB and keeps three old files. `runtime.log` also receives the engine's raw output through a file handle the rotation does not cap, so it can grow large over long sessions.

**From source:** `./scripts/dev.sh`, `./scripts/dev-desktop.sh` and their `.ps1` versions start convsim-core with `CONVSIM_LOG_DIR` set to `~/.convsim/logs` unless you set it yourself, so logs go there; under `dev-desktop.sh` the recovery card still shows the platform folder above. convsim-core run without the scripts and without the desktop shell writes to `<data folder>/logs`, where the data folder is `CONVSIM_DATA_ROOT` when that is set, and otherwise `~/Library/Application Support/com.outrightmental.convsim/` on macOS, `%LOCALAPPDATA%\outrightmental\convsim\` on Windows and `~/.local/share/convsim/` on Linux.

---

## Copy diagnostics

Every error card has a **Copy diagnostics** button. It copies one report: the error itself (what the card says, with its code and status where it has them, and which screen showed it), followed by an excerpt of the local logs from `GET /api/diag/log-excerpt`: the recent warnings and errors from `app.log`, `runtime.log` since the AI engine last started, and the end of `kokoro.log` when there is one. In the excerpt, paths in your home folder appear as `~`, so your user name is not in it. Nothing is sent anywhere: you paste it into an issue yourself. If the engine cannot be reached within four seconds, the report has the error and a note that the log excerpts were unavailable; attach the files from the [logs folder](#logs) instead.

The button reads **Copied!** when the report is on the clipboard and **Copy failed** if no way of copying worked. In the desktop app it copies through the shell's clipboard plugin first, which is the only way that works in the macOS and Linux builds (their webview has neither `navigator.clipboard` nor a usable `execCommand('copy')` by then); then it tries `navigator.clipboard`, then `execCommand('copy')`. Each fallback is logged to the console with a `[clipboard]` prefix.

The cards on the **Getting things ready** screen have **Details ▸** with a **Copy** button that copies the same kind of report.

---

## Developer debug drawer

The conversation screen includes a collapsible debug drawer for diagnosing model drift or unexpected NPC behaviour. It is never shown during normal play.

**How to enable:**

- **Build-time flag:** set `VITE_DEV_TOOLS=true` in `apps/web/.env.local` before running `pnpm dev`. The drawer appears for all sessions in that build.
- **Per-device toggle:** open **Settings**, click **Show advanced** at the bottom, and turn on **Developer debug mode**. Reload the conversation screen after toggling. The demo has no **Show advanced**.

**What the drawer shows per turn:**

- The raw model JSON payload (the full `npc_opening` / `npc_turn` event payload as returned by the backend).
- The applied state delta committed to tracked NPC state variables for that turn.
- The rejected state delta (red `⊘ rejected` badge): changes the model requested for variables the simulator does not track. These are dropped and never applied, and they are a common model-drift signal.
- An amber `agenda` badge when the payload contains hidden NPC fields (`agenda`, `npc_agenda`, `hidden_state`, `private_notes`, `internal_notes`, `prompt_metadata`).

**Copy JSON:** raw audio fields (`audio`, `audio_data`, `tts_audio`, `raw_audio`) and `secret` fields are removed before copying. A label beside the button says so.

**Security note:** the drawer is not mounted in the page in normal mode, so hidden NPC fields cannot be read through browser developer tools when the setting is off. Disable developer debug mode before sharing your screen or recording a session.

---

## Where to get help

- Open a [GitHub issue](https://github.com/outrightmental/ConversationSimulator/issues) for bugs or missing documentation.
- See [install.md](install.md) for installation steps.
- See [quickstart.md](quickstart.md) for first-run instructions.
- See [local-models.md](local-models.md) for model selection and hardware guidance.
- See [performance.md](performance.md) for what the turn panel shows and the limits on a turn.
