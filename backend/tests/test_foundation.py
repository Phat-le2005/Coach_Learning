import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import configure_logging
from app.application import create_app


def test_database_url_handles_reserved_password_characters() -> None:
    configured = Settings(
        _env_file=None,
        database_name="edums_test",
        database_user="test_user",
        database_password="synthetic@:/?#%password",
    )
    url = configured.database_url
    assert url.password == "synthetic@:/?#%password"
    assert url.drivername == "postgresql+psycopg"
    assert "synthetic" not in repr(configured)
    assert "synthetic" not in str(url)


def test_database_settings_come_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_HOST", "db.example.test")
    monkeypatch.setenv("DATABASE_PORT", "5544")
    monkeypatch.setenv("DATABASE_NAME", "custom_db")
    monkeypatch.setenv("DATABASE_USER", "custom_user")
    monkeypatch.setenv("DATABASE_PASSWORD", "synthetic_password")
    configured = Settings(_env_file=None)
    assert configured.database_url.host == "db.example.test"
    assert configured.database_url.port == 5544
    assert configured.database_url.database == "custom_db"
    assert configured.database_url.username == "custom_user"


def test_default_test_environment_has_required_database_settings() -> None:
    configured = Settings(_env_file=None)

    assert configured.app_env == "test"
    assert configured.database_name == "edums_test"
    assert configured.database_user == "test_user"


def test_database_name_and_user_are_required_without_test_fixture_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_NAME", raising=False)
    monkeypatch.delenv("DATABASE_USER", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_frontend_url_requires_an_origin() -> None:
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            database_name="test_db",
            database_user="test_user",
            frontend_url="http://localhost:3000/student",
        )


def test_unknown_route_uses_error_envelope(client: TestClient) -> None:
    response = client.get("/missing")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "HTTP_404", "message": "Not Found"}}


def test_validation_does_not_echo_input(settings: Settings) -> None:
    application = create_app(settings)

    @application.get("/test-validation")
    def validation_route(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(application) as client:
        response = client.get("/test-validation", params={"value": "synthetic_secret"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["details"] == [
        {
            "field": "query -> value",
            "message": "Input should be a valid integer, unable to parse string as an integer",
        }
    ]
    assert "synthetic_secret" not in response.text


def test_validation_details_are_hidden_in_production(settings: Settings) -> None:
    production = settings.model_copy(update={"app_env": "production"})
    application = create_app(production)

    @application.get("/test-validation")
    def validation_route(value: int) -> dict[str, int]:
        return {"value": value}

    with TestClient(application) as client:
        response = client.get("/test-validation", params={"value": "synthetic_secret"})

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "Request validation failed.",
        }
    }
    assert "synthetic_secret" not in response.text


def test_unexpected_error_is_safe_in_production(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    production = settings.model_copy(update={"app_env": "production", "debug": False})
    application: FastAPI = create_app(production)

    @application.get("/test-error")
    def error_route() -> None:
        raise RuntimeError("synthetic_secret_must_not_be_exposed")

    with caplog.at_level(logging.ERROR):
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.get("/test-error", headers={"Origin": settings.frontend_origin})
    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected error occurred."}
    }
    assert response.headers["access-control-allow-origin"] == settings.frontend_origin
    assert "RuntimeError" in caplog.text
    assert "synthetic_secret" not in caplog.text + response.text
    assert "Traceback" not in response.text


def test_cors_allows_configured_origin_only() -> None:
    configured = Settings(
        _env_file=None,
        database_name="test_db",
        database_user="test_user",
        frontend_url="http://localhost:3300",
    )
    with TestClient(create_app(configured)) as client:
        allowed = client.get("/health", headers={"Origin": "http://localhost:3300"})
        denied = client.get("/health", headers={"Origin": "http://untrusted.example"})
        preflight = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3300",
                "Access-Control-Request-Method": "GET",
            },
        )
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:3300"
    assert "access-control-allow-origin" not in denied.headers
    assert preflight.status_code == 200


def test_uvicorn_exception_logging_does_not_expose_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging()
    logger = logging.getLogger("uvicorn.error")
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        try:
            raise RuntimeError("synthetic_secret")
        except RuntimeError:
            logger.exception("Exception in ASGI application")
    assert "RuntimeError" in caplog.text
    assert "synthetic_secret" not in caplog.text


def test_debug_logging_preserves_traceback(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging(debug=True)
    logger = logging.getLogger("uvicorn.error")
    with caplog.at_level(logging.ERROR, logger="uvicorn.error"):
        try:
            raise RuntimeError("development diagnostic")
        except RuntimeError:
            logger.exception("Exception in ASGI application")

    record = caplog.records[-1]
    assert record.exc_info is not None
    assert "development diagnostic" in caplog.text


def test_production_rejects_empty_jwt_secret() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            database_name="test_db",
            database_user="test_user",
            jwt_secret_key="",
        )
    assert "JWT_SECRET_KEY must contain at least 32 bytes in production" in str(exc_info.value)


def test_production_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            app_env="production",
            debug=False,
            database_name="test_db",
            database_user="test_user",
            jwt_secret_key="short-secret",
        )
    assert "JWT_SECRET_KEY must contain at least 32 bytes" in str(exc_info.value)


def test_production_rejects_debug_true() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            app_env="production",
            debug=True,
            database_name="test_db",
            database_user="test_user",
            jwt_secret_key="a" * 32,
        )
    assert "DEBUG must be false in production" in str(exc_info.value)


def test_production_accepts_secure_configuration() -> None:
    configured = Settings(
        _env_file=None,
        app_env="production",
        debug=False,
        database_name="prod_db",
        database_user="prod_user",
        jwt_secret_key="a" * 32,
    )
    assert configured.app_env == "production"
    assert configured.debug is False
    assert len(configured.jwt_secret_key.get_secret_value()) == 32
