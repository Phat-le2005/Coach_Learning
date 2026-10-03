"""Hardening invariants for deterministic root-cause verification."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
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
    RootCauseVerificationTargetType,
)
from app.knowledge_gap.schemas import (
    NextDiagnosticActionType,
    RootCauseVerificationAnswerSubmit,
)
from app.knowledge_gap.target_resolver import VerifiedLearningTargetService
from app.knowledge_gap.verification import RootCauseVerificationService
from app.knowledge_gap.verification_policy import (
    RootCauseVerificationPolicy,
    TargetResolutionSpec,
)
from app.learning_evidence.models import (
    LearningEvidenceEvent,
    LearningEvidenceSourceKind,
)
from app.practice.evaluation import AnswerEvaluation
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.questions.exposure import QuestionExposureService
from app.questions.models import Question, QuestionStatus, QuestionType
from app.students.models import StudentProfile
from tests.knowledge_gap.test_verification import (
    _create_diagnosis,
    _create_question,
)
from tests.practice.conftest import (
    PracticeContent,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)


def _new_concept(session: Session, content: PracticeContent, code: str) -> Concept:
    concept = Concept(subject_id=content.subject.id, code=code, name=code)
    session.add(concept)
    session.flush()
    return concept


def _one_probe_result(
    session: Session,
    content: PracticeContent,
    student: StudentProfile,
    *,
    code: str,
    answer: str,
) -> tuple[RootCauseVerificationOutcome, RootCauseVerificationStatus, NextDiagnosticActionType]:
    concept = _new_concept(session, content, code)
    _create_question(
        session,
        content,
        concept,
        content.problem_type,
        text=f"{code} only probe",
        correct_answer="A",
    )
    diagnosis = _create_diagnosis(
        session,
        content,
        student.id,
        root_concept_id=concept.id,
        candidate_concept_id=concept.id,
    )
    service = RootCauseVerificationService(session)
    verification = service.start_verification(student.id, diagnosis.id)
    assert verification.required_probe_count == 1

    result = service.submit_verification_answer(
        student.id,
        diagnosis.id,
        verification.targets[0].items[0].id,
        RootCauseVerificationAnswerSubmit(student_answer=answer),
    )
    action = VerifiedLearningTargetService(session).resolve_next_action(
        student.id, diagnosis.id
    )
    return result.target_outcome, result.verification_status, action.action


def test_open_response_is_never_selected_for_verification(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    concept = _new_concept(db_session, practice_content, "MATH.12.VER.AUTO")
    open_response = _create_question(
        db_session,
        practice_content,
        concept,
        practice_content.problem_type,
        text="Manual response",
        question_type=QuestionType.OPEN_RESPONSE,
    )
    eligible = _create_question(
        db_session,
        practice_content,
        concept,
        practice_content.problem_type,
        text="Deterministic response",
    )
    diagnosis = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=concept.id,
        candidate_concept_id=concept.id,
    )

    verification = RootCauseVerificationService(db_session).start_verification(
        student_profile.id, diagnosis.id
    )
    selected = [item.question_id for item in verification.targets[0].items]

    assert eligible.id in selected
    assert open_response.id not in selected


def test_unevaluated_attempt_is_not_counted_as_probe() -> None:
    attempt_id = uuid4()
    item = RootCauseVerificationItem(
        id=uuid4(),
        verification_target_id=uuid4(),
        question_id=uuid4(),
        order_index=1,
        desired_difficulty=0.4,
        selection_score=0.8,
        attempt_id=attempt_id,
    )
    pending = QuestionAttempt(
        id=attempt_id,
        practice_session_id=uuid4(),
        student_id=uuid4(),
        question_id=item.question_id,
        student_answer="draft",
        is_correct=None,
        score=None,
        attempt_number=1,
        evaluation_status=EvaluationStatus.NEEDS_EVALUATION,
    )

    outcome, probe_count, correct_count, average_score = (
        RootCauseVerificationPolicy.evaluate_target_outcome(
            [item], {attempt_id: pending}
        )
    )

    assert outcome == RootCauseVerificationOutcome.PENDING
    assert probe_count == 0
    assert correct_count == 0
    assert average_score is None


def test_submit_rejects_unevaluated_result_without_persisting_attempt(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    concept = _new_concept(db_session, practice_content, "MATH.12.VER.DEFENSE")
    _create_question(
        db_session,
        practice_content,
        concept,
        practice_content.problem_type,
        text="Defense probe",
    )
    diagnosis = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=concept.id,
        candidate_concept_id=concept.id,
    )
    normal_service = RootCauseVerificationService(db_session)
    verification = normal_service.start_verification(student_profile.id, diagnosis.id)
    item = verification.targets[0].items[0]

    class PendingEvaluator:
        def evaluate(self, question: Question, student_answer: str) -> AnswerEvaluation:
            return AnswerEvaluation(None, None, EvaluationStatus.NEEDS_EVALUATION)

    service = RootCauseVerificationService(db_session, evaluator=PendingEvaluator())
    before_count = db_session.scalar(select(func.count()).select_from(QuestionAttempt))

    with pytest.raises(ApplicationError) as error:
        service.submit_verification_answer(
            student_profile.id,
            diagnosis.id,
            item.id,
            RootCauseVerificationAnswerSubmit(student_answer="A"),
        )

    assert error.value.status_code == 409
    assert error.value.code == "VERIFICATION_QUESTION_NOT_AUTO_EVALUABLE"
    assert db_session.scalar(select(func.count()).select_from(QuestionAttempt)) == before_count
    assert db_session.get(RootCauseVerificationItem, item.id).attempt_id is None
    persisted = db_session.get(RootCauseVerification, verification.id)
    assert persisted.completed_probe_count == 0
    assert persisted.status == RootCauseVerificationStatus.ACTIVE


def test_one_wrong_probe_is_inconclusive(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    outcome, status, action = _one_probe_result(
        db_session,
        practice_content,
        student_profile,
        code="MATH.12.VER.ONE.WRONG",
        answer="B",
    )
    assert outcome == RootCauseVerificationOutcome.INCONCLUSIVE
    assert status == RootCauseVerificationStatus.COMPLETED
    assert action == NextDiagnosticActionType.COLLECT_MORE_EVIDENCE


def test_one_correct_probe_is_inconclusive(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    outcome, status, action = _one_probe_result(
        db_session,
        practice_content,
        student_profile,
        code="MATH.12.VER.ONE.CORRECT",
        answer="A",
    )
    assert outcome == RootCauseVerificationOutcome.INCONCLUSIVE
    assert status == RootCauseVerificationStatus.COMPLETED
    assert action == NextDiagnosticActionType.COLLECT_MORE_EVIDENCE


def test_primary_problem_type_mapping_is_preferred(
    db_session: Session,
    practice_content: PracticeContent,
) -> None:
    target = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code="MATH.12.VER.PRIMARY.PT",
        name="Primary ranking target",
        order_index=20,
        is_active=True,
    )
    concept = _new_concept(db_session, practice_content, "MATH.12.VER.PRIMARY.C")
    db_session.add(target)
    db_session.flush()
    non_primary = _create_question(
        db_session,
        practice_content,
        concept,
        target,
        text="Non-primary mapping",
        is_primary=False,
    )
    primary = _create_question(
        db_session,
        practice_content,
        concept,
        target,
        text="Primary mapping",
        is_primary=True,
    )
    spec = TargetResolutionSpec(
        target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        candidate_id=None,
        target_concept_id=None,
        target_problem_type_id=target.id,
        misconception_definition_id=None,
        priority_order=1,
        desired_difficulty=0.35,
        required_probes=2,
    )

    selected = RootCauseVerificationPolicy.select_probe_questions(
        db_session, practice_content.subject.id, spec, set()
    )

    assert [question.id for question, _ in selected] == [primary.id, non_primary.id]


def test_target_mapping_weight_affects_probe_ranking(
    db_session: Session,
    practice_content: PracticeContent,
) -> None:
    concept = _new_concept(db_session, practice_content, "MATH.12.VER.WEIGHT")
    weak = _create_question(
        db_session,
        practice_content,
        concept,
        practice_content.problem_type,
        text="Weak mapping",
        concept_weight=0.3,
    )
    strong = _create_question(
        db_session,
        practice_content,
        concept,
        practice_content.problem_type,
        text="Strong mapping",
        concept_weight=1.0,
    )
    spec = TargetResolutionSpec(
        target_type=RootCauseVerificationTargetType.CONCEPT,
        candidate_id=None,
        target_concept_id=concept.id,
        target_problem_type_id=None,
        misconception_definition_id=None,
        priority_order=1,
        desired_difficulty=0.35,
        required_probes=2,
    )

    selected = RootCauseVerificationPolicy.select_probe_questions(
        db_session, practice_content.subject.id, spec, set()
    )

    assert [question.id for question, _ in selected] == [strong.id, weak.id]


def test_frozen_probe_selection_does_not_change_after_bank_update(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    concept = _new_concept(db_session, practice_content, "MATH.12.VER.FROZEN")
    _create_question(
        db_session, practice_content, concept, practice_content.problem_type, text="Frozen Q1"
    )
    _create_question(
        db_session, practice_content, concept, practice_content.problem_type, text="Frozen Q2"
    )
    diagnosis = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=concept.id,
        candidate_concept_id=concept.id,
    )
    service = RootCauseVerificationService(db_session)
    started = service.start_verification(student_profile.id, diagnosis.id)
    original_ids = [
        item.question_id for target in started.targets for item in target.items
    ]

    added = _create_question(
        db_session,
        practice_content,
        concept,
        practice_content.problem_type,
        text="New stronger Q3",
        difficulty=0.35,
        concept_weight=1.0,
    )
    db_session.commit()
    fetched = service.get_verification(student_profile.id, diagnosis.id)
    fetched_ids = [item.question_id for target in fetched.targets for item in target.items]

    assert added.id not in fetched_ids
    assert fetched_ids == original_ids


def test_verification_get_does_not_leak_answer(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    concept = _new_concept(db_session, practice_content, "MATH.12.VER.NOLEAK")
    _create_question(
        db_session,
        practice_content,
        concept,
        practice_content.problem_type,
        text="No leak",
        correct_answer="A",
    )
    diagnosis = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=concept.id,
        candidate_concept_id=concept.id,
    )

    read = RootCauseVerificationService(db_session).start_verification(
        student_profile.id, diagnosis.id
    )
    payload = read.model_dump(mode="json")
    item_payload = payload["targets"][0]["items"][0]

    assert "correct_answer" not in str(payload)
    assert item_payload["explanation"] is None
    assert item_payload["student_answer"] is None
    assert item_payload["is_correct"] is None


def test_source_question_is_excluded(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concept = _new_concept(db_session, practice_content, "MATH.12.VER.SOURCE")
    source_question = _create_question(
        db_session,
        practice_content,
        concept,
        practice_content.problem_type,
        text="Diagnosis source question",
    )
    fresh = _create_question(
        db_session,
        practice_content,
        concept,
        practice_content.problem_type,
        text="Fresh probe",
    )
    diagnosis = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=concept.id,
        candidate_concept_id=concept.id,
        source_question=source_question,
    )
    monkeypatch.setattr(
        QuestionExposureService,
        "get_recent_exposed_question_ids",
        lambda self, student_id, limit=20: set(),
    )

    verification = RootCauseVerificationService(db_session).start_verification(
        student_profile.id, diagnosis.id
    )
    selected = [item.question_id for item in verification.targets[0].items]

    assert source_question.id not in selected
    assert selected == [fresh.id]


def test_multi_factor_secondary_unavailable_does_not_block_supported_target(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    available_concept = _new_concept(
        db_session, practice_content, "MATH.12.VER.MULTI.A"
    )
    unavailable_pt = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code="MATH.12.VER.MULTI.B",
        name="Unavailable target",
        order_index=21,
        is_active=True,
    )
    db_session.add(unavailable_pt)
    db_session.flush()
    for index in range(3):
        _create_question(
            db_session,
            practice_content,
            available_concept,
            practice_content.problem_type,
            text=f"Available target Q{index}",
        )

    evidence = LearningEvidenceEvent(
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION,
        source_entity_id=uuid4(),
        is_correct=False,
        score=0.0,
        difficulty=0.5,
        hint_count=0,
        evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=datetime.now(timezone.utc),
    )
    db_session.add(evidence)
    db_session.flush()
    diagnosis = RootCauseDiagnosis(
        learning_evidence_event_id=evidence.id,
        student_id=student_profile.id,
        subject_id=practice_content.subject.id,
        target_problem_type_id=practice_content.problem_type.id,
        diagnosis_type=RootCauseDiagnosisType.MULTI_FACTOR_GAP,
        status=RootCauseDiagnosisStatus.HYPOTHESIS,
        root_concept_id=available_concept.id,
        confidence=0.7,
        supporting_evidence_count=2,
        reason_code="AMBIGUOUS_MULTIPLE_CAUSES",
    )
    db_session.add(diagnosis)
    db_session.flush()
    db_session.add_all(
        [
            RootCauseCandidate(
                diagnosis_id=diagnosis.id,
                rank=1,
                candidate_type=RootCauseDiagnosisType.DIRECT_CONCEPT_GAP,
                concept_id=available_concept.id,
                score=0.8,
                confidence=0.75,
                mastery_deficit_signal=0.7,
                recent_error_signal=0.8,
                structural_signal=0.8,
                misconception_signal=0.0,
                evidence_volume_signal=0.5,
                supporting_event_count=2,
                conflicting_event_count=0,
                reason_codes=["AVAILABLE"],
            ),
            RootCauseCandidate(
                diagnosis_id=diagnosis.id,
                rank=2,
                candidate_type=RootCauseDiagnosisType.PROBLEM_TYPE_PROCEDURE_GAP,
                problem_type_id=unavailable_pt.id,
                score=0.7,
                confidence=0.7,
                mastery_deficit_signal=0.6,
                recent_error_signal=0.7,
                structural_signal=0.7,
                misconception_signal=0.0,
                evidence_volume_signal=0.5,
                supporting_event_count=2,
                conflicting_event_count=0,
                reason_codes=["UNAVAILABLE"],
            ),
        ]
    )
    db_session.commit()

    service = RootCauseVerificationService(db_session)
    verification = service.start_verification(student_profile.id, diagnosis.id)
    assert verification.status == RootCauseVerificationStatus.ACTIVE
    assert verification.required_probe_count == 2
    assert verification.targets[1].outcome == RootCauseVerificationOutcome.UNAVAILABLE

    for item in verification.targets[0].items:
        service.submit_verification_answer(
            student_profile.id,
            diagnosis.id,
            item.id,
            RootCauseVerificationAnswerSubmit(student_answer="B"),
        )

    completed = service.get_verification(student_profile.id, diagnosis.id)
    assert completed.status == RootCauseVerificationStatus.COMPLETED
    assert completed.targets[0].outcome == RootCauseVerificationOutcome.SUPPORTED
    assert completed.targets[1].outcome == RootCauseVerificationOutcome.UNAVAILABLE
    action = VerifiedLearningTargetService(db_session).resolve_next_action(
        student_profile.id, diagnosis.id
    )
    assert action.action == NextDiagnosticActionType.PRACTICE_REPAIR


def test_verification_unique_per_diagnosis_and_race_loser_has_no_orphan_session(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    concept = _new_concept(db_session, practice_content, "MATH.12.VER.RACE")
    _create_question(
        db_session, practice_content, concept, practice_content.problem_type, text="Race Q1"
    )
    _create_question(
        db_session, practice_content, concept, practice_content.problem_type, text="Race Q2"
    )
    diagnosis = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=concept.id,
        candidate_concept_id=concept.id,
    )
    winner = RootCauseVerificationService(db_session).start_verification(
        student_profile.id, diagnosis.id
    )
    before_sessions = db_session.scalar(
        select(func.count())
        .select_from(PracticeSession)
        .where(
            PracticeSession.student_id == student_profile.id,
            PracticeSession.session_type == PracticeSessionType.ROOT_CAUSE_VERIFICATION,
        )
    )

    service = RootCauseVerificationService(db_session)
    original_find = RootCauseVerificationService._find_existing_verification
    find_calls = 0

    def race_find(diagnosis_id):
        nonlocal find_calls
        find_calls += 1
        if find_calls == 1:
            return None
        return original_find(service, diagnosis_id)

    def losing_create(**kwargs):
        leaked = PracticeSession(
            student_id=student_profile.id,
            subject_id=practice_content.subject.id,
            session_type=PracticeSessionType.ROOT_CAUSE_VERIFICATION,
            status=PracticeSessionStatus.ACTIVE,
        )
        db_session.add(leaked)
        db_session.flush()
        raise IntegrityError("concurrent verification insert", {}, Exception("unique"))

    monkeypatch.setattr(service, "_find_existing_verification", race_find)
    monkeypatch.setattr(service, "_create_verification_rows", losing_create)

    recovered = service.start_verification(student_profile.id, diagnosis.id)

    assert recovered.id == winner.id
    after_sessions = db_session.scalar(
        select(func.count())
        .select_from(PracticeSession)
        .where(
            PracticeSession.student_id == student_profile.id,
            PracticeSession.session_type == PracticeSessionType.ROOT_CAUSE_VERIFICATION,
        )
    )
    assert after_sessions == before_sessions
    assert db_session.scalar(
        select(func.count())
        .select_from(RootCauseVerification)
        .where(RootCauseVerification.diagnosis_id == diagnosis.id)
    ) == 1

def test_problem_type_mapping_weight_affects_probe_ranking(
    db_session: Session,
    practice_content: PracticeContent,
) -> None:
    target = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code="MATH.12.VER.PT.WEIGHT",
        name="ProblemType weight target",
        order_index=22,
        is_active=True,
    )
    concept = _new_concept(db_session, practice_content, "MATH.12.VER.PT.WEIGHT.C")
    db_session.add(target)
    db_session.flush()
    weak = _create_question(
        db_session,
        practice_content,
        concept,
        target,
        text="Weak ProblemType mapping",
        problem_type_weight=0.3,
    )
    strong = _create_question(
        db_session,
        practice_content,
        concept,
        target,
        text="Strong ProblemType mapping",
        problem_type_weight=1.0,
    )
    spec = TargetResolutionSpec(
        target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        candidate_id=None,
        target_concept_id=None,
        target_problem_type_id=target.id,
        misconception_definition_id=None,
        priority_order=1,
        desired_difficulty=0.35,
        required_probes=2,
    )

    selected = RootCauseVerificationPolicy.select_probe_questions(
        db_session, practice_content.subject.id, spec, set()
    )

    assert [question.id for question, _ in selected] == [strong.id, weak.id]
