<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Voice setup

Voice is optional. Text always works. When a player wants to speak their
turns and hear the replies, the app installs what that needs itself: one
button, one download, no command line. This page is the reference for that
install: what it fetches, where it puts it, how the app uses it, and what it
does not cover.

The download rules are those of the
[model download policy](model-download-policy.md): nothing is fetched before
the player presses a button on a screen that states the size, the source and
the licence, and no file is used that does not match its pinned SHA-256.

## Where a player finds it

- **Conversation brief.** While voice is not installed, the *Session setup*
  card opens with **Add voice** and an **Install voice** button showing the
  download size. The greyed-out **Push-to-talk voice** and **Hands-free voice
  (VAD)** rows, the **NPC voice (TTS)** note and the **Runtime readiness**
  panel each carry a link that brings that button into view. Pressing one of
  those links starts nothing; only **Install voice** starts the download.
- **Settings → Voice output** (full app). The same card sits above **Voice
  readiness**.

The install runs in the background. The player can keep setting up the
conversation, or start it in text, while it runs. When it finishes, voice
switches on without a restart, and on the brief push-to-talk is selected and
the character's voice is ticked where the scenario supports voice.

The demo edition offers the same install. See
[the demo decision record](steam-next-fest-demo.md#voice-in-the-demo).

## What is installed

About 559 MB in total on Windows x64. Sizes are download sizes.

| Asset | Size | Source | Licence |
|-------|------|--------|---------|
| Speech engine: [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx) 1.13.8, the build for this platform | 20 to 28 MB | GitHub release `v1.13.8` | Apache-2.0. Includes ONNX Runtime (MIT) and eSpeak NG (GPL-3.0-or-later). |
| Listening model: Whisper *base*, multilingual, int8 | 161 MB | Hugging Face `csukuangfj/sherpa-onnx-whisper-base` at commit `bb53ee20…` | MIT |
| Voices: Kokoro v1.0, full precision, with its US and UK English lexicons | 366 MB | Hugging Face `csukuangfj/kokoro-multi-lang-v1_0` at commit `f7b96bb6…` | Apache-2.0 |
| Pronunciation data for the voices: eSpeak NG data | 7 MB | GitHub release `tts-models` of sherpa-onnx | GPL-3.0-or-later |

Every URL, size and SHA-256 is in
`services/convsim-core/convsim_core/voice/catalog.py`, and the card's **What
gets downloaded** lists them before the player presses the button. The Hugging
Face files are pinned to a commit, which cannot change. The engine is pinned
to a versioned release. The eSpeak NG data archive sits under a release tag
its publisher can re-upload to; if that happens its checksum stops matching
and installs fail, loudly, until the pin is updated.

The engine is a separate program that the app downloads from its publisher on
the player's request and runs as its own process. It is not part of the app's
distribution and nothing of it is linked into the app.

Each direction can be installed alone (`components: ["stt"]` or `["tts"]`);
both share the engine, which is downloaded once.

## Where it goes

Under the *voice folder*, `models/voice/` in the app's data folder, beside the
LLM models folder (`CONVSIM_VOICE_DIR` overrides it):

```
<voice folder>/
  engine/   bin/sherpa-onnx-offline[.exe], sherpa-onnx-offline-tts[.exe], libraries
  stt/      base-encoder.int8.onnx, base-decoder.int8.onnx, base-tokens.txt
  tts/      model.onnx, voices.bin, tokens.txt, lexicon-*.txt, espeak-ng-data/
  tmp/      audio in flight; emptied after each request
```

Synthesised sentences are cached as WAV under `cache/tts/` in the data folder.
**Settings → Voice output → Clear TTS cache** empties it.

Each asset folder holds a `.installed.json` marker written last. An asset
counts as installed when the marker names the catalog's current version and
its required files are present, so an interrupted install is never mistaken
for a finished one.

## How an install runs

`POST /api/voice/setup/install` starts a job with one stage per missing asset
and a final check:

1. **Getting the speech engine**, **Downloading the listening model**,
   **Downloading the voices.** Each file is streamed to a `.part` in a staging
   folder, checked for size and SHA-256, and only then kept. The asset is
   assembled in staging and moved into place in one step.
2. **Checking that it works.** The engine is started once. A download that
   verified but cannot run on this machine fails here, in the installer, and
   not later in a silent conversation.

| What happens | Result |
|--------------|--------|
| Network drops | The job fails with `NETWORK`. Verified files and the interrupted `.part` are kept; **Try again** continues from there. |
| A file does not match its checksum | The job fails with `CHECKSUM` and the file is deleted. Nothing is installed from it. |
| The player cancels | The job ends as `cancelled` and the staging folder is removed. Assets that had already finished stay installed. |
| The app closes mid-install | Staged downloads are kept. Pressing **Install voice** again continues. |
| Not enough disk space | The job fails with `DISK` before downloading. |
| No engine build for this kind of computer | The card says so and offers no download. |

Jobs live in memory, not in the database. Nothing about a voice install has
to survive a restart except the files, and those do.

## How the app uses it

Once the files are there, the default speech-to-text and text-to-speech
workers (`whisper_cpp` and `kokoro`, the set-it-up-yourself ones) give way to
`sherpa_whisper` and `sherpa_kokoro`. A worker chosen explicitly with
`CONVSIM_STT_WORKER_ID` or `CONVSIM_TTS_WORKER_ID` is left alone.

The engine is a set of command-line programs. The app runs one short process
per request: about a second to load the model, then the work.

- **Speaking a turn.** The app converts the recording to 16 kHz mono WAV in
  the web view before uploading it (`apps/web/src/lib/wavAudio.ts`), so the
  player needs no ffmpeg. Whisper hears 30 seconds at a time, so a longer
  recording is cut at the quietest moment near each 28-second mark and the
  pieces are transcribed in one engine run. Any Whisper language works; the
  session's language is passed as a hint.
- **Hearing a reply.** Each sentence is synthesised by its own process, up to
  three at a time on a machine with twelve or more cores, two with six or
  more, otherwise one. English uses Kokoro's lexicon (British for the `bf_`
  and `bm_` voices) with eSpeak NG for words it lacks. Spanish, French,
  Italian, Portuguese and Hindi are phonemised by eSpeak NG. In any other
  language the reply stays text, and the brief says so before the
  conversation starts.
