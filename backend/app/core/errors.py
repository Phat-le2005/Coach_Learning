import logging

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from app.core.exceptions import ApplicationError

logger = logging.getLogger(__name__)

MATH_SOLUTIONS_ROOT_PATH = "/api/v2"
MATH_SOLUTIONS_ROUTE_PREFIX = "/math-solutions"


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list["ValidationIssue"] | None = None


class ValidationIssue(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: list[ValidationIssue] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, details=details)
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(exclude_none=True),
    )


def apply_math_solutions_no_store(request: Request, response: Response) -> None:
    """Apply private workspace cache policy without affecting other API routes."""
    if request.method == "OPTIONS":
        return

    route_path = str(request.scope.get("path", ""))
    root_path = str(request.scope.get("root_path", "")).rstrip("/")
    candidate_paths = {route_path, request.url.path}
    if root_path and not route_path.startswith(f"{root_path}/"):
        candidate_paths.add(f"{root_path}{route_path}")
    prefix = f"{MATH_SOLUTIONS_ROOT_PATH}{MATH_SOLUTIONS_ROUTE_PREFIX}"
    is_math_solutions_route = any(
        path == prefix or path.startswith(f"{prefix}/") for path in candidate_paths
    )
    if is_math_solutions_route:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Pragma"] = "no-cache"


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    response = error_response(exc.status_code, f"HTTP_{exc.status_code}", message)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    settings = request.app.state.settings
    if settings.app_env != "production":
        details = [
            ValidationIssue(
                field=" -> ".join(str(part) for part in error["loc"]),
                message=str(error["msg"]),
            )
            for error in exc.errors()
        ]
        return error_response(
            422,
            "VALIDATION_ERROR",
            "Request validation failed.",
            details=details,
        )
    # Production never echoes validation input or field-level details.
    return error_response(422, "VALIDATION_ERROR", "Request validation failed.")


async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    settings = request.app.state.settings
    if settings.debug and settings.app_env != "production":
        logger.error(
            "Unexpected application error (%s)",
            type(exc).__name__,
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    else:
        # Exception messages and locals can contain credentials; record only the type.
        logger.error("Unexpected application error (%s)", type(exc).__name__)
    response = error_response(500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred.")
    # ServerErrorMiddleware handles uncaught exceptions outside user middleware,
    # so apply the Math Workspace cache policy directly to its 500 response.
    apply_math_solutions_no_store(request, response)
    # The outer ServerErrorMiddleware bypasses CORSMiddleware for uncaught exceptions.
    origin = request.headers.get("origin")
    if origin == request.app.state.settings.frontend_origin:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApplicationError, application_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unexpected_exception_handler)


async def application_exception_handler(request: Request, exc: ApplicationError) -> JSONResponse:
    response = error_response(exc.status_code, exc.code, exc.message)
    response.headers.update(exc.headers)
    return response
