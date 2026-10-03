# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import asyncio

from convsim_core.runtime.procflags import CREATE_NO_WINDOW
import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from convsim_core.runtime.toolpath import find_tool
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

logger = logging.getLogger(__name__)

_DEFAULT_MODEL_PATH = str(Path.home() / ".convsim" / "models" / "stt" / "ggml-base.en.bin")
# Binary name search order — newer releases use "whisper-cli"; older use "whisper".
# "main" is intentionally excluded: it is a common name for compiled C/Go programs
# and would cause the PATH lookup to pick up an unrelated binary on developer machines.
_DEFAULT_BINARY_NAMES = ("whisper-cli", "whisper")
# Steam depot builds ship whisper-cli inside the bundled runtimes/ directory and
# tell the backend where it is through this variable rather than touching PATH
# (publishing/STEAM_DEPOT_CONTENTS.md, docs/sidecar-bundling.md).
_BUNDLED_RUNTIME_DIR_ENV_VAR = "CONVSIM_BUNDLED_RUNTIME_DIR"
# Per-user install directory, the same one llama-server resolves from. Resolved
# per lookup rather than at import so a redirected HOME is honoured.
_USER_BIN_SUBPATH = (".convsim", "bin")


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
    timeout: float = 60.0


def _executable(candidate: Path) -> str | None:
    """Return *candidate* as a string when it is an executable file, else None."""
    return str(candidate) if candidate.is_file() and os.access(candidate, os.X_OK) else None


# whisper-cli decodes its input with miniaudio — WAV, FLAC, MP3 and Ogg Vorbis
# — and only falls back to ffmpeg when it was compiled with WHISPER_FFMPEG.
# Neither Homebrew's formula nor the source builds the guided setup flow hands
# out enable that, so for every install this app walks a player through,
# whisper-cli has no ffmpeg in it.
#
# The browser records WebM/Opus (Safari: MP4/AAC), neither of which miniaudio
# can read, so handing the recording over untouched gets "failed to read audio
# data" and a non-zero exit on every utterance. The transcode happens here
# instead, which is also what makes the setup screen's ffmpeg row true: ffmpeg
# really is the piece that lets a browser recording reach the speech model.
_WHISPER_SAMPLE_RATE = 16_000
# Only WAV is passed through. MP3/FLAC/Ogg are decodable by miniaudio in
# principle, but "ogg" covers Opus as well as Vorbis and the container alone
# does not say which, so transcoding everything but WAV keeps one predictable
# path rather than one that works for some recordings.
_PASSTHROUGH_AUDIO_FORMATS = frozenset({"wav"})


def _ffmpeg_path() -> str | None:
    """Return the resolved ffmpeg path, or None when it cannot be found.

    One hook for all three callers below, so ``health`` can never report a
    state ``transcribe`` would then contradict — and so tests can pin either
    answer instead of inheriting whatever the machine happens to have
    installed. Resolution goes through ``find_tool`` rather than ``PATH``
    alone: a Finder- or Steam-launched macOS build inherits launchd's minimal
    ``PATH``, which omits Homebrew's bin directory, and ``brew install ffmpeg``
    is the command this very worker's health message sends the player to run.

    The *path* rather than a bool, because ``_transcode_to_wav`` has to spawn
    it, and spawning the bare name would go straight back to the ``PATH`` this
    lookup exists to work around.
    """
    return find_tool("ffmpeg")


_FFMPEG_MISSING_MESSAGE = (
    "ffmpeg was not found, and it is needed to decode the "
    "{fmt} audio your browser records into the WAV whisper.cpp reads. "
    "Install ffmpeg (the voice setup screen shows the command for this "
    "platform) and try again."
)


