import csv
import io
import json
from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.questions.duplicate_detection import ExactContentHashDuplicateDetector
from app.questions.import_service import QuestionImportService
from app.questions.models import (
    ImportBatchStatus,
    ImportRowStatus,
    Question,
    QuestionImportBatch,
    QuestionImportRow,
    QuestionStatus,
)
from app.subjects.models import Subject
from app.users.models import Role, User

UserFactory = Callable[[Role, str], User]
BearerFactory = Callable[[User], dict[str, str]]


def import_record(
    subject: Subject,
    derivative: Concept,
    *,
    content: str = "What is the derivative of x squared?",
) -> dict[str, object]:
    return {
        "subject_code": subject.code,
        "content": content,
        "question_type": "MULTIPLE_CHOICE",
        "difficulty": 0.4,
        "correct_answer": "B",
        "explanation": "Use the power rule.",
        "source": "teacher",
        "source_reference": "Import fixture",
        "exam_weight": 0.6,
        "options": [
            {"label": "A", "content": "x", "order_index": 0},
            {"label": "B", "content": "2x", "order_index": 1},
        ],
        "concepts": [{"code": derivative.code, "weight": 0.8}],
    }


def preview_json(
    client: TestClient,
    headers: dict[str, str],
    rows: object,
    *,
    trusted: bool = False,
    filename: str = "questions.json",
):
    return client.post(
        "/questions/import/preview",
        params={"trusted_seed_data": str(trusted).lower()},
        files={"file": (filename, json.dumps(rows).encode("utf-8"), "application/json")},
        headers=headers,
    )


