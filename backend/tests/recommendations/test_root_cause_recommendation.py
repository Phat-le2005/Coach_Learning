"""Tests for Root Cause Recommendation: verified targets, isolation scoring, and exposure exclusion."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentStudentQuestion,
    AssignmentType,
    StudentAssignment,
    StudentAssignmentStatus,
)
from app.classes.models import Classroom
from app.concepts.models import Concept
from app.curriculum.models import ProblemType
from app.knowledge_gap.models import (
    RootCauseCandidate,
    RootCauseDiagnosis,
    RootCauseDiagnosisStatus,
    RootCauseDiagnosisType,
    RootCauseVerification,
    RootCauseVerificationItem,
    RootCauseVerificationOutcome,
    RootCauseVerificationStatus,
    RootCauseVerificationTarget,
    RootCauseVerificationTargetType,
)
from app.knowledge_gap.schemas import NextDiagnosticActionType
from app.knowledge_gap.target_resolver import VerifiedLearningTargetService
from app.learning_evidence.models import (
    LearningEvidenceConcept,
    LearningEvidenceEvent,
    LearningEvidenceProblemType,
    LearningEvidenceSourceKind,
)
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.questions.exposure import QuestionExposureService
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
from app.recommendations.question_service import QuestionRecommendationService
from app.recommendations.schemas import PriorityReasonCode
from app.students.models import StudentProfile
from app.users.models import User
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
    concept_ids: list[UUID],
    problem_type_id: UUID,
    text: str,
    difficulty: float = 0.5,
    status: QuestionStatus = QuestionStatus.APPROVED,
) -> Question:
    teacher = session.query(User).filter_by(email="teacher@practice.local").first()
    q = Question(
        subject_id=content.subject.id,
        content=text,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=difficulty,
        correct_answer="A",
        explanation="Explanation",
        source_type="TEST",
        exam_weight=0.5,
        status=status,
        cognitive_level=CognitiveLevel.UNDERSTAND,
        created_by=teacher.id if teacher else content.mcq.created_by,
        options=[
            QuestionOption(label="A", content="Option A", order_index=0),
            QuestionOption(label="B", content="Option B", order_index=1),
        ],
    )
    q.concept_links = [
        QuestionConcept(concept_id=cid, weight=1.0) for cid in concept_ids
    ]
    q.problem_type_links = [
        QuestionProblemType(problem_type_id=problem_type_id, weight=1.0, is_primary=True)
    ]
    q.learning_outcome_links = [
        QuestionLearningOutcome(
            learning_outcome_id=content.learning_outcome.id, weight=1.0
        )
    ]
    session.add(q)
    session.flush()
    return q


def _create_verified_diagnosis_with_target(
    session: Session,
    content: PracticeContent,
    student_id: UUID,
    target_concept_id: UUID,
    *,
    outcome: RootCauseVerificationOutcome = RootCauseVerificationOutcome.SUPPORTED,
    probe_questions: list[Question] | None = None,
) -> tuple[RootCauseDiagnosis, RootCauseVerification]:
    now = datetime.now(timezone.utc)
    ev = LearningEvidenceEvent(
        student_id=student_id,
        subject_id=content.subject.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION,
        source_entity_id=uuid4(),
        is_correct=False,
        score=0.0,
        difficulty=0.5,
        hint_count=0,
        evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=now,
    )
    session.add(ev)
    session.flush()

    diag = RootCauseDiagnosis(
        learning_evidence_event_id=ev.id,
        student_id=student_id,
        subject_id=content.subject.id,
        target_problem_type_id=content.problem_type.id,
        diagnosis_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        status=RootCauseDiagnosisStatus.HYPOTHESIS,
        root_concept_id=target_concept_id,
        confidence=0.8,
        supporting_evidence_count=2,
        reason_code="PREREQUISITE_LOW_MASTERY_REPEATED_ERRORS",
    )
    session.add(diag)
    session.flush()

    cand = RootCauseCandidate(
        diagnosis_id=diag.id,
        rank=1,
        candidate_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        concept_id=target_concept_id,
        problem_type_id=content.problem_type.id,
        score=0.85,
        confidence=0.80,
        mastery_deficit_signal=0.8,
        recent_error_signal=0.8,
        structural_signal=0.8,
        misconception_signal=0.0,
        evidence_volume_signal=0.5,
        supporting_event_count=2,
        conflicting_event_count=0,
        reason_codes=["TEST_REASON"],
    )
    session.add(cand)
    session.flush()

    ps = PracticeSession(
        student_id=student_id,
        subject_id=content.subject.id,
        session_type=PracticeSessionType.ROOT_CAUSE_VERIFICATION,
        status=PracticeSessionStatus.COMPLETED,
        completed_at=now,
    )
    session.add(ps)
    session.flush()

    ver_status = (
        RootCauseVerificationStatus.COMPLETED
        if outcome in {RootCauseVerificationOutcome.SUPPORTED, RootCauseVerificationOutcome.NOT_SUPPORTED, RootCauseVerificationOutcome.INCONCLUSIVE}
        else RootCauseVerificationStatus.UNAVAILABLE
    )
    ver = RootCauseVerification(
        diagnosis_id=diag.id,
        practice_session_id=ps.id,
        status=ver_status,
        required_probe_count=len(probe_questions) if probe_questions else 0,
        completed_probe_count=len(probe_questions) if probe_questions else 0,
        completed_at=now,
    )
    session.add(ver)
    session.flush()

    target = RootCauseVerificationTarget(
        verification_id=ver.id,
        root_cause_candidate_id=cand.id,
        target_type=RootCauseVerificationTargetType.CONCEPT,
        target_concept_id=target_concept_id,
        priority_order=1,
        outcome=outcome,
        probe_count=len(probe_questions) if probe_questions else 0,
        correct_count=0 if outcome == RootCauseVerificationOutcome.SUPPORTED else len(probe_questions or []),
        average_score=0.0 if outcome == RootCauseVerificationOutcome.SUPPORTED else 1.0,
        completed_at=now,
    )
    session.add(target)
    session.flush()

    if probe_questions:
        for idx, pq in enumerate(probe_questions, start=1):
            att = QuestionAttempt(
                practice_session_id=ps.id,
                student_id=student_id,
                question_id=pq.id,
                student_answer="B",
                is_correct=(outcome == RootCauseVerificationOutcome.NOT_SUPPORTED),
                score=1.0 if outcome == RootCauseVerificationOutcome.NOT_SUPPORTED else 0.0,
                attempt_number=idx,
                evaluation_status=EvaluationStatus.AUTO_EVALUATED,
            )
            session.add(att)
            session.flush()

            item = RootCauseVerificationItem(
                verification_target_id=target.id,
                question_id=pq.id,
                order_index=idx,
                desired_difficulty=0.35,
                selection_score=0.8,
                attempt_id=att.id,
            )
            session.add(item)

    session.commit()
    return diag, ver


def test_recommendation_for_verified_prerequisite_target(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    prereq = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.REC.PREREQ.01",
        name="Verified Target Concept",
    )
    db_session.add(prereq)
    db_session.flush()

    probe1 = _make_question(
        db_session, practice_content, concept_ids=[prereq.id], problem_type_id=practice_content.problem_type.id, text="Probe 1"
    )
    probe2 = _make_question(
        db_session, practice_content, concept_ids=[prereq.id], problem_type_id=practice_content.problem_type.id, text="Probe 2"
    )
    repair_q = _make_question(
        db_session, practice_content, concept_ids=[prereq.id], problem_type_id=practice_content.problem_type.id, text="Repair Question", difficulty=0.40
    )

    diag, _ = _create_verified_diagnosis_with_target(
        db_session,
        practice_content,
        student_profile.id,
        prereq.id,
        outcome=RootCauseVerificationOutcome.SUPPORTED,
        probe_questions=[probe1, probe2],
    )

    resolver = VerifiedLearningTargetService(db_session)
    action = resolver.resolve_next_action(student_profile.id, diag.id)

    assert action.action == NextDiagnosticActionType.PRACTICE_REPAIR
    assert action.verified_target is not None
    assert action.verified_target.target_concept_id == prereq.id
    assert action.recommended_question is not None
    assert action.recommended_question.question_id == repair_q.id
    assert action.recommended_question.reason_code == PriorityReasonCode.VERIFIED_ROOT_CAUSE


def test_recommendation_excludes_probes_and_recent_exposures(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    prereq = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.EXCLUDE.01",
        name="Exclusion Concept",
    )
    db_session.add(prereq)
    db_session.flush()

    probe1 = _make_question(
        db_session, practice_content, concept_ids=[prereq.id], problem_type_id=practice_content.problem_type.id, text="Ex Probe 1"
    )
    probe2 = _make_question(
        db_session, practice_content, concept_ids=[prereq.id], problem_type_id=practice_content.problem_type.id, text="Ex Probe 2"
    )
    recent_q = _make_question(
        db_session, practice_content, concept_ids=[prereq.id], problem_type_id=practice_content.problem_type.id, text="Recent Question"
    )
    fresh_repair_q = _make_question(
        db_session, practice_content, concept_ids=[prereq.id], problem_type_id=practice_content.problem_type.id, text="Fresh Repair Q"
    )

    # Record recent QuestionAttempt on recent_q
    ps = PracticeSession(
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.COMPLETED,
        completed_at=datetime.now(timezone.utc),
    )
    db_session.add(ps)
    db_session.flush()
    db_session.add(
        QuestionAttempt(
            practice_session_id=ps.id,
            student_id=student_profile.id,
            question_id=recent_q.id,
            student_answer="A",
            is_correct=True,
            score=1.0,
            attempt_number=1,
            evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        )
    )
    db_session.commit()

    diag, _ = _create_verified_diagnosis_with_target(
        db_session,
        practice_content,
        student_profile.id,
        prereq.id,
        outcome=RootCauseVerificationOutcome.SUPPORTED,
        probe_questions=[probe1, probe2],
    )

    resolver = VerifiedLearningTargetService(db_session)
    action = resolver.resolve_next_action(student_profile.id, diag.id)

    assert action.action == NextDiagnosticActionType.PRACTICE_REPAIR
    # Probe 1, Probe 2, and Recent Q must be excluded! Fresh Repair Q must be chosen!
    assert action.recommended_question.question_id == fresh_repair_q.id


def test_recommendation_prioritizes_higher_isolation_score(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    prereq = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.ISO.01",
        name="Target Concept",
    )
    other1 = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.ISO.OTHER1",
        name="Confounding Concept 1",
    )
    other2 = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.ISO.OTHER2",
        name="Confounding Concept 2",
    )
    db_session.add_all([prereq, other1, other2])
    db_session.flush()

    probe1 = _make_question(
        db_session, practice_content, concept_ids=[prereq.id], problem_type_id=practice_content.problem_type.id, text="Iso Probe 1"
    )
    probe2 = _make_question(
        db_session, practice_content, concept_ids=[prereq.id], problem_type_id=practice_content.problem_type.id, text="Iso Probe 2"
    )

    # Low isolation question (tests 3 concepts simultaneously)
    q_low_iso = _make_question(
        db_session,
        practice_content,
        concept_ids=[prereq.id, other1.id, other2.id],
        problem_type_id=practice_content.problem_type.id,
        text="Confounded Question",
        difficulty=0.40,
    )
    # High isolation question (tests only target concept)
    q_high_iso = _make_question(
        db_session,
        practice_content,
        concept_ids=[prereq.id],
        problem_type_id=practice_content.problem_type.id,
        text="Isolated Question",
        difficulty=0.40,
    )

    diag, _ = _create_verified_diagnosis_with_target(
        db_session,
        practice_content,
        student_profile.id,
        prereq.id,
        outcome=RootCauseVerificationOutcome.SUPPORTED,
        probe_questions=[probe1, probe2],
    )

    resolver = VerifiedLearningTargetService(db_session)
    action = resolver.resolve_next_action(student_profile.id, diag.id)

    assert action.action == NextDiagnosticActionType.PRACTICE_REPAIR
    # High isolation question must beat low isolation question!
    assert action.recommended_question.question_id == q_high_iso.id


def test_unverified_hypothesis_requires_verification_not_repair(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    c = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.UNVER.01",
        name="Unverified Concept",
    )
    db_session.add(c)
    db_session.flush()

    now = datetime.now(timezone.utc)
    ev = LearningEvidenceEvent(
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION,
        source_entity_id=uuid4(),
        is_correct=False,
        score=0.0,
        difficulty=0.5,
        hint_count=0,
        evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=now,
    )
    db_session.add(ev)
    db_session.flush()

    diag = RootCauseDiagnosis(
        learning_evidence_event_id=ev.id,
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        target_problem_type_id=practice_content.problem_type.id,
        diagnosis_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        status=RootCauseDiagnosisStatus.HYPOTHESIS,
        root_concept_id=c.id,
        confidence=0.75,
        supporting_evidence_count=2,
        reason_code="PREREQUISITE_LOW_MASTERY_REPEATED_ERRORS",
    )
    db_session.add(diag)
    db_session.commit()

    resolver = VerifiedLearningTargetService(db_session)
    action = resolver.resolve_next_action(student_profile.id, diag.id)

    assert action.action == NextDiagnosticActionType.VERIFY_ROOT_CAUSE
    assert action.recommended_question is None


def test_disproved_hypothesis_yields_collect_more_evidence(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    c = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.DISPROVED.01",
        name="Disproved Concept",
    )
    db_session.add(c)
    db_session.flush()

    p1 = _make_question(db_session, practice_content, concept_ids=[c.id], problem_type_id=practice_content.problem_type.id, text="P1")
    p2 = _make_question(db_session, practice_content, concept_ids=[c.id], problem_type_id=practice_content.problem_type.id, text="P2")

    diag, _ = _create_verified_diagnosis_with_target(
        db_session,
        practice_content,
        student_profile.id,
        c.id,
        outcome=RootCauseVerificationOutcome.NOT_SUPPORTED,
        probe_questions=[p1, p2],
    )

    resolver = VerifiedLearningTargetService(db_session)
    action = resolver.resolve_next_action(student_profile.id, diag.id)

    assert action.action == NextDiagnosticActionType.COLLECT_MORE_EVIDENCE
    assert action.recommended_question is None


def test_missing_mastery_uses_neutral_progression_difficulty(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    service = QuestionRecommendationService(db_session)
    # When student has NO mastery row for concept, difficulty should default to 0.50 (neutral), not 0.30
    diff = service._target_difficulty(
        student_id=student_profile.id,
        problem_type_id=None,
        concept_id=practice_content.concept.id,
        selected_priority=None,
    )
    assert diff == 0.50

def test_assignment_canonical_recent_exposure_is_excluded(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    concept = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.REC.ASSIGNMENT.EXPOSURE",
        name="Assignment exposure target",
    )
    db_session.add(concept)
    db_session.flush()
    exposed = _make_question(
        db_session,
        practice_content,
        concept_ids=[concept.id],
        problem_type_id=practice_content.problem_type.id,
        text="Already assigned canonical question",
    )
    fresh = _make_question(
        db_session,
        practice_content,
        concept_ids=[concept.id],
        problem_type_id=practice_content.problem_type.id,
        text="Fresh canonical question",
    )
    teacher = db_session.get(User, practice_content.mcq.created_by)
    assert teacher is not None
    classroom = Classroom(
        name="Recommendation exposure",
        academic_year="2026-2027",
        grade_level=12,
        created_by=teacher.id,
    )
    db_session.add(classroom)
    db_session.flush()
    assignment = Assignment(
        classroom_id=classroom.id,
        subject_id=practice_content.subject.id,
        title="Exposure assignment",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED,
        question_count=1,
        created_by=teacher.id,
    )
    db_session.add(assignment)
    db_session.flush()
    student_assignment = StudentAssignment(
        assignment_id=assignment.id,
        student_id=student_profile.id,
        status=StudentAssignmentStatus.SUBMITTED,
    )
    db_session.add(student_assignment)
    db_session.flush()
    assigned_question = AssignmentStudentQuestion(
        student_assignment_id=student_assignment.id,
        question_id=exposed.id,
        order_index=0,
        student_answer="A",
        is_correct=True,
        score=1.0,
        answered_at=datetime.now(timezone.utc),
    )
    db_session.add(assigned_question)
    db_session.flush()
    db_session.add(
        LearningEvidenceEvent(
            student_id=student_profile.id,
            subject_id=practice_content.subject.id,
            assignment_id=assignment.id,
            source_kind=LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION,
            source_entity_id=assigned_question.id,
            is_correct=True,
            score=1.0,
            difficulty=exposed.difficulty,
            hint_count=0,
            evaluation_status=EvaluationStatus.AUTO_EVALUATED,
            occurred_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    recommendation = QuestionRecommendationService(db_session).recommend(
        student_profile.id,
        practice_content.subject.id,
        target_concept_id=concept.id,
    )

    assert recommendation is not None
    assert recommendation.question_id == fresh.id


def test_root_cause_target_fit_beats_exam_weight(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    target = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.REC.EXACT",
        name="Exact repair target",
    )
    confounder = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.REC.CONFOUNDER",
        name="Confounding concept",
    )
    db_session.add_all([target, confounder])
    db_session.flush()

    probe1 = _make_question(
        db_session,
        practice_content,
        concept_ids=[target.id],
        problem_type_id=practice_content.problem_type.id,
        text="Exactness probe 1",
    )
    probe2 = _make_question(
        db_session,
        practice_content,
        concept_ids=[target.id],
        problem_type_id=practice_content.problem_type.id,
        text="Exactness probe 2",
    )
    exact = _make_question(
        db_session,
        practice_content,
        concept_ids=[target.id],
        problem_type_id=practice_content.problem_type.id,
        text="Exact isolated repair",
        difficulty=0.4,
    )
    exact.exam_weight = 0.0
    high_exam_confounder = _make_question(
        db_session,
        practice_content,
        concept_ids=[target.id, confounder.id],
        problem_type_id=practice_content.problem_type.id,
        text="High exam but weak target repair",
        difficulty=0.4,
    )
    high_exam_confounder.exam_weight = 1.0
    next(
        link
        for link in high_exam_confounder.concept_links
        if link.concept_id == target.id
    ).weight = 0.2

    diagnosis, _ = _create_verified_diagnosis_with_target(
        db_session,
        practice_content,
        student_profile.id,
        target.id,
        outcome=RootCauseVerificationOutcome.SUPPORTED,
        probe_questions=[probe1, probe2],
    )

    action = VerifiedLearningTargetService(db_session).resolve_next_action(
        student_profile.id, diagnosis.id
    )

    assert action.action == NextDiagnosticActionType.PRACTICE_REPAIR
    assert action.recommended_question is not None
    assert action.recommended_question.question_id == exact.id


def test_verified_target_with_no_question_returns_no_canonical_question(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    target = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.REC.NO.REPAIR",
        name="Verified target without repair question",
    )
    db_session.add(target)
    db_session.flush()
    probe1 = _make_question(
        db_session,
        practice_content,
        concept_ids=[target.id],
        problem_type_id=practice_content.problem_type.id,
        text="Only probe 1",
    )
    probe2 = _make_question(
        db_session,
        practice_content,
        concept_ids=[target.id],
        problem_type_id=practice_content.problem_type.id,
        text="Only probe 2",
    )
    diagnosis, _ = _create_verified_diagnosis_with_target(
        db_session,
        practice_content,
        student_profile.id,
        target.id,
        outcome=RootCauseVerificationOutcome.SUPPORTED,
        probe_questions=[probe1, probe2],
    )

    action = VerifiedLearningTargetService(db_session).resolve_next_action(
        student_profile.id, diagnosis.id
    )

    assert action.action == NextDiagnosticActionType.NO_CANONICAL_QUESTION
    assert action.recommended_question is None
