# SPDX-License-Identifier: Apache-2.0
from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from convsim_core.runtime.types import RuntimeStatus
from convsim_core.tts.base import TtsWorker
from convsim_core.tts.registry import register_tts
from convsim_core.tts.types import TtsError, TtsHealth, TtsRequest, TtsResult, TtsUnavailableError
from convsim_core.tts.voices import APPROVED_VOICES, validate_voice_id

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_DIR = str(Path.home() / ".convsim" / "tts_cache")


class KokoroConfig(BaseSettings):
    """Configuration for the Kokoro TTS worker.

    All values can be set via CONVSIM_KOKORO_* environment variables.
    """

    model_config = SettingsConfigDict(
        env_prefix="CONVSIM_KOKORO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    base_url: str = "http://127.0.0.1:7358"
    timeout: float = 30.0
    cache_dir: str = _DEFAULT_CACHE_DIR


def _cache_key(text: str, voice_id: str, speed: float) -> str:
    """Stable SHA-256 cache key derived from synthesis parameters."""
    raw = f"{voice_id}:{speed:.3f}:{text}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


@register_tts("kokoro")
class KokoroTtsWorker(TtsWorker):
    """TTS worker that calls a local Kokoro REST server (OpenAI-compatible audio API).

    Audio responses are cached under CONVSIM_KOKORO_CACHE_DIR so repeated
    utterances avoid re-synthesis. The cache key is derived from (voice_id,
    speed, text); changing any parameter produces a new cache entry.

    If the Kokoro server is unreachable the worker raises TtsUnavailableError;
    callers convert this to a text-only fallback rather than an HTTP error.
    Voice ids are validated against the approved built-in list before every
    synthesis call — there is no path to synthesize with a cloned or imported voice.
    """

    def __init__(self, config: KokoroConfig | None = None) -> None:
        cfg = config or KokoroConfig()
        self._base_url = cfg.base_url.rstrip("/")
        self._timeout = cfg.timeout
        # Resolve the cache dir but do not create it here: constructing a worker
        # (which happens at every app startup and in every test that builds the
        # app) should not have a filesystem side effect. The directory is created
        # lazily in synthesize() right before the first cache write.
        self._cache_dir = Path(cfg.cache_dir)

    @property
    def id(self) -> str:
        return "kokoro"

    @property
    def display_name(self) -> str:
        return "Kokoro (local)"

    async def synthesize(self, request: TtsRequest) -> TtsResult:
        validate_voice_id(request.voice_id)

        key = _cache_key(request.text, request.voice_id, request.speed)
        cache_path = self._cache_dir / f"{key}.wav"

        if cache_path.exists():
            return TtsResult(
                audio_path=str(cache_path),
                audio_format="wav",
                voice_id=request.voice_id,
            )

        payload = {
            "model": "kokoro",
            "input": request.text,
            "voice": request.voice_id,
            "response_format": "wav",
            "speed": request.speed,
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                t0 = time.monotonic()
                resp = await client.post(f"{self._base_url}/v1/audio/speech", json=payload)
                duration_ms = (time.monotonic() - t0) * 1000.0
        except httpx.ConnectError as exc:
            raise TtsUnavailableError(
                f"Kokoro TTS server not reachable at {self._base_url}. "
                "Start the Kokoro server or set CONVSIM_KOKORO_BASE_URL. "
                f"Detail: {exc}"
            ) from exc
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise TtsError(
                f"Request to Kokoro TTS server failed: {exc}", recoverable=True
            ) from exc

        if resp.status_code != 200:
            raise TtsError(
                f"Kokoro TTS server returned HTTP {resp.status_code}: {resp.text[:200]}",
                recoverable=True,
            )

        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(resp.content)
        return TtsResult(
            audio_path=str(cache_path),
            audio_format="wav",
            duration_ms=duration_ms,
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

    async def health(self) -> TtsHealth:
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/health")
            if resp.status_code == 200:
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
                status=RuntimeStatus.DEGRADED,
                voice_count=len(APPROVED_VOICES),
                message=f"Kokoro server returned HTTP {resp.status_code}",
                checked_at=checked_at,
            )
        except (httpx.ConnectError, httpx.TimeoutException, httpx.RequestError):
            return TtsHealth(
                worker_id=self.id,
                worker_name=self.display_name,
                status=RuntimeStatus.UNAVAILABLE,
                message=(
                    f"Kokoro TTS server not reachable at {self._base_url}. "
                    "See runtimes/kokoro/README.md for installation instructions."
                ),
                checked_at=checked_at,
            )
