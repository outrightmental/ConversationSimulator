<!-- SPDX-License-Identifier: Apache-2.0 -->
# runtimes/whisper_cpp

Integration layer for whisper.cpp — local speech-to-text (STT) runtime.

**Status:** Not yet implemented. Planned in Milestone 3 (local voice input).

This directory will contain:
- Scripts to download platform-specific whisper.cpp binaries and model files
- Configuration helpers for the whisper worker process
- The STT adapter interface implementation

The whisper worker runs internally or at `http://127.0.0.1:7357` in dev mode.

## References

- whisper.cpp: https://github.com/ggml-org/whisper.cpp
- Supports CPU, CUDA, ROCm, Vulkan, and Metal (Apple Silicon)
- Short utterance mode targets 1–3 second transcription latency
