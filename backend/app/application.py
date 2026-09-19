import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
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
        version="0.13.0",
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
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Accept", "Content-Type", "Authorization"],
    )
    register_exception_handlers(application)
    application.include_router(api_router)
    return application
