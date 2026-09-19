from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from httpx import Response
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation
from app.subjects.models import Subject
from app.users.models import Role

BearerFactory = Callable[[Role], dict[str, str]]


def concept_payload(subject_id: str, code: str = "C1") -> dict[str, object]:
    return {"subject_id": subject_id, "code": code, "name": "Concept one", "description": "A concept description", "grade_level": 12, "order_index": 0}


def admin_requests(client: TestClient, headers: dict[str, str]) -> list[Response]:
    missing = str(uuid4())
    return [
        client.post("/admin/subjects", json={"code": "S", "name": "Subject"}, headers=headers),
        client.get("/admin/subjects", headers=headers),
        client.post("/admin/concepts", json=concept_payload(missing), headers=headers),
        client.patch(f"/admin/concepts/{missing}", json={}, headers=headers),
        client.post("/admin/concept-relations", json={"source_concept_id": missing, "target_concept_id": str(uuid4()), "relation_type": "PREREQUISITE"}, headers=headers),
        client.delete(f"/admin/concept-relations/{missing}", headers=headers),
    ]


@pytest.mark.parametrize("role", [Role.STUDENT, Role.TEACHER, Role.PARENT])
def test_all_admin_endpoints_reject_other_roles(
    db_client: TestClient, academic_bearer: BearerFactory, db_session: Session, role: Role,
) -> None:
    for response in admin_requests(db_client, academic_bearer(role)):
        assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN"
    for model in [Subject, Concept, ConceptRelation]:
        assert db_session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer invalid-token"}])
def test_admin_endpoints_require_authentication(db_client: TestClient, headers: dict[str, str]) -> None:
    for response in admin_requests(db_client, headers):
        assert response.status_code == 401


def test_admin_crud_persists_data_and_updates_graph(db_client: TestClient, academic_bearer: BearerFactory, db_session: Session) -> None:
    headers = academic_bearer(Role.ADMIN)
    response = db_client.post("/admin/subjects", json={"code": " math ", "name": " Mathematics ", "grade_level": 12, "description": " Subject description "}, headers=headers)
    assert response.status_code == 201
    subject = response.json()
    assert subject["code"] == "MATH" and subject["name"] == "Mathematics"
    assert subject["description"] == "Subject description"
    assert db_client.get("/admin/subjects", headers=headers).json() == [subject]
    first = db_client.post("/admin/concepts", json=concept_payload(subject["id"]), headers=headers)
    second = db_client.post("/admin/concepts", json=concept_payload(subject["id"], "C2"), headers=headers)
    assert first.status_code == second.status_code == 201
    concept = first.json()
    patched = db_client.patch(f"/admin/concepts/{concept['id']}", json={"name": " Updated concept ", "order_index": 3}, headers=headers)
    assert patched.status_code == 200 and patched.json()["name"] == "Updated concept"
    assert patched.json()["description"] == concept["description"] and patched.json()["order_index"] == 3
    assert db_client.patch(f"/admin/concepts/{concept['id']}", json={}, headers=headers).json() == patched.json()
    relation = db_client.post("/admin/concept-relations", json={"source_concept_id": concept["id"], "target_concept_id": second.json()["id"], "relation_type": "PREREQUISITE"}, headers=headers)
    assert relation.status_code == 201 and relation.json()["source_concept_id"] == concept["id"]
    deleted = db_client.delete(f"/admin/concept-relations/{relation.json()['id']}", headers=headers)
    assert deleted.status_code == 204 and deleted.content == b""
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(ConceptRelation)) == 0
    stored = db_session.get(Concept, UUID(concept["id"]))
    assert stored is not None and stored.name == "Updated concept"


