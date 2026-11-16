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

    A worker that declares ``max_concurrency`` above one has that many
    sentences synthesised at a time; the order of the result is the order of
    the sentences either way.  ``language`` is the language the utterance is
    written in, for a worker that pronounces by language.

    Returns an empty list for empty utterances.  Never raises.
    """
    sentences = split_into_sentences(utterance)
    if not sentences:
        return []

    total = len(sentences)
    concurrency = getattr(tts_worker, "max_concurrency", 1)
    slots = asyncio.Semaphore(concurrency if isinstance(concurrency, int) and concurrency > 0 else 1)

    async def _one(idx: int, sentence: str) -> TtsChunkResult:
        chunk = TtsChunkResult(
            chunk_index=idx,
            total_chunks=total,
            text=sentence,
            voice_id=voice_id,
        )
        try:
            async with slots:
                tts_result = await tts_worker.synthesize(
                    TtsRequest(text=sentence, voice_id=voice_id, speed=speed, language=language)
                )
            chunk.audio_path = tts_result.audio_path
        except TtsUnavailableError as exc:
            logger.info("TTS unavailable (chunk %d/%d): %s", idx + 1, total, exc)
            chunk.error = str(exc)
        except TtsError as exc:
            logger.warning(
                "TTS synthesis error (chunk %d/%d): %s", idx + 1, total, exc,
                exc_info=True,
            )
            chunk.error = str(exc)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Unexpected TTS error (chunk %d/%d): %s", idx + 1, total, exc,
                exc_info=True,
            )
            chunk.error = f"Unexpected error: {exc}"
        return chunk

    return list(await asyncio.gather(*(_one(i, s) for i, s in enumerate(sentences))))
