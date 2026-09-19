from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import AuthSession, RefreshToken
from app.auth.security import as_utc, hash_refresh_token, utc_now

from tests.auth.test_auth import bearer


def test_refresh_rotates_token_without_extending_session(
    auth_client: TestClient, tokens: dict[str, str | int], db_session: Session
) -> None:
    auth_session = db_session.scalar(select(AuthSession))
    assert auth_session is not None
    original_expiry = as_utc(auth_session.expires_at)
    response = auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 200
    rotated = response.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]
    assert rotated["access_token"] != tokens["access_token"]
    assert response.headers["cache-control"] == "no-store"
    db_session.expire_all()
    stored = db_session.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(tokens["refresh_token"])))
    assert stored is not None and stored.consumed_at is not None
    assert as_utc(auth_session.expires_at) == original_expiry
    assert auth_client.get("/auth/me", headers=bearer(rotated)).status_code == 200


def test_refresh_replay_revokes_entire_session(
    auth_client: TestClient, tokens: dict[str, str | int], db_session: Session
) -> None:
    rotated = auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).json()
    assert auth_client.get("/auth/me", headers=bearer(rotated)).status_code == 200
    replay = auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert replay.status_code == 401
    assert auth_client.post("/auth/refresh", json={"refresh_token": rotated["refresh_token"]}).status_code == 401
    assert auth_client.get("/auth/me", headers=bearer(rotated)).status_code == 401
    assert auth_client.get("/auth/me", headers=bearer(tokens)).status_code == 401
    db_session.expire_all()
    auth_session = db_session.scalar(select(AuthSession))
    assert auth_session is not None and auth_session.revoked_at is not None


def test_refresh_replay_does_not_revoke_another_login(
    auth_client: TestClient, tokens: dict[str, str | int], registration: dict[str, str]
) -> None:
    other = auth_client.post("/auth/login", json={"email": registration["email"], "password": registration["password"]}).json()
    auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert auth_client.get("/auth/me", headers=bearer(other)).status_code == 200
    assert auth_client.post("/auth/refresh", json={"refresh_token": other["refresh_token"]}).status_code == 200


def test_expired_session_cannot_refresh_or_access(
    auth_client: TestClient, tokens: dict[str, str | int], db_session: Session
) -> None:
    auth_session = db_session.scalar(select(AuthSession))
    assert auth_session is not None
    auth_session.expires_at = utc_now() - timedelta(minutes=1)
    db_session.commit()
    assert auth_client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401
    assert auth_client.get("/auth/me", headers=bearer(tokens)).status_code == 401


def test_token_types_are_not_interchangeable(auth_client: TestClient, tokens: dict[str, str | int]) -> None:
    assert auth_client.post("/auth/refresh", json={"refresh_token": tokens["access_token"]}).status_code == 401
    assert auth_client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}).status_code == 401
    assert auth_client.post("/auth/refresh", json={"refresh_token": "unknown-token"}).status_code == 401


def test_refresh_validation_does_not_echo_token(auth_client: TestClient) -> None:
    value = "synthetic_secret_" * 40
    response = auth_client.post("/auth/refresh", json={"refresh_token": value})
    assert response.status_code == 422
    assert value not in response.text
