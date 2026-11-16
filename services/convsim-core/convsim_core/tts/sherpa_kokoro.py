# SPDX-License-Identifier: Apache-2.0
"""Text-to-speech through the installed voice engine (Kokoro v1.0).

This is the worker a one-click voice install switches on. The legacy
``kokoro`` worker talks to a server the player has to run; this one runs the
engine the app downloaded (see :mod:`convsim_core.voice`), one short process
per sentence, and keeps the same contract: approved built-in voices only,
audio cached as WAV under the app's cache folder.

Each sentence costs about a second of model loading plus roughly a fifth of
its own length to synthesise, so the worker lets a few sentences of one reply
be synthesised side by side (:attr:`max_concurrency`) instead of in a queue.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.tts.base import TtsWorker
from convsim_core.tts.registry import register_tts
from convsim_core.tts.types import (
    TtsError,
    TtsHealth,
    TtsRequest,
    TtsResult,
    TtsUnavailableError,
)
from convsim_core.tts.voices import APPROVED_VOICES, validate_voice_id
from convsim_core.voice import catalog
from convsim_core.voice.engine import (
    EngineError,
    default_threads,
    failure_detail,
    run_engine,
    text_for_argv,
)
from convsim_core.voice.layout import VoiceLayout

logger = logging.getLogger(__name__)

_NOT_INSTALLED = (
    "The character voice is not installed. Choose Install voice on the "
    "conversation brief to download it."
)


def kokoro_language(language: Optional[str]) -> Optional[str]:
    """The engine's language name for a session language.

    ``None`` in means "the voice's own language", which for every approved
    voice is English. ``None`` out means the voices cannot speak it.
    """
    if not language:
        return catalog.KOKORO_LANGUAGES["en"]
    primary = language.strip().lower().replace("_", "-").split("-")[0]
    return catalog.KOKORO_LANGUAGES.get(primary)


def _cache_key(text: str, voice_id: str, speed: float, language: str) -> str:
    """Stable cache key. The model version is part of it, so a later model
    never serves audio an earlier one synthesised."""
    raw = f"{catalog.KOKORO_ASSET.version}:{voice_id}:{speed:.3f}:{language}:{text}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


@register_tts("sherpa_kokoro")
class SherpaKokoroTtsWorker(TtsWorker):
    """Kokoro v1.0 voices, run by the installed voice engine."""

    def __init__(
        self,
        voice_dir: str | Path | None = None,
        cache_dir: str | Path | None = None,
        *,
        timeout: float = 60.0,
    ) -> None:
        if voice_dir is None or cache_dir is None:
            from convsim_core.config import ServiceConfig

            config = ServiceConfig()
            voice_dir = voice_dir or config.voice_dir
            cache_dir = cache_dir or Path(config.cache_dir) / "tts"
        self._layout = VoiceLayout(voice_dir)
        # Read by the /api/tts/audio route to find the files it serves.
        self._cache_dir = Path(cache_dir)
        self._timeout = timeout
        cores = os.cpu_count() or 2
        # Sentences synthesised at once. Each process uses up to four threads;
        # a small machine gets one at a time.
        self.max_concurrency = 3 if cores >= 12 else 2 if cores >= 6 else 1
        self._slots: Optional[asyncio.Semaphore] = None

    @property
    def id(self) -> str:
        return "sherpa_kokoro"

    @property
    def display_name(self) -> str:
        return "Kokoro (built-in voice)"

    def _semaphore(self) -> asyncio.Semaphore:
        # Created on first use so it belongs to the loop that serves requests.
        if self._slots is None:
            self._slots = asyncio.Semaphore(self.max_concurrency)
        return self._slots

    async def synthesize(self, request: TtsRequest) -> TtsResult:
        voice = validate_voice_id(request.voice_id)
        layout = self._layout
        if not layout.tts_installed():
            raise TtsUnavailableError(_NOT_INSTALLED)

        language = kokoro_language(request.language)
        if language is None:
            raise TtsUnavailableError(
                f"The built-in voices cannot speak this language yet ({request.language})."
            )

        key = _cache_key(request.text, request.voice_id, request.speed, language)
        cache_path = self._cache_dir / f"{key}.wav"
        if cache_path.exists():
            return TtsResult(
                audio_path=str(cache_path), audio_format="wav", voice_id=request.voice_id
            )

        spoken = text_for_argv(request.text)
        if not spoken:
            raise TtsError("There is nothing to say in this text.", recoverable=True)

        asset = catalog.KOKORO_ASSET
        base = asset.install_dir
        work_dir = layout.tmp_dir
        work_dir.mkdir(parents=True, exist_ok=True)
        out_name = f"{uuid.uuid4().hex}.wav"
        out_path = work_dir / out_name
        args = [
            f"--kokoro-model={base}/model.onnx",
            f"--kokoro-voices={base}/voices.bin",
            f"--kokoro-tokens={base}/tokens.txt",
            f"--kokoro-data-dir={base}/espeak-ng-data",
            f"--kokoro-lang={language}",
            f"--kokoro-length-scale={1.0 / max(request.speed, 0.1):.3f}",
            f"--num-threads={default_threads()}",
            f"--sid={catalog.KOKORO_SPEAKER_IDS[voice.voice_id]}",
            f"--output-filename={work_dir.name}/{out_name}",
        ]
        if language == "en":
            # English goes through Kokoro's own lexicon first (British or
            # American to match the voice); eSpeak NG covers what it lacks.
            lexicon = "lexicon-gb-en.txt" if voice.locale == "en-GB" else "lexicon-us-en.txt"
            args.append(f"--kokoro-lexicon={base}/{lexicon}")
        args.append(spoken)

        started = time.monotonic()
        try:
            async with self._semaphore():
                try:
                    result = await run_engine(
                        layout, catalog.ENGINE_TTS_PROGRAM, args, timeout=self._timeout
                    )
                except EngineError as exc:
                    raise TtsError(str(exc), recoverable=True) from exc
            if result.returncode != 0 or not out_path.is_file() or out_path.stat().st_size <= 44:
                raise TtsError(
                    f"The speech engine could not synthesise this sentence "
                    f"({failure_detail(result)}).",
                    recoverable=True,
                )
            self._cache_dir.mkdir(parents=True, exist_ok=True)
            os.replace(out_path, cache_path)
        finally:
            out_path.unlink(missing_ok=True)

        return TtsResult(
            audio_path=str(cache_path),
            audio_format="wav",
            duration_ms=(time.monotonic() - started) * 1000.0,
            voice_id=request.voice_id,
        )

    async def clear_cache(self) -> int:
        if not self._cache_dir.exists():
            return 0
        count = 0
        for entry in self._cache_dir.glob("*.wav"):
            try:
                entry.unlink()
                count += 1
            except OSError:
                pass
        return count

    async def cache_size(self) -> dict:
        if not self._cache_dir.exists():
            return {"files": 0, "size_bytes": 0}
        files = 0
        size_bytes = 0
        for entry in self._cache_dir.glob("*.wav"):
            try:
                size_bytes += entry.stat().st_size
                files += 1
            except OSError:
                pass
        return {"files": files, "size_bytes": size_bytes}

    async def health(self) -> TtsHealth:
        checked_at = datetime.now(timezone.utc).isoformat()
        if self._layout.tts_installed():
            return TtsHealth(
                worker_id=self.id,
                worker_name=self.display_name,
                status=RuntimeStatus.READY,
                voice_count=len(APPROVED_VOICES),
                checked_at=checked_at,
            )
        return TtsHealth(
            worker_id=self.id,
            worker_name=self.display_name,
            status=RuntimeStatus.UNAVAILABLE,
            message=_NOT_INSTALLED,
            checked_at=checked_at,
        )
