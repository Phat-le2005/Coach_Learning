from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.concepts.models import Concept, ConceptRelation, RelationType
from app.curriculum.models import ProblemType, ProblemTypeConcept
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
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
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.recommendations.priority_service import LearningPriorityService
from app.recommendations.question_service import QuestionRecommendationService
from app.recommendations.schemas import (
    ActiveTeachingPlanContext,
    PriorityReasonCode,
    PriorityTargetType,
)
from app.students.models import StudentProfile
from tests.practice.conftest import PracticeContent


def _set_problem_type_mastery(
    session: Session,
    student_id: UUID,
    problem_type_id: UUID,
    *,
    mastery: float,
    confidence: float = 0.8,
    practiced_at: datetime | None = None,
) -> None:
    session.add(
        StudentProblemTypeMastery(
            student_id=student_id,
            problem_type_id=problem_type_id,
            mastery_score=mastery,
            confidence=confidence,
            attempt_count=10,
            correct_count=round(mastery * 10),
            last_practiced_at=practiced_at or datetime.now(timezone.utc),
        )
    )
    session.flush()


def _set_concept_mastery(
    session: Session,
    student_id: UUID,
    concept_id: UUID,
    *,
    mastery: float,
    confidence: float = 0.8,
) -> None:
    session.add(
        StudentConceptMastery(
            student_id=student_id,
            concept_id=concept_id,
            mastery_score=mastery,
            confidence=confidence,
            attempt_count=10,
            correct_count=round(mastery * 10),
            last_practiced_at=datetime.now(timezone.utc),
        )
    )
    session.flush()


def _add_question(
    session: Session,
    content: PracticeContent,
    *,
    text: str,
    difficulty: float,
    problem_type_id: UUID | None = None,
    concept_id: UUID | None = None,
    status: QuestionStatus = QuestionStatus.APPROVED,
    cognitive_level: CognitiveLevel | None = None,
) -> Question:
    question = Question(
        subject_id=content.subject.id,
        content=text,
        question_type=QuestionType.TRUE_FALSE,
        difficulty=difficulty,
        correct_answer="TRUE",
        explanation="Recommendation test question.",
        source_type="TEST",
        source_reference="recommendation-suite",
        cognitive_level=cognitive_level,
        exam_weight=0.5,
        status=status,
        created_by=content.mcq.created_by,
        problem_type_links=[
            QuestionProblemType(
                problem_type_id=problem_type_id or content.problem_type.id,
                weight=1.0,
                is_primary=True,
            )
        ],
        concept_links=[
            QuestionConcept(concept_id=concept_id or content.concept.id, weight=1.0)
        ],
        learning_outcome_links=[
            QuestionLearningOutcome(
                learning_outcome_id=content.learning_outcome.id,
                weight=1.0,
            )
        ],
    )
    session.add(question)
    session.flush()
    return question


def _add_problem_type(session: Session, content: PracticeContent, code: str) -> ProblemType:
    item = ProblemType(
        topic_id=content.problem_type.topic_id,
        code=code,
        name=code.replace("_", " ").title(),
        description=f"Test ProblemType {code}.",
        order_index=20,
        is_active=True,
    )
    session.add(item)
    session.flush()
    return item


def _record_recent_attempt(
    session: Session,
    student_id: UUID,
    content: PracticeContent,
    question_id: UUID,
    *,
    session_type: PracticeSessionType = PracticeSessionType.PRACTICE,
    is_correct: bool = True,
) -> None:
    practice_session = PracticeSession(
        student_id=student_id,
        subject_id=content.subject.id,
        session_type=session_type,
        status=PracticeSessionStatus.ACTIVE,
    )
    session.add(practice_session)
    session.flush()
    session.add(
        QuestionAttempt(
            practice_session_id=practice_session.id,
            student_id=student_id,
            question_id=question_id,
            student_answer="TRUE",
            is_correct=is_correct,
            score=1.0 if is_correct else 0.0,
            response_time_seconds=30.0,
            hint_count=0,
            attempt_number=1,
            evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        )
    )
    session.flush()


