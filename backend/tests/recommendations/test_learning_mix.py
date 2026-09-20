from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, ProblemTypeConcept, Topic
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
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
from app.recommendations.mix import (
    LearningMixCategory,
    LearningMixConfig,
    categorize_priority_reason,
)
from app.recommendations.priority_service import LearningPriorityService
from app.recommendations.question_service import QuestionRecommendationService
from app.recommendations.schemas import (
    ActiveTeachingPlanContext,
    PriorityReasonCode,
    PriorityTargetType,
)
from app.review.service import ReviewScheduleService
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TEST_PASSWORD = "LearningMix-Secret-2026!"


def _create_user(session: Session, role: Role, email: str) -> User:
    return UserService(session).create_user(
        UserCreate(email=email, password=TEST_PASSWORD, full_name=f"{role.value} User", role=role)
    )


def test_learning_mix_quota_allocation_default_70_20_10() -> None:
    config = LearningMixConfig()
    assert config.current_weight == 0.70
    assert config.weakness_weight == 0.20
    assert config.review_weight == 0.10

    # Total 10 -> 7 current, 2 weakness, 1 review
    quotas_10 = config.allocate_quotas(10)
    assert quotas_10[LearningMixCategory.CURRENT_LEARNING] == 7
    assert quotas_10[LearningMixCategory.WEAKNESS_REPAIR] == 2
    assert quotas_10[LearningMixCategory.REVIEW_DUE] == 1
    assert sum(quotas_10.values()) == 10

    # Total 20 -> 14 current, 4 weakness, 2 review
    quotas_20 = config.allocate_quotas(20)
    assert quotas_20[LearningMixCategory.CURRENT_LEARNING] == 14
    assert quotas_20[LearningMixCategory.WEAKNESS_REPAIR] == 4
    assert quotas_20[LearningMixCategory.REVIEW_DUE] == 2
    assert sum(quotas_20.values()) == 20


def test_learning_mix_custom_config() -> None:
    # Custom config: 50% current, 30% weakness, 20% review
    config = LearningMixConfig(current_weight=0.50, weakness_weight=0.30, review_weight=0.20)
    quotas = config.allocate_quotas(10)
    assert quotas[LearningMixCategory.CURRENT_LEARNING] == 5
    assert quotas[LearningMixCategory.WEAKNESS_REPAIR] == 3
    assert quotas[LearningMixCategory.REVIEW_DUE] == 2
    assert sum(quotas.values()) == 10


def test_learning_mix_validation() -> None:
    # Cannot have negative weight
    with pytest.raises(Exception):
        LearningMixConfig(current_weight=-0.1, weakness_weight=0.5, review_weight=0.5)

    # Cannot have all zero weights
    with pytest.raises(ValueError):
        LearningMixConfig(current_weight=0.0, weakness_weight=0.0, review_weight=0.0)


def test_categorize_priority_reason() -> None:
    assert (
        categorize_priority_reason(PriorityReasonCode.CURRENT_LESSON)
        == LearningMixCategory.CURRENT_LEARNING
    )
    assert (
        categorize_priority_reason(PriorityReasonCode.PREREQUISITE_REPAIR)
        == LearningMixCategory.WEAKNESS_REPAIR
    )
    assert (
        categorize_priority_reason(PriorityReasonCode.WEAK_PROBLEM_TYPE)
        == LearningMixCategory.WEAKNESS_REPAIR
    )
    assert (
        categorize_priority_reason(PriorityReasonCode.WEAK_CONCEPT)
        == LearningMixCategory.WEAKNESS_REPAIR
    )
    assert (
        categorize_priority_reason(PriorityReasonCode.DIAGNOSTIC_FOLLOWUP)
        == LearningMixCategory.WEAKNESS_REPAIR
    )
    assert (
        categorize_priority_reason(PriorityReasonCode.REVIEW_DUE)
        == LearningMixCategory.REVIEW_DUE
    )
    assert (
        categorize_priority_reason(PriorityReasonCode.DIFFICULTY_PROGRESSION)
        == LearningMixCategory.OTHER
    )


