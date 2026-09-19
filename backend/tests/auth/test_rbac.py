from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_any_role, require_role
from app.users.models import Role, User
from tests.auth.test_auth import bearer


@pytest.mark.parametrize("role", list(Role))
def test_role_permission_matrix(
    auth_client: TestClient, user_factory: Callable[[Role], User], registration: dict[str, str], role: Role
) -> None:
    user_factory(role)
    tokens = auth_client.post("/auth/login", json={"email": registration["email"], "password": registration["password"]}).json()
    for required in Role:
        response = auth_client.get(f"/test/role/{required.value}", headers=bearer(tokens))
        assert response.status_code == (200 if role == required else 403)
        if role != required:
            assert response.json()["error"]["code"] == "FORBIDDEN"


@pytest.mark.parametrize("role", list(Role))
def test_require_any_role(
    auth_client: TestClient, user_factory: Callable[[Role], User], registration: dict[str, str], role: Role
) -> None:
    user_factory(role)
    tokens = auth_client.post("/auth/login", json={"email": registration["email"], "password": registration["password"]}).json()
    response = auth_client.get("/test/teaching", headers=bearer(tokens))
    assert response.status_code == (200 if role in (Role.TEACHER, Role.ADMIN) else 403)


def test_protected_role_endpoint_requires_authentication(auth_client: TestClient) -> None:
    assert auth_client.get("/test/role/ADMIN").status_code == 401
    assert auth_client.get("/test/teaching").status_code == 401


def test_role_changes_and_deactivation_apply_to_existing_tokens(
    auth_client: TestClient, tokens: dict[str, str | int], db_session: Session
) -> None:
    assert auth_client.get("/test/role/ADMIN", headers=bearer(tokens)).status_code == 403
    user = db_session.scalar(select(User))
    assert user is not None
    user.role = Role.ADMIN
    db_session.commit()
    assert auth_client.get("/test/role/ADMIN", headers=bearer(tokens)).status_code == 200
    assert auth_client.get("/auth/me", headers=bearer(tokens)).json()["role"] == "ADMIN"
    user.role = Role.STUDENT
    db_session.commit()
    assert auth_client.get("/test/role/ADMIN", headers=bearer(tokens)).status_code == 403
    user.is_active = False
    db_session.commit()
    assert auth_client.get("/auth/me", headers=bearer(tokens)).status_code == 401
    assert auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_authorization_factory_rejects_empty_or_invalid_roles() -> None:
    with pytest.raises(ValueError):
        require_any_role()
    with pytest.raises(TypeError):
        require_role("ADMIN")
