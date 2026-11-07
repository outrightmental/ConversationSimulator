---
title: "Performance & hardware"
description: "Latency budgets, hardware tiers, measured results, and practical steps to speed up Conversation Simulator on your machine."
sidebar:
  order: 2
---

ConversationSimulator runs a local LLM, optionally local STT (Whisper) and TTS (Kokoro), all on the same machine as the app. Performance depends heavily on available hardware. The tiers below are **product targets**, not guarantees — actual results vary by model family, driver versions, and system load.

## Latency budgets

These are the official latency budgets for the **mid-spec reference machine** (Apple M2 / NVIDIA RTX 3060 equivalent). In-app performance warnings fire when a measurement exceeds the corresponding budget. Nightly CI smoke tests flag any regression greater than 20 % against these values.

| Metric | Budget | Condition |
|--------|--------|-----------|
| Cold start → interactive Home | < 10 s | Model already downloaded; startup to playable state |
| Time-to-first-token (TTFT) | < 2.5 s | Starter model (4 B Q4\_K\_M) on recommended-tier hardware |
| TTS first-audio chunk | < 1.5 s | Kokoro sidecar, sentence-level streaming |
| STT round-trip | < 2 s | 10-word utterance, whisper.cpp small model |

All values in the `LATENCY_BUDGETS` constant in [`packages/shared/src/types/metrics.ts`](https://github.com/outrightmental/ConversationSimulator/blob/main/packages/shared/src/types/metrics.ts). They are reference figures only: since issue #539 nothing in the app warns when one is exceeded.

## Hardware tiers

| Tier | Example hardware | Expected NPC first-token latency | Notes |
|------|-----------------|----------------------------------|-------|
| **Fast** | Apple M-series (≥M2), NVIDIA RTX 3060+ | < 1 s | GPU offload enabled; small–medium models |
| **Comfortable** | Older integrated GPU, 6-core CPU | 1–2.5 s | Reduced GPU layers or CPU-only; small model recommended |
| **Slow** | Low-power CPU, 4 GB RAM | 2.5–10 s | Text-only recommended; disable VAD and TTS |
| **Unsupported** | < 8 GB RAM total, no GPU | > 10 s or OOM | Cannot run local models reliably |

> **Note:** the tiers and budgets above are targets, not measurements, and are being replaced by one shared, measured definition (#522). The app shows no tier label; the conversation screen states the pace it measures.

## Results table by hardware tier

Measured with the **starter model** (Qwen3 4B Q4\_K\_M, 2.5 GB, context 8192) using a 30-token scripted turn. All timings in seconds (median of 5 runs). STT and TTS use whisper.cpp small and Kokoro TTS respectively.

| Metric | Fast tier (M2 / RTX 3060) | Comfortable tier (6-core CPU + iGPU) | Slow tier (4-core CPU, no GPU) |
|--------|--------------------------|--------------------------------------|-------------------------------|
| Cold start → Home | ~3 s | ~6 s | ~9 s |
| Time-to-first-token | ~0.8 s | ~1.8 s | ~2.4 s |
| Full response (30 tok) | ~1.5 s | ~3.5 s | ~8 s |
| TTS first audio | ~0.5 s | ~1.0 s | ~1.4 s |
| STT round-trip | ~0.6 s | ~1.2 s | ~1.9 s |

Budget column for reference: TTFT < 2.5 s, TTS < 1.5 s, STT < 2 s, cold start < 10 s. Comfortable and Slow tiers operate within budget on the starter model; high-quality models (14 B+) push into Slow or Unsupported territory on those tiers.

> These results are for the Steam system-requirements reference platform described in [#283](https://github.com/outrightmental/ConversationSimulator/issues/283)'s docs. For players whose hardware matches a tier, the table sets honest download and runtime expectations.

## What the app measures

The app tracks the following timings locally. No data leaves your machine.

| Metric | Description |
|--------|-------------|
| Session start | Time from start request to NPC opening |
| First token | Time from player turn to first streamed NPC token |
| Full response | Time from player turn to complete NPC response |
| STT final | Time for speech-to-text to return a transcript |
| TTS first sentence | Time for first audio chunk to be ready |
| Debrief generation | Time for debrief to generate |

These are shown in the developer debug drawer only. The per-turn timing record
(`turn_timing`, issue #519) is the measured account of each turn: stages, token
counts and speeds.

Conversation-screen metrics (session start, first token, full response, STT final, TTS first sentence) are visible in the **Developer debug** panel; debrief-generation latency is shown on the debrief screen. Both require dev mode (enable it in Settings).

The conversation screen also remembers how long recent turns took, so it can tell the player what to expect from the next one — see [How long a turn will take](#how-long-a-turn-will-take).

## How long a turn will take

While the character is out, the conversation screen shows one panel that says
what the turn is doing, in the fiction and with the character's name, and —
when it has something honest to say — when the reply will start.

| What you see | What it means |
|---|---|
| **Dana is getting ready…** over a hatched bar | The engine has the request but has not started reading (it is loading, or finishing other work). |
| **Dana is thinking…** over a filling bar | The engine is reading the conversation. The bar is the one real fraction a turn has: how much of the prompt has been read, with the part it already had in its cache filled in from the start. |
| **Reply starts in about 5–8 s.** | Time from now, so it counts down with the clock. Shown only while the character is getting ready or thinking, and only when the reply is more than about four seconds away. The range is built from this machine's measured reading and writing speeds and how much is left to read. Without a progress report from the engine (before the first one, or from an engine that sends none) it is this machine's measured time to first words less the time already waited, and once that has passed it is withdrawn rather than promised again. With nothing measured yet there is no number: only the stage, the bar and the clock. |
| **Dana is replying…** | Words are arriving in the transcript, one checked sentence at a time. No estimate: the transcript is the progress. |
| **Updating the scene…** beside the reply box | The whole line is on screen and the engine is finishing the turn's bookkeeping. The reply box already works; a message sent now is queued and goes the moment the turn is saved. |
| **Dana is trying that again…** | The reply failed a check and is being regenerated. No estimate: this second attempt is not streamed, and nothing measured says how long it takes. |
| The clock | Runs for the whole wait, so a long turn never looks like a frozen app. A screen reader hears each stage once, with the estimate as that stage began, and never a new figure per progress report. After 30 s it is told the elapsed time once per half-minute, with the current estimate when there is one, and that the reply is not lost. |
| **Once this reply arrives, you can shorten the next ones under Reply speed, in Settings.** | Added under the bar once a wait passes about five seconds. It is text, not a link: leaving the screen mid-turn loses the pending message when the session resumes, so the setting is named and left for after the reply. The demo adds that closing other apps usually helps, which is the one thing its hardware can do. |

With no live connection to the engine's progress (an older core, or the socket
unavailable), the panel falls back to the previous behaviour: the clock and
the median of up to eight recent whole turns on this machine, with a bar that
never fills completely and plain honesty when the turn outruns the estimate.

Worth knowing about every number the panel quotes:

- **It is measured on this machine or it is not shown.** Reading speed,
  writing speed and time to first words are medians over this machine's
  recent recorded turns (`GET /api/performance/rolling`); the fraction read
  comes from the engine's own progress reports. Nothing comes from the docs
  or a model size.
- **Estimates are ranges**, because a median is not a promise, and each
  end is rounded no finer than a median deserves: to the second under ten
  seconds, to five seconds under a minute, and to the whole minute beyond
  ("Reply starts in about 1–2 min.").
- **They never leave the machine.** The per-turn records live in the local
  session database beside the transcript (see [privacy](privacy.md)); the
  older whole-turn samples sit in browser local storage under
  `convsim.turnTiming`. **Clear all local data** in Settings forgets both.
- **Nothing nags.** The amber "first token took…" rows and the separate
  five-second "taking longer than usual" notice are gone: they named settings
  that did nothing and sent players out of the conversation. What stays is the
  one sentence from that notice that did help, the reply-speed footnote above,
  now part of the panel so that nothing repeats the panel in other words.

## What to do when the app is slow

The conversation screen itself no longer surfaces warnings (see above). If
turns are slow on your hardware, these are the levers:

### NPC response is slow

- **Try a smaller model.** A 4 B-parameter model runs 2–4× faster than an 8 B model on the same hardware. See the Model Manager for size-categorised options.
- **Increase GPU layers.** If you have a GPU, set GPU Layers to `-1` (all layers to GPU) in Runtime Settings.
- **Reduce context length.** Shorter context = faster KV-cache fill. Try 2048 or 4096 instead of the model default.

### Full response is very slow (> 10 s)

All of the above, plus:

- **Switch to push-to-talk.** VAD (hands-free) adds latency before each turn. Push-to-talk removes that overhead.
- **Switch to text-only mode.** Skip STT/TTS entirely for the lowest-latency experience.

### TTS audio is slow (first audio > 1.5 s)

- **Disable TTS.** Uncheck "Enable TTS" in scenario setup. Text is delivered immediately.
- The Kokoro TTS sidecar requires a live connection to the sidecar process. If it is slow, check that the process is running and has sufficient CPU resources.

### STT recognition is slow (round-trip > 2 s)

- **Switch to push-to-talk.** VAD silence detection adds overhead. Push-to-talk avoids it.
- **Switch to text input.** Eliminates STT entirely; type your player turns instead.

### STT unavailable

When whisper.cpp is not running or returns an error, the app falls back to text input automatically. A status indicator appears at the top of the conversation screen.

### TTS unavailable

When Kokoro is not running, the app operates in text-only mode. No audio is played. The scenario plays normally; only the voice output is absent.

### Timeout errors

A slow turn is not a failed turn. A local model on CPU-only hardware can spend a minute or more on a single reply — mostly reading the prompt back in — and the app waits for it. The panel described in [How long a turn will take](#how-long-a-turn-will-take) is on screen for the whole wait; after five seconds it adds where the next replies can be made shorter, and from thirty seconds on a screen reader is told every half-minute that the reply has not been thrown away.

Two separate limits can still end a turn early:

| Limit | Value | What happens |
|-------|-------|--------------|
| Engine went quiet | 180 s with nothing sent (`CONVSIM_LLAMA_CPP_CHAT_TIMEOUT`) — this covers reading the prompt back in as well as the gaps between words | The turn fails with a timeout error. Nothing is recorded, so you can retype the same turn. |
| App gave up waiting | 10 min | From 5 minutes on, the app stops trusting the request and starts asking the session what it actually recorded, every 15 seconds. As soon as the reply has landed it is shown and play continues. If the request itself answers while that is going on — with the reply, or with a failure of its own — that answer is used straight away. Only if nothing has landed by 10 minutes does the turn fail with a timeout error. (A session started with transcript saving off has nothing to ask about, so the app simply keeps waiting on the request until then.) |

The session is **not** ended by either case — you can retry the same turn. The error message includes the same suggestions listed above.

## Turning off features to improve performance

All of the following can be changed without restarting a session:

| Feature | How to disable | Performance impact |
|---------|---------------|-------------------|
| TTS | Uncheck "Enable TTS" in scenario setup | Removes Kokoro synthesis latency |
| VAD | Switch to push-to-talk in scenario setup | Removes silence-detection overhead |
| State meters | Uncheck "Show state meters" in setup | Minor |
| Transcript saving | Uncheck "Save transcript" in setup | Minor |

Runtime Settings (GPU layers, context length, threads, temperature) take effect on the next model load.
