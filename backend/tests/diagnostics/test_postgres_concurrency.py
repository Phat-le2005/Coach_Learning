"""PostgreSQL concurrency tests for diagnostic assessment row-locking."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from app.concepts.models import Concept
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.diagnostics.schemas import DiagnosticQuestionRead, DiagnosticStartCreate
from app.diagnostics.service import DiagnosticService
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.subjects.models import Subject
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService


def test_concurrent_next_does_not_allocate_two_questions(
    postgres_engine: Engine,
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False)

    with factory() as session:
        teacher = UserService(session).create_user(
            UserCreate(
                email="diag_pg_teacher@example.com",
                password="Teacher-Password-2026!",
                full_name="Diag PG Teacher",
                role=Role.TEACHER,
            )
        )
        student = UserService(session).create_user(
            UserCreate(
                email="diag_pg_student@example.com",
                password="Student-Password-2026!",
                full_name="Diag PG Student",
                role=Role.STUDENT,
            )
        )
        subject = Subject(code="DIAG-PG-MATH", name="PG Mathematics", grade_level=12)
        session.add(subject)
        session.flush()

        chapter = Chapter(subject_id=subject.id, code="PG-CH1", name="PG Chapter 1", order_index=0)
        concept = Concept(subject_id=subject.id, code="PG-C1", name="PG Concept 1", grade_level=12, order_index=0)
        outcome = LearningOutcome(subject_id=subject.id, code="PG-LO1", description="PG LO 1", grade_level=12, order_index=0)
        session.add_all([chapter, concept, outcome])
        session.flush()

        topic = Topic(chapter_id=chapter.id, code="PG-TOPIC1", name="PG Topic 1", order_index=0)
        session.add(topic)
        session.flush()

        problem_type = ProblemType(
            topic_id=topic.id, code="PG-PT1", name="PG Problem Type 1", order_index=0, is_active=True
        )
        session.add(problem_type)
        session.flush()

        q = Question(
            subject_id=subject.id,
            content="PostgreSQL Diagnostic Concurrent Question?",
            question_type=QuestionType.TRUE_FALSE,
            difficulty=0.55,
            correct_answer="TRUE",
            explanation="PG Test Explanation",
            source_type="TEST",
            source_reference="postgres-concurrency",
            exam_weight=0.5,
            status=QuestionStatus.APPROVED,
            created_by=teacher.id,
            concept_links=[QuestionConcept(concept_id=concept.id, weight=1.0)],
            problem_type_links=[
                QuestionProblemType(problem_type_id=problem_type.id, weight=1.0, is_primary=True)
            ],
            learning_outcome_links=[
                QuestionLearningOutcome(learning_outcome_id=outcome.id, weight=1.0)
            ],
        )
        session.add(q)
        session.commit()

        service = DiagnosticService(session)
        started = service.start(
            student,
            DiagnosticStartCreate(
                subject_id=subject.id,
                max_questions=4,
                minimum_problem_type_coverage=1.0,
                confidence_threshold=1.0,
            ),
        )
        diagnostic_id = started.id
        student_id = student.id

    barrier = Barrier(2)

    def fetch_next() -> DiagnosticQuestionRead:
        with factory() as thread_session:
            thread_student = thread_session.get(User, student_id)
            assert thread_student is not None
            thread_service = DiagnosticService(thread_session)
            barrier.wait(timeout=10)
            return thread_service.next_question(thread_student, diagnostic_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        future_a = pool.submit(fetch_next)
        future_b = pool.submit(fetch_next)
        result_a = future_a.result(timeout=20)
        result_b = future_b.result(timeout=20)

    # Both concurrent requests on SAME diagnostic_id must receive the EXACT same question
    assert result_a.question is not None
    assert result_b.question is not None
    assert result_a.question.id == result_b.question.id
    assert result_a.target_problem_type_id == result_b.target_problem_type_id
    assert result_a.desired_difficulty == result_b.desired_difficulty
