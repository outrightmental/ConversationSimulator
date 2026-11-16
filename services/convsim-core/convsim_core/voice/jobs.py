# SPDX-License-Identifier: Apache-2.0
"""A voice install as a job: stages, progress, cancel.

One job runs at a time. It installs whatever the requested components still
lack, engine first, then starts the engine once to prove it runs here.

Jobs live in memory, not in the database. A voice install is minutes, not the
LLM's half hour, and it needs no resurrection after a crash: the verified
downloads and the ``.part`` of the interrupted one stay in the staging
folder, so pressing Install again continues from there.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional, Sequence

import httpx

from convsim_core.services.model_download_service import classify_download_error
from convsim_core.voice import catalog
from convsim_core.voice.catalog import VoiceAsset
from convsim_core.voice.engine import EngineError, probe_engine
from convsim_core.voice.installer import (
    VoiceInstallCancelled,
    VoiceInstallError,
    check_free_space,
    discard_staging,
    install_asset,
)
from convsim_core.voice.layout import VoiceLayout

logger = logging.getLogger(__name__)

ERROR_CODE_ENGINE = "ENGINE"
ERROR_CODE_UNSUPPORTED = "UNSUPPORTED"

_STAGE_LABELS = {
    "engine": "Getting the speech engine",
    "whisper-base": "Downloading the listening model",
    "kokoro-v1": "Downloading the voices",
    "check": "Checking that it works",
}

_TERMINAL = frozenset({"complete", "failed", "cancelled"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class VoiceStage:
    id: str
    label: str
    state: str = "pending"  # pending | running | complete | skipped | failed
    detail: Optional[str] = None  # "downloading" | "unpacking" while running
    bytes_downloaded: Optional[int] = None
    bytes_total: Optional[int] = None
    error: Optional[str] = None


@dataclass
class VoiceJob:
    id: int
    components: tuple[str, ...]
    stages: list[VoiceStage]
    status: str = "pending"  # pending | running | complete | failed | cancelled
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @property
    def active(self) -> bool:
        return self.status not in _TERMINAL

    def touch(self) -> None:
        self.updated_at = _now()


ClientFactory = Callable[[], httpx.AsyncClient]
Probe = Callable[[VoiceLayout], Awaitable[str]]


def _default_client() -> httpx.AsyncClient:
    # No overall timeout: a model is hundreds of megabytes. A stalled
    # connection still ends, because every read has its own limit.
    return httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(connect=20.0, read=60.0, write=60.0, pool=20.0),
    )


class VoiceInstallManager:
    """Owns the voice install jobs of one running app."""

    def __init__(
        self,
        layout: VoiceLayout,
        *,
        on_installed: Optional[Callable[[], None]] = None,
        client_factory: ClientFactory = _default_client,
        probe: Probe = probe_engine,
    ) -> None:
        self.layout = layout
        self._on_installed = on_installed
        self._client_factory = client_factory
        self._probe = probe
        self._ids = itertools.count(1)
        self._jobs: dict[int, VoiceJob] = {}
        self._cancel_events: dict[int, asyncio.Event] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # ── Queries ───────────────────────────────────────────────────────────────

    def get(self, job_id: int) -> Optional[VoiceJob]:
        return self._jobs.get(job_id)

    def active_job(self) -> Optional[VoiceJob]:
        return next((j for j in self._jobs.values() if j.active), None)

    def latest_job(self) -> Optional[VoiceJob]:
        return self._jobs[max(self._jobs)] if self._jobs else None

    def assets_needed(self, components: Sequence[str]) -> list[VoiceAsset]:
        """Assets the components still lack, engine first, each once."""
        needed: list[VoiceAsset] = []
        for component_id in components:
            component = catalog.COMPONENTS[component_id]
            for asset in self.layout.component_assets(component):
                if not self.layout.is_installed(asset) and asset not in needed:
                    needed.append(asset)
        needed.sort(key=lambda a: 0 if a.id == "engine" else 1)
        return needed

    # ── Commands ──────────────────────────────────────────────────────────────

    def start(self, components: Sequence[str]) -> VoiceJob:
        """Start installing *components*, or return the job already running."""
        running = self.active_job()
        if running is not None:
            return running

        needed = self.assets_needed(components)
        # Every download's size is known from the catalog, so each stage carries
        # its total from the start: overall progress is then out of the whole
        # install, and never jumps backwards when the next download begins.
        stages = [
            VoiceStage(
                id=a.id,
                label=_STAGE_LABELS.get(a.id, a.label),
                bytes_downloaded=0,
                bytes_total=a.download_bytes,
            )
            for a in needed
        ]
        stages.append(VoiceStage(id="check", label=_STAGE_LABELS["check"]))
        job = VoiceJob(id=next(self._ids), components=tuple(components), stages=stages)
        self._jobs[job.id] = job

        cancel_event = asyncio.Event()
        self._cancel_events[job.id] = cancel_event
        task = asyncio.create_task(self._run(job, needed, cancel_event))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return job

    def cancel(self, job_id: int) -> bool:
        """Ask a running job to stop. False when it is not running."""
        job = self._jobs.get(job_id)
        event = self._cancel_events.get(job_id)
        if job is None or not job.active or event is None:
            return False
        event.set()
        return True

    async def shutdown(self) -> None:
        """Stop any running job when the app closes, keeping its downloads."""
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    # ── The job itself ────────────────────────────────────────────────────────

    async def _run(
        self, job: VoiceJob, needed: list[VoiceAsset], cancel_event: asyncio.Event
    ) -> None:
        stage_by_id = {s.id: s for s in job.stages}
        current: Optional[VoiceStage] = None

        def fail(message: str, code: str) -> None:
            if current is not None:
                current.state = "failed"
                current.error = message
            job.status = "failed"
            job.error_message = message
            job.error_code = code
            job.touch()

        job.status = "running"
        job.touch()
        try:
            if catalog.engine_asset() is None:
                current = job.stages[0]
                fail(
                    "Voice is not available for this kind of computer yet.",
                    ERROR_CODE_UNSUPPORTED,
                )
                return

            check_free_space(self.layout, needed)

            async with self._client_factory() as client:
                for asset in needed:
                    current = stage_by_id[asset.id]
                    current.state = "running"
                    current.bytes_total = asset.download_bytes
                    current.bytes_downloaded = 0
                    job.touch()

                    def on_progress(done: int, total: int, stage: VoiceStage = current) -> None:
                        stage.bytes_downloaded = done
                        stage.bytes_total = total
                        job.touch()

                    def on_phase(phase: str, stage: VoiceStage = current) -> None:
                        stage.detail = phase
                        job.touch()

                    await install_asset(
                        asset,
                        self.layout,
                        client=client,
                        cancel_event=cancel_event,
                        on_progress=on_progress,
                        on_phase=on_phase,
                    )
                    current.state = "complete"
                    current.detail = None
                    job.touch()

            if cancel_event.is_set():
                raise VoiceInstallCancelled()

            current = stage_by_id["check"]
            current.state = "running"
            job.touch()
            version = await self._probe(self.layout)
            logger.info("voice install(%d): engine %s runs on this machine", job.id, version)
            current.state = "complete"

            job.status = "complete"
            job.touch()
            if self._on_installed is not None:
                self._on_installed()
        except VoiceInstallCancelled:
            # Policy: a cancel leaves nothing of the download behind. Assets
            # that finished before the cancel stay installed and usable.
            discard_staging(self.layout)
            message = "Cancelled."
            if current is not None and current.state == "running":
                current.state = "failed"
                current.error = message
            job.status = "cancelled"
            job.error_message = message
            job.touch()
            if self._on_installed is not None:
                self._on_installed()
        except VoiceInstallError as exc:
            fail(exc.message, exc.code)
        except EngineError as exc:
            fail(str(exc), ERROR_CODE_ENGINE)
        except asyncio.CancelledError:
            # The app is closing. Staged downloads are kept for the next run.
            job.status = "cancelled"
            job.error_message = "The app closed before the install finished."
            job.touch()
            raise
        except Exception as exc:  # noqa: BLE001
            code, message = classify_download_error(exc)
            logger.warning("voice install(%d) failed: %s", job.id, message, exc_info=True)
            fail(message, code)
        finally:
            self._cancel_events.pop(job.id, None)
