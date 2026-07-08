# SPDX-License-Identifier: Apache-2.0
"""Tests for WhisperCppWorker — command construction and mocked subprocess output."""
import asyncio
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.stt.types import SttError, SttRequest, SttUnavailableError
from convsim_core.stt.whisper_cpp import (
    WhisperCppConfig,
    WhisperCppWorker,
    _find_binary,
    _parse_json_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_BINARY = "/usr/local/bin/whisper-cli"
_FAKE_MODEL = "/home/user/.convsim/models/stt/ggml-base.en.bin"

_SAMPLE_JSON_OUTPUT = {
    "transcription": [
        {
            "text": " Hello, world.",
            "offsets": {"from": 0, "to": 1500},
            "tokens": [
                {"id": 1, "text": " Hello,", "p": 0.95},
                {"id": 2, "text": " world.", "p": 0.88},
            ],
        },
        {
            "text": " How are you?",
            "offsets": {"from": 1500, "to": 3000},
            "tokens": [
                {"id": 3, "text": " How", "p": 0.92},
                {"id": 4, "text": " are", "p": 0.97},
                {"id": 5, "text": " you?", "p": 0.85},
            ],
        },
    ],
    # Modern whisper-cli (ggml-org/whisper.cpp ≥ 1.x) places detected language
    # under result.language — match that format in the canonical fixture.
    "result": {"language": "en"},
}


def _make_worker(binary: str | None = _FAKE_BINARY, model: str = _FAKE_MODEL) -> WhisperCppWorker:
    config = WhisperCppConfig(binary_path=binary, model_path=model, timeout=5.0)
    with patch("convsim_core.stt.whisper_cpp._find_binary", return_value=binary):
        worker = WhisperCppWorker(config)
    worker._binary = binary
    worker._model_path = model
    return worker


# ---------------------------------------------------------------------------
# _find_binary
# ---------------------------------------------------------------------------


def test_find_binary_returns_explicit_path_when_file_exists(tmp_path):
    binary = tmp_path / "whisper-cli"
    binary.touch()
    assert _find_binary(str(binary)) == str(binary)


def test_find_binary_returns_none_for_missing_explicit_path():
    assert _find_binary("/nonexistent/path/whisper-cli") is None


def test_find_binary_returns_none_when_not_on_path():
    with patch("shutil.which", return_value=None):
        assert _find_binary(None) is None


def test_find_binary_searches_path_when_no_explicit_path():
    with patch("shutil.which", side_effect=lambda name: f"/usr/bin/{name}" if name == "whisper-cli" else None):
        result = _find_binary(None)
    assert result == "/usr/bin/whisper-cli"


# ---------------------------------------------------------------------------
# _build_command
# ---------------------------------------------------------------------------


def test_build_command_includes_model(tmp_path):
    worker = _make_worker()
    cmd = worker._build_command("/tmp/audio.wav", None)
    assert "--model" in cmd
    assert _FAKE_MODEL in cmd


def test_build_command_includes_file(tmp_path):
    worker = _make_worker()
    cmd = worker._build_command("/tmp/audio.wav", None)
    assert "--file" in cmd
    assert "/tmp/audio.wav" in cmd


def test_build_command_includes_output_json():
    worker = _make_worker()
    cmd = worker._build_command("/tmp/audio.wav", None)
    assert "--output-json" in cmd


def test_build_command_includes_language_when_provided():
    worker = _make_worker()
    cmd = worker._build_command("/tmp/audio.wav", "fr")
    assert "--language" in cmd
    assert "fr" in cmd


def test_build_command_omits_language_when_none():
    worker = _make_worker()
    cmd = worker._build_command("/tmp/audio.wav", None)
    assert "--language" not in cmd


def test_build_command_includes_threads_when_set():
    worker = WhisperCppWorker.__new__(WhisperCppWorker)
    worker._binary = _FAKE_BINARY
    worker._model_path = _FAKE_MODEL
    worker._n_threads = 4
    worker._timeout = 5.0
    cmd = worker._build_command("/tmp/audio.wav", None)
    assert "--threads" in cmd
    assert "4" in cmd


def test_build_command_raises_when_binary_missing():
    worker = _make_worker(binary=None)
    with pytest.raises(SttUnavailableError):
        worker._build_command("/tmp/audio.wav", None)


# ---------------------------------------------------------------------------
# _parse_json_output
# ---------------------------------------------------------------------------


def test_parse_json_output_extracts_transcript():
    result = _parse_json_output(_SAMPLE_JSON_OUTPUT, processing_ms=250.0)
    assert "Hello, world." in result.transcript
    assert "How are you?" in result.transcript


def test_parse_json_output_detected_language():
    result = _parse_json_output(_SAMPLE_JSON_OUTPUT, processing_ms=0.0)
    assert result.language == "en"


def test_parse_json_output_processing_ms():
    result = _parse_json_output(_SAMPLE_JSON_OUTPUT, processing_ms=123.4)
    assert result.processing_ms == pytest.approx(123.4)


def test_parse_json_output_duration_from_last_segment():
    result = _parse_json_output(_SAMPLE_JSON_OUTPUT, processing_ms=0.0)
    assert result.duration_ms == pytest.approx(3000.0)


def test_parse_json_output_segments_count():
    result = _parse_json_output(_SAMPLE_JSON_OUTPUT, processing_ms=0.0)
    assert result.segments is not None
    assert len(result.segments) == 2


def test_parse_json_output_segment_timestamps():
    result = _parse_json_output(_SAMPLE_JSON_OUTPUT, processing_ms=0.0)
    assert result.segments is not None
    assert result.segments[0].start_ms == 0.0
    assert result.segments[0].end_ms == 1500.0
    assert result.segments[1].start_ms == 1500.0
    assert result.segments[1].end_ms == 3000.0


def test_parse_json_output_confidence_averaged():
    result = _parse_json_output(_SAMPLE_JSON_OUTPUT, processing_ms=0.0)
    assert result.confidence is not None
    assert 0.0 < result.confidence <= 1.0


def test_parse_json_output_empty_transcription():
    result = _parse_json_output({"transcription": []}, processing_ms=0.0)
    assert result.transcript == ""
    assert result.segments is None


def test_parse_json_output_detected_language_top_level_fallback():
    # Some older or custom whisper.cpp builds emit language as a top-level key
    # rather than under result.language — verify both paths work.
    data = {"transcription": [], "language": "fr"}
    result = _parse_json_output(data, processing_ms=0.0)
    assert result.language == "fr"


# ---------------------------------------------------------------------------
# health()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_unavailable_when_binary_missing():
    worker = _make_worker(binary=None)
    h = await worker.health()
    assert h.status == RuntimeStatus.UNAVAILABLE
    assert h.worker_id == "whisper_cpp"
    assert h.message is not None


@pytest.mark.asyncio
async def test_health_unavailable_when_model_missing(tmp_path):
    worker = _make_worker(binary=_FAKE_BINARY, model="/nonexistent/model.bin")
    h = await worker.health()
    assert h.status == RuntimeStatus.UNAVAILABLE
    assert "/nonexistent/model.bin" in (h.message or "")


@pytest.mark.asyncio
async def test_health_ready_when_binary_and_model_exist(tmp_path):
    model_file = tmp_path / "ggml-base.en.bin"
    model_file.write_bytes(b"\x00" * 64)
    worker = _make_worker(binary=_FAKE_BINARY, model=str(model_file))
    with patch("os.path.isfile", return_value=True):
        h = await worker.health()
    assert h.status == RuntimeStatus.READY
    assert h.checked_at


@pytest.mark.asyncio
async def test_health_returns_model_path_when_unavailable(tmp_path):
    missing_model = "/tmp/no-such-model.bin"
    worker = _make_worker(binary=_FAKE_BINARY, model=missing_model)
    h = await worker.health()
    assert h.model_path == missing_model


# ---------------------------------------------------------------------------
# transcribe() — integration test with mocked subprocess
# ---------------------------------------------------------------------------


class _FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int):
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self):
        return self._stdout, self._stderr


