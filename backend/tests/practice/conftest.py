from collections.abc import Callable
from dataclasses import dataclass

import pytest
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.concepts.models import Concept
from app.core.config import Settings
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

PRACTICE_TEST_PASSWORD = "Practice-Engine-Test-Password-2026!"


@dataclass(frozen=True)
class PracticeContent:
    subject: Subject
    concept: Concept
    problem_type: ProblemType
    learning_outcome: LearningOutcome
    mcq: Question
    true_false: Question
    short_answer: Question
    open_response: Question
    draft: Question
    unclassified: Question


@pytest.fixture
def practice_user_factory(db_session: Session) -> Callable[[Role, str], User]:
    def create(role: Role, email: str) -> User:
        return UserService(db_session).create_user(
            UserCreate(
                email=email,
                password=PRACTICE_TEST_PASSWORD,
                full_name=f"{role.value.title()} Practice User",
                role=role,
            )
        )

    return create


@pytest.fixture
def practice_bearer(
    db_session: Session, settings: Settings
) -> Callable[[User], dict[str, str]]:
    def headers(user: User) -> dict[str, str]:
        tokens = AuthService(db_session, settings).login(
            LoginRequest(email=user.email, password=PRACTICE_TEST_PASSWORD)
        )
        return {"Authorization": f"Bearer {tokens.access_token}"}

    return headers


@pytest.fixture
def practice_students(
    practice_user_factory: Callable[[Role, str], User],
) -> tuple[User, User]:
    return (
        practice_user_factory(Role.STUDENT, "practice-student@example.com"),
        practice_user_factory(Role.STUDENT, "practice-outsider@example.com"),
    )


@pytest.fixture
def practice_content(
    db_session: Session,
    practice_user_factory: Callable[[Role, str], User],
) -> PracticeContent:
    teacher = practice_user_factory(Role.TEACHER, "practice-author@example.com")
    subject = Subject(code="PRACTICE-MATH12", name="Practice Mathematics 12", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    chapter = Chapter(
        subject_id=subject.id,
        code="FUNCTIONS",
        name="Functions",
        description="Function chapter",
        order_index=0,
    )
    concept = Concept(
        subject_id=subject.id,
        code="MONOTONICITY-PRACTICE",
        name="Monotonicity",
        description="Monotonicity concept",
        grade_level=12,
        order_index=0,
    )
    outcome = LearningOutcome(
        subject_id=subject.id,
        code="LO-MONOTONICITY-PRACTICE",
        description="Analyze monotonicity of a function.",
        grade_level=12,
        order_index=0,
    )
    db_session.add_all([chapter, concept, outcome])
    db_session.flush()
    topic = Topic(
        chapter_id=chapter.id,
        code="MONOTONICITY",
        name="Monotonicity",
        description="Monotonicity topic",
        order_index=0,
    )
    db_session.add(topic)
    db_session.flush()
    problem_type = ProblemType(
        topic_id=topic.id,
        code="PARAMETER_MONOTONICITY_PRACTICE",
        name="Parameter monotonicity",
        description="Find parameter conditions for monotonicity.",
        order_index=0,
    )
    db_session.add(problem_type)
    db_session.flush()

    def question(
        content: str,
        question_type: QuestionType,
        correct_answer: str | None,
        *,
        status: QuestionStatus = QuestionStatus.APPROVED,
        classified: bool = True,
        options: list[QuestionOption] | None = None,
    ) -> Question:
        item = Question(
            subject_id=subject.id,
            content=content,
            question_type=question_type,
            difficulty=0.5,
            correct_answer=correct_answer,
            explanation="Deterministic test explanation",
            source_type="TEST",
            source_reference="practice-suite",
            exam_weight=0.5,
            status=status,
            created_by=teacher.id,
            options=options or [],
        )
        if classified:
            item.concept_links = [QuestionConcept(concept_id=concept.id, weight=1.0)]
            item.problem_type_links = [
                QuestionProblemType(problem_type_id=problem_type.id, weight=1.0, is_primary=True)
            ]
            item.learning_outcome_links = [
                QuestionLearningOutcome(learning_outcome_id=outcome.id, weight=1.0)
            ]
        return item

    mcq = question(
        "Which interval makes the function increasing?",
        QuestionType.MULTIPLE_CHOICE,
        "B",
        options=[
            QuestionOption(label="A", content="Negative interval", order_index=0),
            QuestionOption(label="B", content="Positive interval", order_index=1),
        ],
    )
    true_false = question(
        "A positive derivative implies increasing behavior.",
        QuestionType.TRUE_FALSE,
        "TRUE",
    )
    short_answer = question(
        "Enter the normalized exact answer.",
        QuestionType.SHORT_ANSWER,
        "Đáp án chuẩn",
    )
    open_response = question(
        "Explain the monotonicity argument.",
        QuestionType.OPEN_RESPONSE,
        None,
    )
    draft = question(
        "Draft question must not be selected.",
        QuestionType.TRUE_FALSE,
        "TRUE",
        status=QuestionStatus.DRAFT,
    )
    unclassified = question(
        "Approved but unclassified question.",
        QuestionType.TRUE_FALSE,
        "TRUE",
        classified=False,
    )
    db_session.add_all([mcq, true_false, short_answer, open_response, draft, unclassified])
    db_session.commit()
    return PracticeContent(
        subject=subject,
        concept=concept,
        problem_type=problem_type,
        learning_outcome=outcome,
        mcq=mcq,
        true_false=true_false,
        short_answer=short_answer,
        open_response=open_response,
        draft=draft,
        unclassified=unclassified,
    )


@pytest.fixture
def student_profile(db_session: Session, practice_students: tuple[User, User]) -> StudentProfile:
    profile = db_session.query(StudentProfile).filter_by(user_id=practice_students[0].id).one()
    return profile

