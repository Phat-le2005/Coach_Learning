"""Independent API v3 surface for provisional AI step review."""

from fastapi import FastAPI, Request, Response

from app.core.config import Settings
from app.core.errors import ErrorResponse, register_exception_handlers
from app.math_solutions.ai_review_router import router as ai_review_router


def create_v3_app(settings: Settings) -> FastAPI:
    application = FastAPI(
        title=f"{settings.app_name} API v3",
        version="3.0.0",
        description="Provisional answer-grounded AI review; never final grade or mastery evidence.",
        debug=False,
        responses={422: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )
    application.state.settings = settings
    register_exception_handlers(application)

    @application.middleware("http")
    async def disable_review_caching(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    application.include_router(ai_review_router)
    return application