def _make_mock_subprocess(json_output: dict, returncode: int = 0):
    """Return a mock for asyncio.create_subprocess_exec that writes a JSON sidecar."""

    async def _fake_exec(*args, stdout=None, stderr=None):
        # The worker writes audio to a temp file and passes it as --file arg.
        # Find the --file argument in the command to know where to write the JSON.
        file_idx = list(args).index("--file") + 1
        audio_path = args[file_idx]
        # whisper-cli strips the audio extension before appending .json:
        # e.g. /tmp/tmpXXX.webm → /tmp/tmpXXX.json (mirrors whisper_cpp.py).
        json_path = os.path.splitext(audio_path)[0] + ".json"
        with open(json_path, "w") as f:
            json.dump(json_output, f)
        return _FakeProcess(b"", b"", returncode)

    return _fake_exec


@pytest.mark.asyncio
async def test_transcribe_returns_result_from_json_sidecar(tmp_path):
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"\x00")

    worker = _make_worker(binary=_FAKE_BINARY, model=str(model_file))

    with patch("os.path.isfile", return_value=True), \
         patch("asyncio.create_subprocess_exec", side_effect=_make_mock_subprocess(_SAMPLE_JSON_OUTPUT)):
        result = await worker.transcribe(
            SttRequest(audio=b"\x00" * 100, audio_format="wav")
        )

    assert "Hello, world." in result.transcript
    assert result.language == "en"
    assert result.segments is not None


