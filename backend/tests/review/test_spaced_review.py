from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, ProblemTypeConcept, Topic
from app.mastery.evidence import MasteryAttemptEvidencePublisher
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.practice.evidence import AttemptEvaluatedEvidence
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.review.models import ReviewResult, ReviewSchedule
from app.review.policy import ReviewPolicy, ReviewThresholds
from app.review.service import ReviewScheduleService
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "SpacedReview-Secret-2026!"


def _create_user(session: Session, role: Role, email: str) -> User:
    return UserService(session).create_user(
        UserCreate(email=email, password=TEST_PASSWORD, full_name=f"{role.value} User", role=role)
    )


def _setup_review_environment(
    session: Session, prefix: str = "SR"
) -> tuple[Subject, ProblemType, Concept, User, User]:
    teacher = _create_user(session, Role.TEACHER, f"{prefix.lower()}.teacher@example.com")
    student = _create_user(session, Role.STUDENT, f"{prefix.lower()}.student@example.com")

    subject = Subject(code=f"{prefix}-SUB", name=f"{prefix} Subject", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{prefix}-CHP", name="Chapter", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{prefix}-TOP", name="Topic", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT",
        name="Problem Type",
        order_index=0,
        is_active=True,
    )
    concept = Concept(subject_id=subject.id, code=f"{prefix}-CON", name="Concept", order_index=0)
    session.add_all([pt, concept])
    session.flush()

    session.add(ProblemTypeConcept(problem_type_id=pt.id, concept_id=concept.id, weight=1.0, is_primary=True))
    session.commit()

    return subject, pt, concept, teacher, student


def test_schedule_creation_for_problem_type(db_session: Session) -> None:
    subject, pt, concept, teacher, student = _setup_review_environment(db_session, "PTSCHED")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))

    service = ReviewScheduleService(db_session)
    now = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)

    schedule = service.ensure_problem_type_schedule(student_profile.id, pt.id, as_of=now)
    assert schedule.student_id == student_profile.id
    assert schedule.problem_type_id == pt.id
    assert schedule.concept_id is None
    assert schedule.review_interval_days == 1.0
    assert schedule.review_count == 0
    assert schedule.last_review_result is None
    assert schedule.next_review_at == now + timedelta(days=1.0)


def test_schedule_creation_for_concept(db_session: Session) -> None:
    subject, pt, concept, teacher, student = _setup_review_environment(db_session, "CNSCHED")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))

    service = ReviewScheduleService(db_session)
    now = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)

    schedule = service.ensure_concept_schedule(student_profile.id, concept.id, as_of=now)
    assert schedule.student_id == student_profile.id
    assert schedule.concept_id == concept.id
    assert schedule.problem_type_id is None
    assert schedule.review_interval_days == 1.0
    assert schedule.review_count == 0
    assert schedule.next_review_at == now + timedelta(days=1.0)


def test_no_duplicate_schedule(db_session: Session) -> None:
    subject, pt, concept, teacher, student = _setup_review_environment(db_session, "NODUP")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))

    service = ReviewScheduleService(db_session)
    now = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)

    # 1. Service idempotency
    s1 = service.ensure_problem_type_schedule(student_profile.id, pt.id, as_of=now)
    s2 = service.ensure_problem_type_schedule(student_profile.id, pt.id, as_of=now)
    assert s1.id == s2.id

    # 2. Database level unique constraint
    dup_row = ReviewSchedule(
        student_id=student_profile.id,
        problem_type_id=pt.id,
        concept_id=None,
        next_review_at=now + timedelta(days=2),
        review_interval_days=2.0,
    )
    db_session.add(dup_row)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_single_target_check_constraint(db_session: Session) -> None:
    subject, pt, concept, teacher, student = _setup_review_environment(db_session, "CHK")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))
    now = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)

    # Both problem_type_id and concept_id provided -> violates CHECK
    invalid_both = ReviewSchedule(
        student_id=student_profile.id,
        problem_type_id=pt.id,
        concept_id=concept.id,
        next_review_at=now,
    )
    db_session.add(invalid_both)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Neither provided -> violates CHECK
    invalid_none = ReviewSchedule(
        student_id=student_profile.id,
        problem_type_id=None,
        concept_id=None,
        next_review_at=now,
    )
    db_session.add(invalid_none)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_interval_growth_on_good_performance(db_session: Session) -> None:
    subject, pt, concept, teacher, student = _setup_review_environment(db_session, "GROWTH")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))

    service = ReviewScheduleService(db_session)
    t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)

    # Initial creation: interval = 1.0 day
    schedule = service.ensure_problem_type_schedule(student_profile.id, pt.id, as_of=t0)
    assert schedule.review_interval_days == 1.0

    # Review 1: Good performance (score = 0.85) -> interval = 2.0 days
    t1 = t0 + timedelta(days=1.0)
    updated1 = service.record_performance(
        student_profile.id, target_problem_type_id=pt.id, score=0.85, as_of=t1
    )
    assert updated1.review_interval_days == 2.0
    assert updated1.review_count == 1
    assert updated1.last_review_result == ReviewResult.GOOD.value
    assert updated1.next_review_at == t1 + timedelta(days=2.0)

    # Review 2: Good performance (is_correct = True) -> interval = 4.0 days
    t2 = t1 + timedelta(days=2.0)
    updated2 = service.record_performance(
        student_profile.id, target_problem_type_id=pt.id, is_correct=True, as_of=t2
    )
    assert updated2.review_interval_days == 4.0
    assert updated2.review_count == 2
    assert updated2.last_review_result == ReviewResult.GOOD.value
    assert updated2.next_review_at == t2 + timedelta(days=4.0)


