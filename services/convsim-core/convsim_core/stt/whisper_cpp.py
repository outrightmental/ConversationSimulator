# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio
import json
import os
import shutil
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.stt.base import SttWorker
from convsim_core.stt.registry import register_stt
from convsim_core.stt.types import (
    SttError,
    SttHealth,
    SttRequest,
    SttResult,
    SttSegment,
    SttUnavailableError,
)

_DEFAULT_MODEL_PATH = str(Path.home() / ".convsim" / "models" / "stt" / "ggml-base.en.bin")
# Binary name search order — newer releases use "whisper-cli"; older use "main" or "whisper"
_DEFAULT_BINARY_NAMES = ("whisper-cli", "whisper", "main")


class WhisperCppConfig(BaseSettings):
    """Configuration for the whisper.cpp worker.

    All values can be set via CONVSIM_WHISPER_CPP_* environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="CONVSIM_WHISPER_CPP_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    binary_path: str | None = None
    model_path: str = _DEFAULT_MODEL_PATH
    n_threads: int | None = None
    # CPU fallback: set gpu=false (default) to skip GPU-layer flags entirely.
    # Set CONVSIM_WHISPER_CPP_GPU=true to allow GPU acceleration when available.
    gpu: bool = False
    timeout: float = 60.0


def _find_binary(explicit_path: str | None) -> str | None:
    """Return the whisper-cli binary path, or None if not found."""
    if explicit_path:
        return explicit_path if os.path.isfile(explicit_path) else None
    for name in _DEFAULT_BINARY_NAMES:
        found = shutil.which(name)
        if found:
            return found
    return None


@register_stt("whisper_cpp")
class WhisperCppWorker(SttWorker):
    """STT worker that invokes the whisper.cpp CLI binary as a subprocess.

    Audio is written to a temporary file, whisper-cli is called with
    --output-json so segment timestamps and per-token probabilities are
    captured alongside the transcript. The temporary file and JSON sidecar
    are removed after each call, regardless of outcome.

    CPU fallback: GPU flags are omitted by default so the worker runs on CPU
    on any machine. Set CONVSIM_WHISPER_CPP_GPU=true to enable GPU layers.

    When the binary or model is absent the worker raises SttUnavailableError;
    callers (the STT router) convert this to a text-only fallback response
    rather than an HTTP error.
    """

    def __init__(self, config: WhisperCppConfig | None = None) -> None:
        cfg = config or WhisperCppConfig()
        self._binary = _find_binary(cfg.binary_path)
        self._model_path = cfg.model_path
        self._n_threads = cfg.n_threads
        self._gpu = cfg.gpu
        self._timeout = cfg.timeout

    @property
    def id(self) -> str:
        return "whisper_cpp"

    @property
    def display_name(self) -> str:
        return "whisper.cpp (local)"

    def _build_command(self, audio_path: str, language: str | None) -> list[str]:
        """Return the whisper-cli command for the given audio file.

        Raises SttUnavailableError if the binary was not found at init time.
        """
        if self._binary is None:
            raise SttUnavailableError(
                "whisper-cli binary not found. Install whisper.cpp and ensure the "
                "binary is on PATH, or set CONVSIM_WHISPER_CPP_BINARY_PATH."
            )
        cmd: list[str] = [
            self._binary,
            "--model", self._model_path,
            "--file", audio_path,
            "--output-json",
        ]
        if language:
            cmd += ["--language", language]
        if self._n_threads is not None:
            cmd += ["--threads", str(self._n_threads)]
        # Omitting GPU flags (default) gives CPU-only operation; GPU flags are
        # only added when the user has explicitly opted in.
        return cmd

    async def transcribe(self, request: SttRequest) -> SttResult:
        if self._binary is None:
            raise SttUnavailableError(
                "whisper-cli binary not found. See runtimes/whisper_cpp/README.md "
                "for installation instructions."
            )
        if not os.path.isfile(self._model_path):
            raise SttUnavailableError(
                f"STT model not found at {self._model_path!r}. "
                "Download a GGML model to ~/.convsim/models/stt/ or set "
                "CONVSIM_WHISPER_CPP_MODEL_PATH."
            )

        suffix = f".{request.audio_format}" if request.audio_format else ".bin"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(request.audio)
            audio_path = tmp.name

        # whisper-cli --output-json writes a sidecar: {audio_path}.json
        json_path = audio_path + ".json"

        try:
            cmd = self._build_command(audio_path, request.language)
            t0 = time.monotonic()
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout
                )
            except asyncio.TimeoutError as exc:
                proc.kill()
                await proc.wait()
                _try_unlink(json_path)
                raise SttError(
                    f"whisper-cli timed out after {self._timeout}s", recoverable=True
                ) from exc
            processing_ms = (time.monotonic() - t0) * 1000.0
        finally:
            try:
                os.unlink(audio_path)
            except OSError:
                pass

        if proc.returncode != 0:
            _try_unlink(json_path)
            err_text = stderr.decode(errors="replace")[:500]
            raise SttError(
                f"whisper-cli exited with code {proc.returncode}: {err_text}",
                recoverable=True,
            )

        return _read_result(json_path, stdout.decode(errors="replace"), processing_ms)

    async def health(self) -> SttHealth:
        checked_at = datetime.now(timezone.utc).isoformat()

        if self._binary is None:
            return SttHealth(
                worker_id=self.id,
                worker_name=self.display_name,
                status=RuntimeStatus.UNAVAILABLE,
                message=(
                    "whisper-cli binary not found. Install whisper.cpp and ensure the "
                    "binary is on PATH, or set CONVSIM_WHISPER_CPP_BINARY_PATH. "
                    "See runtimes/whisper_cpp/README.md."
                ),
                checked_at=checked_at,
            )

        if not os.path.isfile(self._model_path):
            return SttHealth(
                worker_id=self.id,
                worker_name=self.display_name,
                status=RuntimeStatus.UNAVAILABLE,
                model_path=self._model_path,
                message=(
                    f"STT model not found at {self._model_path!r}. "
                    "Download a GGML model to ~/.convsim/models/stt/ or set "
                    "CONVSIM_WHISPER_CPP_MODEL_PATH."
                ),
                checked_at=checked_at,
            )

        return SttHealth(
            worker_id=self.id,
            worker_name=self.display_name,
            status=RuntimeStatus.READY,
            model_path=self._model_path,
            checked_at=checked_at,
        )


def _try_unlink(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def _read_result(json_path: str, stdout: str, processing_ms: float) -> SttResult:
    """Parse the whisper-cli JSON sidecar, falling back to stdout text."""
    try:
        with open(json_path) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        # OSError: sidecar absent (normal for older binaries).
        # JSONDecodeError: sidecar written but malformed; clean it up so it
        # doesn't accumulate in the temp directory.
        _try_unlink(json_path)
        return SttResult(transcript=stdout.strip(), processing_ms=processing_ms)

    _try_unlink(json_path)
    try:
        return _parse_json_output(data, processing_ms)
    except Exception:
        # Unexpected structure in otherwise-valid JSON (e.g. offset field is a
        # string instead of int): fall back to stdout rather than HTTP 500.
        return SttResult(transcript=stdout.strip(), processing_ms=processing_ms)


def _parse_json_output(data: dict, processing_ms: float) -> SttResult:
    """Convert whisper-cli --output-json payload into an SttResult."""
    segments_raw = data.get("transcription", [])
    segments: list[SttSegment] = []
    full_texts: list[str] = []
    total_confidence = 0.0
    confidence_count = 0

    for seg in segments_raw:
        text = seg.get("text", "").strip()
        if not text:
            continue

        offsets = seg.get("offsets", {})
        start_ms = float(offsets.get("from", 0))
        end_ms = float(offsets.get("to", 0))

        # Confidence: average per-token probability reported by whisper
        tokens = seg.get("tokens", [])
        seg_confidence: float | None = None
        if tokens:
            probs = [t["p"] for t in tokens if "p" in t]
            if probs:
                seg_confidence = sum(probs) / len(probs)
                total_confidence += seg_confidence
                confidence_count += 1

        full_texts.append(text)
        segments.append(
            SttSegment(
                start_ms=start_ms,
                end_ms=end_ms,
                text=text,
                confidence=seg_confidence,
            )
        )

    transcript = " ".join(full_texts)
    duration_ms = segments[-1].end_ms if segments else None
    avg_confidence = total_confidence / confidence_count if confidence_count else None
    detected_language: str | None = data.get("language")

    return SttResult(
        transcript=transcript,
        language=detected_language,
        confidence=avg_confidence,
        duration_ms=duration_ms,
        processing_ms=processing_ms,
        segments=segments if segments else None,
    )