- **Playing it.** The reply's words never wait for its audio (issue #533).
  The start and turn responses answer as soon as the words exist and list
  each sentence as pending, with the address it will be spoken from
  (`GET /api/sessions/{id}/speech/{turn}/{index}`). Synthesis runs behind the
  response. A request to a sentence's address waits until that sentence is
  ready, so the conversation screen simply queues the addresses: the first
  sentence is heard as soon as it is synthesised and the rest follow in
  order. A sentence whose synthesis failed answers 404 and is skipped. The
  character's thinking pause is a target, not an addition: what the player
  already waited for the reply is taken off it.

Only the ten approved built-in voices can be used, as before. A pack casts
one for each character in the NPC file (`voice.voice_id`); the brief selects
it, and the player can still change it. The official packs cast every
character their text describes as she or he; a character written as they is
left to the player's default voice. A pack marked `requirements.voice_support:
true` has the character's voice switched on by default once voice is
installed; the five player-facing official packs are marked.

Two engine details are handled in `voice/engine.py`:

- The engine is started in the voice folder and given paths relative to it,
  so the absolute path, which contains the player's user name, never has to
  survive its command line.
- On Windows the engine reads its arguments in the legacy "ANSI" code page
  and then treats them as UTF-8. Curly quotes, dashes and ellipses are
  replaced with their plain forms, and accented text is passed as the string
  whose ANSI encoding is the wanted UTF-8.

## Why engine 1.13.8

The 2.x line removed eSpeak NG. With it went any pronunciation for a word
missing from the Kokoro lexicon: 2.0.1 skips such words without a sound.
"reasons", "noticed", "failures" and "that's" are all missing. 1.13.8 is the
last release that speaks every word, and it is what the catalog pins. A test
(`test_engine_stays_on_the_release_line_that_speaks_every_word`) keeps the pin
from moving to 2.x by accident.

The full-precision Kokoro model is used, not the 114 MB int8 one, because it
synthesised three to five times faster on the same machine.

Measured on the development machine (Windows 11, 32 logical cores, four
threads per process), round-tripping synthesised speech back through Whisper:

| Operation | Time |
|-----------|------|
| Whole install, 559 MB | 85 s |
| Synthesise a 4.4 s sentence (load + synthesis) | 2.1 s |
| Synthesise a one-word reply | 1.1 s |
| The same sentence with the int8 model | 4.4 to 6.3 s |
| Transcribe a 4.7 s recording | 0.9 s |
| Transcribe a 36 s recording (split in two) | 3.0 s |

## Tested where

The install was developed and run by hand on **Windows x64**, in the web UI
and in a PyInstaller build of the core.

On every shipping platform the check is automated: the **Voice smoke**
workflow (`.github/workflows/voice-smoke.yml`) runs `scripts/voice-smoke.py`
on Linux x86_64, macOS on Apple Silicon and Windows x86_64. It installs the
pinned engine and models through the app's own installer, starts the engine,
then round-trips four sentences: each is synthesised with a Kokoro voice,
transcribed with Whisper, and compared word for word with what went in. The
sentences are the ones that have broken before: words missing from the Kokoro
lexicon, curly quotes with an ellipsis, a British voice, and Spanish with its
accents. It runs when the pins or the engine code change, and every Monday,
so a pin that has moved at its source fails there before it fails for a
player.

```bash
python scripts/voice-smoke.py                # full round trip, ~560 MB
python scripts/voice-smoke.py --engine-only  # engine download and start, ~25 MB
```

What no machine checks is a person speaking into a microphone and hearing the
reply in the packaged app. Demo gate D-11 is that check on each platform.

## API

| Request | Purpose |
|---------|---------|
| `GET /api/voice/setup` | What voice needs here, what is installed, the running or most recent job. Downloads nothing. |
| `POST /api/voice/setup/install` | Body `{"components": []}`; empty means everything not ready. Starts a job, or returns the one already running. |
| `GET /api/voice/setup/install/{id}` | Job status and per-stage byte counts. |
| `DELETE /api/voice/setup/install/{id}` | Cancel. 409 once the job has ended. |
| `GET /api/sessions/{id}/speech/{turn}/{index}` | One sentence of a reply as WAV. Waits while the sentence is being synthesised; 404 when there is no audio for it. |

Readiness is reported where it always was: `runtime.stt_ready` and
`runtime.tts_ready` on `GET /api/health`.

## Setting voice up by hand

The earlier routes still work and are what a developer uses to try another
engine: a `whisper-cli` on the PATH with a GGML model
([`runtimes/whisper_cpp`](../runtimes/whisper_cpp/README.md)), and a Kokoro
server on port 7358 ([`runtimes/kokoro`](../runtimes/kokoro/README.md)). An
in-app install takes over from them once it is complete.

## Not covered

- **Removing voice from inside the app.** Delete the voice folder; the app
  falls back to text at the next launch.
- **Spanish-accented voices.** The approved voices are English voices; they
  speak the other supported languages with eSpeak NG phonemes.
- **Silero VAD.** Hands-free turn-taking runs in the web view and needs only
  speech-to-text. The Silero model is used for noise calibration alone and is
  not part of this install.

## Changing a pin

1. Edit `voice/catalog.py`: URL, size and SHA-256 together. Bump the asset's
   `version` so existing installs are replaced.
2. Run `python scripts/voice-smoke.py`: a real install into a scratch folder
   and four round trips.
3. Open the pull request. The Voice smoke workflow repeats step 2 on Linux,
   macOS and Windows. For an engine change, also read the engine's release
   notes for changes to pronunciation.