async def _transcode_to_wav(source_path: str, audio_format: str, timeout: float) -> str:
    """Transcode *source_path* to 16 kHz mono 16-bit WAV and return the new path.

    Raises ``SttUnavailableError`` when ffmpeg is absent — a missing piece the
    player can install, which the setup screen offers a row for — and a
    recoverable ``SttError`` when ffmpeg is present but cannot read the file.

    Output goes to a file rather than a pipe on purpose: a WAV header carries
    the data length up front, so ffmpeg writing to a non-seekable stream has to
    leave that field unset, and the decoder on the other side is then reading a
    length it cannot trust.
    """
    ffmpeg = _ffmpeg_path()
    if ffmpeg is None:
        raise SttUnavailableError(_FFMPEG_MISSING_MESSAGE.format(fmt=audio_format or "recorded"))

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        wav_path = tmp.name

    try:
        proc = await asyncio.create_subprocess_exec(
            ffmpeg, "-y",
            "-i", source_path,
            "-ar", str(_WHISPER_SAMPLE_RATE),
            "-ac", "1",
            "-c:a", "pcm_s16le",
            wav_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
            creationflags=CREATE_NO_WINDOW,
        )
    except OSError as exc:
        _try_unlink(wav_path)
        raise SttError(f"Failed to start ffmpeg: {exc}", recoverable=True) from exc

    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        try:
            proc.kill()
        except OSError:
            pass
        await proc.wait()
        _try_unlink(wav_path)
        raise SttError(f"ffmpeg timed out after {timeout}s", recoverable=True) from exc
    except BaseException:
        # Includes task cancellation: never leave the temp file behind.
        _try_unlink(wav_path)
        raise

    if proc.returncode != 0:
        detail = stderr.decode(errors="replace")[-500:]
        _try_unlink(wav_path)
        raise SttError(
            f"ffmpeg could not decode the {audio_format or 'recorded'} audio "
            f"(exit {proc.returncode}): {detail}",
            recoverable=True,
        )

    return wav_path