def test_subject_optional_fields_uniqueness_and_paginated_order(db_client: TestClient, academic_bearer: BearerFactory) -> None:
    headers = academic_bearer(Role.ADMIN)
    for code in ["Z", "B", "A"]:
        response = db_client.post("/admin/subjects", json={"code": code, "name": code}, headers=headers)
        assert response.status_code == 201 and response.json()["grade_level"] is None and response.json()["description"] is None
    duplicate = db_client.post("/admin/subjects", json={"code": " a ", "name": "Another subject"}, headers=headers)
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "SUBJECT_CODE_EXISTS"
    page = db_client.get("/admin/subjects?offset=1&limit=1", headers=headers)
    assert [subject["code"] for subject in page.json()] == ["B"]
    assert db_client.get("/admin/subjects?offset=10", headers=headers).json() == []
    for query in ["offset=-1", "limit=0", "limit=201"]:
        assert db_client.get(f"/admin/subjects?{query}", headers=headers).status_code == 422


@pytest.mark.parametrize("updates", [
    {"code": " "}, {"code": "X" * 101}, {"name": " "}, {"name": "X" * 201}, {"grade_level": 0},
    {"grade_level": 13}, {"grade_level": True}, {"grade_level": "12"}, {"description": " "}, {"id": str(uuid4())},
])
def test_subject_validation(db_client: TestClient, academic_bearer: BearerFactory, updates: dict[str, object]) -> None:
    headers = academic_bearer(Role.ADMIN)
    response = db_client.post("/admin/subjects", json={"code": "S", "name": "Subject", **updates}, headers=headers)
    assert response.status_code == 422 and response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert db_client.get("/admin/subjects", headers=headers).json() == []


def test_concept_code_is_unique_per_subject_and_patch_conflicts_are_atomic(db_client: TestClient, academic_bearer: BearerFactory) -> None:
    headers = academic_bearer(Role.ADMIN)
    subjects = [db_client.post("/admin/subjects", json={"code": code, "name": code}, headers=headers).json() for code in ["S1", "S2"]]
    first = db_client.post("/admin/concepts", json=concept_payload(subjects[0]["id"]), headers=headers).json()
    assert db_client.post("/admin/concepts", json=concept_payload(subjects[1]["id"]), headers=headers).status_code == 201
    duplicate = db_client.post("/admin/concepts", json=concept_payload(subjects[0]["id"], " c1 "), headers=headers)
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "CONCEPT_CODE_EXISTS"
    collision = db_client.patch(f"/admin/concepts/{first['id']}", json={"subject_id": subjects[1]["id"], "name": "Must rollback"}, headers=headers)
    assert collision.status_code == 409
    assert db_client.patch(f"/admin/concepts/{first['id']}", json={}, headers=headers).json() == first
    moved = db_client.patch(f"/admin/concepts/{first['id']}", json={"subject_id": subjects[1]["id"], "code": " new-code ", "description": "New description", "grade_level": 11}, headers=headers)
    assert moved.status_code == 200 and moved.json()["code"] == "NEW-CODE"
    assert moved.json()["subject_id"] == subjects[1]["id"] and moved.json()["grade_level"] == 11


@pytest.mark.parametrize("updates", [
        {"code": " "}, {"name": " "}, {"description": " "},
    {"grade_level": 13}, {"grade_level": 0}, {"grade_level": "12"}, {"order_index": -1}, {"order_index": True},
    {"order_index": 1.5}, {"order_index": 2147483648}, {"subject_id": "invalid"}, {"id": str(uuid4())},
])
def test_concept_create_and_patch_validation(db_client: TestClient, academic_bearer: BearerFactory, updates: dict[str, object]) -> None:
    headers = academic_bearer(Role.ADMIN)
    subject = db_client.post("/admin/subjects", json={"code": "S", "name": "Subject"}, headers=headers).json()
    payload = concept_payload(subject["id"])
    original = db_client.post("/admin/concepts", json=payload, headers=headers).json()
    assert db_client.post("/admin/concepts", json={**payload, **updates}, headers=headers).status_code == 422
    assert db_client.patch(f"/admin/concepts/{original['id']}", json=updates, headers=headers).status_code == 422
    assert db_client.patch(f"/admin/concepts/{original['id']}", json={}, headers=headers).json() == original


