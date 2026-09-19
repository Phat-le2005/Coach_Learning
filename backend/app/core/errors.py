import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException

from app.core.exceptions import ApplicationError

logger = logging.getLogger(__name__)


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status_code, content=body.model_dump())


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "The request could not be completed."
    response = error_response(exc.status_code, f"HTTP_{exc.status_code}", message)
    if exc.headers:
        response.headers.update(exc.headers)
    return response


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Validation input can contain passwords or tokens; never echo it back.
    return error_response(422, "VALIDATION_ERROR", "Request validation failed.")


async def unexpected_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Exception messages and locals can contain credentials; record only the type.
    logger.error("Unexpected application error (%s)", type(exc).__name__)
    response = error_response(500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred.")
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
