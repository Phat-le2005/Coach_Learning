import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from typing import Literal
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.core.exceptions import ApplicationError

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4, type=Type.ID)


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    # SQLite test drivers omit timezone info; production PostgreSQL returns it.
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


@lru_cache
def dummy_password_hash() -> str:
    return hash_password(secrets.token_urlsafe(32))


def new_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def authentication_error(code: str = "INVALID_TOKEN") -> ApplicationError:
    return ApplicationError(
        401,
        code,
        "Invalid credentials." if code == "INVALID_CREDENTIALS" else "Invalid or expired token.",
        headers={"WWW-Authenticate": "Bearer"},
    )


class AccessClaims(BaseModel):
    sub: UUID
    sid: UUID
    jti: UUID
    type: Literal["access"]


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.secret = settings.jwt_secret_key.get_secret_value()
        if len(self.secret.encode("utf-8")) < 32:
            raise ApplicationError(503, "AUTH_NOT_CONFIGURED", "Authentication is not configured.")

    def issue_access_token(
        self, user_id: UUID, session_id: UUID, session_expires_at: datetime, now: datetime
    ) -> tuple[str, int]:
        expires_at = min(
            now + timedelta(minutes=self.settings.access_token_expire_minutes),
            as_utc(session_expires_at),
        )
        claims = {
            "sub": str(user_id),
            "sid": str(session_id),
            "jti": str(uuid4()),
            "type": "access",
            "iss": self.settings.jwt_issuer,
            "aud": self.settings.jwt_audience,
            "iat": int(now.timestamp()),
            "nbf": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(claims, self.secret, algorithm="HS256")
        return token, max(0, int(expires_at.timestamp()) - int(now.timestamp()))

    def decode_access_token(self, token: str) -> AccessClaims:
        try:
            payload = jwt.decode(
                token,
                self.secret,
                algorithms=["HS256"],
                audience=self.settings.jwt_audience,
                issuer=self.settings.jwt_issuer,
                options={"require": ["sub", "sid", "jti", "type", "iss", "aud", "iat", "nbf", "exp"]},
            )
            return AccessClaims.model_validate(payload)
        except (jwt.InvalidTokenError, ValidationError, ValueError, TypeError, OverflowError):
            raise authentication_error() from None