def test_strong_student_gets_progressively_harder_question(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _set_problem_type_mastery(
        db_session,
        student_profile.id,
        practice_content.problem_type.id,
        mastery=0.9,
    )
    hard = _add_question(
        db_session,
        practice_content,
        text="Hard deterministic recommendation.",
        difficulty=0.85,
        cognitive_level=CognitiveLevel.ANALYZE,
    )

    recommendation = QuestionRecommendationService(db_session).recommend(
        student_profile.id,
        practice_content.subject.id,
        target_problem_type_id=practice_content.problem_type.id,
    )

    assert recommendation is not None
    assert recommendation.question_id == hard.id
    assert recommendation.reason_code == PriorityReasonCode.DIFFICULTY_PROGRESSION


def test_weak_student_gets_easier_question(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _set_problem_type_mastery(
        db_session,
        student_profile.id,
        practice_content.problem_type.id,
        mastery=0.2,
    )
    easy = _add_question(
        db_session,
        practice_content,
        text="Easy deterministic recommendation.",
        difficulty=0.25,
        cognitive_level=CognitiveLevel.UNDERSTAND,
    )

    recommendation = QuestionRecommendationService(db_session).recommend(
        student_profile.id,
        practice_content.subject.id,
        target_problem_type_id=practice_content.problem_type.id,
    )

    assert recommendation is not None
    assert recommendation.question_id == easy.id
    assert recommendation.reason_code == PriorityReasonCode.WEAK_PROBLEM_TYPE


def test_specific_gap_problem_type_ranks_before_strong_problem_type(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    gap = _add_problem_type(db_session, practice_content, "SPECIFIC_GAP_PT")
    _set_problem_type_mastery(
        db_session,
        student_profile.id,
        practice_content.problem_type.id,
        mastery=0.9,
    )
    _set_problem_type_mastery(
        db_session,
        student_profile.id,
        gap.id,
        mastery=0.15,
    )

    priorities = LearningPriorityService(db_session).get_priorities(
        student_profile.id, practice_content.subject.id
    )

    assert priorities[0].target_type == PriorityTargetType.PROBLEM_TYPE
    assert priorities[0].problem_type_id == gap.id
    assert priorities[0].reason_code == PriorityReasonCode.WEAK_PROBLEM_TYPE


def test_prerequisite_gap_is_ranked_as_repair(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    prerequisite = Concept(
        subject_id=practice_content.subject.id,
        code="INEQUALITY_SOLVING_RECOMMENDATION",
        name="Inequality solving",
        description="Prerequisite concept for deterministic recommendation.",
        grade_level=12,
        order_index=50,
    )
    db_session.add(prerequisite)
    db_session.flush()
    db_session.add_all(
        [
            ProblemTypeConcept(
                problem_type_id=practice_content.problem_type.id,
                concept_id=practice_content.concept.id,
                weight=1.0,
                is_primary=True,
            ),
            ConceptRelation(
                source_concept_id=prerequisite.id,
                target_concept_id=practice_content.concept.id,
                relation_type=RelationType.PREREQUISITE,
            ),
        ]
    )
    _set_concept_mastery(
        db_session,
        student_profile.id,
        prerequisite.id,
        mastery=0.2,
    )

    # When the problem_type is part of the active teaching plan, its prerequisite triggers repair
    plan = ActiveTeachingPlanContext(problem_type_ids=(practice_content.problem_type.id,))
    priorities = LearningPriorityService(db_session).get_priorities(
        student_profile.id, practice_content.subject.id, active_teaching_plan=plan
    )

    assert priorities[0].target_type == PriorityTargetType.CONCEPT
    assert priorities[0].concept_id == prerequisite.id
    assert priorities[0].reason_code == PriorityReasonCode.PREREQUISITE_REPAIR


def test_unrelated_weak_prerequisite_does_not_trigger_prerequisite_repair(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    # ProblemType H is the current active lesson
    active_pt = practice_content.problem_type

    # An unrelated problem type B with concept B and prerequisite A
    unrelated_pt = _add_problem_type(db_session, practice_content, "UNRELATED_PT_B")
    unrelated_concept_b = Concept(
        subject_id=practice_content.subject.id,
        code="UNRELATED_CONCEPT_B",
        name="Unrelated Concept B",
        description="Concept for unrelated problem type.",
        grade_level=12,
        order_index=80,
    )
    unrelated_prereq_a = Concept(
        subject_id=practice_content.subject.id,
        code="UNRELATED_PREREQ_A",
        name="Unrelated Prereq A",
        description="Prerequisite for unrelated concept B.",
        grade_level=12,
        order_index=81,
    )
    db_session.add_all([unrelated_concept_b, unrelated_prereq_a])
    db_session.flush()

    db_session.add_all([
        ProblemTypeConcept(
            problem_type_id=unrelated_pt.id,
            concept_id=unrelated_concept_b.id,
            weight=1.0,
            is_primary=True,
        ),
        ConceptRelation(
            source_concept_id=unrelated_prereq_a.id,
            target_concept_id=unrelated_concept_b.id,
            relation_type=RelationType.PREREQUISITE,
        ),
    ])
    # Prerequisite A is WEAK
    _set_concept_mastery(
        db_session,
        student_profile.id,
        unrelated_prereq_a.id,
        mastery=0.1,
    )

    plan = ActiveTeachingPlanContext(problem_type_ids=(active_pt.id,))
    priorities = LearningPriorityService(db_session).get_priorities(
        student_profile.id, practice_content.subject.id, active_teaching_plan=plan
    )

    # Top priority must be CURRENT_LESSON (active_pt), NOT unrelated prerequisite repair
    assert priorities[0].target_type == PriorityTargetType.PROBLEM_TYPE
    assert priorities[0].problem_type_id == active_pt.id
    assert priorities[0].reason_code == PriorityReasonCode.CURRENT_LESSON

    # Prerequisite A must NOT have PREREQUISITE_REPAIR
    for item in priorities:
        if item.concept_id == unrelated_prereq_a.id:
            assert item.reason_code != PriorityReasonCode.PREREQUISITE_REPAIR


def test_review_due_is_derived_from_stale_mastery(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _set_problem_type_mastery(
        db_session,
        student_profile.id,
        practice_content.problem_type.id,
        mastery=0.9,
        practiced_at=datetime.now(timezone.utc) - timedelta(days=15),
    )

    priorities = LearningPriorityService(db_session).get_priorities(
        student_profile.id, practice_content.subject.id
    )

    target = next(
        item for item in priorities if item.problem_type_id == practice_content.problem_type.id
    )
    assert target.reason_code == PriorityReasonCode.REVIEW_DUE


def test_active_lesson_has_explicit_deterministic_reason(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _set_problem_type_mastery(
        db_session,
        student_profile.id,
        practice_content.problem_type.id,
        mastery=0.2,
    )

    priorities = LearningPriorityService(db_session).get_priorities(
        student_profile.id,
        practice_content.subject.id,
        active_teaching_plan=ActiveTeachingPlanContext(
            problem_type_ids=(practice_content.problem_type.id,)
        ),
    )

    target = next(
        item for item in priorities if item.problem_type_id == practice_content.problem_type.id
    )
    assert target.reason_code == PriorityReasonCode.CURRENT_LESSON


def test_recent_question_is_excluded(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    problem_type = _add_problem_type(db_session, practice_content, "REPEAT_EXCLUSION_PT")
    recent = _add_question(
        db_session,
        practice_content,
        text="Recently exposed question.",
        difficulty=0.3,
        problem_type_id=problem_type.id,
    )
    fresh = _add_question(
        db_session,
        practice_content,
        text="Fresh question.",
        difficulty=0.35,
        problem_type_id=problem_type.id,
    )
    _record_recent_attempt(db_session, student_profile.id, practice_content, recent.id)

    recommendation = QuestionRecommendationService(db_session).recommend(
        student_profile.id,
        practice_content.subject.id,
        target_problem_type_id=problem_type.id,
        desired_difficulty=0.3,
    )

    assert recommendation is not None
    assert recommendation.question_id == fresh.id


def test_no_approved_question_has_no_draft_fallback(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    problem_type = _add_problem_type(db_session, practice_content, "DRAFT_ONLY_PT")
    _add_question(
        db_session,
        practice_content,
        text="Draft-only target question.",
        difficulty=0.3,
        problem_type_id=problem_type.id,
        status=QuestionStatus.DRAFT,
    )

    recommendation = QuestionRecommendationService(db_session).recommend(
        student_profile.id,
        practice_content.subject.id,
        target_problem_type_id=problem_type.id,
    )

    assert recommendation is None


def test_incorrect_diagnostic_attempt_creates_followup_reason(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _record_recent_attempt(
        db_session,
        student_profile.id,
        practice_content,
        practice_content.mcq.id,
        session_type=PracticeSessionType.DIAGNOSTIC,
        is_correct=False,
    )

    priorities = LearningPriorityService(db_session).get_priorities(
        student_profile.id, practice_content.subject.id
    )

    target = next(
        item for item in priorities if item.problem_type_id == practice_content.problem_type.id
    )
    assert target.reason_code == PriorityReasonCode.DIAGNOSTIC_FOLLOWUP


def test_recommendation_is_deterministic_for_unchanged_state(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    service = QuestionRecommendationService(db_session)

    first = service.recommend(student_profile.id, practice_content.subject.id)
    second = service.recommend(student_profile.id, practice_content.subject.id)

    assert first is not None
    assert first == second


def test_teaching_plan_with_deactivated_problem_type_does_not_fail_subject_validation(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    from datetime import date
    from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment
    from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus

    # Create an inactive problem type in the same subject
    inactive_pt = _add_problem_type(db_session, practice_content, "INACTIVE_PT")
    inactive_pt.is_active = False

    classroom = Classroom(
        name="Test Room",
        academic_year="2026-2027",
        grade_level=12,
        created_by=student_profile.user_id,
    )
    db_session.add(classroom)
    db_session.flush()

    enrollment = StudentEnrollment(
        classroom_id=classroom.id,
        student_id=student_profile.id,
        status=EnrollmentStatus.ACTIVE,
    )
    db_session.add(enrollment)

    plan = TeachingPlan(
        classroom_id=classroom.id,
        subject_id=practice_content.subject.id,
        start_date=date.today(),
        status=TeachingPlanStatus.ACTIVE,
        created_by=student_profile.user_id,
    )
    db_session.add(plan)
    db_session.flush()

    # Add both active and inactive problem types to the teaching plan
    item1 = TeachingPlanItem(
        teaching_plan_id=plan.id,
        problem_type_id=practice_content.problem_type.id,
        priority=1,
        order_index=1,
    )
    item2 = TeachingPlanItem(
        teaching_plan_id=plan.id,
        problem_type_id=inactive_pt.id,
        priority=2,
        order_index=2,
    )
    db_session.add_all([item1, item2])
    db_session.flush()

    # Priorities resolution should succeed and ignore the inactive problem type
    service = LearningPriorityService(db_session)
    resolved_plan = service._resolve_active_teaching_plan(
        student_profile.id, practice_content.subject.id
    )
    assert resolved_plan is not None
    assert practice_content.problem_type.id in resolved_plan.problem_type_ids
    assert inactive_pt.id not in resolved_plan.problem_type_ids

    priorities = service.get_priorities(student_profile.id, practice_content.subject.id)
    assert priorities is not None
    assert all(p.problem_type_id != inactive_pt.id for p in priorities if p.problem_type_id)

