# Voice smoke tests

End-to-end smoke tests for the local voice pipeline (STT → session turn → TTS).
Covers two paths:

- **English** — `job-interview-basic / behavioral_interview`
- **Non-English** — `language-cafe / spanish_coffee` (Spanish, `es`)

## What is tested

Each path exercises all API-testable stages of the voice flow:

| Stage | What is verified |
|---|---|
| `session_setup` | Session creates, starts, and NPC opening is delivered |
| `stt` | Audio file accepted; transcript returned; language hint preserved |
| `text_correction` | Raw STT output differs from final player text (edit exercised) |
| `turn_loop` | Player turn submitted; NPC responds; no safety stop for benign input |
| `tts` | At least one `tts_audio_chunk` event returned; `cache_path` non-null |
| Text fallback | TTS-disabled sessions still deliver NPC content with no stale audio |

> **Mic capture** and **VAD** are hardware and browser concerns. They cannot be exercised at the HTTP API level. Test them manually using a real microphone and the web UI.

## CI mode (mocked, no binaries)

The default CI run uses `FakeSttWorker` and `FakeTtsWorker`:

```bash
cd services/convsim-core
python -m pytest tests/test_voice_smoke.py -v
```

No `whisper-cli` binary or Kokoro server is needed. Both fake workers:

- Always report `READY` status.
- Return a deterministic transcript for any audio bytes.
- Return a silent WAV file at a temp path for any TTS request.

## Real-runtime mode (local whisper.cpp + Kokoro)

To test the actual model inference path, install the runtimes and point the workers at them.

### 1. Install whisper.cpp (STT)

```bash
# Follow the instructions in runtimes/whisper_cpp/README.md
# then verify the binary is on PATH:
whisper-cli --version

# Download a GGML model:
mkdir -p ~/.convsim/models/stt
curl -L https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin \
  -o ~/.convsim/models/stt/ggml-base.en.bin
```

### 2. Install and start Kokoro (TTS)

```bash
# Follow the instructions in runtimes/kokoro/README.md
# then start the Kokoro server before running tests:
python -m kokoro_server   # or however your install exposes the server
```

### 3. Run voice smoke tests against real workers

```bash
cd services/convsim-core
CONVSIM_STT_WORKER_ID=whisper_cpp \
CONVSIM_TTS_WORKER_ID=kokoro \
python -m pytest tests/test_voice_smoke.py -v
```

### 4. Optional: provide a real audio fixture

The synthetic fixture is a silent WAV with a valid RIFF header. `FakeSttWorker`
ignores audio bytes entirely. With the real `whisper_cpp` worker, silence
produces an empty transcript (or a short noise fragment), which causes the
`text_correction` stage to trivially pass (any non-empty edit differs).

To test full STT accuracy, replace the fixture with a real recording:

```bash
# Record a short WAV (Linux/macOS):
sox -d -r 22050 -c 1 -b 16 /tmp/test_en.wav trim 0 3

# Run the smoke test pointing at the real fixture:
CONVSIM_VOICE_SMOKE_FIXTURE_EN=/tmp/test_en.wav \
CONVSIM_STT_WORKER_ID=whisper_cpp \
python -m pytest tests/test_voice_smoke.py -v -k "English"
```

> The tests use the environment-variable fixture path only when
> `CONVSIM_VOICE_SMOKE_FIXTURE_EN` / `CONVSIM_VOICE_SMOKE_FIXTURE_ES` are set.
> When absent, the built-in silent WAV is used automatically.

## Interpreting failures

Every assertion in `test_voice_smoke.py` starts with a `[stage: X]` label.
Match the label to the table above to isolate the broken component:

| Label | Likely causes |
|---|---|
| `[stage: session_setup]` | Scenario not registered; session DB write failed; pack missing |
| `[stage: stt]` | STT worker unavailable; binary not on PATH; model file missing |
| `[stage: text_correction]` | Fake transcript matches scripted input by accident (implementation issue) |
| `[stage: turn_loop]` | LLM runtime error; safety policy misconfigured; turn state machine issue |
| `[stage: tts]` | Kokoro not running; voice ID rejected; cache directory unwritable |

### Checking worker health

```bash
curl http://127.0.0.1:7355/api/health | python -m json.tool
```

Look at the `stt` and `tts` fields. Status `"unavailable"` means the binary or
server was not found at startup. Status `"ready"` means the worker initialised
successfully.

## Adding new language paths

1. Choose a scenario from the `language-cafe` pack (see `packs/official/language-cafe/scenarios/`).
2. Add a new test class in `test_voice_smoke.py` following the `TestSpanishVoiceSmoke` pattern:
   - Set `_SCENARIO` to the scenario ID.
   - Set `_LANGUAGE` to the BCP-47 language code.
   - Add a scripted player turn constant near the top of the file.
3. Add a smoke fixture YAML in the appropriate pack's `tests/` directory if the scenario is new.

## Test plan checklist

- [ ] `python -m pytest tests/test_voice_smoke.py -v` passes in CI (mocked)
- [ ] `test_full_voice_path` passes for English path
- [ ] `test_full_voice_path` passes for Spanish path
- [ ] Text fallback tests confirm no TTS events when `tts_enabled=False`
- [ ] Manual real-runtime test with `whisper_cpp` + `kokoro` workers (local only)
- [ ] Manual test with microphone input via web UI on push-to-talk mode