def _find_binary(explicit_path: str | None) -> str | None:
    """Return the whisper-cli binary path, or None if not found.

    Resolution order (first hit wins), matching the three-step sidecar
    convention in docs/sidecar-bundling.md that llama-server and the Kokoro
    server already follow:

    1. ``CONVSIM_WHISPER_CPP_BINARY_PATH`` — explicit override.
    2. ``<CONVSIM_BUNDLED_RUNTIME_DIR>/whisper-cli[.exe]`` — Steam depot
       builds. The depot ships the binary and hands the backend that variable
       instead of editing PATH, so a PATH-only lookup reports speech-to-text
       missing on the one platform that bundles it — and the guided setup flow
       then tells those players to build whisper.cpp from source.
    3. ``~/.convsim/bin/whisper-cli[.exe]`` — the per-user install directory.
       Re-resolved on every health check, so dropping the binary there takes
       effect without a PATH edit or an app restart.
    4. PATH lookup — package managers and developer builds.
    """
    if explicit_path:
        return explicit_path if os.path.isfile(explicit_path) and os.access(explicit_path, os.X_OK) else None

    suffix = ".exe" if sys.platform == "win32" else ""
    search_dirs: list[Path] = []
    bundled_dir = os.environ.get(_BUNDLED_RUNTIME_DIR_ENV_VAR)
    if bundled_dir:
        search_dirs.append(Path(bundled_dir))
    search_dirs.append(Path.home().joinpath(*_USER_BIN_SUBPATH))
    for directory in search_dirs:
        for name in _DEFAULT_BINARY_NAMES:
            found = _executable(directory / f"{name}{suffix}")
            if found:
                return found

    for name in _DEFAULT_BINARY_NAMES:
        found = find_tool(name)
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

    When the binary or model is absent the worker raises SttUnavailableError;
    callers (the STT router) convert this to a text-only fallback response
    rather than an HTTP error.
    """

    def __init__(self, config: WhisperCppConfig | None = None) -> None:
        cfg = config or WhisperCppConfig()
        self._configured_binary_path = cfg.binary_path
        self._binary = _find_binary(cfg.binary_path)
        self._model_path = cfg.model_path
        self._n_threads = cfg.n_threads
        self._timeout = cfg.timeout

    @property
    def id(self) -> str:
        return "whisper_cpp"

    @property
    def display_name(self) -> str:
        return "whisper.cpp (local)"

    @property
    def model_path(self) -> str:
        """Path of the GGML model this worker transcribes with."""
        return self._model_path

    def set_model_path(self, path: str) -> None:
        """Switch to the model at *path* without restarting the process.

        Voice onboarding lets the player pick among several whisper models
        (tiny.en, base.en, small.en, multilingual base), so the file that lands
        on disk is not always the configured default. Pointing the live worker
        at the new file makes the choice take effect on the next utterance; the
        path is persisted separately so it also survives a restart.
        """
        self._model_path = path

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
            "--no-timestamps",
        ]
        if language:
            cmd += ["--language", language]
        if self._n_threads is not None:
            cmd += ["--threads", str(self._n_threads)]
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

        audio_format = (request.audio_format or "").lower()
        suffix = f".{request.audio_format}" if request.audio_format else ".bin"
        # All four resources are tracked as None so the finally block can clean
        # up on every exit path — including asyncio.CancelledError (task cancelled
        # mid-transcription), which the inner except handlers don't catch.
        source_path: str | None = None
        audio_path: str | None = None
        json_path: str | None = None
        proc: asyncio.subprocess.Process | None = None
        result: SttResult | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                source_path = tmp.name
                tmp.write(request.audio)

            # whisper-cli cannot decode what the browser records, so anything
            # but WAV is transcoded first and *that* file is what it reads.
            if audio_format in _PASSTHROUGH_AUDIO_FORMATS:
                audio_path = source_path
            else:
                audio_path = await _transcode_to_wav(
                    source_path, audio_format, self._timeout
                )

            # whisper-cli --output-json writes a sidecar named after the input file
            # stem (extension stripped), e.g. /tmp/tmpXXX.wav → /tmp/tmpXXX.json.
            json_path = str(Path(audio_path).with_suffix("")) + ".json"

            cmd = self._build_command(audio_path, request.language)
            t0 = time.monotonic()
            try:
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    creationflags=CREATE_NO_WINDOW,
                )
            except OSError as exc:
                raise SttError(
                    f"Failed to start whisper-cli: {exc}", recoverable=True
                ) from exc
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=self._timeout
                )
            except asyncio.TimeoutError as exc:
                try:
                    proc.kill()
                except OSError:
                    pass
                await proc.wait()
                raise SttError(
                    f"whisper-cli timed out after {self._timeout}s", recoverable=True
                ) from exc
            processing_ms = (time.monotonic() - t0) * 1000.0

            if proc.returncode != 0:
                err_text = stderr.decode(errors="replace")[:500]
                raise SttError(
                    f"whisper-cli exited with code {proc.returncode}: {err_text}",
                    recoverable=True,
                )

            result = _read_result(json_path, stdout.decode(errors="replace"), processing_ms)
        finally:
            if audio_path is not None:
                _try_unlink(audio_path)
            # The same path when the recording was already WAV; unlinking twice
            # is harmless, and skipping it would leak the original transcode input.
            if source_path is not None and source_path != audio_path:
                _try_unlink(source_path)
            if json_path is not None and result is None:
                # _read_result handles json_path cleanup on the success path.
                # On any error or cancellation, clean it here.
                _try_unlink(json_path)
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                except OSError:
                    pass
                await proc.wait()

        assert result is not None  # guaranteed: no exception → _read_result ran
        return result

    async def health(self) -> SttHealth:
        checked_at = datetime.now(timezone.utc).isoformat()

        # Re-check binary on every health call so that installs and removals
        # after startup are reflected without a server restart.
        self._binary = _find_binary(self._configured_binary_path)

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

        # Reported last, because the binary and the model are the more
        # fundamental gaps — but reported, because without ffmpeg this worker
        # cannot serve a single request the app actually makes. Every caller
        # (`POST /api/stt/upload`, from the conversation screen and from voice
        # setup's own test) sends what the browser recorded: WebM/Opus, or
        # MP4/AAC on Safari. `transcribe` transcodes all of it through ffmpeg
        # before whisper-cli sees it and raises SttUnavailableError when ffmpeg
        # is absent, so a READY here would be health contradicting transcribe.
        #
        # It is not a cosmetic contradiction. READY has Home print "STT: ready",
        # Settings print "model loaded" and the brief pre-select push-to-talk —
        # and then the player holds the talk key and gets "Speech-to-text is not
        # installed. Please type your response.", which names nothing and leads
        # nowhere. UNAVAILABLE instead routes all three to /voice-setup, where
        # the ffmpeg row carries the command for the platform (issue #487).
        #
        # Re-checked on every health call, like the binary above, so installing
        # ffmpeg and pressing "Check again" turns the row green without a restart.
        if _ffmpeg_path() is None:
            return SttHealth(
                worker_id=self.id,
                worker_name=self.display_name,
                status=RuntimeStatus.UNAVAILABLE,
                model_path=self._model_path,
                message=(
                    "ffmpeg was not found. whisper.cpp reads WAV and the "
                    "browser records WebM/Opus, so without ffmpeg no recording can "
                    "be transcribed. Set up voice shows the install command for "
                    "this platform."
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
        logger.warning(
            "Failed to parse whisper-cli JSON sidecar; falling back to stdout text.",
            exc_info=True,
        )
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
    # whisper-cli places the detected language under data["result"]["language"] in
    # modern releases (ggml-org/whisper.cpp ≥ 1.x). Older or forked binaries may
    # emit it as a top-level key; check both so the fallback path still works.
    result_section = data.get("result") or {}
    detected_language: str | None = result_section.get("language") or data.get("language")

    return SttResult(
        transcript=transcript,
        language=detected_language,
        confidence=avg_confidence,
        duration_ms=duration_ms,
        processing_ms=processing_ms,
        segments=segments if segments else None,
    )
