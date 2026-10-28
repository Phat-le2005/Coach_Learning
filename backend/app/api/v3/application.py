from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import Settings
from app.core.errors import ErrorResponse, register_exception_handlers
from app.math_solutions.ai_review_router import router as ai_review_router
from app.math_paper.router import router as paper_router
from app.math_canvas.router import router as math_canvas_router


def create_v3_app(settings: Settings) -> FastAPI:
    application = FastAPI(
        title="EduMS Math AI Review V3 API",
        version="3.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.state.settings = settings
    register_exception_handlers(application)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"
        return response

    application.include_router(ai_review_router)
    application.include_router(paper_router)
    application.include_router(math_canvas_router)
    return application
