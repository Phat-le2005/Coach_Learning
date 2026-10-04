"""Tests for QuestionBankSufficiencyService evaluating production and fresh supply."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.misconceptions.models import MisconceptionCategory, MisconceptionDefinition
from app.practice.models import QuestionAttempt
from app.question_supply.models import (
    QuestionSupplyHealth,
    QuestionSupplyReasonCode,
    QuestionSupplySeverity,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.question_supply.service import (
    QuestionBankSufficiencyService,
    QuestionSupplyRequirement,
)
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionConcept,
    QuestionGroup,
    QuestionGroupItem,
    QuestionGroupType,
    QuestionLearningOutcome,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from tests.practice.conftest import (
    PracticeContent,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)


def _make_question(
    session: Session,
    content: PracticeContent,
    *,
    index: int = 1,
    difficulty: float = 0.5,
    status: QuestionStatus = QuestionStatus.APPROVED,
    question_type: QuestionType = QuestionType.MULTIPLE_CHOICE,
    concept_id: UUID | None = None,
    problem_type_id: UUID | None = None,
    correct_answer: str | None = "A",
    has_concept: bool = True,
    has_problem_type: bool = True,
    has_lo: bool = True,
    group_id: UUID | None = None,
    subject_id: UUID | None = None,
) -> Question:
    q = Question(
        subject_id=subject_id or content.subject.id,
        content=f"Question {index} {uuid4()}",
        question_type=question_type,
        difficulty=difficulty,
        correct_answer=correct_answer,
        explanation=f"Exp {index}",
        source_type="TEST",
        exam_weight=0.5,
        status=status,
        cognitive_level=CognitiveLevel.APPLY,
        created_by=content.mcq.created_by,
        options=(
            [
                QuestionOption(label="A", content="Opt A", order_index=0),
                QuestionOption(label="B", content="Opt B", order_index=1),
            ]
            if question_type == QuestionType.MULTIPLE_CHOICE
            else []
        ),
        concept_links=(
            [QuestionConcept(concept_id=concept_id or content.concept.id, weight=1.0)]
            if has_concept
            else []
        ),
        problem_type_links=(
            [QuestionProblemType(problem_type_id=problem_type_id or content.problem_type.id, weight=1.0)]
            if has_problem_type
            else []
        ),
        learning_outcome_links=(
            [QuestionLearningOutcome(learning_outcome_id=content.learning_outcome.id, weight=1.0)]
            if has_lo
            else []
        ),
    )
    session.add(q)
    session.flush()

    if group_id is not None:
        item = QuestionGroupItem(
            group_id=group_id,
            question_id=q.id,
            label="a",
            order_index=0,
        )
        session.add(item)
        session.flush()

    return q


def _archive_questions(session: Session) -> None:
    for q in session.scalars(select(Question)).all():
        q.status = QuestionStatus.ARCHIVED
    session.flush()


def test_approved_exact_target_questions_counted(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    # Create 3 approved questions for content.concept
    for i in range(3):
        _make_question(db_session, practice_content, index=i, difficulty=0.45)

    svc = QuestionBankSufficiencyService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.45,
    )
    report = svc.assess(req)
    assert report.approved_eligible_count == 3
    assert report.approved_in_band_count == 3
    assert report.health == QuestionSupplyHealth.INSUFFICIENT  # Repair min is 4


def test_draft_and_review_do_not_satisfy_production_supply(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    _make_question(db_session, practice_content, status=QuestionStatus.DRAFT)
    _make_question(db_session, practice_content, status=QuestionStatus.REVIEW)

    svc = QuestionBankSufficiencyService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    report = svc.assess(req)
    assert report.approved_eligible_count == 0
    assert report.pipeline_candidate_count == 2
    assert report.health == QuestionSupplyHealth.INSUFFICIENT
    assert report.reason_code == QuestionSupplyReasonCode.NO_APPROVED_TARGET_QUESTIONS


def test_archived_and_group_child_excluded(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    # Archived question
    _make_question(db_session, practice_content, status=QuestionStatus.ARCHIVED)

    from app.questions.models import QuestionGroupScoringPolicy
    grp = QuestionGroup(
        subject_id=practice_content.subject.id,
        content="Group stem",
        difficulty=0.5,
        source_type="TEST",
        exam_weight=0.5,
        created_by=practice_content.mcq.created_by,
        group_type=QuestionGroupType.TRUE_FALSE_FOUR,
        scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
    )
    db_session.add(grp)
    db_session.flush()
    _make_question(db_session, practice_content, group_id=grp.id)

    svc = QuestionBankSufficiencyService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    report = svc.assess(req)
    assert report.approved_eligible_count == 0


def test_missing_taxonomy_excluded(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    # Missing concept link
    _make_question(db_session, practice_content, has_concept=False)
    # Missing problem type link
    _make_question(db_session, practice_content, has_problem_type=False)
    # Missing LO link
    _make_question(db_session, practice_content, has_lo=False)

    svc = QuestionBankSufficiencyService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    report = svc.assess(req)
    assert report.approved_eligible_count == 0


def test_wrong_target_excluded(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    other_concept = Concept(
        subject_id=practice_content.subject.id,
        code="OTHER_CONCEPT_01",
        name="Other Concept",
    )
    db_session.add(other_concept)
    db_session.flush()

    _make_question(db_session, practice_content, concept_id=other_concept.id)

    svc = QuestionBankSufficiencyService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    report = svc.assess(req)
    assert report.approved_eligible_count == 0


def test_open_response_excluded_from_verification_and_repair(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    _make_question(
        db_session,
        practice_content,
        question_type=QuestionType.OPEN_RESPONSE,
        correct_answer="essay",
    )

    svc = QuestionBankSufficiencyService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    report = svc.assess(req)
    assert report.approved_eligible_count == 0


def test_invalid_mcq_and_tf_excluded_from_auto_evaluable(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    # MCQ correct_answer "Z" does not match option labels ("A", "B")
    _make_question(
        db_session,
        practice_content,
        question_type=QuestionType.MULTIPLE_CHOICE,
        correct_answer="Z",
    )
    # TRUE_FALSE correct_answer "MAYBE" not in {"true", "false"}
    _make_question(
        db_session,
        practice_content,
        question_type=QuestionType.TRUE_FALSE,
        correct_answer="MAYBE",
    )
    # Valid SHORT_ANSWER
    _make_question(
        db_session,
        practice_content,
        question_type=QuestionType.SHORT_ANSWER,
        correct_answer="42",
    )

    svc = QuestionBankSufficiencyService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    report = svc.assess(req)
    assert report.approved_eligible_count == 1  # Only the short answer is valid


def test_difficulty_in_band_count_correct(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    # desired = 0.50, tolerance = 0.15 => band [0.35, 0.65]
    _make_question(db_session, practice_content, difficulty=0.40)  # In band
    _make_question(db_session, practice_content, difficulty=0.60)  # In band
    _make_question(db_session, practice_content, difficulty=0.10)  # Out of band
    _make_question(db_session, practice_content, difficulty=0.90)  # Out of band

    svc = QuestionBankSufficiencyService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
    )
    report = svc.assess(req)
    assert report.approved_eligible_count == 4
    assert report.approved_in_band_count == 2
    assert report.difficulty_min == 0.35
    assert report.difficulty_max == 0.65


def test_health_evaluation_levels(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionBankSufficiencyService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )

    # 0 questions -> INSUFFICIENT / CRITICAL
    report = svc.assess(req)
    assert report.health == QuestionSupplyHealth.INSUFFICIENT
    assert report.severity == QuestionSupplySeverity.CRITICAL

    # 1 question -> INSUFFICIENT / HIGH (min = 2)
    _make_question(db_session, practice_content, index=1)
    report = svc.assess(req)
    assert report.health == QuestionSupplyHealth.INSUFFICIENT
    assert report.severity == QuestionSupplySeverity.HIGH

    # 2 questions -> THIN / MEDIUM (min = 2, preferred = 3)
    _make_question(db_session, practice_content, index=2)
    report = svc.assess(req)
    assert report.health == QuestionSupplyHealth.THIN
    assert report.severity == QuestionSupplySeverity.MEDIUM

    # 3 questions -> SUFFICIENT / LOW (preferred = 3 met)
    _make_question(db_session, practice_content, index=3)
    report = svc.assess(req)
    assert report.health == QuestionSupplyHealth.SUFFICIENT
    assert report.severity == QuestionSupplySeverity.LOW


def test_fresh_vs_global_exposure_exhaustion(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    _archive_questions(db_session)
    # Create 5 approved questions
    created = [
        _make_question(db_session, practice_content, index=i) for i in range(5)
    ]

    from app.practice.models import PracticeSession, PracticeSessionType, PracticeSessionStatus, EvaluationStatus
    ps = PracticeSession(
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(ps)
    db_session.flush()

    # Student 1 has attempted all 5 questions
    for idx, q in enumerate(created, start=1):
        attempt = QuestionAttempt(
            practice_session_id=ps.id,
            student_id=student_profile.id,
            question_id=q.id,
            student_answer="A",
            attempt_number=idx,
            is_correct=True,
            score=1.0,
            evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        )
        db_session.add(attempt)
    db_session.flush()

    svc = QuestionBankSufficiencyService(db_session)
    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )

    # Assessed for student 1 -> global = 5, fresh = 0 -> STUDENT_EXPOSURE_EXHAUSTED
    report_s1 = svc.assess(req, student_id=student_profile.id)
    assert report_s1.approved_eligible_count == 5
    assert report_s1.fresh_eligible_count == 0
    assert report_s1.excluded_exposure_count == 5
    assert report_s1.reason_code == QuestionSupplyReasonCode.STUDENT_EXPOSURE_EXHAUSTED
    assert report_s1.health == QuestionSupplyHealth.INSUFFICIENT

    # Assessed without student context -> global = 5, fresh = None -> SUFFICIENT (for min 4)
    report_global = svc.assess(req)
    assert report_global.approved_eligible_count == 5
    assert report_global.fresh_eligible_count is None
    assert report_global.health == QuestionSupplyHealth.THIN  # min 4, pref 8

    # Another student with 0 exposures sees fresh = 5
    from app.users.models import User, Role
    u = User(
        email=f"s_{uuid4().hex[:8]}@example.com",
        password_hash="hash",
        full_name="Other Student",
        role=Role.STUDENT,
    )
    db_session.add(u)
    db_session.flush()
    other_student = StudentProfile(
        user_id=u.id,
        grade_level=12,
    )
    db_session.add(other_student)
    db_session.flush()

    report_s2 = svc.assess(req, student_id=other_student.id)
    assert report_s2.approved_eligible_count == 5
    assert report_s2.fresh_eligible_count == 5
    assert report_s2.excluded_exposure_count == 0


def test_subject_mismatch_validation(
    db_session: Session, practice_content: PracticeContent
) -> None:
    svc = QuestionBankSufficiencyService(db_session)

    other_subject = Subject(code="OTHER_SUBJ", name="Other Subject")
    db_session.add(other_subject)
    db_session.flush()

    other_concept = Concept(
        subject_id=other_subject.id,
        code="OTHER_SUBJ_CONCEPT",
        name="Other Subj Concept",
    )
    db_session.add(other_concept)

    ch = Chapter(
        subject_id=other_subject.id,
        code="OTHER_CH",
        name="Other Ch",
        order_index=1,
    )
    db_session.add(ch)
    db_session.flush()

    tp = Topic(chapter_id=ch.id, code="OTHER_TOPIC", name="Topic", order_index=1)
    db_session.add(tp)
    db_session.flush()

    other_pt = ProblemType(
        topic_id=tp.id,
        code="OTHER_PT",
        name="Other PT",
        order_index=1,
    )
    db_session.add(other_pt)

    other_misc = MisconceptionDefinition(
        code="OTHER_MISC",
        concept_id=other_concept.id,
        name="Other Misc",
        description="Desc",
        category=MisconceptionCategory.CONCEPTUAL,
    )
    db_session.add(other_misc)
    db_session.flush()

    # 1. Concept from another subject
    with pytest.raises(ApplicationError) as exc_concept:
        svc.assess(
            QuestionSupplyRequirement(
                subject_id=practice_content.subject.id,
                use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                target_type=QuestionSupplyTargetType.CONCEPT,
                concept_id=other_concept.id,
            )
        )
    assert exc_concept.value.code == "QUESTION_SUPPLY_CONCEPT_SUBJECT_MISMATCH"

    # 2. ProblemType from another subject
    with pytest.raises(ApplicationError) as exc_pt:
        svc.assess(
            QuestionSupplyRequirement(
                subject_id=practice_content.subject.id,
                use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                target_type=QuestionSupplyTargetType.PROBLEM_TYPE,
                problem_type_id=other_pt.id,
            )
        )
    assert exc_pt.value.code == "QUESTION_SUPPLY_PROBLEM_TYPE_SUBJECT_MISMATCH"

    # 3. Misconception from another subject
    with pytest.raises(ApplicationError) as exc_misc:
        svc.assess(
            QuestionSupplyRequirement(
                subject_id=practice_content.subject.id,
                use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                target_type=QuestionSupplyTargetType.MISCONCEPTION,
                misconception_definition_id=other_misc.id,
            )
        )
    assert exc_misc.value.code == "QUESTION_SUPPLY_MISCONCEPTION_SUBJECT_MISMATCH"


def test_out_of_band_inventory_is_not_sufficient(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionBankSufficiencyService(db_session)

    # 8 approved questions all with difficulty 0.90 (outside desired 0.50 ± 0.15 band [0.35, 0.65])
    for i in range(8):
        _make_question(db_session, practice_content, index=i, difficulty=0.90)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
    )
    report = svc.assess(req)

    assert report.approved_eligible_count == 8
    assert report.approved_in_band_count == 0
    assert report.health == QuestionSupplyHealth.INSUFFICIENT
    assert report.reason_code == QuestionSupplyReasonCode.INSUFFICIENT_DIFFICULTY_COVERAGE


def test_partial_in_band_inventory_is_thin(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionBankSufficiencyService(db_session)

    # 5 in band (0.50), 3 out of band (0.90) -> total 8 meets preferred=8, but in-band=5 < preferred=8
    for i in range(5):
        _make_question(db_session, practice_content, index=i, difficulty=0.50)
    for i in range(5, 8):
        _make_question(db_session, practice_content, index=i, difficulty=0.90)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
    )
    report = svc.assess(req)

    assert report.approved_eligible_count == 8
    assert report.approved_in_band_count == 5
    assert report.health == QuestionSupplyHealth.THIN
    assert report.reason_code == QuestionSupplyReasonCode.THIN_DIFFICULTY_COVERAGE


def test_missing_concept_target_is_rejected(
    db_session: Session, practice_content: PracticeContent
) -> None:
    svc = QuestionBankSufficiencyService(db_session)
    with pytest.raises(ApplicationError) as exc:
        svc.assess(
            QuestionSupplyRequirement(
                subject_id=practice_content.subject.id,
                use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                target_type=QuestionSupplyTargetType.CONCEPT,
                concept_id=None,
            )
        )
    assert exc.value.code == "QUESTION_SUPPLY_CONCEPT_REQUIRED"


def test_missing_problem_type_target_is_rejected(
    db_session: Session, practice_content: PracticeContent
) -> None:
    svc = QuestionBankSufficiencyService(db_session)
    with pytest.raises(ApplicationError) as exc:
        svc.assess(
            QuestionSupplyRequirement(
                subject_id=practice_content.subject.id,
                use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                target_type=QuestionSupplyTargetType.PROBLEM_TYPE,
                problem_type_id=None,
            )
        )
    assert exc.value.code == "QUESTION_SUPPLY_PROBLEM_TYPE_REQUIRED"


def test_missing_misconception_target_is_rejected(
    db_session: Session, practice_content: PracticeContent
) -> None:
    svc = QuestionBankSufficiencyService(db_session)
    # Missing definition
    with pytest.raises(ApplicationError) as exc:
        svc.assess(
            QuestionSupplyRequirement(
                subject_id=practice_content.subject.id,
                use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                target_type=QuestionSupplyTargetType.MISCONCEPTION,
                misconception_definition_id=None,
            )
        )
    assert exc.value.code == "QUESTION_SUPPLY_MISCONCEPTION_REQUIRED"

    # Definition concept mismatch with supplied concept_id
    from app.misconceptions.models import MisconceptionCategory, MisconceptionDefinition
    misc = MisconceptionDefinition(
        concept_id=practice_content.concept.id,
        code="M-MISC-VALID",
        name="Valid Misc",
        description="Desc",
        category=MisconceptionCategory.CONCEPTUAL,
    )
    db_session.add(misc)
    other_concept = Concept(
        subject_id=practice_content.subject.id,
        code=f"C-OTHER-{uuid4().hex[:6].upper()}",
        name="Other Concept Same Subject",
    )
    db_session.add(other_concept)
    db_session.flush()

    with pytest.raises(ApplicationError) as exc_mismatch:
        svc.assess(
            QuestionSupplyRequirement(
                subject_id=practice_content.subject.id,
                use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                target_type=QuestionSupplyTargetType.MISCONCEPTION,
                misconception_definition_id=misc.id,
                concept_id=other_concept.id,
            )
        )
    assert exc_mismatch.value.code == "QUESTION_SUPPLY_MISCONCEPTION_CONCEPT_MISMATCH"


def test_invalid_desired_difficulty_rejected(
    db_session: Session, practice_content: PracticeContent
) -> None:
    svc = QuestionBankSufficiencyService(db_session)
    for invalid in [-0.1, 1.5]:
        with pytest.raises(ApplicationError) as exc:
            svc.assess(
                QuestionSupplyRequirement(
                    subject_id=practice_content.subject.id,
                    use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                    target_type=QuestionSupplyTargetType.CONCEPT,
                    concept_id=practice_content.concept.id,
                    desired_difficulty=invalid,
                )
            )
        assert exc.value.code == "INVALID_QUESTION_SUPPLY_DIFFICULTY"


def test_invalid_count_overrides_rejected(
    db_session: Session, practice_content: PracticeContent
) -> None:
    svc = QuestionBankSufficiencyService(db_session)
    with pytest.raises(ApplicationError) as exc_min:
        svc.assess(
            QuestionSupplyRequirement(
                subject_id=practice_content.subject.id,
                use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                target_type=QuestionSupplyTargetType.CONCEPT,
                concept_id=practice_content.concept.id,
                minimum_required_count=0,
            )
        )
    assert exc_min.value.code == "INVALID_QUESTION_SUPPLY_MINIMUM_COUNT"

    with pytest.raises(ApplicationError) as exc_pref:
        svc.assess(
            QuestionSupplyRequirement(
                subject_id=practice_content.subject.id,
                use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                target_type=QuestionSupplyTargetType.CONCEPT,
                concept_id=practice_content.concept.id,
                preferred_count=0,
            )
        )
    assert exc_pref.value.code == "INVALID_QUESTION_SUPPLY_PREFERRED_COUNT"

    with pytest.raises(ApplicationError) as exc_rel:
        svc.assess(
            QuestionSupplyRequirement(
                subject_id=practice_content.subject.id,
                use_case=QuestionSupplyUseCase.ROOT_CAUSE_VERIFICATION,
                target_type=QuestionSupplyTargetType.CONCEPT,
                concept_id=practice_content.concept.id,
                minimum_required_count=5,
                preferred_count=3,
            )
        )
    assert exc_rel.value.code == "INVALID_QUESTION_SUPPLY_PREFERRED_COUNT"


def test_open_response_inventory_reports_no_auto_evaluable_reason(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionBankSufficiencyService(db_session)

    # 5 APPROVED OPEN_RESPONSE questions targeting concept
    for i in range(5):
        _make_question(
            db_session,
            practice_content,
            index=i,
            question_type=QuestionType.OPEN_RESPONSE,
        )

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    report = svc.assess(req)

    assert report.approved_target_count == 5
    assert report.approved_eligible_count == 0
    assert report.health == QuestionSupplyHealth.INSUFFICIENT
    assert report.reason_code == QuestionSupplyReasonCode.NO_AUTO_EVALUABLE_TARGET_QUESTIONS


def test_invalid_objective_inventory_reports_no_auto_evaluable_reason(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionBankSufficiencyService(db_session)

    # 3 APPROVED MCQ with invalid correct_answer
    for i in range(3):
        _make_question(
            db_session,
            practice_content,
            index=i,
            question_type=QuestionType.MULTIPLE_CHOICE,
            correct_answer="NOT_AN_OPTION",
        )

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
    )
    report = svc.assess(req)

    assert report.approved_target_count == 3
    assert report.approved_eligible_count == 0
    assert report.health == QuestionSupplyHealth.INSUFFICIENT
    assert report.reason_code == QuestionSupplyReasonCode.NO_AUTO_EVALUABLE_TARGET_QUESTIONS


def test_sufficient_report_has_no_reason_code(
    db_session: Session, practice_content: PracticeContent
) -> None:
    _archive_questions(db_session)
    svc = QuestionBankSufficiencyService(db_session)

    for i in range(8):
        _make_question(db_session, practice_content, index=i, difficulty=0.50)

    req = QuestionSupplyRequirement(
        subject_id=practice_content.subject.id,
        use_case=QuestionSupplyUseCase.ADAPTIVE_REPAIR,
        target_type=QuestionSupplyTargetType.CONCEPT,
        concept_id=practice_content.concept.id,
        desired_difficulty=0.50,
    )
    report = svc.assess(req)

    assert report.approved_eligible_count == 8
    assert report.approved_in_band_count == 8
    assert report.health == QuestionSupplyHealth.SUFFICIENT
    assert report.reason_code is None

