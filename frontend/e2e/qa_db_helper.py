"""Isolated PostgreSQL QA fixture provisioner and authoritative database oracle.

Enforces fail-closed QA infrastructure safety before any database operation:
1. Requires QA_E2E_PASSWORD from environment or local untracked .tmp/tri-ocr-e2e/.qa-e2e.env (no hardcoded fallback).
2. Reads actual backend Settings and explicitly rejects APP_ENV=production.
3. Requires explicit QA_E2E_DATABASE_NAME matching both backend DATABASE_NAME and PostgreSQL current_database().
4. Requires a dedicated QA database (e.g. edums_qa_e2e) and rejects the ordinary development database ('edums').
5. Restricts all fixture mutations strictly to QA-owned records (qa.ocr.e2e.isolated@edums.edu.vn / QA_ISOLATED_FIXTURE).
Never prints passwords, tokens, or secrets to stdout/stderr.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from uuid import UUID, uuid4

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = REPO_ROOT / "backend"
DEFAULT_UNTRACKED_ENV_FILE = REPO_ROOT / ".tmp" / "tri-ocr-e2e" / ".qa-e2e.env"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

QA_STUDENT_EMAIL = "qa.ocr.e2e.isolated@edums.edu.vn"
QA_STUDENT_NAME = "QA Isolated E2E Student"
QA_QUESTION_SOURCE_TYPE = "QA_ISOLATED_FIXTURE"

FORBIDDEN_DATABASE_NAMES = frozenset(
    {
        "edums",
        "postgres",
        "template0",
        "template1",
        "production",
        "prod",
        "main",
        "default",
        "dev",
        "development",
        "staging",
    }
)
SAFE_DB_IDENTIFIER_RE = re.compile(r"^[a-zA-Z0-9_]+$")


def load_untracked_qa_env(env_file: Path | None = None) -> None:
    """Load untracked local QA env file into os.environ without overriding existing env vars."""
    if os.environ.get("QA_E2E_IGNORE_ENV_FILE") == "1":
        return
    custom_path = os.environ.get("QA_E2E_ENV_FILE", "").strip()
    target = env_file or (Path(custom_path) if custom_path else DEFAULT_UNTRACKED_ENV_FILE)
    if not target.is_file():
        return
    for raw_line in target.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def is_dedicated_qa_database_name(db_name: str) -> bool:
    normalized = db_name.strip().lower()
    if not normalized or not SAFE_DB_IDENTIFIER_RE.match(normalized):
        return False
    if normalized in FORBIDDEN_DATABASE_NAMES:
        return False
    # Must explicitly contain 'qa' token (e.g. edums_qa_e2e)
    tokens = set(normalized.split("_"))
    return "qa" in tokens or normalized.endswith("_qa") or "_qa_" in normalized


def get_required_qa_password() -> str:
    password = os.environ.get("QA_E2E_PASSWORD", "").strip()
    if not password:
        raise RuntimeError(
            "QA_E2E_CONFIG_ERROR: QA_E2E_PASSWORD is required and must not be empty. "
            "Set QA_E2E_PASSWORD in the environment or in the local untracked "
            ".tmp/tri-ocr-e2e/.qa-e2e.env file."
        )
    if len(password) < 12:
        raise RuntimeError(
            "QA_E2E_CONFIG_ERROR: QA_E2E_PASSWORD must contain at least 12 characters."
        )
    return password


def verify_qa_database_safety(
    *,
    session=None,
    require_password: bool = True,
) -> dict[str, str]:
    """Fail-closed validation of QA password, APP_ENV, DATABASE_NAME, and connected DB."""
    if require_password:
        get_required_qa_password()

    raw_app_env = os.environ.get("APP_ENV", "").strip().lower()
    if raw_app_env == "production":
        raise RuntimeError(
            "QA_E2E_SAFETY_ERROR: APP_ENV=production is strictly forbidden for QA E2E operations."
        )

    from app.core.config import get_settings

    get_settings.cache_clear()
    settings = get_settings()

    if str(settings.app_env).strip().lower() == "production":
        raise RuntimeError(
            "QA_E2E_SAFETY_ERROR: Backend Settings app_env='production' is strictly forbidden for QA E2E operations."
        )

    qa_db_name = os.environ.get("QA_E2E_DATABASE_NAME", "").strip()
    if not qa_db_name:
        raise RuntimeError(
            "QA_E2E_SAFETY_ERROR: QA_E2E_DATABASE_NAME is required and must explicitly name the dedicated QA database."
        )

    if not is_dedicated_qa_database_name(qa_db_name):
        raise RuntimeError(
            f"QA_E2E_SAFETY_ERROR: QA_E2E_DATABASE_NAME='{qa_db_name}' is not a dedicated QA database. "
            "Refusing to run against ordinary development or shared databases (such as 'edums')."
        )

    configured_db_name = str(settings.database_name).strip()
    if not is_dedicated_qa_database_name(configured_db_name):
        raise RuntimeError(
            f"QA_E2E_SAFETY_ERROR: Backend DATABASE_NAME='{configured_db_name}' is not a dedicated QA database. "
            "Configure DATABASE_NAME to match QA_E2E_DATABASE_NAME (e.g. 'edums_qa_e2e')."
        )

    if qa_db_name != configured_db_name:
        raise RuntimeError(
            f"QA_E2E_SAFETY_ERROR: QA_E2E_DATABASE_NAME ('{qa_db_name}') does not match "
            f"backend DATABASE_NAME ('{configured_db_name}')."
        )

    actual_connected_db = configured_db_name
    if session is not None:
        from sqlalchemy import text

        actual_connected_db = str(
            session.execute(text("SELECT current_database()")).scalar_one()
        ).strip()
        if actual_connected_db != qa_db_name or not is_dedicated_qa_database_name(actual_connected_db):
            raise RuntimeError(
                f"QA_E2E_SAFETY_ERROR: Connected PostgreSQL database ('{actual_connected_db}') "
                f"does not match QA_E2E_DATABASE_NAME ('{qa_db_name}')."
            )

    return {
        "app_env": str(settings.app_env),
        "qa_database_name": qa_db_name,
        "configured_database_name": configured_db_name,
        "connected_database_name": actual_connected_db,
    }


def bootstrap_dedicated_qa_database() -> dict[str, object]:
    """Create and migrate the dedicated QA PostgreSQL database without touching 'edums'."""
    safety = verify_qa_database_safety(session=None, require_password=True)
    qa_db_name = safety["qa_database_name"]

    from sqlalchemy import URL, create_engine, select, text
    from app.core.config import get_settings
    from app.curriculum.constants import LEGACY_CURRICULUM_VERSION_ID
    from app.database.session import dispose_engine, get_session_factory
    from app.subjects.models import Subject
    from tests.migrations import upgrade_test_schema

    settings = get_settings()
    admin_url = URL.create(
        drivername="postgresql+psycopg",
        username=settings.database_user,
        password=settings.database_password.get_secret_value(),
        host=settings.database_host,
        port=settings.database_port,
        database="postgres",
    )
    created_db = False
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    try:
        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": qa_db_name},
            ).scalar()
            if not exists:
                conn.exec_driver_sql(f'CREATE DATABASE "{qa_db_name}"')
                created_db = True
    finally:
        admin_engine.dispose()

    dispose_engine()
    qa_engine = create_engine(settings.database_url, hide_parameters=True)
    try:
        with qa_engine.begin() as conn:
            connected_name = str(conn.execute(text("SELECT current_database()")).scalar_one()).strip()
            if connected_name != qa_db_name:
                raise RuntimeError(
                    f"QA_E2E_SAFETY_ERROR: Expected connection to '{qa_db_name}', got '{connected_name}'."
                )
            conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            has_users_table = conn.execute(
                text("SELECT to_regclass('public.users')")
            ).scalar()
            if not has_users_table:
                upgrade_test_schema(conn)
    finally:
        qa_engine.dispose()

    with get_session_factory()() as session:
        verified = verify_qa_database_safety(session=session, require_password=True)
        subject = session.scalar(select(Subject).where(Subject.code == "MATH_G12"))
        if subject is None:
            subject = Subject(
                curriculum_version_id=LEGACY_CURRICULUM_VERSION_ID,
                code="MATH_G12",
                name="Toán 12 (QA Isolated)",
                grade_level=12,
                description="Dedicated QA E2E subject fixture",
                order_index=1,
            )
            session.add(subject)
            session.commit()
        ensure_qa_student_and_question(session)

    return {
        "bootstrapped": True,
        "created_database": created_db,
        **verified,
    }


def ensure_qa_student_and_question(session):
    verify_qa_database_safety(session=session, require_password=True)
    qa_password = get_required_qa_password()

    from sqlalchemy import select
    from app.auth.security import hash_password, verify_password
    from app.questions.fingerprint import question_content_hash
    from app.questions.models import Question, QuestionStatus, QuestionType
    from app.students.models import StudentProfile
    from app.subjects.models import Subject
    from app.users.models import Role
    from app.users.schemas import UserCreate
    from app.users.service import UserService

    user_svc = UserService(session)
    user = user_svc.find_by_email(QA_STUDENT_EMAIL)
    if user is None:
        user = user_svc.create_user(
            UserCreate(
                email=QA_STUDENT_EMAIL,
                full_name=QA_STUDENT_NAME,
                role=Role.STUDENT,
                password=qa_password,
            )
        )
    else:
        if user.email != QA_STUDENT_EMAIL:
            raise RuntimeError("QA_E2E_SAFETY_ERROR: Refusing to mutate non-QA user record.")
        if not verify_password(qa_password, user.password_hash):
            user.password_hash = hash_password(qa_password)
            session.commit()

    student = session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    assert student is not None, "StudentProfile missing for QA user"

    subject = session.scalar(select(Subject).where(Subject.code == "MATH_G12"))
    if subject is None:
        subject = session.scalar(select(Subject))
    assert subject is not None, "No Subject found in dedicated QA database"

    qa_q_content = (
        "[QA-ISOLATED-OCR-E2E] Khảo sát sự biến thiên và vẽ đồ thị của hàm số $y = x^3 - 3x^2 + 2$."
    )
    question = session.scalar(
        select(Question).where(
            Question.subject_id == subject.id,
            Question.content == qa_q_content,
        )
    )
    if question is None:
        question = Question(
            subject_id=subject.id,
            question_type=QuestionType.OPEN_RESPONSE,
            difficulty=0.5,
            source_type=QA_QUESTION_SOURCE_TYPE,
            exam_weight=0.5,
            status=QuestionStatus.APPROVED,
            content=qa_q_content,
            content_hash=question_content_hash(qa_q_content),
            explanation="TXĐ: D = R. y' = 3x^2 - 6x. Cho y' = 0 <=> x = 0 hoặc x = 2.",
            created_by=user.id,
        )
        session.add(question)
        session.commit()
        session.refresh(question)
    else:
        if question.source_type != QA_QUESTION_SOURCE_TYPE:
            raise RuntimeError(
                "QA_E2E_SAFETY_ERROR: Refusing to modify question not marked as QA_ISOLATED_FIXTURE."
            )
        if question.status != QuestionStatus.APPROVED:
            question.status = QuestionStatus.APPROVED
            session.commit()

    return user, student, subject, question


def create_isolated_attempt(session, label: str = "") -> dict:
    verified = verify_qa_database_safety(session=session, require_password=True)
    from app.math_solutions.service import MathSolutionService
    from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType

    user, student, subject, question = ensure_qa_student_and_question(session)
    practice = PracticeSession(
        student_id=student.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    session.add(practice)
    session.flush()

    idem_key = f"qa-e2e:{label}:{uuid4()}"[:95]
    svc = MathSolutionService(session)
    snapshot = svc.create(
        user.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key=idem_key,
        question_id=question.id,
        practice_session_id=practice.id,
    )
    return {
        "attempt_id": snapshot["id"],
        "question_id": str(question.id),
        "practice_session_id": str(practice.id),
        "student_email": QA_STUDENT_EMAIL,
        "database_name": verified["connected_database_name"],
        "initial_revision": snapshot["attempt_revision_number"],
        "status": snapshot["status"],
    }


def inspect_attempt(session, attempt_id: UUID) -> dict:
    verified = verify_qa_database_safety(session=session, require_password=True)
    from sqlalchemy import select
    from app.math_ink.models import MathInkDocument, MathInkPage
    from app.math_solutions.models import (
        SolutionAttempt,
        SolutionOperation,
        SolutionStep,
        StepRevision,
    )

    attempt = session.get(SolutionAttempt, attempt_id)
    if attempt is None:
        return {
            "exists": False,
            "attempt_id": str(attempt_id),
            "database_name": verified["connected_database_name"],
        }

    steps_rows = list(
        session.scalars(
            select(SolutionStep)
            .where(SolutionStep.attempt_id == attempt.id)
            .order_by(SolutionStep.step_index, SolutionStep.created_at)
        ).all()
    )
    active_steps = []
    all_steps = []
    for s in steps_rows:
        latest_rev = session.scalar(
            select(StepRevision)
            .where(StepRevision.step_id == s.id)
            .order_by(StepRevision.step_revision_number.desc())
            .limit(1)
        )
        item = {
            "id": str(s.id),
            "step_index": s.step_index,
            "step_type": s.step_type,
            "status": s.status,
            "is_deleted": s.is_deleted,
            "content_latex": s.content_latex,
            "explanation_text": s.explanation_text,
            "step_revision_number": latest_rev.step_revision_number if latest_rev else 0,
        }
        all_steps.append(item)
        if not s.is_deleted:
            active_steps.append(item)

    ops_rows = list(
        session.scalars(
            select(SolutionOperation)
            .where(SolutionOperation.attempt_id == attempt.id)
            .order_by(SolutionOperation.result_attempt_revision, SolutionOperation.created_at)
        ).all()
    )
    operations = [
        {
            "id": str(op.id),
            "client_action_id": str(op.client_action_id),
            "operation_type": op.operation_type,
            "request_hash": op.request_hash,
            "result_attempt_revision": op.result_attempt_revision,
        }
        for op in ops_rows
    ]

    ink_doc = session.scalar(
        select(MathInkDocument).where(MathInkDocument.attempt_id == attempt.id)
    )
    ink_info = None
    if ink_doc is not None:
        ink_pages = list(
            session.scalars(
                select(MathInkPage)
                .where(MathInkPage.document_id == ink_doc.id)
                .order_by(MathInkPage.page_index)
            ).all()
        )
        ink_info = {
            "id": str(ink_doc.id),
            "revision": ink_doc.revision,
            "pages": [
                {
                    "page_index": p.page_index,
                    "stroke_count": p.stroke_count,
                    "point_count": p.point_count,
                    "sha256": p.sha256,
                }
                for p in ink_pages
            ],
        }

    return {
        "exists": True,
        "database_name": verified["connected_database_name"],
        "attempt": {
            "id": str(attempt.id),
            "status": attempt.status,
            "attempt_revision_number": attempt.attempt_revision_number,
            "question_id": str(attempt.question_id) if attempt.question_id else None,
            "practice_session_id": str(attempt.practice_session_id) if attempt.practice_session_id else None,
        },
        "active_step_count": len(active_steps),
        "active_steps": active_steps,
        "all_steps": all_steps,
        "operation_count": len(operations),
        "operations": operations,
        "ink_document": ink_info,
    }


def bump_revision(session, attempt_id: UUID, latex: str = "x \\in \\mathbb{R}") -> dict:
    verified = verify_qa_database_safety(session=session, require_password=True)
    from app.math_solutions.models import SolutionAttempt
    from app.math_solutions.schemas import SolutionStepDraft
    from app.math_solutions.service import MathSolutionService

    user, student, _, question = ensure_qa_student_and_question(session)
    attempt = session.get(SolutionAttempt, attempt_id)
    if attempt is None:
        raise ValueError(f"Attempt {attempt_id} not found")
    if attempt.student_id != student.id or attempt.question_id != question.id:
        raise RuntimeError(
            "QA_E2E_SAFETY_ERROR: Refusing to mutate SolutionAttempt that is not owned by the isolated QA fixture."
        )
    svc = MathSolutionService(session)
    updated = svc.add_step(
        user.id,
        attempt_id,
        expected_attempt_revision=attempt.attempt_revision_number,
        client_action_id=uuid4(),
        draft=SolutionStepDraft(
            step_type="ASSUMPTION",
            content_latex=latex,
            explanation_text="External concurrent step",
            artifact=None,
        ),
    )
    return {
        "attempt_id": str(attempt_id),
        "database_name": verified["connected_database_name"],
        "new_revision": updated["attempt_revision_number"],
        "step_count": len(updated["steps"]),
    }


def main(argv: list[str] | None = None) -> int:
    load_untracked_qa_env()

    parser = argparse.ArgumentParser(description="QA E2E Database Helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("verify-safety")
    sub.add_parser("bootstrap-qa-db")

    p_create = sub.add_parser("create-attempt")
    p_create.add_argument("--label", default="test")

    p_inspect = sub.add_parser("inspect-attempt")
    p_inspect.add_argument("--attempt-id", required=True)

    p_bump = sub.add_parser("bump-revision")
    p_bump.add_argument("--attempt-id", required=True)
    p_bump.add_argument("--latex", default="D = \\mathbb{R}")

    args = parser.parse_args(argv)

    # Pre-check environment safety before opening any DB session
    verify_qa_database_safety(session=None, require_password=True)

    if args.cmd == "bootstrap-qa-db":
        out = bootstrap_dedicated_qa_database()
        print(json.dumps(out))
        return 0

    from app.database.session import dispose_engine, get_session_factory

    try:
        with get_session_factory()() as session:
            verified = verify_qa_database_safety(session=session, require_password=True)
            if args.cmd == "verify-safety":
                print(json.dumps({"ok": True, **verified}))
            elif args.cmd == "create-attempt":
                out = create_isolated_attempt(session, args.label)
                print(json.dumps(out))
            elif args.cmd == "inspect-attempt":
                out = inspect_attempt(session, UUID(args.attempt_id))
                print(json.dumps(out))
            elif args.cmd == "bump-revision":
                out = bump_revision(session, UUID(args.attempt_id), args.latex)
                print(json.dumps(out))
        return 0
    finally:
        dispose_engine()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
