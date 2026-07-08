# SPDX-License-Identifier: Apache-2.0
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from convsim_core.config import ServiceConfig
from convsim_core.errors import (
    ConvsimError,
    convsim_error_handler,
    internal_error_handler,
    request_validation_error_handler,
)
from convsim_core.logging_setup import configure_logging
from convsim_core.routers import diag as diag_router, health, models as models_router, packs as packs_router, sessions as sessions_router, settings as settings_router, sidecar as sidecar_router, stt as stt_router
from convsim_core.routers import vad as vad_router
from convsim_core.runtime import build_runtime
from convsim_core.runtime.sidecar import LlamaCppSidecar
from convsim_core.storage.database import Database
from convsim_core.storage.repositories.settings_repo import load_settings
from convsim_core.stt import build_stt_worker
from convsim_core.vad import build_vad_worker


def create_app(config: ServiceConfig | None = None) -> FastAPI:
    """App factory — create and configure the FastAPI application."""
    if config is None:
        config = ServiceConfig()

    configure_logging(config.log_dir, debug=config.dev_debug)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database.open(config.db_dir)
        app.state.service_config = config
        app.state.db = db
        app.state.app_settings = load_settings(db.connection(), config.data_dir, config.log_dir)
        app.state.runtime = build_runtime(config.runtime_id)
        app.state.stt_worker = build_stt_worker(config.stt_worker_id)
        app.state.vad_worker = build_vad_worker(config.vad_worker_id)
        app.state.sidecar = LlamaCppSidecar(log_dir=config.log_dir)
        yield
        await app.state.sidecar.stop()
        db.close()

    app = FastAPI(title="convsim-core", version="0.1.0", lifespan=lifespan)

    app.add_exception_handler(ConvsimError, convsim_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, internal_error_handler)

    app.include_router(health.router)
    app.include_router(settings_router.router)
    app.include_router(diag_router.router)
    app.include_router(models_router.router)
    app.include_router(sidecar_router.router)
    app.include_router(stt_router.router)
    app.include_router(vad_router.router)
    app.include_router(packs_router.router)
    app.include_router(sessions_router.router)

    return app
