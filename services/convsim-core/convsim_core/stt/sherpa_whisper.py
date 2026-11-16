# SPDX-License-Identifier: Apache-2.0
"""Speech-to-text through the installed voice engine (Whisper base).

This is the worker a one-click voice install switches on. It needs nothing
the player has to set up: the engine and the model are the ones the app
downloaded (see :mod:`convsim_core.voice`).

Two properties of the engine shape this file:

* It reads WAV only. The app's own client converts a recording to WAV before
  uploading it; anything else is converted with ``ffmpeg`` when that happens
  to be installed and refused with a clear message when it is not.
* Whisper hears thirty seconds at a time and the engine discards the rest. A
  longer recording is cut at the quietest moment near each boundary and the
  pieces are transcribed in one engine run.
"""
from __future__ import annotations

import array
import asyncio
import io
import json
import logging
import shutil
import subprocess
import sys
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from convsim_core.runtime.procflags import CREATE_NO_WINDOW
from convsim_core.runtime.types import RuntimeStatus
from convsim_core.stt.base import SttWorker
from convsim_core.stt.registry import register_stt
from convsim_core.stt.types import (
    SttError,
    SttHealth,
    SttRequest,
    SttResult,
    SttUnavailableError,
)
from convsim_core.voice import catalog
from convsim_core.voice.engine import (
    EngineError,
    default_threads,
    failure_detail,
    run_engine,
)
from convsim_core.voice.layout import VoiceLayout

logger = logging.getLogger(__name__)

# Whisper's window is 30 s. Pieces are kept a little under it.
_MAX_PIECE_SECONDS = 28.0
# How far back from a boundary to look for a quiet moment to cut at.
_CUT_SEARCH_SECONDS = 6.0
_CUT_BLOCK_SECONDS = 0.1

# The languages Whisper can be told to expect. Anything else is left for it
# to detect, because an unknown code makes the engine refuse the request.
_WHISPER_LANGUAGES = frozenset(
    "en zh de es ru ko fr ja pt tr pl ca nl ar sv it id hi fi vi he uk el ms cs ro da hu ta no "
    "th ur hr bg lt la mi ml cy sk te fa lv bn sr az sl kn et mk br eu is hy ne mn bs kk sq sw "
    "gl mr pa si km sn yo so af oc ka be tg sd gu am yi lo uz fo ht ps tk nn mt sa lb my bo tl "
    "mg as tt haw ln ha ba jw su yue".split()
)

_NOT_INSTALLED = (
    "Voice input is not installed. Choose Install voice on the conversation brief "
    "to download it."
)


def whisper_language(language: Optional[str]) -> str:
    """The Whisper language code for a session language, or "" to auto-detect."""
    if not language:
        return ""
    primary = language.strip().lower().replace("_", "-").split("-")[0]
    return primary if primary in _WHISPER_LANGUAGES else ""


def is_wav(data: bytes) -> bool:
    return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE"


def _quietest_cut(samples: "array.array[int]", start: int, end: int, block: int) -> int:
    """Index in [start, end) where the quietest *block* of samples begins."""
    best_index = end - block
    best_energy: Optional[float] = None
    index = start
    while index + block <= end:
        energy = 0.0
        for value in samples[index : index + block]:
            energy += value * value
        if best_energy is None or energy < best_energy:
            best_energy = energy
            best_index = index
        index += block
    # Cut in the middle of the quiet block, not at its edge.
    return best_index + block // 2


def split_wav(data: bytes) -> list[bytes]:
    """Split a WAV into pieces Whisper can hear whole.

    A recording that already fits, or that this code cannot read (not PCM),
    is returned unchanged as a single piece: the engine has its own reader
    and will accept or refuse it itself.
    """
    try:
        with wave.open(io.BytesIO(data)) as reader:
            channels = reader.getnchannels()
            width = reader.getsampwidth()
            rate = reader.getframerate()
            frame_count = reader.getnframes()
            frames = reader.readframes(frame_count)
    except (wave.Error, EOFError, OSError):
        return [data]

    if rate <= 0 or frame_count / rate <= _MAX_PIECE_SECONDS + 1.0:
        return [data]

    frame_bytes = channels * width
    max_frames = int(_MAX_PIECE_SECONDS * rate)
    search_frames = int(_CUT_SEARCH_SECONDS * rate)
    block_frames = max(1, int(_CUT_BLOCK_SECONDS * rate))

    # Loudness is read from the first channel of 16-bit audio, which is what
    # the app's client sends. Other widths are cut at fixed intervals.
    mono: Optional["array.array[int]"] = None
    if width == 2:
        all_samples = array.array("h")
        all_samples.frombytes(frames[: frame_count * frame_bytes])
        if sys.byteorder == "big":
            all_samples.byteswap()
        mono = all_samples[::channels] if channels > 1 else all_samples

    cuts: list[int] = [0]
    position = 0
    while frame_count - position > max_frames:
        boundary = position + max_frames
        if mono is not None:
            boundary = _quietest_cut(mono, boundary - search_frames, boundary, block_frames)
        cuts.append(boundary)
        position = boundary
    cuts.append(frame_count)

    pieces: list[bytes] = []
    for begin, finish in zip(cuts, cuts[1:]):
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as writer:
            writer.setnchannels(channels)
            writer.setsampwidth(width)
            writer.setframerate(rate)
            writer.writeframes(frames[begin * frame_bytes : finish * frame_bytes])
        pieces.append(buffer.getvalue())
    return pieces


