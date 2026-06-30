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
from convsim_core.routers import health, settings as settings_router
from convsim_core.storage.database import Database
from convsim_core.storage.repositories.settings_repo import load_settings


def create_app(config: ServiceConfig | None = None) -> FastAPI:
    """App factory — create and configure the FastAPI application."""
    if config is None:
        config = ServiceConfig()

    configure_logging(config.log_dir)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        db = Database.open(config.db_dir)
        app.state.service_config = config
        app.state.db = db
        app.state.app_settings = load_settings(db.connection(), config.data_dir, config.log_dir)
        yield
        db.close()

    app = FastAPI(title="convsim-core", version="0.1.0", lifespan=lifespan)

    app.add_exception_handler(ConvsimError, convsim_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, internal_error_handler)

    app.include_router(health.router)
    app.include_router(settings_router.router)

    return app
