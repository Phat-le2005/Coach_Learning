from unittest.mock import MagicMock

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database.session import get_db


def test_health(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_success(db_client: TestClient) -> None:
    response = db_client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_failure_returns_503(db_client: TestClient) -> None:
    mock_db = MagicMock(spec=Session)
    mock_db.execute.side_effect = RuntimeError("Database unreachable")

    db_client.app.dependency_overrides[get_db] = lambda: mock_db
    try:
        response = db_client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["error"]["code"] == "SERVICE_NOT_READY"
        assert data["error"]["message"] == "Database dependency is unavailable."
    finally:
        db_client.app.dependency_overrides.pop(get_db, None)


def test_openapi_and_docs(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert schema["info"]["title"] == "EduMS"
    assert "/health" in schema["paths"]
    assert "/ready" in schema["paths"]
