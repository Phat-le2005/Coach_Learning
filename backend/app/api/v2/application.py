from fastapi import FastAPI

from app.api.v2.router import api_v2_router
from app.core.config import Settings
from app.core.errors import ErrorResponse, register_exception_handlers

API_V2_VERSION = "2.0.0"


def create_v2_app(settings: Settings) -> FastAPI:
    application = FastAPI(
        title=f"{settings.app_name} API v2",
        version=API_V2_VERSION,
        description="EduMS API v2 for the step-by-step mathematics workspace.",
        debug=False,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        responses={
            422: {"model": ErrorResponse},
            500: {"model": ErrorResponse},
        },
    )
    application.state.settings = settings
    register_exception_handlers(application)
    application.include_router(api_v2_router)
    return application