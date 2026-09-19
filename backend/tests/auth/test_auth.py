from datetime import timedelta
import logging
import secrets
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.models import AuthSession, RefreshToken
from app.auth.security import hash_refresh_token, utc_now, verify_password
from app.core.config import Settings
from app.users.models import Role, User


def bearer(tokens: dict[str, str | int]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_register(auth_client: TestClient, registration: dict[str, str], db_session: Session) -> None:
    registration.update(email="Student@Example.COM", full_name="  Nguyễn Minh Anh  ")
    response = auth_client.post("/auth/register", json=registration)
    assert response.status_code == 201
    body = response.json()
    assert UUID(body["id"])
    assert body["email"] == "student@example.com"
    assert body["full_name"] == "Nguyễn Minh Anh"
    assert body["role"] == "STUDENT" and body["is_active"] is True
    assert body["created_at"] and body["updated_at"]
    assert "password_hash" not in body and "password" not in body
    user = db_session.scalar(select(User))
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert verify_password(registration["password"], user.password_hash)
    assert registration["password"] not in user.password_hash


def test_duplicate_email_is_case_insensitive(
    auth_client: TestClient, registration: dict[str, str], db_session: Session
) -> None:
    assert auth_client.post("/auth/register", json=registration).status_code == 201
    registration["email"] = "STUDENT@EXAMPLE.COM"
    response = auth_client.post("/auth/register", json=registration)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"
    assert db_session.scalar(select(func.count()).select_from(User)) == 1


@pytest.mark.parametrize("role", [Role.TEACHER, Role.PARENT, Role.ADMIN])
def test_public_registration_cannot_assign_privileged_roles(
    auth_client: TestClient, registration: dict[str, str], db_session: Session, role: Role
) -> None:
    response = auth_client.post("/auth/register", json={**registration, "role": role.value})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ROLE_NOT_ALLOWED"
    assert db_session.scalar(select(func.count()).select_from(User)) == 0


@pytest.mark.parametrize(
    "change",
    [{"password": "short"}, {"password": "x" * 129}, {"email": "invalid"}, {"full_name": "  "}, {"role": "UNKNOWN"}, {"is_active": False}],
)
def test_register_validation(auth_client: TestClient, registration: dict[str, str], change: dict[str, object]) -> None:
    response = auth_client.post("/auth/register", json={**registration, **change})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert registration["password"] not in response.text


def test_successful_login_returns_tokens_and_only_persists_refresh_hash(
    auth_client: TestClient,
    registration: dict[str, str],
    tokens: dict[str, str | int],
    db_session: Session,
    settings: Settings,
) -> None:
    assert tokens["token_type"] == "bearer"
    assert 0 < tokens["expires_in"] <= 900
    assert tokens["access_token"] != tokens["refresh_token"]
    claims = jwt.decode(
        tokens["access_token"], settings.jwt_secret_key.get_secret_value(), algorithms=["HS256"],
        audience=settings.jwt_audience, issuer=settings.jwt_issuer,
    )
    user = db_session.scalar(select(User))
    assert user is not None and claims["sub"] == str(user.id)
    assert claims["type"] == "access" and "role" not in claims
    stored = db_session.scalar(select(RefreshToken))
    assert stored is not None and stored.token_hash == hash_refresh_token(tokens["refresh_token"])
    assert stored.token_hash != tokens["refresh_token"]
    response = auth_client.post("/auth/login", json={"email": registration["email"].upper(), "password": registration["password"]})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("failure", ["password", "email", "inactive"])
def test_login_failure_has_uniform_response(
    auth_client: TestClient, registration: dict[str, str], db_session: Session, failure: str
) -> None:
    assert auth_client.post("/auth/register", json=registration).status_code == 201
    credentials = {"email": registration["email"], "password": registration["password"]}
    if failure == "password":
        credentials["password"] = "Wrong-Synthetic-Password"
    elif failure == "email":
        credentials["email"] = "missing@example.com"
    else:
        user = db_session.scalar(select(User))
        assert user is not None
        user.is_active = False
        db_session.commit()
    response = auth_client.post("/auth/login", json=credentials)
    assert response.status_code == 401
    assert response.json() == {"error": {"code": "INVALID_CREDENTIALS", "message": "Invalid credentials."}}
    assert response.headers["www-authenticate"] == "Bearer"
    assert db_session.scalar(select(func.count()).select_from(AuthSession)) == 0


@pytest.mark.parametrize("authorization", [None, "Bearer invalid-token", "Basic invalid", "Bearer"])
def test_protected_endpoint_rejects_missing_or_invalid_token(auth_client: TestClient, authorization: str | None) -> None:
    response = auth_client.get("/auth/me", headers={"Authorization": authorization} if authorization else {})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_TOKEN"
    assert response.headers["www-authenticate"] == "Bearer"


def test_current_user(auth_client: TestClient, tokens: dict[str, str | int]) -> None:
    response = auth_client.get("/auth/me", headers=bearer(tokens))
    assert response.status_code == 200
    assert response.json()["email"] == "student@example.com"
    assert "password_hash" not in response.json()
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("mutation", ["expired", "issuer", "audience", "future", "type", "missing_exp", "subject", "session", "wrong_key", "algorithm"])
def test_invalid_jwt_claims_are_rejected(
    auth_client: TestClient, tokens: dict[str, str | int], settings: Settings, mutation: str
) -> None:
    secret = settings.jwt_secret_key.get_secret_value()
    claims = jwt.decode(tokens["access_token"], secret, algorithms=["HS256"], audience=settings.jwt_audience, issuer=settings.jwt_issuer)
    key, algorithm = secret, "HS256"
    if mutation == "expired":
        claims["exp"] = int((utc_now() - timedelta(minutes=1)).timestamp())
    elif mutation == "issuer":
        claims["iss"] = "wrong-issuer"
    elif mutation == "audience":
        claims["aud"] = "wrong-audience"
    elif mutation == "future":
        claims["nbf"] = int((utc_now() + timedelta(hours=1)).timestamp())
    elif mutation == "type":
        claims["type"] = "refresh"
    elif mutation == "missing_exp":
        del claims["exp"]
    elif mutation == "subject":
        claims["sub"] = str(uuid4())
    elif mutation == "session":
        claims["sid"] = str(uuid4())
    elif mutation == "wrong_key":
        key = secrets.token_urlsafe(48)
    else:
        key, algorithm = "", "none"
    token = jwt.encode(claims, key, algorithm=algorithm)
    response = auth_client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


def test_secrets_are_not_logged(
    auth_client: TestClient, registration: dict[str, str], caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        auth_client.post("/auth/register", json=registration)
        response = auth_client.post("/auth/login", json={"email": registration["email"], "password": registration["password"]})
        tokens = response.json()
        auth_client.get("/auth/me", headers=bearer(tokens))
        auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    for secret in (registration["password"], tokens["access_token"], tokens["refresh_token"]):
        assert secret not in caplog.text


def test_auth_cors_supports_post_and_authorization(auth_client: TestClient) -> None:
    response = auth_client.options(
        "/auth/login",
        headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,authorization"},
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "Authorization" in response.headers["access-control-allow-headers"]
