# SPDX-License-Identifier: Apache-2.0
"""One-click voice install.

GET    /api/voice/setup                what voice needs, what is installed, any job
POST   /api/voice/setup/install        start (or reattach to) an install
GET    /api/voice/setup/install/{id}   poll a job
DELETE /api/voice/setup/install/{id}   cancel a running job

Reading the plan downloads nothing. The POST is the player's consent, and the
plan it follows states every file's source, size, licence and checksum
(``docs/model-download-policy.md``).

Open in the demo edition as well as the full app: voice is the one extra
download a demo player may choose.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from convsim_core.errors import ConvsimError
from convsim_core.runtime.types import RuntimeStatus
from convsim_core.voice import catalog
from convsim_core.voice.catalog import VoiceAsset
from convsim_core.voice.installer import VoiceInstallError
from convsim_core.voice.jobs import VoiceInstallManager, VoiceJob
from convsim_core.voice.layout import VoiceLayout

router = APIRouter()

_UNSUPPORTED = "Voice is not available for this kind of computer yet."


# ── Schemas ───────────────────────────────────────────────────────────────────


class VoiceDownloadInfo(BaseModel):
    url: str
    size_bytes: int
    sha256: str


class VoiceAssetInfo(BaseModel):
    id: str
    label: str
    installed: bool
    download_bytes: int
    license: str
    license_note: Optional[str] = None
    source_name: str
    source_url: str
    downloads: list[VoiceDownloadInfo]


class VoiceComponentInfo(BaseModel):
    """Matches ``VoiceComponentStatus`` in packages/shared/src/types/voice-setup.ts."""

    id: str
    label: str
    description: str
    # Usable right now, whether through this install or a voice setup the
    # player made themselves (their own whisper-cli, their own Kokoro server).
    ready: bool
    # The files of *this* install are on disk.
    installed: bool
    # What pressing Install would still download for this component alone.
    download_bytes: int
    # Languages it handles (primary subtags), or null for any.
    languages: Optional[list[str]] = None
    asset_ids: list[str]


class VoiceStageInfo(BaseModel):
    id: str
    label: str
    state: str
    detail: Optional[str] = None
    bytes_downloaded: Optional[int] = None
    bytes_total: Optional[int] = None
    error: Optional[str] = None


class VoiceInstallJobResponse(BaseModel):
    id: int
    status: str
    components: list[str]
    stages: list[VoiceStageInfo]
    error_message: Optional[str] = None
    # NETWORK, HTTP, CHECKSUM, DISK, ARCHIVE, ENGINE, UNSUPPORTED or UNKNOWN.
    error_code: Optional[str] = None
    created_at: str
    updated_at: str


class VoiceSetupResponse(BaseModel):
    """Matches ``VoiceSetupStatus`` in packages/shared/src/types/voice-setup.ts."""

    supported: bool
    unsupported_reason: Optional[str] = None
    install_dir: str
    # What installing every component that is not ready would download.
    download_bytes: int
    # What the in-app install takes on disk now; 0 when nothing is installed.
    installed_bytes: int = 0
    components: list[VoiceComponentInfo]
    assets: list[VoiceAssetInfo]
    # The running job, or the most recent one, so a screen opened mid-install
    # (or just after a failure) shows it.
    job: Optional[VoiceInstallJobResponse] = None


class StartVoiceInstallRequest(BaseModel):
    # Which components to install. Empty or omitted = every one not ready.
    components: list[str] = Field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _manager(request: Request) -> VoiceInstallManager:
    return request.app.state.voice_install


def _job_response(job: VoiceJob) -> VoiceInstallJobResponse:
    return VoiceInstallJobResponse(
        id=job.id,
        status=job.status,
        components=list(job.components),
        stages=[VoiceStageInfo(**vars(stage)) for stage in job.stages],
        error_message=job.error_message,
        error_code=job.error_code,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _asset_info(asset: VoiceAsset, layout: VoiceLayout) -> VoiceAssetInfo:
    return VoiceAssetInfo(
        id=asset.id,
        label=asset.label,
        installed=layout.is_installed(asset),
        download_bytes=asset.download_bytes,
        license=asset.license,
        license_note=asset.license_note,
        source_name=asset.source_name,
        source_url=asset.source_url,
        downloads=[
            VoiceDownloadInfo(url=d.url, size_bytes=d.size_bytes, sha256=d.sha256)
            for d in asset.downloads
        ],
    )


async def _ready(worker: object) -> bool:
    try:
        health = await worker.health()  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        return False
    return health.status in (RuntimeStatus.READY, RuntimeStatus.DEGRADED)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/api/voice/setup", response_model=VoiceSetupResponse)
async def get_voice_setup(request: Request) -> VoiceSetupResponse:
    """What voice needs on this machine and how much of it is already here."""
    manager = _manager(request)
    layout = manager.layout
    engine = catalog.engine_asset()
    supported = engine is not None

    ready_by_component = {
        "stt": await _ready(request.app.state.stt_worker),
        "tts": await _ready(request.app.state.tts_worker),
    }

    components: list[VoiceComponentInfo] = []
    for component in catalog.COMPONENTS.values():
        missing = manager.assets_needed([component.id]) if supported else []
        components.append(
            VoiceComponentInfo(
                id=component.id,
                label=component.label,
                description=component.description,
                ready=ready_by_component[component.id],
                installed=layout.component_installed(component),
                download_bytes=sum(a.download_bytes for a in missing),
                languages=list(component.languages) if component.languages else None,
                asset_ids=[a.id for a in layout.component_assets(component)],
            )
        )

    not_ready = [c.id for c in components if not c.ready]
    to_download = manager.assets_needed(not_ready) if supported else []

    assets = ([engine] if engine is not None else []) + list(catalog.MODEL_ASSETS.values())
    job = manager.active_job() or manager.latest_job()
    return VoiceSetupResponse(
        supported=supported,
        unsupported_reason=None if supported else _UNSUPPORTED,
        install_dir=str(layout.root),
        download_bytes=sum(a.download_bytes for a in to_download),
        installed_bytes=layout.installed_bytes(),
        components=components,
        assets=[_asset_info(a, layout) for a in assets],
        job=_job_response(job) if job is not None else None,
    )


class RemoveVoiceResponse(BaseModel):
    freed_bytes: int


@router.delete("/api/voice/setup", response_model=RemoveVoiceResponse)
async def remove_voice(request: Request) -> RemoveVoiceResponse:
    """Delete the in-app voice install and free its disk space.

    Text keeps working; voice can be installed again at any time. A voice
    set up by hand (a whisper-cli on the PATH, a Kokoro server) is not
    touched. 409 while an install runs or a file is in use.
    """
    try:
        freed = _manager(request).remove()
    except VoiceInstallError as exc:
        raise ConvsimError(exc.code, exc.message, status_code=409) from exc
    return RemoveVoiceResponse(freed_bytes=max(0, freed))


@router.post("/api/voice/setup/install", response_model=VoiceInstallJobResponse)
async def start_voice_install(
    request: Request, body: StartVoiceInstallRequest
) -> VoiceInstallJobResponse:
    """Start a voice install, or reattach to the one already running."""
    manager = _manager(request)
    if catalog.engine_asset() is None:
        raise ConvsimError("VOICE_UNSUPPORTED", _UNSUPPORTED, status_code=409)

    unknown = [c for c in body.components if c not in catalog.COMPONENTS]
    if unknown:
        raise ConvsimError(
            "VOICE_COMPONENT_UNKNOWN",
            f"Unknown voice component: {', '.join(unknown)}. "
            f"Known components: {', '.join(catalog.COMPONENTS)}.",
            status_code=422,
        )

    components = list(dict.fromkeys(body.components))
    if not components:
        ready = {
            "stt": await _ready(request.app.state.stt_worker),
            "tts": await _ready(request.app.state.tts_worker),
        }
        components = [c for c in catalog.COMPONENTS if not ready[c]] or list(catalog.COMPONENTS)

    return _job_response(manager.start(components))


@router.get("/api/voice/setup/install/{job_id}", response_model=VoiceInstallJobResponse)
async def get_voice_install(request: Request, job_id: int) -> VoiceInstallJobResponse:
    """Progress of one voice install job."""
    job = _manager(request).get(job_id)
    if job is None:
        raise ConvsimError("JOB_NOT_FOUND", f"Voice install job {job_id} not found.", 404)
    return _job_response(job)


@router.delete("/api/voice/setup/install/{job_id}", status_code=204)
async def cancel_voice_install(request: Request, job_id: int) -> None:
    """Cancel a running voice install. Leaves no partial download behind."""
    manager = _manager(request)
    job = manager.get(job_id)
    if job is None:
        raise ConvsimError("JOB_NOT_FOUND", f"Voice install job {job_id} not found.", 404)
    if not manager.cancel(job_id):
        raise ConvsimError(
            "JOB_NOT_CANCELLABLE",
            f"Voice install job {job_id} is already in terminal state '{job.status}'.",
            status_code=409,
        )
