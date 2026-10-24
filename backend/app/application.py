import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.v2.application import create_v2_app
from app.api.v3.application import create_v3_app
from app.api.version import API_VERSION
from app.core.config import Settings, get_settings
from app.core.errors import ErrorResponse, register_exception_handlers
from app.core.logging import configure_logging
from app.database.session import dispose_engine

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings: Settings = application.state.settings
    configure_logging(settings.debug and settings.app_env != "production")
    logger.info("%s startup (environment=%s)", settings.app_name, settings.app_env)
    try:
        yield
    finally:
        dispose_engine()
        logger.info("%s shutdown", settings.app_name)


def create_app(settings: Settings | None = None) -> FastAPI:
    configuration = settings if settings is not None else get_settings()
    application = FastAPI(
        title=configuration.app_name,
        version=API_VERSION,
        description="EduMS education management and university entrance exam support API.",
        # Always use the structured exception response, even when DEBUG=true.
        debug=False,
        lifespan=lifespan,
        responses={
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    application.state.settings = configuration
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[configuration.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type", "Authorization"],
    )
    register_exception_handlers(application)
    application.include_router(api_router)
    v2_application = create_v2_app(configuration)
    # Keep test/runtime dependency replacements consistent across the mount boundary.
    v2_application.dependency_overrides = application.dependency_overrides
    application.mount("/api/v2", v2_application)
    v3_application = create_v3_app(configuration)
    v3_application.dependency_overrides = application.dependency_overrides
    application.mount("/api/v3", v3_application)
    return application
