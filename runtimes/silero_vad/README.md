# Silero VAD Runtime

[Silero VAD](https://github.com/snakers4/silero-vad) provides local voice activity detection via an ONNX model. ConversationSimulator uses it for noise calibration in hands-free recording mode.

## What it does

- Analyses a short (≈ 3 s) ambient noise recording to set a silence threshold.
- The threshold is stored in browser `localStorage` — no raw audio is persisted.
- Silence is detected client-side in real-time during hands-free recording using the Web Audio `AnalyserNode`; no audio is streamed to the backend during live capture.

## Setup

**1. Download the ONNX model:**

```bash
runtimes/silero_vad/download-model.sh
```

This places `silero_vad.onnx` in `~/.convsim/models/vad/`.  
Override the path with `CONVSIM_SILERO_VAD_MODEL_PATH`.

**2. Install `onnxruntime`:**

```bash
pip install onnxruntime
# or for GPU acceleration:
pip install onnxruntime-gpu
```

Or install with the project's `vad` extra:

```bash
pip install "convsim-core[vad]"
```

## Audio conversion

Calibration audio from the browser arrives as WebM/Opus or Ogg/Opus. The VAD worker uses `ffmpeg` to convert it to 16 kHz mono PCM before running Silero inference. If `ffmpeg` is not on PATH, the worker still performs energy-based calibration for WAV input; other formats receive a static default threshold.

## Fallback behaviour

If either `onnxruntime` or the model file is absent:

- `GET /api/vad/health` returns `status: "unavailable"` with a setup message.
- `POST /api/vad/calibrate` still returns a usable (energy-based) threshold with `status: "ok"` and a `message` field explaining the fallback.
- The frontend falls back to a fixed energy threshold if the calibration call fails entirely.
- Push-to-talk mode is always available regardless of VAD status.

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `CONVSIM_VAD_WORKER_ID` | `silero_vad` | Worker ID (`silero_vad` or `fake`) |
| `CONVSIM_SILERO_VAD_MODEL_PATH` | `~/.convsim/models/vad/silero_vad.onnx` | Path to the ONNX model |
