# Performance and Hardware Tiers

ConversationSimulator runs a local LLM, optionally local STT (Whisper) and TTS (Kokoro), all on the same machine as the app. Performance depends heavily on available hardware. The tiers below are **product targets**, not guarantees — actual results vary by model family, driver versions, and system load.

## Hardware tiers

| Tier | Example hardware | Expected NPC first-token latency | Notes |
|------|-----------------|----------------------------------|-------|
| **Fast** | Apple M-series (≥M2), NVIDIA RTX 3060+ | < 1 s | GPU offload enabled; small–medium models |
| **Comfortable** | Older integrated GPU, 6-core CPU | 1–3 s | Reduced GPU layers or CPU-only; small model recommended |
| **Slow** | Low-power CPU, 4 GB RAM | 3–10 s | Text-only recommended; disable VAD and TTS |
| **Unsupported** | < 8 GB RAM total, no GPU | > 10 s or OOM | Cannot run local models reliably |

> **Note:** "Slow" tier is functional but will trigger in-app performance warnings that link to Runtime Settings.

## What the app measures

The app tracks the following timings locally. No data leaves your machine.

| Metric | Description | Warning threshold |
|--------|-------------|-------------------|
| Session start | Time from start request to NPC opening | > 5 s |
| First token | Time from player turn to first streamed NPC token | > 3 s |
| Full response | Time from player turn to complete NPC response | > 10 s |
| STT final | Time for speech-to-text to return a transcript | — |
| TTS first sentence | Time for first audio chunk to be ready | — (captured once TTS sentence streaming lands) |
| Debrief generation | Time for debrief to generate | — |

> **Note:** TTS first-sentence latency is defined in the metrics schema and debug view but is only populated once local TTS sentence streaming is wired into the conversation screen; until then it is omitted rather than shown.

Conversation-screen metrics (session start, first token, full response, STT final) are visible in the **Developer debug** panel; debrief-generation latency is shown on the debrief screen. Both require dev mode (enable it in Settings).

## What to do when the app is slow

The app surfaces actionable warnings when thresholds are exceeded. Each links to **Runtime Settings**.

### NPC response is slow (first token > 3 s)

- **Try a smaller model.** A 4 B-parameter model runs 2–4× faster than an 8 B model on the same hardware. See the Model Manager for size-categorised options.
- **Increase GPU layers.** If you have a GPU, set GPU Layers to `-1` (all layers to GPU) in Runtime Settings.
- **Reduce context length.** Shorter context = faster KV-cache fill. Try 2048 or 4096 instead of the model default.

### Full response is very slow (> 10 s)

All of the above, plus:

- **Switch to push-to-talk.** VAD (hands-free) adds latency before each turn. Push-to-talk removes that overhead.
- **Switch to text-only mode.** Skip STT/TTS entirely for the lowest-latency experience.

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
