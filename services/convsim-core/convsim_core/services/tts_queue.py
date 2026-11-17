# SPDX-License-Identifier: Apache-2.0
"""TTS queue: split NPC utterances into sentences and synthesize each chunk.

Usage::

    chunks = await synthesize_utterance(
        utterance=result.npc_utterance,
        voice_id="af_heart",
        tts_worker=tts_worker,
    )
    for chunk in chunks:
        if chunk.succeeded:
            # play chunk.audio_path
        else:
            # show chunk.text as fallback
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable

from convsim_core.tts.base import TtsWorker
from convsim_core.tts.sentence_splitter import split_into_sentences
from convsim_core.tts.types import TtsError, TtsRequest, TtsUnavailableError

logger = logging.getLogger(__name__)


@dataclass
class TtsChunkResult:
    """Result for a single synthesized sentence chunk."""

    chunk_index: int
    total_chunks: int
    text: str
    voice_id: str
    audio_path: str | None = field(default=None)
    error: str | None = field(default=None)

    @property
    def succeeded(self) -> bool:
        return self.audio_path is not None


async def synthesize_utterance(
    utterance: str,
    voice_id: str,
    tts_worker: TtsWorker,
    speed: float = 1.0,
    language: str | None = None,
) -> list[TtsChunkResult]:
    """Split *utterance* into sentences and synthesize each as a TTS chunk.

    Chunks are returned in sentence order.  Synthesis failures are recorded
    per chunk (``error`` field set, ``audio_path`` is None) and do not abort
    subsequent chunks — text fallback is always available.

    Returns an empty list for empty utterances.  Never raises.
    """
    return await synthesize_sentences(
        split_into_sentences(utterance), voice_id, tts_worker, speed=speed, language=language
    )


async def synthesize_sentences(
    sentences: list[str],
    voice_id: str,
    tts_worker: TtsWorker,
    *,
    speed: float = 1.0,
    language: str | None = None,
    on_chunk: Callable[[TtsChunkResult], None] | None = None,
) -> list[TtsChunkResult]:
    """Synthesize sentences already split, one chunk each, in sentence order.

    A worker that declares ``max_concurrency`` above one has that many
    sentences synthesised at a time; the order of the result is the order of
    the sentences either way.  ``language`` is the language the sentences are
    written in, for a worker that pronounces by language.

    ``on_chunk`` is called as each sentence finishes, in the order they
    finish, which with a concurrent worker is not always sentence order.  It
    is how a caller hands each sentence's audio on without waiting for the
    last one.  A failure in the callback is logged and does not stop the rest.

    Never raises.
    """
    if not sentences:
        return []

    total = len(sentences)
    slots = synthesis_slots(tts_worker)

    async def _one(idx: int, sentence: str) -> TtsChunkResult:
        chunk = await synthesize_chunk(
            idx, sentence, voice_id, tts_worker, slots, total=total, speed=speed, language=language
        )
        if on_chunk is not None:
            try:
                on_chunk(chunk)
            except Exception:  # noqa: BLE001
                logger.error("TTS chunk callback failed (chunk %d/%d)", idx + 1, total, exc_info=True)
        return chunk

    return list(await asyncio.gather(*(_one(i, s) for i, s in enumerate(sentences))))


def synthesis_slots(tts_worker: TtsWorker) -> asyncio.Semaphore:
    """How many sentences ``tts_worker`` may synthesise at a time.

    A worker that declares ``max_concurrency`` above one gets that many;
    anything else gets one.
    """
    concurrency = getattr(tts_worker, "max_concurrency", 1)
    return asyncio.Semaphore(concurrency if isinstance(concurrency, int) and concurrency > 0 else 1)


async def synthesize_chunk(
    idx: int,
    sentence: str,
    voice_id: str,
    tts_worker: TtsWorker,
    slots: asyncio.Semaphore,
    *,
    total: int = 0,
    speed: float = 1.0,
    language: str | None = None,
) -> TtsChunkResult:
    """Synthesise one sentence, holding one of ``slots`` while it runs.

    A failure is recorded on the chunk (``error`` set, ``audio_path`` None)
    rather than raised, so text is always the fallback. ``total`` is the
    number of sentences in the reply when it is known, for the logs and the
    chunk; 0 while a reply is still being written. Never raises.
    """
    chunk = TtsChunkResult(
        chunk_index=idx,
        total_chunks=total,
        text=sentence,
        voice_id=voice_id,
    )
    of = f"{idx + 1}/{total}" if total else str(idx + 1)
    try:
        async with slots:
            tts_result = await tts_worker.synthesize(
                TtsRequest(text=sentence, voice_id=voice_id, speed=speed, language=language)
            )
        chunk.audio_path = tts_result.audio_path
    except TtsUnavailableError as exc:
        logger.info("TTS unavailable (chunk %s): %s", of, exc)
        chunk.error = str(exc)
    except TtsError as exc:
        logger.warning("TTS synthesis error (chunk %s): %s", of, exc, exc_info=True)
        chunk.error = str(exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unexpected TTS error (chunk %s): %s", of, exc, exc_info=True)
        chunk.error = f"Unexpected error: {exc}"
    return chunk
