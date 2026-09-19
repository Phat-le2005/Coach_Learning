from fastapi.testclient import TestClient


def post(client: TestClient, path: str, payload: dict, headers: dict[str, str]) -> dict:
    response = client.post(path, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_creates_curriculum_hierarchy_and_subject_tree(
    db_client: TestClient, curriculum_admin_headers: dict[str, str]
) -> None:
    headers = curriculum_admin_headers
    curriculum = post(db_client, "/admin/curricula", {
        "code": "TEST_CURRICULUM", "name": "Test Curriculum"
    }, headers)
    version = post(db_client, "/admin/curriculum-versions", {
        "curriculum_id": curriculum["id"],
        "code": "V2026",
        "version": "2026",
        "source_reference": "Test source",
        "is_active": True,
    }, headers)
    subject = post(db_client, "/admin/subjects", {
        "curriculum_version_id": version["id"],
        "code": "MATH12_TEST",
        "name": "Mathematics 12",
        "grade_level": 12,
        "order_index": 1,
    }, headers)
    later = post(db_client, "/admin/chapters", {
        "subject_id": subject["id"], "code": "C2", "name": "Chapter 2", "order_index": 20
    }, headers)
    chapter = post(db_client, "/admin/chapters", {
        "subject_id": subject["id"], "code": "C1", "name": "Chapter 1", "order_index": 10
    }, headers)
    topic = post(db_client, "/admin/topics", {
        "chapter_id": chapter["id"], "code": "T1", "name": "Topic 1", "order_index": 10
    }, headers)
    problem = post(db_client, "/admin/problem-types", {
        "topic_id": topic["id"],
        "code": "PT1",
        "name": "Problem Type 1",
        "order_index": 10,
        "default_difficulty": 0.5,
        "is_active": True,
    }, headers)
    concept = post(db_client, "/admin/concepts", {
        "subject_id": subject["id"],
        "code": "CONCEPT1",
        "name": "Concept 1",
        "description": "Concept description",
        "grade_level": 12,
        "order_index": 10,
    }, headers)
    outcome = post(db_client, "/admin/learning-outcomes", {
        "subject_id": subject["id"],
        "code": "LO1",
        "description": "Expected learning outcome",
        "grade_level": 12,
        "order_index": 10,
    }, headers)
    post(db_client, "/admin/problem-type-concepts", {
        "problem_type_id": problem["id"],
        "concept_id": concept["id"],
        "weight": 0.8,
        "is_primary": True,
    }, headers)
    post(db_client, "/admin/problem-type-learning-outcomes", {
        "problem_type_id": problem["id"],
        "learning_outcome_id": outcome["id"],
        "weight": 1.0,
    }, headers)

    tree_response = db_client.get(
        f"/admin/subjects/{subject['id']}/curriculum-tree", headers=headers
    )
    assert tree_response.status_code == 200
    tree = tree_response.json()
    assert [item["id"] for item in tree["chapters"]] == [chapter["id"], later["id"]]
    node = tree["chapters"][0]["topics"][0]["problem_types"][0]
    assert node["code"] == "PT1"
    assert node["concept_count"] == 1 and node["learning_outcome_count"] == 1

    detail = db_client.get(f"/admin/problem-types/{problem['id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["concepts"][0]["concept_id"] == concept["id"]
    assert detail.json()["learning_outcomes"][0]["learning_outcome_id"] == outcome["id"]
    outcomes = db_client.get(
        f"/admin/subjects/{subject['id']}/learning-outcomes", headers=headers
    )
    assert outcomes.status_code == 200
    assert [item["id"] for item in outcomes.json()] == [outcome["id"]]


def test_duplicate_codes_are_scoped_to_the_parent(
    db_client: TestClient, curriculum_admin_headers: dict[str, str]
) -> None:
    headers = curriculum_admin_headers
    curriculum = post(db_client, "/admin/curricula", {
        "code": "SCOPED", "name": "Scoped"
    }, headers)
    version = post(db_client, "/admin/curriculum-versions", {
        "curriculum_id": curriculum["id"], "code": "V1", "version": "1"
    }, headers)
    subject = post(db_client, "/admin/subjects", {
        "curriculum_version_id": version["id"], "code": "S1", "name": "Subject"
    }, headers)
    payload = {"subject_id": subject["id"], "code": "C1", "name": "Chapter", "order_index": 1}
    post(db_client, "/admin/chapters", payload, headers)
    duplicate = db_client.post("/admin/chapters", json=payload, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "CHAPTER_CODE_EXISTS"


def test_curriculum_admin_endpoints_require_admin(
    db_client: TestClient,
) -> None:
    assert db_client.get("/admin/curricula").status_code == 401
