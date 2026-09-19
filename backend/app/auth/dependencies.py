from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import authentication_error
from app.auth.service import AuthService
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.database.session import get_db
from app.users.models import Role, User

bearer_scheme = HTTPBearer(auto_error=False)


def get_auth_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_auth_service(
    session: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_auth_settings)],
) -> AuthService:
    return AuthService(session, settings)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> User:
    if credentials is None:
        raise authentication_error()
    return service.current_user(credentials.credentials)


def require_any_role(*roles: Role) -> Callable[..., User]:
    if not roles:
        raise ValueError("At least one role is required")
    if any(not isinstance(role, Role) for role in roles):
        raise TypeError("Roles must be Role enum values")
    allowed_roles = frozenset(roles)

    def authorize(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in allowed_roles:
            raise ApplicationError(403, "FORBIDDEN", "You do not have permission to access this resource.")
        return user

    return authorize


def require_role(role: Role) -> Callable[..., User]:
    return require_any_role(role)
