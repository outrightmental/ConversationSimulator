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

All values in the `LATENCY_BUDGETS` constant in [`packages/shared/src/types/metrics.ts`](https://github.com/outrightmental/ConversationSimulator/blob/main/packages/shared/src/types/metrics.ts). PerformanceWarning thresholds are derived from these constants.

## Hardware tiers

| Tier | Example hardware | Expected NPC first-token latency | Notes |
|------|-----------------|----------------------------------|-------|
| **Fast** | Apple M-series (≥M2), NVIDIA RTX 3060+ | < 1 s | GPU offload enabled; small–medium models |
| **Comfortable** | Older integrated GPU, 6-core CPU | 1–2.5 s | Reduced GPU layers or CPU-only; small model recommended |
| **Slow** | Low-power CPU, 4 GB RAM | 2.5–10 s | Text-only recommended; disable VAD and TTS |
| **Unsupported** | < 8 GB RAM total, no GPU | > 10 s or OOM | Cannot run local models reliably |

> **Note:** "Slow" tier is functional but will trigger in-app performance warnings that link to Runtime Settings.

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

| Metric | Description | Warning threshold |
|--------|-------------|-------------------|
| Session start | Time from start request to NPC opening | > 10 s |
| First token | Time from player turn to first streamed NPC token | > 2.5 s |
| Full response | Time from player turn to complete NPC response | > 10 s |
| STT final | Time for speech-to-text to return a transcript | > 2 s |
| TTS first sentence | Time for first audio chunk to be ready | > 1.5 s |
| Debrief generation | Time for debrief to generate | — |

Conversation-screen metrics (session start, first token, full response, STT final, TTS first sentence) are visible in the **Developer debug** panel; debrief-generation latency is shown on the debrief screen. Both require dev mode (enable it in Settings).

## What to do when the app is slow

The app surfaces actionable warnings when thresholds are exceeded. Each links to **Runtime Settings**.

### NPC response is slow (first token > 2.5 s)

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

If the LLM does not produce a response within 60 seconds, the turn fails with a timeout error. The session is **not** ended — you can retry the same turn. The error message includes the same suggestions listed above.

## Turning off features to improve performance

All of the following can be changed without restarting a session:

| Feature | How to disable | Performance impact |
|---------|---------------|-------------------|
| TTS | Uncheck "Enable TTS" in scenario setup | Removes Kokoro synthesis latency |
| VAD | Switch to push-to-talk in scenario setup | Removes silence-detection overhead |
| State meters | Uncheck "Show state meters" in setup | Minor |
| Transcript saving | Uncheck "Save transcript" in setup | Minor |

Runtime Settings (GPU layers, context length, threads, temperature) take effect on the next model load.
