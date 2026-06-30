<!-- SPDX-License-Identifier: Apache-2.0 -->
# runtimes/whisper_cpp

Integration layer for [whisper.cpp](https://github.com/ggml-org/whisper.cpp) — local speech-to-text (STT).

Audio recorded via push-to-talk is transcribed on-device. No audio is sent to remote services.

## Quick start

```sh
bash runtimes/whisper_cpp/download-runtime.sh
```

The script downloads a pre-built whisper.cpp binary and the `ggml-base.en` model into `~/.convsim/models/stt/`.

### Manual install

1. **Build or download the binary**

   Follow the whisper.cpp build instructions for your platform:
   ```sh
   git clone https://github.com/ggml-org/whisper.cpp
   cd whisper.cpp
   cmake -B build && cmake --build build --config Release
   # or on Apple Silicon:
   cmake -B build -DWHISPER_METAL=ON && cmake --build build --config Release
   ```
   Copy the resulting `whisper-cli` (or `main` in older releases) to somewhere on `PATH`, e.g. `/usr/local/bin/`.

2. **Download a model**

   ```sh
   mkdir -p ~/.convsim/models/stt
   # Example: base English model (~142 MB)
   curl -L -o ~/.convsim/models/stt/ggml-base.en.bin \
     https://huggingface.co/ggml-org/whisper.cpp/resolve/main/ggml-base.en.bin
   ```

   Available models (smallest to largest): `tiny.en`, `base.en`, `small.en`, `medium.en`, `large-v3`  
   Larger models are more accurate but slower. `base.en` is a good default.

3. **Verify**

   ```sh
   whisper-cli --version
   # or
   whisper-cli --help
   ```

## Configuration

All settings are read from `CONVSIM_WHISPER_CPP_*` environment variables or a `.env` file.

| Variable | Default | Description |
|---|---|---|
| `CONVSIM_WHISPER_CPP_BINARY_PATH` | auto-detect from PATH | Explicit path to `whisper-cli` binary |
| `CONVSIM_WHISPER_CPP_MODEL_PATH` | `~/.convsim/models/stt/ggml-base.en.bin` | Path to GGML model file |
| `CONVSIM_WHISPER_CPP_N_THREADS` | (auto) | CPU threads for inference |
| `CONVSIM_WHISPER_CPP_GPU` | `false` | Enable GPU acceleration (requires GPU build) |
| `CONVSIM_WHISPER_CPP_TIMEOUT` | `60.0` | Max seconds to wait for transcription |

The STT worker is also selected via:

| Variable | Default | Description |
|---|---|---|
| `CONVSIM_STT_WORKER_ID` | `whisper_cpp` | Worker backend: `whisper_cpp` or `fake` |

## Hardware support

| Platform | Backend | Notes |
|---|---|---|
| Any CPU | CPU (default) | Works out-of-the-box; slowest |
| NVIDIA | CUDA | Build with `-DWHISPER_CUDA=ON` |
| AMD | ROCm / hipBLAS | Build with `-DWHISPER_HIPBLAS=ON` |
| Intel ARC | SYCL | Build with `-DWHISPER_SYCL=ON` |
| Apple Silicon | Metal | Build with `-DWHISPER_METAL=ON` |
| Vulkan (any GPU) | Vulkan | Build with `-DWHISPER_VULKAN=ON` |

When `CONVSIM_WHISPER_CPP_GPU=false` (the default) GPU flags are omitted from the
command, giving CPU-only operation on any machine.

## Fallback behaviour

When the binary or model is absent:
- `GET /api/health` returns `stt.status = "unavailable"` with an explanatory message.
- `POST /api/stt/upload` returns `{ "status": "unavailable", "transcript": null }`.
- The app continues in text-only mode — no crash, no HTTP error.

## Audio format

The browser records audio as WebM/Opus. whisper.cpp natively reads WAV/PCM.
For full format support, install [ffmpeg](https://ffmpeg.org/) and ensure it is on `PATH`.
Without ffmpeg, the binary may reject non-WAV input; the worker surfaces this as a
recoverable `SttError` and the app falls back to text input.

## References

- whisper.cpp source: <https://github.com/ggml-org/whisper.cpp>
- GGML model hub: <https://huggingface.co/ggml-org/whisper.cpp>
- OpenAI Whisper paper: <https://arxiv.org/abs/2212.04356>
