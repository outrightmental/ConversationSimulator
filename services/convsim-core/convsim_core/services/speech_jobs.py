# SPDX-License-Identifier: Apache-2.0
"""Speech for a reply, synthesised after the reply has been sent.

A turn used to wait for its audio: the response was held until every sentence
of the reply had been synthesised, so turning the character's voice on made
the *text* slower, by seconds on a long line (issue #533).

Now the words go out as soon as they exist. Each sentence of the reply gets a
place here, a future that resolves to its audio file, and synthesis runs in
the background. The client asks for each sentence's audio by address
(``GET /api/sessions/{id}/speech/{turn}/{index}``); that request waits on the
sentence's future and answers when the audio is ready. So the first sentence
is heard as soon as *it* is synthesised, in order, with no polling.

Nothing here is persisted. The audio files live in the TTS cache and the
session's ``tts_audio_chunk`` events record where; this registry only bridges
the seconds in between.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from convsim_core.services.tts_queue import TtsChunkResult, synthesize_sentences
from convsim_core.tts.base import TtsWorker

logger = logging.getLogger(__name__)

# Jobs kept per session: the turn being spoken and the one before it. Older
# audio is on disk and is served from the session's recorded events.
_JOBS_KEPT_PER_SESSION = 2


@dataclass
class SpeechJob:
    """One reply being synthesised, sentence by sentence."""

    session_id: str
    turn_number: int
    # One future per sentence: the cached WAV path, or None when it failed.
    sentences: list["asyncio.Future[Optional[str]]"]
    started: float = field(default_factory=time.perf_counter)
    # Milliseconds from the start of synthesis until the first sentence's
    # audio existed, and until the last one did. None until known.
    first_audio_ms: Optional[float] = None
    synth_ms: Optional[float] = None


class SpeechRegistry:
    """The replies whose audio is being made, for one running app."""

    def __init__(self) -> None:
        self._jobs: dict[tuple[str, int], SpeechJob] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def start(
        self,
        *,
        session_id: str,
        turn_number: int,
        sentences: list[str],
        voice_id: str,
        language: Optional[str],
        tts_worker: TtsWorker,
        on_sentence: Optional[Callable[[TtsChunkResult], None]] = None,
        on_done: Optional[Callable[[SpeechJob], None]] = None,
    ) -> SpeechJob:
        """Begin synthesising *sentences* in the background.

        ``on_sentence`` is called as each sentence finishes (to record where
        its audio is); ``on_done`` once the last one has. Both run on the
        event loop.
        """
        loop = asyncio.get_running_loop()
        job = SpeechJob(
            session_id=session_id,
            turn_number=turn_number,
            sentences=[loop.create_future() for _ in sentences],
        )
        self._jobs[(session_id, turn_number)] = job
        self._trim(session_id)

        def _sentence_done(chunk: TtsChunkResult) -> None:
            if chunk.audio_path is not None and job.first_audio_ms is None:
                job.first_audio_ms = round((time.perf_counter() - job.started) * 1000.0, 1)
            try:
                if on_sentence is not None:
                    on_sentence(chunk)
            finally:
                future = job.sentences[chunk.chunk_index]
                if not future.done():
                    future.set_result(chunk.audio_path)

        async def _run() -> None:
            try:
                await synthesize_sentences(
                    sentences, voice_id, tts_worker, language=language, on_chunk=_sentence_done
                )
                job.synth_ms = round((time.perf_counter() - job.started) * 1000.0, 1)
                if on_done is not None:
                    on_done(job)
            except Exception:  # noqa: BLE001
                logger.error(
                    "speech for session %s turn %d failed", session_id, turn_number, exc_info=True
                )
            finally:
                # Whatever happened, nobody waits forever on a sentence.
                for future in job.sentences:
                    if not future.done():
                        future.set_result(None)

        task = asyncio.create_task(_run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def sentence(
        self, session_id: str, turn_number: int, index: int
    ) -> Optional["asyncio.Future[Optional[str]]"]:
        """The future for one sentence's audio, or None when not in flight."""
        job = self._jobs.get((session_id, turn_number))
        if job is None or not 0 <= index < len(job.sentences):
            return None
        return job.sentences[index]

    def forget_session(self, session_id: str) -> None:
        """Drop a session's jobs (it ended or was deleted)."""
        for key in [k for k in self._jobs if k[0] == session_id]:
            del self._jobs[key]

    def _trim(self, session_id: str) -> None:
        turns = sorted(k[1] for k in self._jobs if k[0] == session_id)
        for turn in turns[:-_JOBS_KEPT_PER_SESSION]:
            del self._jobs[(session_id, turn)]

    async def shutdown(self) -> None:
        """Stop synthesis in flight when the app closes."""
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
