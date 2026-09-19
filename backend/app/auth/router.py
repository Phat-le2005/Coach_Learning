from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.auth.dependencies import get_auth_service, get_current_user
from app.auth.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenPair
from app.auth.service import AuthService
from app.core.errors import ErrorResponse
from app.users.models import User
from app.users.schemas import UserRead

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
)


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: RegisterRequest, service: Annotated[AuthService, Depends(get_auth_service)]) -> User:
    return service.register(data)


@router.post("/login", response_model=TokenPair)
def login(
    data: LoginRequest, response: Response, service: Annotated[AuthService, Depends(get_auth_service)]
) -> TokenPair:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return service.login(data)


@router.post("/refresh", response_model=TokenPair)
def refresh(
    data: RefreshRequest, response: Response, service: Annotated[AuthService, Depends(get_auth_service)]
) -> TokenPair:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return service.refresh(data.refresh_token.get_secret_value())


@router.get("/me", response_model=UserRead)
def me(user: Annotated[User, Depends(get_current_user)], response: Response) -> User:
    response.headers["Cache-Control"] = "no-store"
    return user
