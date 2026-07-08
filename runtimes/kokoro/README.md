# Kokoro TTS Runtime

[Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) is a small, open-weight
text-to-speech model. ConversationSimulator uses it to synthesize NPC speech
locally from a **fixed set of built-in synthetic voices**. There is no voice
cloning, voice import, or real-person voice path — see
[Voice policy](#voice-policy) below.

## What it does

- The `kokoro` TTS worker calls a local Kokoro REST server that exposes an
  OpenAI-compatible audio API (`POST /v1/audio/speech`) and a `GET /health`
  endpoint.
- Synthesized WAV files are cached under `~/.convsim/tts_cache/`. The cache key
  is derived from `(voice_id, speed, text)`, so repeated utterances are not
  re-synthesized.
- `GET /api/tts/voices` lists the approved built-in voices; `GET /api/health`
  reports TTS readiness in its `tts` field.

## Setup

**1. Run a local Kokoro server** exposing the OpenAI-compatible speech API
(for example [Kokoro-FastAPI](https://github.com/remsky/Kokoro-FastAPI)) and
bind it to port `7358`:

```bash
# Example: containerized Kokoro-FastAPI on the port ConversationSimulator expects
docker run --rm -p 7358:8880 ghcr.io/remsky/kokoro-fastapi-cpu:latest
```

The worker expects the server to answer:

- `GET  http://127.0.0.1:7358/health`
- `POST http://127.0.0.1:7358/v1/audio/speech` with a JSON body
  `{ "model": "kokoro", "input": ..., "voice": ..., "response_format": "wav", "speed": ... }`

Override the base URL with `CONVSIM_KOKORO_BASE_URL` if you run the server on a
different host or port.

**2. Verify it is reachable:**

```bash
curl http://127.0.0.1:7358/health
```

Once the server is up, `GET /api/health` reports `tts.status: "ready"`.

## Voice policy

Only the ten built-in voices in
`convsim_core/tts/voices.py` (`APPROVED_VOICES`) may be used for synthesis.
`validate_voice_id()` rejects any other id — including cloned, imported, or
real-person voice ids — with a `422` before the backend is ever called. The API
exposes **no** endpoint to upload voice samples or clone voices.

## Fallback behaviour

If the Kokoro server is not running or is unreachable:

- `GET /api/health` returns `tts.status: "unavailable"` with a setup message.
- `POST /api/tts/synthesize` returns `status: "unavailable"` (HTTP `200`, not a
  `5xx`), so the app falls back to text-only playback instead of failing the
  session.

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `CONVSIM_TTS_WORKER_ID` | `kokoro` | Worker ID (`kokoro` or `fake`) |
| `CONVSIM_KOKORO_BASE_URL` | `http://127.0.0.1:7358` | Base URL of the local Kokoro server |
| `CONVSIM_KOKORO_TIMEOUT` | `30.0` | Synthesis request timeout (seconds) |
| `CONVSIM_KOKORO_CACHE_DIR` | `~/.convsim/tts_cache` | Directory for cached WAV output |
