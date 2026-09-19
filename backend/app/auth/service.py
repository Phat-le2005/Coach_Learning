import logging
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.models import AuthSession, RefreshToken
from app.auth.schemas import LoginRequest, RegisterRequest, TokenPair
from app.auth.security import (
    TokenService,
    as_utc,
    authentication_error,
    dummy_password_hash,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    password_hasher,
    utc_now,
    verify_password,
)
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.users.models import Role, User
from app.users.service import UserService

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.tokens = TokenService(settings)
        self.users = UserService(session)

    def register(self, data: RegisterRequest) -> User:
        if data.role != Role.STUDENT:
            raise ApplicationError(403, "ROLE_NOT_ALLOWED", "Public registration only creates STUDENT accounts.")
        return self.users.create_user(data)

    def login(self, data: LoginRequest) -> TokenPair:
        user = self.users.find_by_email(str(data.email))
        password = data.password.get_secret_value()
        stored_hash = user.password_hash if user is not None else dummy_password_hash()
        valid = verify_password(password, stored_hash)
        if user is None or not valid or not user.is_active:
            raise authentication_error("INVALID_CREDENTIALS")
        now = utc_now()
        if password_hasher.check_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        auth_session = AuthSession(
            user_id=user.id,
            expires_at=now + timedelta(days=self.settings.refresh_token_expire_days),
        )
        self.session.add(auth_session)
        self.session.flush()
        refresh_token = new_refresh_token()
        self.session.add(RefreshToken(session_id=auth_session.id, token_hash=hash_refresh_token(refresh_token)))
        access_token, expires_in = self.tokens.issue_access_token(user.id, auth_session.id, auth_session.expires_at, now)
        self.session.commit()
        logger.info("Login successful (user_id=%s)", user.id)
        return TokenPair(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)

    def refresh(self, raw_token: str) -> TokenPair:
        token_hash = hash_refresh_token(raw_token)
        existing = self.session.scalar(select(RefreshToken).where(RefreshToken.token_hash == token_hash))
        if existing is None:
            raise authentication_error()
        # Lock the family row first: rotations/replays of ANY token in this session serialize.
        auth_session = self.session.scalar(
            select(AuthSession)
            .where(AuthSession.id == existing.session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = utc_now()
        if auth_session is None or auth_session.revoked_at is not None or as_utc(auth_session.expires_at) <= now:
            raise authentication_error()
        # Refresh identity-map state after acquiring the session lock.
        existing = self.session.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == token_hash)
            .execution_options(populate_existing=True)
        )
        if existing is None:
            raise authentication_error()
        if existing.consumed_at is not None:
            auth_session.revoked_at = now
            # Persist replay revocation even though the HTTP operation returns 401.
            self.session.commit()
            logger.warning("Refresh token replay; session revoked (session_id=%s)", auth_session.id)
            raise authentication_error()
        user = self.session.get(User, auth_session.user_id)
        if user is None or not user.is_active:
            raise authentication_error()
        existing.consumed_at = now
        refresh_token = new_refresh_token()
        self.session.add(RefreshToken(session_id=auth_session.id, token_hash=hash_refresh_token(refresh_token)))
        access_token, expires_in = self.tokens.issue_access_token(user.id, auth_session.id, auth_session.expires_at, now)
        self.session.commit()
        return TokenPair(access_token=access_token, refresh_token=refresh_token, expires_in=expires_in)

    def current_user(self, access_token: str) -> User:
        claims = self.tokens.decode_access_token(access_token)
        auth_session = self.session.get(AuthSession, claims.sid)
        if (
            auth_session is None
            or auth_session.user_id != claims.sub
            or auth_session.revoked_at is not None
            or as_utc(auth_session.expires_at) <= utc_now()
        ):
            raise authentication_error()
        user = self.session.get(User, claims.sub)
        if user is None or not user.is_active:
            raise authentication_error()
        return user