def test_interval_reduction_on_weak_performance(db_session: Session) -> None:
    subject, pt, concept, teacher, student = _setup_review_environment(db_session, "REDUC")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))

    service = ReviewScheduleService(db_session)
    t0 = datetime(2026, 9, 20, 10, 0, 0, tzinfo=timezone.utc)

    # Set up schedule with interval 8.0 days
    schedule = service.ensure_problem_type_schedule(
        student_profile.id, pt.id, as_of=t0, initial_interval_days=8.0
    )
    assert schedule.review_interval_days == 8.0

    # Review 1: Weak performance (score = 0.3) -> interval reduced to 4.0 days (reduction_factor = 0.5)
    t1 = t0 + timedelta(days=8.0)
    updated1 = service.record_performance(
        student_profile.id, target_problem_type_id=pt.id, score=0.3, as_of=t1
    )
    assert updated1.review_interval_days == 4.0
    assert updated1.review_count == 1
    assert updated1.last_review_result == ReviewResult.POOR.value
    assert updated1.next_review_at == t1 + timedelta(days=4.0)

    # Review 2: Weak performance (is_correct = False) -> interval reduced to 2.0 days
    t2 = t1 + timedelta(days=4.0)
    updated2 = service.record_performance(
        student_profile.id, target_problem_type_id=pt.id, is_correct=False, as_of=t2
    )
    assert updated2.review_interval_days == 2.0
    assert updated2.review_count == 2
    assert updated2.last_review_result == ReviewResult.POOR.value

    # Review 3: Weak performance -> bounded at min_interval_days (1.0)
    t3 = t2 + timedelta(days=2.0)
    updated3 = service.record_performance(
        student_profile.id, target_problem_type_id=pt.id, score=0.1, as_of=t3
    )
    assert updated3.review_interval_days == 1.0


def test_review_due_detection(db_session: Session) -> None:
    subject, pt, concept, teacher, student = _setup_review_environment(db_session, "DUE")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))

    service = ReviewScheduleService(db_session)
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    # ProblemType schedule is DUE (next_review_at was yesterday)
    s_pt = service.ensure_problem_type_schedule(
        student_profile.id, pt.id, as_of=now - timedelta(days=2.0), initial_interval_days=1.0
    )

    # Concept schedule is NOT DUE (next_review_at is in 5 days)
    s_c = service.ensure_concept_schedule(
        student_profile.id, concept.id, as_of=now, initial_interval_days=5.0
    )

    # Query due schedules as of now
    due_schedules = service.get_due_schedules(student_profile.id, as_of=now)
    assert len(due_schedules) == 1
    assert due_schedules[0].id == s_pt.id

    due_pts, due_concepts = service.get_due_target_ids(student_profile.id, subject.id, as_of=now)
    assert pt.id in due_pts
    assert concept.id not in due_concepts


def test_mastery_engine_creates_review_schedule_on_mastered(db_session: Session) -> None:
    subject, pt, concept, teacher, student = _setup_review_environment(db_session, "MEG")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))

    # Pre-seed high mastery on problem type right below threshold
    db_session.add(
        StudentProblemTypeMastery(
            student_id=student_profile.id,
            problem_type_id=pt.id,
            mastery_score=0.79,
            confidence=0.70,
            attempt_count=5,
            correct_count=4,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    # Practice session and attempt with correct answer
    practice_session = PracticeSession(
        student_id=student_profile.id,
        subject_id=subject.id,
        session_type=PracticeSessionType.PRACTICE,
    )
    db_session.add(practice_session)
    db_session.flush()

    q = Question(
        subject_id=subject.id,
        content="Test Question",
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=0.7,
        correct_answer="A",
        source_type="TEST",
        source_reference="test",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        created_by=teacher.id,
        problem_type_links=[QuestionProblemType(problem_type_id=pt.id, weight=1.0, is_primary=True)],
        concept_links=[QuestionConcept(concept_id=concept.id, weight=1.0)],
    )
    db_session.add(q)
    db_session.flush()

    attempt = QuestionAttempt(
        practice_session_id=practice_session.id,
        student_id=student_profile.id,
        question_id=q.id,
        student_answer="A",
        is_correct=True,
        score=1.0,
        attempt_number=1,
        evaluation_status=EvaluationStatus.AUTO_EVALUATED,
    )
    db_session.add(attempt)
    db_session.flush()

    evidence = AttemptEvaluatedEvidence(
        attempt_id=attempt.id,
        practice_session_id=practice_session.id,
        student_id=student_profile.id,
        question_id=q.id,
        subject_id=subject.id,
        is_correct=True,
        score=1.0,
        problem_type_ids=(pt.id,),
        concept_ids=(concept.id,),
        learning_outcome_ids=(),
        occurred_at=datetime.now(timezone.utc),
    )

    # Publish evidence via Mastery Engine
    publisher = MasteryAttemptEvidencePublisher()
    publisher.publish(evidence, db_session)
    db_session.commit()

    # Check that mastery reached MASTERED (>= 0.8)
    pt_mastery = db_session.scalar(
        select(StudentProblemTypeMastery).where(
            StudentProblemTypeMastery.student_id == student_profile.id,
            StudentProblemTypeMastery.problem_type_id == pt.id,
        )
    )
    assert pt_mastery is not None
    assert pt_mastery.mastery_score >= 0.8

    # Check that ReviewSchedule was automatically created
    sched = db_session.scalar(
        select(ReviewSchedule).where(
            ReviewSchedule.student_id == student_profile.id,
            ReviewSchedule.problem_type_id == pt.id,
        )
    )
    assert sched is not None
    assert sched.review_interval_days == 1.0
    assert sched.review_count == 0