def test_mixed_priorities_selection_and_backfill(db_session: Session) -> None:
    teacher = _create_user(db_session, Role.TEACHER, "mix.teacher@example.com")
    student = _create_user(db_session, Role.STUDENT, "mix.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))

    subject = Subject(code="MIX-SUB", name="Mix Subject", grade_level=12)
    db_session.add(subject)
    db_session.flush()

    chapter = Chapter(subject_id=subject.id, code="MIX-CHP", name="Chapter", order_index=0)
    db_session.add(chapter)
    db_session.flush()

    topic = Topic(chapter_id=chapter.id, code="MIX-TOP", name="Topic", order_index=0)
    db_session.add(topic)
    db_session.flush()

    # Create 3 ProblemTypes: PT1 (active/current), PT2 (weak), PT3 (review due)
    pt1 = ProblemType(topic_id=topic.id, code="MIX-PT1", name="PT1", order_index=0, is_active=True)
    pt2 = ProblemType(topic_id=topic.id, code="MIX-PT2", name="PT2", order_index=1, is_active=True)
    pt3 = ProblemType(topic_id=topic.id, code="MIX-PT3", name="PT3", order_index=2, is_active=True)
    concept = Concept(subject_id=subject.id, code="MIX-CON", name="Concept", order_index=0)
    db_session.add_all([pt1, pt2, pt3, concept])
    db_session.flush()

    db_session.add(ProblemTypeConcept(problem_type_id=pt1.id, concept_id=concept.id, weight=1.0, is_primary=True))
    db_session.add(ProblemTypeConcept(problem_type_id=pt2.id, concept_id=concept.id, weight=1.0, is_primary=True))
    db_session.add(ProblemTypeConcept(problem_type_id=pt3.id, concept_id=concept.id, weight=1.0, is_primary=True))

    # PT2 has WEAK mastery
    db_session.add(
        StudentProblemTypeMastery(
            student_id=student_profile.id,
            problem_type_id=pt2.id,
            mastery_score=0.25,
            confidence=0.8,
            attempt_count=5,
            correct_count=1,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )

    # PT3 has DUE review schedule
    review_service = ReviewScheduleService(db_session)
    review_service.ensure_problem_type_schedule(
        student_profile.id,
        pt3.id,
        as_of=datetime.now(timezone.utc) - timedelta(days=2),
        initial_interval_days=1.0,
    )

    db_session.commit()

    # Active teaching plan includes PT1 (Current Lesson)
    active_plan = ActiveTeachingPlanContext(
        problem_type_ids=(pt1.id,),
        priority_by_problem_type={pt1.id: 2},
    )

    priority_service = LearningPriorityService(db_session)

    # Request mixed priorities with total 3
    mixed = priority_service.get_mixed_priorities(
        student_profile.id,
        subject.id,
        total_count=3,
        mix_config=LearningMixConfig(current_weight=0.5, weakness_weight=0.25, review_weight=0.25),
        active_teaching_plan=active_plan,
    )

    assert len(mixed) == 3
    reasons = {m.reason_code for m in mixed}
    assert PriorityReasonCode.CURRENT_LESSON in reasons
    assert PriorityReasonCode.WEAK_PROBLEM_TYPE in reasons
    assert PriorityReasonCode.REVIEW_DUE in reasons


def test_recommend_mixed_batch(db_session: Session) -> None:
    teacher = _create_user(db_session, Role.TEACHER, "mix.rec.teacher@example.com")
    student = _create_user(db_session, Role.STUDENT, "mix.rec.student@example.com")
    student_profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student.id))

    subject = Subject(code="MIX-REC-SUB", name="Mix Rec Subject", grade_level=12)
    db_session.add(subject)
    db_session.flush()

    chapter = Chapter(subject_id=subject.id, code="MIX-REC-CHP", name="Chapter", order_index=0)
    db_session.add(chapter)
    db_session.flush()

    topic = Topic(chapter_id=chapter.id, code="MIX-REC-TOP", name="Topic", order_index=0)
    db_session.add(topic)
    db_session.flush()

    pt1 = ProblemType(topic_id=topic.id, code="MIX-REC-PT1", name="PT1", order_index=0, is_active=True)
    pt2 = ProblemType(topic_id=topic.id, code="MIX-REC-PT2", name="PT2", order_index=1, is_active=True)
    pt3 = ProblemType(topic_id=topic.id, code="MIX-REC-PT3", name="PT3", order_index=2, is_active=True)
    concept = Concept(subject_id=subject.id, code="MIX-REC-CON", name="Concept", order_index=0)
    db_session.add_all([pt1, pt2, pt3, concept])
    db_session.flush()

    lo = LearningOutcome(subject_id=subject.id, code="MIX-REC-LO", description="LO Desc", grade_level=12)
    db_session.add(lo)
    db_session.flush()

    db_session.add(ProblemTypeConcept(problem_type_id=pt1.id, concept_id=concept.id, weight=1.0, is_primary=True))
    db_session.add(ProblemTypeConcept(problem_type_id=pt2.id, concept_id=concept.id, weight=1.0, is_primary=True))
    db_session.add(ProblemTypeConcept(problem_type_id=pt3.id, concept_id=concept.id, weight=1.0, is_primary=True))

    # Add questions for each problem type
    for idx, pt in enumerate([pt1, pt2, pt3], start=1):
        q = Question(
            subject_id=subject.id,
            content=f"Question for {pt.code}",
            question_type=QuestionType.TRUE_FALSE,
            difficulty=0.5,
            correct_answer="TRUE",
            explanation="Explanation",
            source_type="TEST",
            source_reference="mix-test",
            status=QuestionStatus.APPROVED,
            exam_weight=1.0,
            created_by=teacher.id,
            problem_type_links=[QuestionProblemType(problem_type_id=pt.id, weight=1.0, is_primary=True)],
            concept_links=[QuestionConcept(concept_id=concept.id, weight=1.0)],
            learning_outcome_links=[QuestionLearningOutcome(learning_outcome_id=lo.id, weight=1.0)],
        )
        db_session.add(q)

    # PT2 weak
    db_session.add(
        StudentProblemTypeMastery(
            student_id=student_profile.id,
            problem_type_id=pt2.id,
            mastery_score=0.2,
            confidence=0.8,
            attempt_count=5,
            correct_count=1,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )

    # PT3 review due
    review_service = ReviewScheduleService(db_session)
    review_service.ensure_problem_type_schedule(
        student_profile.id,
        pt3.id,
        as_of=datetime.now(timezone.utc) - timedelta(days=2),
        initial_interval_days=1.0,
    )
    db_session.commit()

    active_plan = ActiveTeachingPlanContext(
        problem_type_ids=(pt1.id,),
        priority_by_problem_type={pt1.id: 1},
    )

    rec_service = QuestionRecommendationService(db_session)
    batch = rec_service.recommend_mixed_batch(
        student_profile.id,
        subject.id,
        count=3,
        mix_config=LearningMixConfig(current_weight=0.5, weakness_weight=0.25, review_weight=0.25),
        active_teaching_plan=active_plan,
    )

    assert len(batch) == 3
    q_ids = {r.question_id for r in batch}
    assert len(q_ids) == 3  # All distinct questions
    reasons = {r.reason_code for r in batch}
    assert PriorityReasonCode.CURRENT_LESSON in reasons
    assert PriorityReasonCode.WEAK_PROBLEM_TYPE in reasons
    assert PriorityReasonCode.REVIEW_DUE in reasons