def _wav_duration_ms(data: bytes) -> Optional[float]:
    try:
        with wave.open(io.BytesIO(data)) as reader:
            rate = reader.getframerate()
            return reader.getnframes() / rate * 1000.0 if rate > 0 else None
    except (wave.Error, EOFError, OSError):
        return None


def _ffmpeg_to_wav(data: bytes, audio_format: str, work_dir: Path) -> Optional[bytes]:
    """Convert a recording to 16 kHz mono WAV with ffmpeg, if it is installed."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        return None
    stem = uuid.uuid4().hex
    source = work_dir / f"{stem}.{audio_format or 'bin'}"
    target = work_dir / f"{stem}.wav"
    try:
        source.write_bytes(data)
        result = subprocess.run(
            [ffmpeg, "-y", "-i", str(source), "-ar", "16000", "-ac", "1", "-f", "wav", str(target)],
            capture_output=True,
            timeout=60.0,
            creationflags=CREATE_NO_WINDOW,
        )
        if result.returncode != 0 or not target.is_file():
            return None
        return target.read_bytes()
    except (OSError, subprocess.TimeoutExpired):
        return None
    finally:
        source.unlink(missing_ok=True)
        target.unlink(missing_ok=True)


def parse_engine_transcripts(output: str) -> list[dict]:
    """The JSON result objects the engine prints, one per audio file, in order."""
    results: list[dict] = []
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict) and "text" in parsed:
            results.append(parsed)
    return results


@register_stt("sherpa_whisper")
class SherpaWhisperWorker(SttWorker):
    """Whisper base, run by the installed voice engine."""

    def __init__(self, voice_dir: str | Path | None = None, *, timeout: float = 60.0) -> None:
        if voice_dir is None:
            from convsim_core.config import ServiceConfig

            voice_dir = ServiceConfig().voice_dir
        self._layout = VoiceLayout(voice_dir)
        self._timeout = timeout

    @property
    def id(self) -> str:
        return "sherpa_whisper"

    @property
    def display_name(self) -> str:
        return "Whisper base (built-in voice)"

    async def transcribe(self, request: SttRequest) -> SttResult:
        layout = self._layout
        if not layout.stt_installed():
            raise SttUnavailableError(_NOT_INSTALLED)

        work_dir = layout.tmp_dir
        work_dir.mkdir(parents=True, exist_ok=True)

        audio = request.audio
        if not is_wav(audio):
            converted = await asyncio.to_thread(
                _ffmpeg_to_wav, audio, request.audio_format, work_dir
            )
            if converted is None:
                raise SttError(
                    "This recording is not WAV audio and could not be converted "
                    f"(format: {request.audio_format or 'unknown'}). The app records "
                    "WAV itself; another client needs ffmpeg installed.",
                    recoverable=True,
                )
            audio = converted

        pieces = await asyncio.to_thread(split_wav, audio)
        stem = uuid.uuid4().hex
        names = [f"{stem}-{index:02d}.wav" for index in range(len(pieces))]
        asset = catalog.WHISPER_ASSET
        args = [
            f"--whisper-encoder={asset.install_dir}/base-encoder.int8.onnx",
            f"--whisper-decoder={asset.install_dir}/base-decoder.int8.onnx",
            f"--tokens={asset.install_dir}/base-tokens.txt",
            "--whisper-task=transcribe",
            f"--whisper-language={whisper_language(request.language)}",
            f"--num-threads={default_threads()}",
            *[f"{work_dir.name}/{name}" for name in names],
        ]

        started = time.monotonic()
        try:
            for name, piece in zip(names, pieces):
                (work_dir / name).write_bytes(piece)
            try:
                result = await run_engine(
                    layout, catalog.ENGINE_STT_PROGRAM, args, timeout=self._timeout
                )
            except EngineError as exc:
                raise SttError(str(exc), recoverable=True) from exc
        finally:
            for name in names:
                (work_dir / name).unlink(missing_ok=True)
        processing_ms = (time.monotonic() - started) * 1000.0

        transcripts = parse_engine_transcripts(result.stdout + "\n" + result.stderr)
        if result.returncode != 0 or not transcripts:
            raise SttError(
                f"The speech engine could not transcribe the recording ({failure_detail(result)}).",
                recoverable=True,
            )
        if len(transcripts) != len(pieces):
            logger.warning(
                "sherpa_whisper: %d audio pieces but %d transcripts", len(pieces), len(transcripts)
            )

        text = " ".join(str(t.get("text", "")).strip() for t in transcripts)
        language = next((t.get("lang") for t in transcripts if t.get("lang")), None)
        return SttResult(
            transcript=" ".join(text.split()),
            language=language if isinstance(language, str) else None,
            duration_ms=_wav_duration_ms(audio),
            processing_ms=processing_ms,
        )

    async def health(self) -> SttHealth:
        checked_at = datetime.now(timezone.utc).isoformat()
        layout = self._layout
        if layout.stt_installed():
            return SttHealth(
                worker_id=self.id,
                worker_name=self.display_name,
                status=RuntimeStatus.READY,
                model_path=str(layout.asset_dir(catalog.WHISPER_ASSET)),
                checked_at=checked_at,
            )
        return SttHealth(
            worker_id=self.id,
            worker_name=self.display_name,
            status=RuntimeStatus.UNAVAILABLE,
            message=_NOT_INSTALLED,
            checked_at=checked_at,
        )
