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

A reply streamed over the session socket is spoken as it is written (issue
#544): each sentence the streaming gate releases is added to the turn's job
the moment it is released (``open`` and ``add``), so the character starts
talking while the model is still writing the turn's bookkeeping. When the
turn commits, its sentences are matched against the job and only the ones
not yet started are added.

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

from convsim_core.services.tts_queue import (
    TtsChunkResult,
    synthesis_slots,
    synthesize_chunk,
)
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
    # The text of each sentence, in order, and why one failed (None if not).
    texts: list[str] = field(default_factory=list)
    errors: list[Optional[str]] = field(default_factory=list)
    voice_id: str = ""
    language: Optional[str] = None
    tts_worker: Optional[TtsWorker] = None
    slots: Optional["asyncio.Semaphore"] = None
    # True once the turn committed and no sentence will be added.
    finished: bool = False

    def matches(self, sentences: list[str], voice_id: str) -> bool:
        """Whether this job spoke the start of ``sentences``, in ``voice_id``.

        The streamed sentences are the committed line's own (released text
        is committed text), so normally they are a prefix of it.
        """
        if voice_id != self.voice_id or len(self.texts) > len(sentences):
            return False
        return self.texts == sentences[: len(self.texts)]


class SpeechRegistry:
    """The replies whose audio is being made, for one running app."""

    def __init__(self) -> None:
        self._jobs: dict[tuple[str, int], SpeechJob] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def open(
        self,
        *,
        session_id: str,
        turn_number: int,
        voice_id: str,
        language: Optional[str],
        tts_worker: TtsWorker,
        in_order: bool = False,
    ) -> SpeechJob:
        """A job for one reply, with no sentence yet; ``add`` gives it them.

        ``in_order`` synthesises one sentence at a time, first to last. A
        reply spoken while the model is still writing (issue #544) shares the
        processor with it on a machine without a graphics card; sentences
        synthesised side by side there all finished late, and the first one
        was heard at 9.7 s instead of as soon as it could be. One at a time,
        the first is ready first and the rest follow while it plays.
        """
        job = SpeechJob(
            session_id=session_id,
            turn_number=turn_number,
            sentences=[],
            voice_id=voice_id,
            language=language,
            tts_worker=tts_worker,
            slots=asyncio.Semaphore(1) if in_order else synthesis_slots(tts_worker),
        )
        self._jobs[(session_id, turn_number)] = job
        self._trim(session_id)
        return job

    def add(self, job: SpeechJob, text: str) -> int:
        """Start synthesising one more sentence of ``job``; return its index."""
        assert job.tts_worker is not None and job.slots is not None
        worker, slots = job.tts_worker, job.slots
        loop = asyncio.get_running_loop()
        index = len(job.texts)
        future: "asyncio.Future[Optional[str]]" = loop.create_future()
        job.texts.append(text)
        job.errors.append(None)
        job.sentences.append(future)

        async def _run() -> None:
            try:
                chunk = await synthesize_chunk(
                    index, text, job.voice_id, worker, slots, language=job.language
                )
                job.errors[index] = chunk.error
                if chunk.audio_path is not None and job.first_audio_ms is None:
                    job.first_audio_ms = round((time.perf_counter() - job.started) * 1000.0, 1)
                if not future.done():
                    future.set_result(chunk.audio_path)
            finally:
                # Whatever happened, nobody waits forever on a sentence.
                if not future.done():
                    future.set_result(None)

        task = asyncio.create_task(_run())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return index

    def finish(
        self,
        job: SpeechJob,
        on_done: Optional[Callable[[SpeechJob], None]] = None,
    ) -> None:
        """No more sentences: once every one is done, time the job and call ``on_done``."""
        job.finished = True

        async def _wait() -> None:
            try:
                if job.sentences:
                    await asyncio.gather(*job.sentences)
                job.synth_ms = round((time.perf_counter() - job.started) * 1000.0, 1)
                if on_done is not None:
                    on_done(job)
            except Exception:  # noqa: BLE001
                logger.error(
                    "speech for session %s turn %d failed",
                    job.session_id, job.turn_number, exc_info=True,
                )

        task = asyncio.create_task(_wait())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def job(self, session_id: str, turn_number: int) -> Optional[SpeechJob]:
        """The job for one reply, or None when there is none in flight."""
        return self._jobs.get((session_id, turn_number))

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
        """Begin synthesising *sentences* in the background, all at once.

        ``on_sentence`` is called as each sentence finishes (to record where
        its audio is); ``on_done`` once the last one has. Both run on the
        event loop.
        """
        job = self.open(
            session_id=session_id,
            turn_number=turn_number,
            voice_id=voice_id,
            language=language,
            tts_worker=tts_worker,
        )
        for text in sentences:
            self.add(job, text)
        if on_sentence is not None:
            self.on_each_sentence(job, on_sentence, total=len(sentences))
        self.finish(job, on_done)
        return job

    @staticmethod
    def on_each_sentence(
        job: SpeechJob,
        on_sentence: Callable[[TtsChunkResult], None],
        *,
        total: int,
        start: int = 0,
    ) -> None:
        """Call ``on_sentence`` as each of ``job``'s sentences from ``start`` on is done.

        A sentence already done is reported as soon as the loop runs.
        """
        for index in range(start, len(job.sentences)):
            def _report(future: "asyncio.Future[Optional[str]]", index: int = index) -> None:
                audio_path = None if future.cancelled() else future.result()
                error = job.errors[index]
                if audio_path is None and error is None:
                    error = "Speech synthesis failed"
                chunk = TtsChunkResult(
                    chunk_index=index,
                    total_chunks=total,
                    text=job.texts[index],
                    voice_id=job.voice_id,
                    audio_path=audio_path,
                    error=error,
                )
                try:
                    on_sentence(chunk)
                except Exception:  # noqa: BLE001
                    logger.error("speech callback failed (chunk %d)", index, exc_info=True)

            job.sentences[index].add_done_callback(_report)

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
