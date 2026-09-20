"""Tests for AI Tutor: TutorContextBuilder, StudentTutorService, and /ai/tutor endpoint.

Uses MockAIProvider and SQLite in-memory DB.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.ai.dependencies import get_ai_gateway
from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.ai.student_tutor_service import StudentTutorService
from app.ai.tutor_context_builder import TutorContextBuilder
from app.ai.tutor_schemas import TutorRequest, TutorResponse
from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.concepts.models import Concept
from app.core.config import Settings
from app.curriculum.models import Chapter, ProblemType, Topic
from app.database.session import get_db
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.models import QuestionAttempt, EvaluationStatus
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TUTOR_TEST_PASSWORD = "Tutor-Test-Password-2026!"


# ─────────────────────────── fixtures ───────────────────────────


@dataclass(frozen=True)
class TutorContent:
    subject: Subject
    concept: Concept
    problem_type: ProblemType
    question: Question
    student: User
    student_profile: StudentProfile
    teacher: User


@pytest.fixture
def tutor_user_factory(db_session: Session) -> Callable[[Role, str], User]:
    def create(role: Role, email: str) -> User:
        return UserService(db_session).create_user(
            UserCreate(
                email=email,
                password=TUTOR_TEST_PASSWORD,
                full_name=f"{role.value.title()} Tutor Test",
                role=role,
            )
        )
    return create


@pytest.fixture
def tutor_content(
    db_session: Session,
    tutor_user_factory: Callable[[Role, str], User],
) -> TutorContent:
    teacher = tutor_user_factory(Role.TEACHER, "tutor-teacher@example.com")
    student = tutor_user_factory(Role.STUDENT, "tutor-student@example.com")

    subject = Subject(code="TUTOR-MATH12", name="Toán học lớp 12", grade_level=12)
    db_session.add(subject)
    db_session.flush()

    chapter = Chapter(
        subject_id=subject.id, code="CALCULUS", name="Giải tích", order_index=0
    )
    concept = Concept(
        subject_id=subject.id,
        code="DERIVATIVE",
        name="Đạo hàm",
        description="Khái niệm đạo hàm và ứng dụng.",
        grade_level=12,
        order_index=0,
    )
    db_session.add_all([chapter, concept])
    db_session.flush()

    topic = Topic(
        chapter_id=chapter.id, code="MONOTONICITY", name="Tính đơn điệu", order_index=0
    )
    db_session.add(topic)
    db_session.flush()

    problem_type = ProblemType(
        topic_id=topic.id,
        code="PARAM_MONOTONE",
        name="Tìm điều kiện tham số cho hàm đơn điệu",
        order_index=0,
    )
    db_session.add(problem_type)
    db_session.flush()

    question = Question(
        subject_id=subject.id,
        content="Tìm giá trị của m để hàm số y = x³ - 3mx đồng biến trên ℝ.",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.6,
        correct_answer=None,
        explanation="Hàm đồng biến khi đạo hàm y' ≥ 0 với mọi x.",
        source_type="TEST",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        created_by=teacher.id,
        concept_links=[QuestionConcept(concept_id=concept.id, weight=1.0)],
        problem_type_links=[
            QuestionProblemType(problem_type_id=problem_type.id, weight=1.0, is_primary=True)
        ],
    )
    db_session.add(question)
    db_session.flush()

    student_profile = (
        db_session.query(StudentProfile).filter_by(user_id=student.id).one()
    )
    db_session.commit()

    return TutorContent(
        subject=subject,
        concept=concept,
        problem_type=problem_type,
        question=question,
        student=student,
        student_profile=student_profile,
        teacher=teacher,
    )


@pytest.fixture
def mock_gateway(settings: Settings) -> AIGateway:
    return AIGateway(provider=MockAIProvider(), settings=settings)


@pytest.fixture
def tutor_bearer(
    db_session: Session, settings: Settings
) -> Callable[[User], dict[str, str]]:
    def headers(user: User) -> dict[str, str]:
        tokens = AuthService(db_session, settings).login(
            LoginRequest(email=user.email, password=TUTOR_TEST_PASSWORD)
        )
        return {"Authorization": f"Bearer {tokens.access_token}"}
    return headers


@pytest.fixture
def tutor_db_client(
    db_app: FastAPI,
    mock_gateway: AIGateway,
    db_engine,
) -> Iterator[TestClient]:
    """Client with mock AI gateway injected."""
    db_app.dependency_overrides[get_ai_gateway] = lambda: mock_gateway
    factory = sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)

    def override_db() -> Iterator[Session]:
        with factory() as s:
            try:
                yield s
            except Exception:
                s.rollback()
                raise

    db_app.dependency_overrides[get_db] = override_db
    with TestClient(db_app, raise_server_exceptions=True) as c:
        yield c
    # cleanup overrides
    db_app.dependency_overrides.pop(get_ai_gateway, None)


# ─────────────────────────── context builder tests ───────────────────────────


@pytest.mark.anyio
async def test_context_builder_basic(
    db_session: Session,
    tutor_content: TutorContent,
    mock_gateway: AIGateway,
) -> None:
    """TutorContextBuilder returns correctly populated TutorContextData."""
    builder = TutorContextBuilder(db_session)
    request = TutorRequest(
        message="Em không hiểu đạo hàm là gì.",
        question_id=tutor_content.question.id,
    )
    ctx = await builder.build_context(
        tutor_content.student, request, gateway=mock_gateway
    )

    assert ctx.student_name == tutor_content.student.full_name
    assert ctx.grade_level == 12
    assert "Toán" in ctx.subject_name or "TUTOR-MATH12" in ctx.subject_name
    assert "Tính đơn điệu" in ctx.topic_name
    assert "đơn điệu" in ctx.problem_type_name.lower() or "monotone" in ctx.problem_type_name.lower()
    assert "Đạo hàm" in ctx.concept_context
    assert "Em không hiểu đạo hàm" in ctx.student_query


@pytest.mark.anyio
async def test_context_builder_no_question(
    db_session: Session,
    tutor_content: TutorContent,
    mock_gateway: AIGateway,
) -> None:
    """Context builder gracefully falls back when no question_id provided."""
    builder = TutorContextBuilder(db_session)
    request = TutorRequest(message="Cho em hỏi về đạo hàm.")
    ctx = await builder.build_context(
        tutor_content.student, request, gateway=mock_gateway
    )
    assert "Không có câu hỏi" in ctx.question_context
    assert ctx.student_query == "Cho em hỏi về đạo hàm."


@pytest.mark.anyio
async def test_context_builder_with_mastery(
    db_session: Session,
    tutor_content: TutorContent,
    mock_gateway: AIGateway,
) -> None:
    """Mastery context includes concept and problem type mastery when records exist."""
    from datetime import datetime, timezone

    db_session.add(
        StudentConceptMastery(
            student_id=tutor_content.student_profile.id,
            concept_id=tutor_content.concept.id,
            mastery_score=0.3,
            confidence=0.5,
            attempt_count=5,
            correct_count=1,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.add(
        StudentProblemTypeMastery(
            student_id=tutor_content.student_profile.id,
            problem_type_id=tutor_content.problem_type.id,
            mastery_score=0.25,
            confidence=0.4,
            attempt_count=4,
            correct_count=1,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    builder = TutorContextBuilder(db_session)
    request = TutorRequest(
        message="Em không hiểu dạng bài này.",
        question_id=tutor_content.question.id,
    )
    ctx = await builder.build_context(
        tutor_content.student, request, gateway=mock_gateway
    )

    assert "Đạo hàm" in ctx.mastery_context
    assert "0.30" in ctx.mastery_context or "0.3" in ctx.mastery_context
    assert "Yếu" in ctx.mastery_context


@pytest.mark.anyio
async def test_context_builder_no_db_writes(
    db_session: Session,
    tutor_content: TutorContent,
    mock_gateway: AIGateway,
) -> None:
    """Building context does NOT create any DB records."""
    from sqlalchemy import text

    def count_all_rows() -> dict[str, int]:
        tables = [
            "student_concept_mastery",
            "student_problem_type_mastery",
            "question_attempts",
        ]
        return {t: db_session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in tables}

    before = count_all_rows()

    builder = TutorContextBuilder(db_session)
    request = TutorRequest(
        message="Em cần giải thích thêm.",
        question_id=tutor_content.question.id,
    )
    await builder.build_context(tutor_content.student, request, gateway=mock_gateway)

    after = count_all_rows()
    assert before == after, "Context builder must not write to the database"


# ─────────────────────────── service tests ───────────────────────────


@pytest.mark.anyio
async def test_tutor_service_returns_response(
    db_session: Session,
    tutor_content: TutorContent,
    mock_gateway: AIGateway,
) -> None:
    """StudentTutorService.tutor() returns a non-empty TutorResponse."""
    service = StudentTutorService(db_session)
    request = TutorRequest(
        message="Đạo hàm của x^3 bằng bao nhiêu?",
        question_id=tutor_content.question.id,
    )
    response = await service.tutor(
        student_user=tutor_content.student,
        gateway=mock_gateway,
        request=request,
    )
    assert isinstance(response, TutorResponse)
    assert response.reply  # non-empty
    assert response.metadata["prompt_name"] == "student_tutor"
    assert response.metadata["prompt_version"] == "v1"


@pytest.mark.anyio
async def test_tutor_service_stream_yields_chunks(
    db_session: Session,
    tutor_content: TutorContent,
    mock_gateway: AIGateway,
) -> None:
    """StudentTutorService.tutor_stream() yields at least one chunk."""
    service = StudentTutorService(db_session)
    request = TutorRequest(
        message="Giải thích cho em về hàm đơn điệu.",
        stream=True,
    )
    chunks: list[str] = []
    async for chunk in service.tutor_stream(
        student_user=tutor_content.student,
        gateway=mock_gateway,
        request=request,
    ):
        chunks.append(chunk)

    assert len(chunks) >= 1
    full = "".join(chunks)
    assert len(full) > 0


# ─────────────────────────── endpoint tests ───────────────────────────


def test_tutor_endpoint_requires_student_role(
    tutor_db_client: TestClient,
    db_session: Session,
    tutor_content: TutorContent,
    tutor_bearer: Callable[[User], dict[str, str]],
) -> None:
    """Non-student (teacher) cannot access /ai/tutor."""
    teacher_headers = tutor_bearer(tutor_content.teacher)
    resp = tutor_db_client.post(
        "/ai/tutor",
        json={"message": "Hello", "stream": False},
        headers=teacher_headers,
    )
    assert resp.status_code == 403


def test_tutor_endpoint_unauthenticated(tutor_db_client: TestClient) -> None:
    """Unauthenticated request returns 401/403."""
    resp = tutor_db_client.post("/ai/tutor", json={"message": "Hi"})
    assert resp.status_code in (401, 403)


def test_tutor_endpoint_non_streaming(
    tutor_db_client: TestClient,
    db_session: Session,
    tutor_content: TutorContent,
    tutor_bearer: Callable[[User], dict[str, str]],
) -> None:
    """POST /ai/tutor with stream=false returns JSON TutorResponse."""
    headers = tutor_bearer(tutor_content.student)
    resp = tutor_db_client.post(
        "/ai/tutor",
        json={
            "message": "Em chưa hiểu bài đạo hàm này.",
            "question_id": str(tutor_content.question.id),
            "stream": False,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "reply" in data
    assert isinstance(data["reply"], str)
    assert len(data["reply"]) > 0
    assert "metadata" in data


def test_tutor_endpoint_streaming(
    tutor_db_client: TestClient,
    tutor_content: TutorContent,
    tutor_bearer: Callable[[User], dict[str, str]],
) -> None:
    """POST /ai/tutor with stream=true returns text/plain streaming response."""
    headers = tutor_bearer(tutor_content.student)
    with tutor_db_client.stream(
        "POST",
        "/ai/tutor",
        json={
            "message": "Hãy giải thích hàm đồng biến.",
            "stream": True,
        },
        headers=headers,
    ) as resp:
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/plain" in content_type
        full = b"".join(resp.iter_bytes()).decode()
        assert len(full) > 0


def test_tutor_endpoint_message_validation(
    tutor_db_client: TestClient,
    tutor_content: TutorContent,
    tutor_bearer: Callable[[User], dict[str, str]],
) -> None:
    """Empty message string is rejected with 422."""
    headers = tutor_bearer(tutor_content.student)
    resp = tutor_db_client.post(
        "/ai/tutor",
        json={"message": "", "stream": False},
        headers=headers,
    )
    assert resp.status_code == 422


def test_tutor_endpoint_does_not_modify_mastery(
    tutor_db_client: TestClient,
    db_session: Session,
    tutor_content: TutorContent,
    tutor_bearer: Callable[[User], dict[str, str]],
) -> None:
    """Calling /ai/tutor does not create or modify any mastery records."""
    from sqlalchemy import text

    def mastery_count() -> int:
        return (
            db_session.execute(text("SELECT COUNT(*) FROM student_concept_mastery")).scalar()
            + db_session.execute(
                text("SELECT COUNT(*) FROM student_problem_type_mastery")
            ).scalar()
        )

    before = mastery_count()

    headers = tutor_bearer(tutor_content.student)
    tutor_db_client.post(
        "/ai/tutor",
        json={"message": "Em cần giúp đỡ về bài này.", "stream": False},
        headers=headers,
    )

    db_session.expire_all()
    after = mastery_count()
    assert before == after, "Tutor endpoint must not modify mastery records"
