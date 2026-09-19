from collections.abc import Callable, Iterator
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role, require_role
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.fixture
def auth_client(db_app: FastAPI) -> Iterator[TestClient]:
    application = db_app
    for role in Role:
        dependency = require_role(role)

        def protected(user: Annotated[User, Depends(dependency)]) -> dict[str, str]:
            return {"role": user.role.value}

        application.add_api_route(f"/test/role/{role.value}", protected, methods=["GET"])

    @application.get("/test/teaching")
    def teaching(user: Annotated[User, Depends(require_any_role(Role.TEACHER, Role.ADMIN))]) -> dict[str, str]:
        return {"role": user.role.value}

    with TestClient(application) as client:
        yield client


@pytest.fixture
def registration() -> dict[str, str]:
    return {
        "email": "student@example.com",
        "password": "Synthetic-Test-Password-2026!",
        "full_name": "Nguyễn Minh Anh",
    }


@pytest.fixture
def tokens(auth_client: TestClient, registration: dict[str, str]) -> dict[str, str | int]:
    assert auth_client.post("/auth/register", json=registration).status_code == 201
    response = auth_client.post("/auth/login", json={"email": registration["email"], "password": registration["password"]})
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def user_factory(db_session: Session, registration: dict[str, str]) -> Callable[[Role], User]:
    def create(role: Role) -> User:
        return UserService(db_session).create_user(UserCreate(**registration, role=role))

    return create
