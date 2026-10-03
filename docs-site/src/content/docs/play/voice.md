---
title: "Speaking and listening"
description: "Turn on speech-to-text and the NPC voice in Conversation Simulator — what the app installs for you, what it hands you the command for instead, and how to test the result."
sidebar:
  order: 5
verified_against: v0.3.0
---
<!-- SPDX-License-Identifier: CC-BY-4.0 -->

Practising out loud is where the real gains are, so Conversation Simulator can
transcribe what you say and read the NPC's replies aloud. Like everything else
in the app, it runs on your own machine — **no audio ever leaves your
computer**, and nothing here needs an account.

Voice is entirely optional. The app is fully playable in text, and the
conversation screen falls back to typing and on-screen dialogue whenever a
voice component is missing.

---

## Open the setup screen

**Settings → Voice readiness → Set up voice.**

You can also reach it from the **STT** or **TTS** badge on the Home screen,
from the conversation brief when a spoken input mode is greyed out, or from the
"Next time, say it out loud" card the app shows after your first conversation.

The screen lists every piece voice needs, says which you already have, and
gives each gap its own next action. It re-checks itself whenever you switch
back to the app, so anything you install in a terminal appears without a
reload.

---

## What voice is made of

| Feature | What it needs | Optional? |
|---------|---------------|-----------|
| **Speak your turns** | The whisper.cpp program, plus one speech model | Needed for any voice input |
| **Hear the NPC** | The Kokoro voice server | Needed for spoken replies |
| **Hands-free turn-taking** | The voice-activity model, plus `onnxruntime` | Optional — push-to-talk works without it |

The split that matters is between **model files**, which the app downloads and
verifies for you, and **programs**, which it does not. No speech engine
publishes a checksummed download for every platform, so rather than fetch an
unverified binary the app shows you the exact command to install it yourself.

---

## The model files (the app installs these)

Press the download button and the app fetches the recommended set — about
**143 MB** — from the original publishers, checks each file against a known
SHA-256, and only then installs it. Nothing is transferred until you press the
button, and the screen discloses the source URL, licence, exact size, checksum
and destination of every file first.

You can pick a different speech model before downloading:

| Model | Size | Notes |
|-------|------|-------|
| Whisper tiny.en | 74 MB | Fastest; noticeably weaker on accents and background noise |
| **Whisper base.en** | 141 MB | **Recommended** — the balance of accuracy and speed for spoken practice |
| Whisper base (multilingual) | 141 MB | Same size as base.en, every language Whisper supports |
| Whisper small.en | 465 MB | Most accurate; slower, and wants a little more memory |

Downloads show per-file progress and can be cancelled at any time — partial
files are removed. If one fails, the screen offers a retry.

Install more than one model and the picker lets you switch between them;
choosing one you already have re-points the engine without downloading
anything. See
[Model download policy](/trust/model-download-policy/) for the rules every
download in the app follows.

---

## The programs (you install these)

### whisper.cpp — transcribes what you say

Steam builds ship this one, so there is usually nothing to do: the setup screen
finds the bundled copy and the row is already green.

Everywhere else the screen shows the command for your platform and a **Copy**
button:

| Platform | Command |
|----------|---------|
| macOS | `brew install whisper.cpp` |
| Linux | Build from source — the screen shows the full `cmake` line |
| Windows | Build from source — the screen shows the full `cmake` line |

Run it in a terminal, switch back to the app, and the row turns green. If it
does not, press **Check again**.

Homebrew is the only package manager that ships whisper.cpp, so Linux and
Windows build it. Building needs `git`, `cmake` and a C++ compiler, which the
app does not bundle — the setup screen names them under the command so the
first thing you meet is not `git: command not found`. On macOS, Homebrew itself
is the thing you might not have: it is not part of macOS, so if `brew` is
missing the screen says so under the command and points you at
[brew.sh](https://brew.sh) or the source build. The build produces a
self-contained program, so once it has been copied into place you can delete
the cloned source folder.

Both builds put the finished program in the `.convsim/bin` folder inside your
user folder, which the app checks every time it re-reads the plan. On Linux the
command does that copy itself; on Windows the build leaves `whisper-cli.exe` in
`build\bin\Release` and the setup screen asks you to copy it across, because no
single command line can name your user folder in both Command Prompt and
PowerShell. Either way, press **Check again** when the build finishes —
no restart needed.

The Windows command arrives as three separate lines rather than one chained
line, because Windows PowerShell 5.1 — the shell a stock Windows install opens
— has no `&&` operator and would reject the whole thing.

If you would rather not build it, the
[whisper.cpp releases page](https://github.com/ggml-org/whisper.cpp/releases)
has prebuilt `whisper-bin-x64.zip` archives on the `bNNNN` tags — unzip one and
drop `whisper-cli.exe` into the same `.convsim\bin` folder. The app does not
download these for you because they ship without a published checksum.

### The Kokoro voice server — reads the NPC's replies

Steam builds bundle the voice server. If it is installed but not running, the
setup screen offers a **Start the voice server** button and the feature goes
live without leaving the screen.

Everywhere else, the quickest route is the official container image, which the
screen gives you ready to copy:

```sh
docker run --rm -p 7358:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

That command needs [Docker](https://www.docker.com/get-started/). If you do not
have it, the setup screen says so under the command rather than letting you find
out from `docker: command not found` — install Docker and run the command again,
or follow **Other ways to install it** to run the server without a container.

A container puts no `kokoro-server` program on your machine for the app to find,
so once it answers the row reads **already running** rather than claiming the
server is missing. The app did not start it and will not stop it — closing the
container is up to you.

### Two smaller pieces

- **`ffmpeg`** — your browser records WebM/Opus and whisper.cpp reads WAV,
  and `ffmpeg` is what converts one into the other. Nothing can be transcribed
  without it, however complete the rest of the list is, so the setup screen
  gives it its own card with the command for your platform.
- **`onnxruntime`** — only needed for hands-free turn-taking. The packaged
  app does not include it and cannot have it added, so hands-free is a
  source-checkout feature (`pip install onnxruntime` there); the setup screen
  says which case you are in rather than offering a command that cannot work.
  Push-to-talk covers every scenario either way.

---

## Test it before you play

The last row of the speech section is your microphone. The browser has to be
allowed to use it — the setup screen asks once, and nothing is ever recorded
until you hold the talk key in a scenario.

Once the speech model and program are both in place, **Record a test phrase**
runs one real round trip: microphone → decoder → speech model. The screen
repeats back what it heard, so you know the whole chain works before a
conversation depends on it. If it comes back empty or complains, the message
names the likely culprit.

When speech and the NPC voice are both working, the screen says so and points
you at a scenario. Choose **push-to-talk** or **hands-free** on the scenario
setup screen; the NPC voice and its timing are adjustable in Settings at any
time.

---

## If something is still not working

- The setup screen is the first place to look — it reports the live state of
  every component rather than a cached one.
- Microphone greyed out in a conversation? Check your operating system's
  microphone permission for the app, then `ffmpeg`.
- More symptoms and fixes:
  [Voice unavailable](/start/troubleshooting/#voice-ready).
