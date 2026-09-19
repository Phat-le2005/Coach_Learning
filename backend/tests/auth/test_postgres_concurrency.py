"""Optional real PostgreSQL tests; every case owns and removes a separate schema."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.models import AuthSession
from app.auth.schemas import LoginRequest, RegisterRequest, TokenPair
from app.auth.service import AuthService
from app.core.config import Settings
from app.core.exceptions import ApplicationError
from app.users.models import User
from app.users.schemas import UserCreate
from app.users.service import UserService


@pytest.mark.parametrize("mode", ["same_token", "old_and_current"])
def test_concurrent_refresh_replay_revokes_session(
    postgres_engine: Engine, settings: Settings, registration: dict[str, str], mode: str
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    with factory() as session:
        service = AuthService(session, settings)
        service.register(RegisterRequest(**registration))
        original = service.login(LoginRequest(email=registration["email"], password=registration["password"]))
        other = service.refresh(original.refresh_token) if mode == "old_and_current" else original
    barrier = Barrier(2)

    def refresh(token: str) -> tuple[int, TokenPair | None]:
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                return 200, AuthService(session, settings).refresh(token)
            except ApplicationError as exc:
                session.rollback()
                return exc.status_code, None

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(refresh, original.refresh_token)
        second = pool.submit(refresh, other.refresh_token)
        results = [first.result(timeout=20), second.result(timeout=20)]
    codes = sorted(code for code, pair in results)
    if mode == "same_token":
        assert codes == [200, 401]
    else:
        assert codes in ([200, 401], [401, 401])
    with factory() as session:
        auth_session = session.scalar(select(AuthSession))
        assert auth_session is not None and auth_session.revoked_at is not None
        service = AuthService(session, settings)
        for pair in [original, other, *(pair for code, pair in results if pair is not None)]:
            with pytest.raises(ApplicationError) as error:
                service.current_user(pair.access_token)
            assert error.value.status_code == 401
            with pytest.raises(ApplicationError):
                service.refresh(pair.refresh_token)


def test_concurrent_duplicate_registration_is_rejected(
    postgres_engine: Engine, registration: dict[str, str]
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    barrier = Barrier(2)

    def register() -> int:
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                UserService(session).create_user(UserCreate(**registration))
                return 201
            except ApplicationError as exc:
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(register), pool.submit(register)]
        assert sorted(result.result(timeout=20) for result in results) == [201, 409]
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 1