def test_json_preview_reports_valid_invalid_and_duplicate_rows(
    db_client: TestClient,
    db_session: Session,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "json-import@example.com")
    headers = question_bearer(teacher)
    subject, derivative, _ = math_content
    valid = import_record(subject, derivative)
    invalid_schema = {**valid, "content": "Invalid difficulty", "difficulty": 1.5}
    duplicate = {**valid, "content": "  WHAT is the derivative\n of X squared?  "}
    invalid_concept = {
        **valid,
        "content": "Unknown concept",
        "concepts": [{"code": "DOES_NOT_EXIST", "weight": 0.5}],
    }
    response = preview_json(
        db_client, headers, [valid, invalid_schema, duplicate, invalid_concept]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "PREVIEWED"
    assert body["report"] == {
        "total": 4, "valid": 1, "invalid": 2, "duplicate": 1, "imported": 0
    }
    assert [row["status"] for row in body["rows"]] == [
        "VALID", "INVALID", "DUPLICATE", "INVALID"
    ]
    assert "difficulty" in " ".join(body["rows"][1]["errors"])
    assert "matches import row 1" in body["rows"][2]["errors"][0]
    assert "DOES_NOT_EXIST" in body["rows"][3]["errors"][0]
    batch = db_session.get(QuestionImportBatch, UUID(body["batch_id"]))
    assert batch is not None and batch.status == ImportBatchStatus.PREVIEWED
    assert db_session.scalar(select(func.count()).select_from(QuestionImportRow)) == 4
    assert db_session.scalar(select(func.count()).select_from(Question)) == 0


@pytest.mark.parametrize(
    "updates,expected_field",
    [
        ({"content": " "}, "content"),
        ({"question_type": "UNKNOWN"}, "question_type"),
        ({"options": []}, "MULTIPLE_CHOICE"),
        ({"correct_answer": "Z"}, "correct_answer"),
        ({"difficulty": -0.1}, "difficulty"),
        ({"exam_weight": 1.1}, "exam_weight"),
        ({"source": " "}, "source"),
    ],
)
def test_import_schema_reports_required_field_errors_per_row(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
    updates: dict[str, object],
    expected_field: str,
) -> None:
    teacher = question_user_factory(Role.TEACHER, f"validation-{uuid4()}@example.com")
    row = {**import_record(math_content[0], math_content[1]), **updates}
    response = preview_json(db_client, question_bearer(teacher), [row])
    assert response.status_code == 201
    body = response.json()
    assert body["report"] == {
        "total": 1, "valid": 0, "invalid": 1, "duplicate": 0, "imported": 0
    }
    assert expected_field in " ".join(body["rows"][0]["errors"])


def test_confirm_imports_only_valid_rows_as_draft_and_is_idempotent(
    db_client: TestClient,
    db_session: Session,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "confirm-import@example.com")
    headers = question_bearer(teacher)
    subject, derivative, _ = math_content
    preview = preview_json(
        db_client,
        headers,
        [
            import_record(subject, derivative),
            {**import_record(subject, derivative), "content": "Bad", "source": ""},
        ],
    ).json()
    endpoint = f"/questions/import/{preview['batch_id']}/confirm"
    confirmed = db_client.post(endpoint, headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    body = confirmed.json()
    assert body["status"] == "IMPORTED" and body["confirmed_at"]
    assert body["report"] == {
        "total": 2, "valid": 1, "invalid": 1, "duplicate": 0, "imported": 1
    }
    question_id = UUID(body["rows"][0]["imported_question_id"])
    db_session.expire_all()
    question = db_session.get(Question, question_id)
    assert question is not None
    assert question.status == QuestionStatus.DRAFT
    assert question.created_by == teacher.id
    assert question.source_type == "TEACHER"
    assert len(question.options) == 2 and len(question.concept_links) == 1
    repeated = db_client.post(endpoint, headers=headers)
    assert repeated.status_code == 200
    assert repeated.json()["rows"][0]["imported_question_id"] == str(question_id)
    assert db_session.scalar(select(func.count()).select_from(Question)) == 1


def test_csv_upload_parses_nested_options_and_concepts(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "csv-import@example.com")
    subject, derivative, _ = math_content
    record = import_record(subject, derivative, content="CSV question")
    csv_record = {
        **record,
        "options": json.dumps(record["options"]),
        "concepts": json.dumps(record["concepts"]),
    }
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(csv_record))
    writer.writeheader()
    writer.writerow(csv_record)
    response = db_client.post(
        "/questions/import/preview",
        files={"file": ("questions.csv", stream.getvalue().encode(), "text/csv")},
        headers=question_bearer(teacher),
    )
    assert response.status_code == 201, response.text
    assert response.json()["file_format"] == "CSV"
    assert response.json()["report"]["valid"] == 1
    assert response.json()["rows"][0]["row_number"] == 2


def test_existing_question_is_detected_by_normalized_content_hash(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "existing-duplicate@example.com")
    headers = question_bearer(teacher)
    subject, derivative, function = math_content
    from tests.questions.test_api import create_question, multiple_choice_payload

    existing = multiple_choice_payload(subject, derivative, function)
    existing["content"] = "Normalized exact CONTENT"
    created = create_question(db_client, headers, existing)
    response = preview_json(
        db_client,
        headers,
        [import_record(subject, derivative, content=" normalized\nexact content ")],
    )
    assert response.status_code == 201
    row = response.json()["rows"][0]
    assert row["status"] == "DUPLICATE"
    assert created["id"] in row["errors"][0]
    assert response.json()["report"]["duplicate"] == 1


def test_confirm_rechecks_duplicates_created_after_preview(
    db_client: TestClient,
    db_session: Session,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "race-preview@example.com")
    headers = question_bearer(teacher)
    subject, derivative, function = math_content
    content = "Created between preview and confirm"
    preview = preview_json(
        db_client, headers, [import_record(subject, derivative, content=content)]
    ).json()
    assert preview["report"]["valid"] == 1
    from tests.questions.test_api import create_question, multiple_choice_payload

    direct = multiple_choice_payload(subject, derivative, function)
    direct["content"] = content
    create_question(db_client, headers, direct)
    confirmed = db_client.post(
        f"/questions/import/{preview['batch_id']}/confirm", headers=headers
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["report"] == {
        "total": 1, "valid": 0, "invalid": 0, "duplicate": 1, "imported": 0
    }
    assert db_session.scalar(select(func.count()).select_from(Question)) == 1


def test_confirm_reports_concept_removed_after_preview(
    db_client: TestClient,
    db_session: Session,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "removed-concept@example.com")
    headers = question_bearer(teacher)
    subject, derivative, _ = math_content
    preview = preview_json(
        db_client, headers, [import_record(subject, derivative, content="Reference race")]
    ).json()
    db_session.delete(derivative)
    db_session.commit()
    confirmed = db_client.post(
        f"/questions/import/{preview['batch_id']}/confirm", headers=headers
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["report"] == {
        "total": 1, "valid": 0, "invalid": 1, "duplicate": 0, "imported": 0
    }
    assert "removed after preview" in confirmed.json()["rows"][0]["errors"][0]


def test_trusted_seed_import_requires_admin_and_creates_approved_question(
    db_client: TestClient,
    db_session: Session,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "trusted-teacher@example.com")
    admin = question_user_factory(Role.ADMIN, "trusted-admin@example.com")
    row = import_record(math_content[0], math_content[1], content="Trusted seed question")
    denied = preview_json(db_client, question_bearer(teacher), [row], trusted=True)
    assert denied.status_code == 403
    preview = preview_json(db_client, question_bearer(admin), [row], trusted=True)
    assert preview.status_code == 201
    confirmed = db_client.post(
        f"/questions/import/{preview.json()['batch_id']}/confirm",
        headers=question_bearer(admin),
    )
    assert confirmed.status_code == 200
    question_id = UUID(confirmed.json()["rows"][0]["imported_question_id"])
    db_session.expire_all()
    assert db_session.get(Question, question_id).status == QuestionStatus.APPROVED


def test_import_batch_can_only_be_confirmed_by_its_creator(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    owner = question_user_factory(Role.TEACHER, "import-owner@example.com")
    outsider = question_user_factory(Role.TEACHER, "import-outsider@example.com")
    preview = preview_json(
        db_client,
        question_bearer(owner),
        [import_record(math_content[0], math_content[1])],
    ).json()
    denied = db_client.post(
        f"/questions/import/{preview['batch_id']}/confirm",
        headers=question_bearer(outsider),
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "QUESTION_IMPORT_ACCESS_DENIED"


@pytest.mark.parametrize(
    "filename,payload,code",
    [
        ("questions.txt", b"anything", "UNSUPPORTED_IMPORT_FORMAT"),
        ("questions.json", b"not-json", "IMPORT_PARSE_ERROR"),
        ("questions.json", b"{}", "IMPORT_PARSE_ERROR"),
        ("questions.csv", b"", "EMPTY_IMPORT_FILE"),
        ("questions.json", b"\xff", "IMPORT_ENCODING_ERROR"),
    ],
)
def test_file_level_errors_are_clear(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    filename: str,
    payload: bytes,
    code: str,
) -> None:
    teacher = question_user_factory(Role.TEACHER, f"file-{uuid4()}@example.com")
    response = db_client.post(
        "/questions/import/preview",
        files={"file": (filename, payload, "application/octet-stream")},
        headers=question_bearer(teacher),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == code


def test_json_non_object_is_an_invalid_row_with_message(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
) -> None:
    teacher = question_user_factory(Role.TEACHER, "non-object@example.com")
    response = preview_json(db_client, question_bearer(teacher), ["not an object"])
    assert response.status_code == 201
    assert response.json()["report"]["invalid"] == 1
    assert response.json()["rows"][0]["errors"] == ["Row must be a JSON object."]


def test_exact_detector_normalizes_unicode_case_and_whitespace(db_session: Session) -> None:
    detector = ExactContentHashDuplicateDetector()
    assert detector.fingerprint("  Hàm   SỐ\n") == detector.fingerprint("hàm số")
    matches = detector.detect(db_session, ["Question A", " question\nA ", "Question B"])
    assert matches[1].duplicate_of_index == 0
    assert 0 not in matches and 2 not in matches


def test_duplicate_detector_queries_only_candidate_hashes(
    db_session: Session,
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "hash-query@example.com")
    payload = import_record(
        math_content[0], math_content[1], content="Existing indexed fingerprint"
    )
    from tests.questions.test_api import create_question, multiple_choice_payload

    direct = multiple_choice_payload(math_content[0], math_content[1], math_content[2])
    direct["content"] = payload["content"]
    existing = create_question(db_client, question_bearer(teacher), direct)
    statements: list[str] = []

    def capture_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        matches = ExactContentHashDuplicateDetector().detect(
            db_session, [str(payload["content"]), "Unrelated candidate"]
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)

    assert str(matches[0].existing_question_id) == existing["id"]
    question_selects = [
        statement.lower()
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT") and "from questions" in statement.lower()
    ]
    assert len(question_selects) == 1
    assert "questions.content_hash" in question_selects[0]
    assert "questions.content," not in question_selects[0]


def test_preview_preloads_reference_catalog_once_per_batch(
    db_session: Session,
    question_user_factory: UserFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "batch-reference-cache@example.com")
    subject, derivative, _ = math_content
    rows = [
        import_record(subject, derivative, content=f"Batch preload question {index}")
        for index in range(50)
    ]
    statements: list[str] = []

    def capture_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        preview = QuestionImportService(db_session).preview(
            teacher,
            file_name="batch.json",
            content=json.dumps(rows).encode("utf-8"),
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)

    assert preview.report.valid == 50
    selects = [
        statement.lower()
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    assert sum("from subjects" in statement for statement in selects) == 1
    assert sum("from concepts" in statement for statement in selects) == 1
    assert sum("from problem_types" in statement for statement in selects) == 0
    assert sum("from learning_outcomes" in statement for statement in selects) == 0


def test_confirm_revalidates_references_in_batches(
    db_session: Session,
    question_user_factory: UserFactory,
    math_content: tuple[Subject, Concept, Concept],
) -> None:
    teacher = question_user_factory(Role.TEACHER, "confirm-reference-cache@example.com")
    subject, derivative, _ = math_content
    rows = [
        import_record(subject, derivative, content=f"Confirm preload question {index}")
        for index in range(50)
    ]
    service = QuestionImportService(db_session)
    preview = service.preview(
        teacher,
        file_name="confirm-batch.json",
        content=json.dumps(rows).encode("utf-8"),
    )
    statements: list[str] = []

    def capture_statement(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        statements.append(statement)

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        confirmed = service.confirm(teacher, preview.batch_id)
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)

    assert confirmed.report.imported == 50
    selects = [
        statement.lower()
        for statement in statements
        if statement.lstrip().upper().startswith("SELECT")
    ]
    assert sum("from subjects" in statement for statement in selects) == 1
    assert sum("from concepts" in statement for statement in selects) == 1
    assert sum("from problem_types" in statement for statement in selects) == 0
    assert sum("from learning_outcomes" in statement for statement in selects) == 0


@pytest.mark.parametrize("role", [Role.STUDENT, Role.PARENT])
def test_import_rejects_non_staff_roles(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
    role: Role,
) -> None:
    user = question_user_factory(role, f"import-{role.value.lower()}@example.com")
    response = db_client.post(
        "/questions/import/preview",
        files={"file": ("questions.json", b"[]", "application/json")},
        headers=question_bearer(user),
    )
    assert response.status_code == 403


def test_confirm_missing_batch_returns_stable_error(
    db_client: TestClient,
    question_user_factory: UserFactory,
    question_bearer: BearerFactory,
) -> None:
    teacher = question_user_factory(Role.TEACHER, "missing-batch@example.com")
    response = db_client.post(
        f"/questions/import/{uuid4()}/confirm", headers=question_bearer(teacher)
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "QUESTION_IMPORT_NOT_FOUND"
