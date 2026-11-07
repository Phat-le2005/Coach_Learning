from contextlib import contextmanager
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import seed_step_review_demo
from app.curriculum.constants import LEGACY_CURRICULUM_VERSION_ID
from app.curriculum.models import CurriculumVersion
from app.math_solutions.answer_reference import resolve_answer_reference
from app.math_solutions.models import SolutionAttempt
from app.math_solutions.service import MathSolutionService
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService


def test_demo_reference_command_refuses_production(monkeypatch):
    monkeypatch.setattr(seed_step_review_demo, "get_settings", lambda: SimpleNamespace(app_env="production"))
    with pytest.raises(RuntimeError, match="disabled in production"):
        seed_step_review_demo.install()


def test_demo_reference_contains_checkable_step_sequence():
    answer = seed_step_review_demo.DEMO_ANSWER
    explanation = seed_step_review_demo.DEMO_EXPLANATION
    for marker in ("x²-2x-3", "x=-1", "x=3", "8/3", "-8"):
        assert marker in answer + explanation


def _ensure_test_fixtures(db_session: Session):
    version = db_session.get(CurriculumVersion, LEGACY_CURRICULUM_VERSION_ID)
    if not version:
        version = CurriculumVersion(id=LEGACY_CURRICULUM_VERSION_ID, version_code="VER-2018", name="CTGD 2018")
        db_session.add(version)
        db_session.commit()

    subject = db_session.query(Subject).filter(Subject.code == "MATH_G12").first()
    if not subject:
        subject = Subject(
            id=uuid4(),
            curriculum_version_id=LEGACY_CURRICULUM_VERSION_ID,
            code="MATH_G12",
            name="Toán 12",
        )
        db_session.add(subject)
        db_session.commit()

    teacher = UserService(db_session).create_user(
        UserCreate(
            email=f"teacher-{uuid4().hex[:8]}@example.com",
            password="DemoPassword@2026!",
            full_name="Teacher Math Demo",
            role=Role.TEACHER,
        )
    )
    return subject, teacher


def test_demo_install_creates_question_if_missing(db_session: Session, monkeypatch):
    _ensure_test_fixtures(db_session)

    @contextmanager
    def mock_session_factory():
        yield db_session

    monkeypatch.setattr(seed_step_review_demo, "get_session_factory", lambda: mock_session_factory)
    monkeypatch.setattr(seed_step_review_demo, "get_settings", lambda: SimpleNamespace(app_env="test"))

    result = seed_step_review_demo.install()
    assert result == "installed"

    q = db_session.get(Question, seed_step_review_demo.DEMO_QUESTION_ID)
    assert q is not None
    assert q.source_type == "SAMPLE_TEST"
    assert q.question_type == QuestionType.OPEN_RESPONSE
    assert q.status == QuestionStatus.APPROVED
    assert q.correct_answer == seed_step_review_demo.DEMO_ANSWER
    assert q.explanation == seed_step_review_demo.DEMO_EXPLANATION
    assert seed_step_review_demo.DEMO_CONTENT_MARKER in q.content

    # Verify idempotency
    assert seed_step_review_demo.install() == "already_installed"


def test_demo_install_enables_math_solution_create_and_ai_review(db_session: Session, monkeypatch):
    subject, _ = _ensure_test_fixtures(db_session)

    @contextmanager
    def mock_session_factory():
        yield db_session

    monkeypatch.setattr(seed_step_review_demo, "get_session_factory", lambda: mock_session_factory)
    monkeypatch.setattr(seed_step_review_demo, "get_settings", lambda: SimpleNamespace(app_env="test"))

    seed_step_review_demo.install()

    student = UserService(db_session).create_user(
        UserCreate(
            email=f"student-{uuid4().hex[:8]}@example.com",
            password="DemoPassword@2026!",
            full_name="Student Demo",
            role=Role.STUDENT,
        )
    )

    profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    assert profile is not None

    practice_session = PracticeSession(
        id=uuid4(),
        student_id=profile.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    db_session.add(practice_session)
    db_session.commit()

    service = MathSolutionService(db_session)
    attempt_dict = service.create(
        actor_user_id=student.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key=f"demo-test-{uuid4()}",
        question_id=seed_step_review_demo.DEMO_QUESTION_ID,
        practice_session_id=practice_session.id,
    )
    assert attempt_dict["status"] in {"DRAFT", "IN_PROGRESS"}
    assert attempt_dict["question_id"] == str(seed_step_review_demo.DEMO_QUESTION_ID)

    attempt_entity = db_session.get(SolutionAttempt, UUID(attempt_dict["id"]))
    assert attempt_entity is not None
    ref = resolve_answer_reference(db_session, attempt_entity, require_submitted=False)
    assert ref.correct_answer == seed_step_review_demo.DEMO_ANSWER
    assert ref.explanation == seed_step_review_demo.DEMO_EXPLANATION
