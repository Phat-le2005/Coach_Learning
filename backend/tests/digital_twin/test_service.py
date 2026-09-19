from datetime import datetime, timezone

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.database.base import Base
from app.digital_twin.schemas import DigitalTwinContextType
from app.digital_twin.service import StudentDigitalTwinService
from app.curriculum.models import ProblemTypeConcept
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.schemas import PracticeAnswerCreate, PracticeSessionCreate
from app.practice.service import PracticeService
from app.students.models import StudentProfile
from app.users.models import User
from tests.practice.conftest import PracticeContent


def create_attempt(
    session: Session, student: User, content: PracticeContent
) -> StudentProfile:
    service = PracticeService(session)
    practice = service.create_session(
        student,
        PracticeSessionCreate(
            subject_id=content.subject.id,
            session_type="PRACTICE",
            problem_type_ids=[content.problem_type.id],
            concept_ids=[content.concept.id],
        ),
    )
    service.answer(
        student,
        practice.id,
        PracticeAnswerCreate(
            question_id=content.mcq.id,
            student_answer="B",
            response_time_seconds=18.0,
            hint_count=2,
        ),
    )
    profile = session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == student.id)
    )
    assert profile is not None
    return profile


def test_snapshot_reflects_profile_mastery_attempt_and_chapter_aggregate(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    profile = create_attempt(db_session, student, practice_content)
    snapshot = StudentDigitalTwinService(db_session).get_snapshot(profile.id)

    assert snapshot.basic_profile.student_id == profile.id
    assert snapshot.basic_profile.email == student.email
    subject = next(
        item
        for item in snapshot.curriculum_progress
        if item.subject_id == practice_content.subject.id
    )
    problem = subject.chapters[0].topics[0].problem_types[0]
    assert problem.attempt_count == 1
    assert subject.chapters[0].mastery_score == problem.mastery_score
    assert snapshot.knowledge_state.concepts[0].attempt_count == 1
    assert snapshot.recent_attempts[0].question_id == practice_content.mcq.id
    assert snapshot.recent_attempts[0].concept_ids == [practice_content.concept.id]
    assert snapshot.study_behavior.total_sessions == 1
    assert snapshot.study_behavior.total_attempts == 1
    assert snapshot.study_behavior.total_hints == 2


def test_weak_problem_type_and_weak_prerequisite_concept_remain_distinct(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    profile = create_attempt(db_session, student, practice_content)
    prerequisite = Concept(
        subject_id=practice_content.subject.id,
        code="INEQUALITY_SOLVING_TWIN",
        name="Inequality solving",
        description="Solve inequalities before parameter monotonicity.",
        grade_level=12,
        order_index=50,
    )
    db_session.add(prerequisite)
    db_session.flush()
    db_session.add(
        ConceptRelation(
            source_concept_id=prerequisite.id,
            target_concept_id=practice_content.concept.id,
            relation_type=RelationType.PREREQUISITE,
        )
    )
    db_session.add(
        ProblemTypeConcept(
            problem_type_id=practice_content.problem_type.id,
            concept_id=prerequisite.id,
            weight=1.0,
            is_primary=True,
        )
    )
    concept_row = db_session.get(
        StudentConceptMastery, (profile.id, practice_content.concept.id)
    )
    problem_row = db_session.get(
        StudentProblemTypeMastery, (profile.id, practice_content.problem_type.id)
    )
    assert concept_row is not None and problem_row is not None
    concept_row.mastery_score = 0.65
    concept_row.confidence = 0.6
    concept_row.attempt_count = 4
    concept_row.correct_count = 3
    problem_row.mastery_score = 0.2
    problem_row.confidence = 0.6
    problem_row.attempt_count = 4
    problem_row.correct_count = 1
    now = datetime.now(timezone.utc)
    db_session.add(
        StudentConceptMastery(
            student_id=profile.id,
            concept_id=prerequisite.id,
            mastery_score=0.25,
            confidence=0.6,
            attempt_count=5,
            correct_count=1,
            last_practiced_at=now,
            last_updated_at=now,
        )
    )
    db_session.commit()

    snapshot = StudentDigitalTwinService(db_session).get_snapshot(profile.id)
    assert [item.code for item in snapshot.weak_problem_types] == [
        practice_content.problem_type.code
    ]
    assert [item.code for item in snapshot.knowledge_state.weak_concepts] == [
        prerequisite.code
    ]
    target = next(
        item
        for item in snapshot.knowledge_state.concepts
        if item.concept_id == practice_content.concept.id
    )
    assert [item.concept_id for item in target.prerequisites] == [prerequisite.id]
    assert target.prerequisites[0].state == "WEAK"
    assert snapshot.knowledge_state.problem_type_concept_links[0].concept_id == prerequisite.id


def test_snapshot_is_recomputed_and_has_no_duplicate_source_table(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    profile = create_attempt(db_session, student, practice_content)
    service = StudentDigitalTwinService(db_session)
    first = service.get_snapshot(profile.id)
    first_problem = first.curriculum_progress[0].chapters[0].topics[0].problem_types[0]
    row = db_session.get(
        StudentProblemTypeMastery, (profile.id, practice_content.problem_type.id)
    )
    assert row is not None
    row.mastery_score = 0.42
    db_session.commit()
    second = service.get_snapshot(profile.id)
    second_problem = second.curriculum_progress[0].chapters[0].topics[0].problem_types[0]

    assert first_problem.mastery_score != second_problem.mastery_score
    assert second_problem.mastery_score == 0.42
    assert not any("digital_twin" in name for name in Base.metadata.tables)
    payload = second.model_dump()
    for unavailable_domain in (
        "academic_goal",
        "known_misconceptions",
        "study_plan",
        "exam_performance",
        "risk_indicators",
    ):
        assert unavailable_domain not in payload


def test_ai_contexts_are_trimmed_for_each_consumer(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    profile = create_attempt(db_session, student, practice_content)
    service = StudentDigitalTwinService(db_session)

    tutor = service.get_ai_context(profile.id, DigitalTwinContextType.TUTOR).model_dump()
    planner = service.get_ai_context(profile.id, "PLANNER").model_dump()
    parent = service.get_ai_context(profile.id, "PARENT_SUMMARY").model_dump()
    exam = service.get_ai_context(profile.id, "EXAM_ANALYSIS").model_dump()

    assert set(tutor) == {
        "context_type",
        "student_id",
        "weak_problem_types",
        "weak_concepts",
        "problem_type_concept_links",
        "review_due",
        "recent_attempts",
    }
    assert "recent_attempts" not in planner
    assert "basic_profile" not in planner
    assert "student_id" not in parent
    assert "recent_attempts" not in parent
    assert "knowledge_state" not in parent
    assert "email" not in parent
    assert exam["recent_exam_attempts"] == []
    assert "recent_attempts" not in exam


def test_snapshot_uses_bounded_batch_queries(
    db_session: Session,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    student, _ = practice_students
    profile = create_attempt(db_session, student, practice_content)
    statements = 0

    def count_query(*args: object, **kwargs: object) -> None:
        nonlocal statements
        statements += 1

    engine = db_session.get_bind()
    event.listen(engine, "before_cursor_execute", count_query)
    try:
        StudentDigitalTwinService(db_session).get_snapshot(profile.id)
    finally:
        event.remove(engine, "before_cursor_execute", count_query)

    # Profile, seven mastery batches, prerequisites, global problem/concept
    # mappings, three recent-attempt batches, and two behavior aggregates.
    # The count does not grow per row.
    assert statements <= 16