@pytest.mark.asyncio
async def test_transcribe_passes_language_to_command(tmp_path):
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"\x00")

    worker = _make_worker(binary=_FAKE_BINARY, model=str(model_file))
    captured_cmd: list[list] = []

    async def _capturing_exec(*args, **kwargs):
        captured_cmd.append(list(args))
        file_idx = list(args).index("--file") + 1
        audio_path = args[file_idx]
        with open(os.path.splitext(audio_path)[0] + ".json", "w") as f:
            json.dump({"transcription": [], "language": "fr"}, f)
        return _FakeProcess(b"", b"", 0)

    with patch("os.path.isfile", return_value=True), \
         patch("asyncio.create_subprocess_exec", side_effect=_capturing_exec):
        await worker.transcribe(
            SttRequest(audio=b"\x00" * 100, audio_format="wav", language="fr")
        )

    cmd = captured_cmd[0]
    assert "--language" in cmd
    lang_idx = cmd.index("--language")
    assert cmd[lang_idx + 1] == "fr"


@pytest.mark.asyncio
async def test_transcribe_raises_unavailable_when_binary_missing():
    worker = _make_worker(binary=None)
    with pytest.raises(SttUnavailableError):
        await worker.transcribe(SttRequest(audio=b"\x00" * 100, audio_format="wav"))


@pytest.mark.asyncio
async def test_transcribe_raises_unavailable_when_model_missing():
    worker = _make_worker(model="/nonexistent/model.bin")
    with pytest.raises(SttUnavailableError):
        await worker.transcribe(SttRequest(audio=b"\x00" * 100, audio_format="wav"))


@pytest.mark.asyncio
async def test_transcribe_raises_stt_error_on_nonzero_returncode(tmp_path):
    """whisper-cli non-zero exit should raise SttError, not crash the request."""
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"\x00")

    worker = _make_worker(binary=_FAKE_BINARY, model=str(model_file))

    async def _failing_exec(*args, stdout=None, stderr=None):
        return _FakeProcess(b"", b"error: bad input", 1)

    with patch("os.path.isfile", return_value=True), \
         patch("asyncio.create_subprocess_exec", side_effect=_failing_exec):
        with pytest.raises(SttError) as exc_info:
            await worker.transcribe(SttRequest(audio=b"\x00" * 100, audio_format="wav"))

    assert exc_info.value.recoverable is True


@pytest.mark.asyncio
async def test_transcribe_falls_back_to_stdout_when_json_sidecar_absent(tmp_path):
    """Older whisper-cli binaries that don't write --output-json: fall back to stdout."""
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"\x00")

    worker = _make_worker(binary=_FAKE_BINARY, model=str(model_file))

    async def _no_sidecar_exec(*args, stdout=None, stderr=None):
        # Deliberately do NOT write a JSON sidecar — simulates older binary.
        return _FakeProcess(b"hello world", b"", 0)

    with patch("os.path.isfile", return_value=True), \
         patch("asyncio.create_subprocess_exec", side_effect=_no_sidecar_exec):
        result = await worker.transcribe(
            SttRequest(audio=b"\x00" * 100, audio_format="wav")
        )

    assert result.transcript == "hello world"
    assert result.segments is None


@pytest.mark.asyncio
async def test_transcribe_raises_stt_error_when_exec_raises_os_error(tmp_path):
    """PermissionError / FileNotFoundError from exec must surface as SttError, not 500."""
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"\x00")

    worker = _make_worker(binary=_FAKE_BINARY, model=str(model_file))

    with patch("os.path.isfile", return_value=True), \
         patch("asyncio.create_subprocess_exec", side_effect=PermissionError("not executable")):
        with pytest.raises(SttError) as exc_info:
            await worker.transcribe(SttRequest(audio=b"\x00" * 100, audio_format="wav"))

    assert exc_info.value.recoverable is True


@pytest.mark.asyncio
async def test_transcribe_raises_stt_error_on_timeout(tmp_path):
    """Subprocess timeout should kill the process and raise a recoverable SttError."""
    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"\x00")

    worker = _make_worker(binary=_FAKE_BINARY, model=str(model_file))

    class _SlowProcess:
        # Non-coroutine return is fine: asyncio.wait_for is patched to raise
        # before it awaits anything, so no "coroutine never awaited" warning.
        def communicate(self):
            return MagicMock()

        def kill(self) -> None:
            pass

        async def wait(self) -> None:
            pass

    async def _slow_exec(*args, **kwargs):
        return _SlowProcess()

    with patch("os.path.isfile", return_value=True), \
         patch("asyncio.create_subprocess_exec", side_effect=_slow_exec), \
         patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        with pytest.raises(SttError) as exc_info:
            await worker.transcribe(SttRequest(audio=b"\x00" * 100, audio_format="wav"))

    assert "timed out" in str(exc_info.value)
    assert exc_info.value.recoverable is True