@pytest.mark.parametrize("field", ["subject_id", "code", "name"])
def test_patch_cannot_clear_required_fields(db_client: TestClient, academic_bearer: BearerFactory, field: str) -> None:
    headers = academic_bearer(Role.ADMIN)
    response = db_client.patch(f"/admin/concepts/{uuid4()}", json={field: None}, headers=headers)
    assert response.status_code == 422


def test_unknown_resources_return_404(db_client: TestClient, academic_bearer: BearerFactory) -> None:
    headers = academic_bearer(Role.ADMIN)
    missing = str(uuid4())
    assert db_client.post("/admin/concepts", json=concept_payload(missing), headers=headers).json()["error"]["code"] == "SUBJECT_NOT_FOUND"
    response = db_client.patch(f"/admin/concepts/{missing}", json={}, headers=headers)
    assert response.status_code == 404 and response.json()["error"]["code"] == "CONCEPT_NOT_FOUND"
    response = db_client.delete(f"/admin/concept-relations/{missing}", headers=headers)
    assert response.status_code == 404 and response.json()["error"]["code"] == "CONCEPT_RELATION_NOT_FOUND"
    response = db_client.post("/admin/concept-relations", json={"source_concept_id": missing, "target_concept_id": str(uuid4()), "relation_type": "PART_OF"}, headers=headers)
    assert response.status_code == 404 and response.json()["error"]["code"] == "CONCEPT_NOT_FOUND"


def test_relation_conflicts_cycles_self_edges_and_related_deduplication(db_client: TestClient, academic_bearer: BearerFactory) -> None:
    headers = academic_bearer(Role.ADMIN)
    subject = db_client.post("/admin/subjects", json={"code": "S", "name": "Subject"}, headers=headers).json()
    a, b = [db_client.post("/admin/concepts", json=concept_payload(subject["id"], code), headers=headers).json() for code in ["A", "B"]]
    payload = {"source_concept_id": a["id"], "target_concept_id": b["id"], "relation_type": "PREREQUISITE"}
    assert db_client.post("/admin/concept-relations", json=payload, headers=headers).status_code == 201
    duplicate = db_client.post("/admin/concept-relations", json=payload, headers=headers)
    assert duplicate.status_code == 409 and duplicate.json()["error"]["code"] == "CONCEPT_RELATION_EXISTS"
    cycle = db_client.post("/admin/concept-relations", json={**payload, "source_concept_id": b["id"], "target_concept_id": a["id"]}, headers=headers)
    assert cycle.status_code == 409 and cycle.json()["error"]["code"] == "CONCEPT_GRAPH_CYCLE"
    self_edge = db_client.post("/admin/concept-relations", json={**payload, "target_concept_id": a["id"]}, headers=headers)
    assert self_edge.status_code == 422 and self_edge.json()["error"]["code"] == "SELF_RELATION"
    related = db_client.post("/admin/concept-relations", json={**payload, "relation_type": "RELATED_TO"}, headers=headers)
    assert related.status_code == 201
    reverse = db_client.post("/admin/concept-relations", json={**payload, "source_concept_id": b["id"], "target_concept_id": a["id"], "relation_type": "RELATED_TO"}, headers=headers)
    assert reverse.status_code == 409
    invalid = db_client.post("/admin/concept-relations", json={**payload, "relation_type": "UNKNOWN"}, headers=headers)
    assert invalid.status_code == 422


def test_delete_cors_preflight(db_client: TestClient) -> None:
    response = db_client.options(f"/admin/concept-relations/{uuid4()}", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "DELETE", "Access-Control-Request-Headers": "authorization"})
    assert response.status_code == 200 and "DELETE" in response.headers["access-control-allow-methods"]
