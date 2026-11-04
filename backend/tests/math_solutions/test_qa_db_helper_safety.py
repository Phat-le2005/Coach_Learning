from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
HELPER_PATH = REPO_ROOT / "frontend" / "e2e" / "qa_db_helper.py"


def load_qa_db_helper():
    spec = importlib.util.spec_from_file_location("qa_db_helper", HELPER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeScalarResult:
    def __init__(self, value: str) -> None:
        self._value = value

    def scalar_one(self) -> str:
        return self._value


class FakeConnectedSession:
    def __init__(self, connected_db: str) -> None:
        self._connected_db = connected_db

    def execute(self, _stmt):
        return FakeScalarResult(self._connected_db)


def test_missing_qa_password_causes_clear_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = load_qa_db_helper()
    monkeypatch.setenv("QA_E2E_IGNORE_ENV_FILE", "1")
    monkeypatch.delenv("QA_E2E_PASSWORD", raising=False)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_NAME", "edums_qa_e2e")
    monkeypatch.setenv("QA_E2E_DATABASE_NAME", "edums_qa_e2e")

    with pytest.raises(RuntimeError, match="QA_E2E_CONFIG_ERROR: QA_E2E_PASSWORD is required"):
        helper.verify_qa_database_safety(session=None, require_password=True)

    monkeypatch.setenv("QA_E2E_PASSWORD", "short")
    with pytest.raises(
        RuntimeError, match="QA_E2E_CONFIG_ERROR: QA_E2E_PASSWORD must contain at least 12 characters"
    ):
        helper.verify_qa_database_safety(session=None, require_password=True)


def test_wrong_or_ordinary_dev_database_name_blocks_provisioning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    helper = load_qa_db_helper()
    monkeypatch.setenv("QA_E2E_IGNORE_ENV_FILE", "1")
    monkeypatch.setenv("QA_E2E_PASSWORD", "ValidTestSecret#2026!")
    monkeypatch.setenv("APP_ENV", "test")

    # 1. Missing QA_E2E_DATABASE_NAME
    monkeypatch.delenv("QA_E2E_DATABASE_NAME", raising=False)
    monkeypatch.setenv("DATABASE_NAME", "edums_qa_e2e")
    with pytest.raises(
        RuntimeError, match="QA_E2E_SAFETY_ERROR: QA_E2E_DATABASE_NAME is required"
    ):
        helper.verify_qa_database_safety(session=None, require_password=True)

    # 2. Ordinary development database 'edums' is explicitly rejected
    for forbidden in ("edums", "postgres", "production", "prod", "main", "dev", "edums_dev"):
        monkeypatch.setenv("QA_E2E_DATABASE_NAME", forbidden)
        monkeypatch.setenv("DATABASE_NAME", forbidden)
        with pytest.raises(RuntimeError, match="QA_E2E_SAFETY_ERROR: .*not a dedicated QA database"):
            helper.verify_qa_database_safety(session=None, require_password=True)

    # 3. Mismatched QA_E2E_DATABASE_NAME vs backend DATABASE_NAME
    monkeypatch.setenv("QA_E2E_DATABASE_NAME", "edums_qa_e2e")
    monkeypatch.setenv("DATABASE_NAME", "edums_qa_other")
    with pytest.raises(
        RuntimeError,
        match="QA_E2E_SAFETY_ERROR: QA_E2E_DATABASE_NAME \\('edums_qa_e2e'\\) does not match backend DATABASE_NAME \\('edums_qa_other'\\)",
    ):
        helper.verify_qa_database_safety(session=None, require_password=True)

    # 4. Mismatched actual connected PostgreSQL current_database()
    monkeypatch.setenv("QA_E2E_DATABASE_NAME", "edums_qa_e2e")
    monkeypatch.setenv("DATABASE_NAME", "edums_qa_e2e")
    with pytest.raises(
        RuntimeError,
        match="QA_E2E_SAFETY_ERROR: Connected PostgreSQL database \\('edums'\\) does not match QA_E2E_DATABASE_NAME \\('edums_qa_e2e'\\)",
    ):
        helper.verify_qa_database_safety(
            session=FakeConnectedSession("edums"),
            require_password=True,
        )


def test_production_configuration_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    helper = load_qa_db_helper()
    monkeypatch.setenv("QA_E2E_IGNORE_ENV_FILE", "1")
    monkeypatch.setenv("QA_E2E_PASSWORD", "ValidTestSecret#2026!")
    monkeypatch.setenv("DATABASE_NAME", "edums_qa_e2e")
    monkeypatch.setenv("QA_E2E_DATABASE_NAME", "edums_qa_e2e")
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(
        RuntimeError,
        match="QA_E2E_SAFETY_ERROR: APP_ENV=production is strictly forbidden",
    ):
        helper.verify_qa_database_safety(session=None, require_password=True)


def test_correct_qa_configuration_allows_fixtures_and_guards_ownership(
    monkeypatch: pytest.MonkeyPatch,
    db_session,
) -> None:
    helper = load_qa_db_helper()
    monkeypatch.setenv("QA_E2E_IGNORE_ENV_FILE", "1")
    monkeypatch.setenv("QA_E2E_PASSWORD", "ValidTestSecret#2026!")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_NAME", "edums_qa_e2e")
    monkeypatch.setenv("QA_E2E_DATABASE_NAME", "edums_qa_e2e")

    verified = helper.verify_qa_database_safety(
        session=FakeConnectedSession("edums_qa_e2e"),
        require_password=True,
    )
    assert verified == {
        "app_env": "test",
        "qa_database_name": "edums_qa_e2e",
        "configured_database_name": "edums_qa_e2e",
        "connected_database_name": "edums_qa_e2e",
    }

    # Verify real fixture creation against isolated test session when current_database() matches
    from app.curriculum.constants import LEGACY_CURRICULUM_VERSION_ID
    from app.subjects.models import Subject

    db_session.add(
        Subject(
            curriculum_version_id=LEGACY_CURRICULUM_VERSION_ID,
            code="MATH_G12",
            name="Toán 12",
            grade_level=12,
        )
    )
    db_session.commit()

    orig_execute = db_session.execute

    def execute_with_current_db(stmt, *args, **kwargs):
        if "current_database()" in str(stmt):
            return FakeScalarResult("edums_qa_e2e")
        return orig_execute(stmt, *args, **kwargs)

    monkeypatch.setattr(db_session, "execute", execute_with_current_db)

    created = helper.create_isolated_attempt(db_session, label="safety-unit")
    assert created["database_name"] == "edums_qa_e2e"
    assert created["student_email"] == helper.QA_STUDENT_EMAIL
    assert created["initial_revision"] == 1

    # Bump revision works on QA-owned attempt
    bumped = helper.bump_revision(db_session, UUID_from_str(created["attempt_id"]))
    assert bumped["new_revision"] == 2
    assert bumped["database_name"] == "edums_qa_e2e"

    # Mutating a non-QA-owned attempt is rejected
    from app.math_solutions.models import SolutionAttempt

    attempt_obj = db_session.get(SolutionAttempt, UUID_from_str(created["attempt_id"]))
    assert attempt_obj is not None
    with db_session.no_autoflush:
        monkeypatch.setattr(attempt_obj, "question_id", uuid4())
        with pytest.raises(
            RuntimeError,
            match="QA_E2E_SAFETY_ERROR: Refusing to mutate SolutionAttempt that is not owned by the isolated QA fixture",
        ):
            helper.bump_revision(db_session, UUID_from_str(created["attempt_id"]))


def UUID_from_str(val: str):
    from uuid import UUID

    return UUID(val)
