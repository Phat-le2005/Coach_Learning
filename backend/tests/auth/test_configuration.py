import secrets

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.application import create_app
from app.core.config import Settings
from app.database.session import get_db


def test_empty_signing_key_disables_authentication(db_session: Session) -> None:
    configured = Settings(
        _env_file=None, database_name="test_db", database_user="test_user", jwt_secret_key=""
    )
    application = create_app(configured)
    application.dependency_overrides[get_db] = lambda: db_session
    with TestClient(application) as client:
        assert client.get("/health").status_code == 200
        response = client.get("/auth/me")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


def test_short_signing_key_is_rejected_without_echoing_input() -> None:
    key = secrets.token_hex(8)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_name="test_db", database_user="test_user", jwt_secret_key=key)
    assert key not in str(error.value)
