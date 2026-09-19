from uuid import UUID

from fastapi.testclient import TestClient

from app.users.models import User
from tests.diagnostics.conftest import DiagnosticContent


def test_diagnostic_api_flow_and_owner_authorization(
    db_client: TestClient,
    practice_students: tuple[User, User],
    practice_bearer,
    diagnostic_content: DiagnosticContent,
) -> None:
    owner_headers = practice_bearer(practice_students[0])
    outsider_headers = practice_bearer(practice_students[1])
    started = db_client.post(
        "/diagnostic/start",
        json={
            "subject_id": str(diagnostic_content.base.subject.id),
            "max_questions": 1,
            "minimum_problem_type_coverage": 1.0,
            "confidence_threshold": 1.0,
        },
        headers=owner_headers,
    )
    assert started.status_code == 201, started.text
    diagnostic_id = UUID(started.json()["id"])

    denied = db_client.get(
        f"/diagnostic/{diagnostic_id}/next", headers=outsider_headers
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "DIAGNOSTIC_ACCESS_DENIED"

    pending_result = db_client.get(
        f"/diagnostic/{diagnostic_id}/result", headers=owner_headers
    )
    assert pending_result.status_code == 409
    selected = db_client.get(
        f"/diagnostic/{diagnostic_id}/next", headers=owner_headers
    )
    assert selected.status_code == 200, selected.text
    question_id = selected.json()["question"]["id"]
    answered = db_client.post(
        f"/diagnostic/{diagnostic_id}/answer",
        json={
            "question_id": question_id,
            "student_answer": "TRUE",
            "response_time_seconds": 20,
            "hint_count": 0,
        },
        headers=owner_headers,
    )
    assert answered.status_code == 201, answered.text
    assert answered.json()["status"] == "COMPLETED"

    result = db_client.get(
        f"/diagnostic/{diagnostic_id}/result", headers=owner_headers
    )
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["question_count"] == 1
    assert body["subject_summary"]["subject_id"] == str(
        diagnostic_content.base.subject.id
    )
