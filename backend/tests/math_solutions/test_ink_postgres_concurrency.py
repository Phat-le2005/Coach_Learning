"""Real PostgreSQL race and migration checks for Math Ink persistence."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import ApplicationError
from app.math_ink.codec import encode_strokes
from app.math_ink.models import MathInkDocument, MathInkOperation, MathInkPage
from app.math_ink.schemas import InkPageWrite, InkPoint, InkStroke
from app.math_ink.service import MathInkService
from app.math_solutions.service import MathSolutionService
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role
from app.users.schemas import UserCreate
from app.users.service import UserService
from tests.migrations import load_migration


PASSWORD = "Ink-Postgres-Password-2026!"


def _page(revision: int, x: float) -> InkPageWrite:
    return InkPageWrite(
        expected_document_revision=revision,
        client_action_id=uuid4(),
        strokes=[
            InkStroke(
                id=uuid4(),
                tool="PEN",
                color="#225544",
                width=2,
                points=[InkPoint(x=x, y=0.4)],
            )
        ],
    )


def _create_attempt(session: Session) -> tuple[UUID, UUID]:
    suffix = uuid4().hex[:10].upper()
    users = UserService(session)
    student = users.create_user(
        UserCreate(
            email=f"ink-pg-student-{suffix}@example.com",
            password=PASSWORD,
            full_name="Ink PostgreSQL Student",
            role=Role.STUDENT,
        )
    )
    teacher = users.create_user(
        UserCreate(
            email=f"ink-pg-teacher-{suffix}@example.com",
            password=PASSWORD,
            full_name="Ink PostgreSQL Teacher",
            role=Role.TEACHER,
        )
    )
    profile = session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    assert profile is not None

    subject = Subject(
        code=f"INK-PG-{suffix}",
        name="Ink PostgreSQL Concurrency",
        grade_level=12,
    )
    session.add(subject)
    session.flush()
    question = Question(
        subject_id=subject.id,
        content=f"Concurrent ink save test {suffix}",
        question_type=QuestionType.OPEN_RESPONSE,
        difficulty=0.5,
        correct_answer=None,
        explanation="Test-only question",
        source_type="TEST",
        source_reference=f"ink-pg-{suffix}",
        exam_weight=0.5,
        status=QuestionStatus.APPROVED,
        created_by=teacher.id,
    )
    session.add(question)
    session.flush()
    practice = PracticeSession(
        student_id=profile.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    session.add(practice)
    session.commit()

    attempt = MathSolutionService(session).create(
        student.id,
        source_kind="CANONICAL",
        context_type="SELF_PRACTICE",
        mode="INDEPENDENT_SOLUTION",
        create_idempotency_key=f"ink-pg-{suffix}",
        question_id=question.id,
        practice_session_id=practice.id,
    )
    return student.id, UUID(attempt["id"])


def test_concurrent_saves_with_same_revision_allow_exactly_one_writer(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)
    with factory() as session:
        student_id, attempt_id = _create_attempt(session)
        initial = _page(0, 0.1)
        saved = MathInkService(session).save_page(student_id, attempt_id, 0, initial)
        assert saved.document_revision == 1

    candidates = [_page(1, 0.2), _page(1, 0.3)]
    barrier = Barrier(2)

    def save(payload: InkPageWrite) -> tuple[str, int | str]:
        with factory() as session:
            barrier.wait(timeout=10)
            try:
                result = MathInkService(session).save_page(
                    student_id, attempt_id, 0, payload
                )
                return "saved", result.document_revision
            except ApplicationError as exc:
                session.rollback()
                return "rejected", exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(save, payload) for payload in candidates]
        results = [future.result(timeout=25) for future in futures]

    assert [result[0] for result in results].count("saved") == 1
    assert [result[0] for result in results].count("rejected") == 1
    assert ("saved", 2) in results
    assert ("rejected", "INK_REVISION_CONFLICT") in results

    allowed_hashes = {encode_strokes(payload.strokes)[1] for payload in candidates}
    with factory() as session:
        document = session.scalar(
            select(MathInkDocument).where(MathInkDocument.attempt_id == attempt_id)
        )
        assert document is not None and document.revision == 2
        page = session.scalar(
            select(MathInkPage).where(
                MathInkPage.document_id == document.id, MathInkPage.page_index == 0
            )
        )
        assert page is not None and page.sha256 in allowed_hashes
        assert len(
            session.scalars(
                select(MathInkOperation).where(
                    MathInkOperation.document_id == document.id
                )
            ).all()
        ) == 2


def test_math_ink_retention_index_migration_can_downgrade_and_upgrade_postgres(
    postgres_engine: Engine,
) -> None:
    migration = load_migration("0048_math_ink_retention_index")
    index_name = "ix_math_ink_operations_created_at_id"

    with postgres_engine.begin() as connection:
        assert inspect(connection).has_index("math_ink_operations", index_name)
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert not inspect(connection).has_index("math_ink_operations", index_name)
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert inspect(connection).has_index("math_ink_operations", index_name)
