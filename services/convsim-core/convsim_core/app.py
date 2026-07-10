# SPDX-License-Identifier: Apache-2.0
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from convsim_core.config import ServiceConfig
from convsim_core.data_migration import migrate, needs_migration
from convsim_core.errors import (
    ConvsimError,
    convsim_error_handler,
    internal_error_handler,
    request_validation_error_handler,
)
from convsim_core.logging_setup import configure_logging
from convsim_core.packs.seeder import seed_official_packs
from convsim_core.paths import legacy_convsim_dir, platform_data_root
from convsim_core.routers import cloud_settings as cloud_settings_router, diag as diag_router, health, logbook as logbook_router, models as models_router, packs as packs_router, preflight as preflight_router, privacy as privacy_router, scenarios as scenarios_router, sessions as sessions_router, settings as settings_router, sidecar as sidecar_router, stt as stt_router, tts as tts_router, vad as vad_router, workbench as workbench_router
from convsim_core.runtime import build_runtime
from convsim_core.runtime.sidecar import LlamaCppSidecar
from convsim_core.runtime.kokoro_sidecar import KokoroSidecar
from convsim_core.runtime.supervisor import ProcessSupervisor
from convsim_core.storage.database import Database
from convsim_core.storage.repositories.settings_repo import load_settings
from convsim_core.stt import build_stt_worker
from convsim_core.tts import build_tts_worker
from convsim_core.vad import build_vad_worker


# Origins the packaged Tauri desktop shell serves its web UI from. In a bundled
# build the UI loads from tauri://localhost (macOS/Linux) or https://tauri.localhost
# (Windows) and calls the API cross-origin at http://127.0.0.1:<port>, so the
# native webview enforces CORS and blocks the responses unless the server opts in.
# In dev mode the Vite proxy keeps API traffic same-origin, so these are only
# needed for packaged builds. Listing explicit local webview origins keeps the
# local-first promise intact — the server still binds to 127.0.0.1 and no LAN
# origin is granted access.
_TAURI_WEBVIEW_ORIGINS = [
    "tauri://localhost",
    "http://tauri.localhost",
    "https://tauri.localhost",
]


def create_app(config: ServiceConfig | None = None) -> FastAPI:
    """App factory — create and configure the FastAPI application."""
    if config is None:
        config = ServiceConfig()

    # Migrate user data from the legacy ~/.convsim directory if this is the
    # first launch with platform-specific paths and old data exists.  This must
    # run *before* configure_logging(), which eagerly creates <root>/logs and
    # would otherwise make the new platform root non-empty — causing
    # needs_migration() to conclude the root is already in use and skip the
    # migration entirely.
    new_root = platform_data_root()
    legacy = legacy_convsim_dir()
    if needs_migration(new_root, legacy):
        migrate(new_root, legacy)

    configure_logging(config.log_dir, debug=config.dev_debug)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database.open(config.db_dir)

        # Create mutable user-data directories eagerly so OS file-manager
        # shortcuts work on a fresh install before any data is written.
        # Also place a .nosteamcloudpath marker in each directory; this signals
        # to Steam (and any sync tools that honour it) that the directory
        # contains user-private data that must not be uploaded to Steam Cloud.
        # db_dir (conversation transcripts + prompts) and models_dir (model
        # files) are included deliberately: issue #221 names both as data that
        # must never reach Steam Cloud.
        for _dir in (
            config.data_dir,
            config.db_dir,
            config.log_dir,
            config.packs_dir,
            config.exports_dir,
            config.cache_dir,
            config.crash_bundles_dir,
            config.models_dir,
        ):
            _p = Path(_dir)
            _p.mkdir(parents=True, exist_ok=True)
            (_p / ".nosteamcloudpath").touch(exist_ok=True)
        app.state.service_config = config
        app.state.db = db
        app.state.models_dir = config.models_dir
        app.state.cancel_events = {}   # install_id → asyncio.Event (per-app)
        app.state.app_settings = load_settings(db.connection(), config.data_dir, config.log_dir)
        app.state.runtime = build_runtime(config.runtime_id)
        app.state.stt_worker = build_stt_worker(config.stt_worker_id)
        app.state.tts_worker = build_tts_worker(config.tts_worker_id)
        app.state.vad_worker = build_vad_worker(config.vad_worker_id)
        sidecar = LlamaCppSidecar(log_dir=config.log_dir)
        app.state.sidecar = sidecar
        kokoro_sidecar = KokoroSidecar(log_dir=config.log_dir)
        app.state.kokoro_sidecar = kokoro_sidecar
        supervisor = ProcessSupervisor()
        supervisor.register(sidecar)
        supervisor.register(kokoro_sidecar)
        app.state.supervisor = supervisor
        seed_official_packs(config, db.connection())
        yield
        await supervisor.stop_all()
        db.close()

    app = FastAPI(title="convsim-core", version="0.1.0", lifespan=lifespan)

    # Allow the packaged Tauri desktop webview to read cross-origin API responses.
    # No cookies/credentials are used, so credentials stay disabled and origins
    # are pinned to the local webview schemes only.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_TAURI_WEBVIEW_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.add_exception_handler(ConvsimError, convsim_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, internal_error_handler)

    app.include_router(health.router)
    app.include_router(preflight_router.router)
    app.include_router(settings_router.router)
    app.include_router(cloud_settings_router.router)
    app.include_router(privacy_router.router)
    app.include_router(diag_router.router)
    app.include_router(models_router.router)
    app.include_router(sidecar_router.router)
    app.include_router(stt_router.router)
    app.include_router(tts_router.router)
    app.include_router(vad_router.router)
    app.include_router(packs_router.router)
    app.include_router(scenarios_router.router)
    app.include_router(sessions_router.router)
    app.include_router(workbench_router.router)
    app.include_router(logbook_router.router)

    return app
