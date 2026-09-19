from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.curriculum.models import ProblemType, Topic
from app.mastery.aggregation import MasteryAggregationService
from app.mastery.models import StudentProblemTypeMastery
from app.mastery.state import DerivedMasteryState, derive_mastery_state
from app.practice.schemas import PracticeAnswerCreate, PracticeSessionCreate
from app.practice.service import PracticeService
from app.students.models import StudentProfile
from app.users.models import User
from tests.practice.conftest import PracticeContent


def test_topic_chapter_and_subject_aggregate_active_problem_types_without_storing_rows(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    extra = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code="UNSTARTED_ACTIVE_PROBLEM",
        name="Unstarted active problem",
        description="Included as zero in hierarchy aggregate",
        order_index=20,
        is_active=True,
    )
    db_session.add(extra)
    db_session.commit()
    service = PracticeService(db_session)
    practice = service.create_session(
        student,
        PracticeSessionCreate(
            subject_id=practice_content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=[practice_content.problem_type.id],
            concept_ids=[practice_content.concept.id],
        ),
    )
    service.answer(
        student,
        practice.id,
        PracticeAnswerCreate(question_id=practice_content.mcq.id, student_answer="B"),
    )
    profile = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    assert profile is not None
    leaf = db_session.get(
        StudentProblemTypeMastery, (profile.id, practice_content.problem_type.id)
    )
    assert leaf is not None
    aggregation = MasteryAggregationService(db_session)
    topic = aggregation.get_topic_mastery(profile.id, practice_content.problem_type.topic_id)
    chapter_id = db_session.scalar(
        select(Topic.chapter_id).where(Topic.id == practice_content.problem_type.topic_id)
    )
    assert chapter_id is not None
    chapter = aggregation.get_chapter_mastery(profile.id, chapter_id)
    subject = aggregation.get_subject_mastery(profile.id, practice_content.subject.id)

    assert topic.problem_type_count == 2
    assert topic.started_problem_type_count == 1
    assert topic.mastery_score == round(leaf.mastery_score / 2, 6)
    assert chapter.mastery_score == topic.mastery_score
    assert subject.mastery_score == topic.mastery_score
    assert db_session.query(StudentProblemTypeMastery).count() == 1


def test_derived_state_handles_not_started_mastered_and_review_due() -> None:
    now = datetime(2026, 9, 18, tzinfo=timezone.utc)
    assert derive_mastery_state(
        mastery_score=0.0,
        confidence=0.0,
        attempt_count=0,
        last_practiced_at=None,
        as_of=now,
    ) == DerivedMasteryState.NOT_STARTED
    assert derive_mastery_state(
        mastery_score=0.2,
        confidence=0.1,
        attempt_count=1,
        last_practiced_at=now,
        as_of=now,
    ) == DerivedMasteryState.LEARNING
    assert derive_mastery_state(
        mastery_score=0.25,
        confidence=0.4,
        attempt_count=4,
        last_practiced_at=now,
        as_of=now,
    ) == DerivedMasteryState.WEAK
    assert derive_mastery_state(
        mastery_score=0.6,
        confidence=0.5,
        attempt_count=4,
        last_practiced_at=now,
        as_of=now,
    ) == DerivedMasteryState.PRACTICING
    assert derive_mastery_state(
        mastery_score=0.85,
        confidence=0.8,
        attempt_count=10,
        last_practiced_at=datetime(2026, 9, 17, tzinfo=timezone.utc),
        as_of=now,
    ) == DerivedMasteryState.MASTERED
    assert derive_mastery_state(
        mastery_score=0.85,
        confidence=0.8,
        attempt_count=10,
        last_practiced_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        as_of=now,
    ) == DerivedMasteryState.REVIEW_DUE
