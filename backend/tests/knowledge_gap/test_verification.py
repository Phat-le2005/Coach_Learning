"""Tests for Root Cause Verification: lifecycle, policies, probe isolation, and evidence pipeline."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.knowledge_gap.models import (
    RootCauseCandidate,
    RootCauseDiagnosis,
    RootCauseDiagnosisStatus,
    RootCauseDiagnosisType,
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
from app.learning_evidence.models import (
    LearningEvidenceConcept,
    LearningEvidenceEvent,
    LearningEvidenceProblemType,
    LearningEvidenceSourceKind,
)
from app.mastery.models import StudentConceptMastery
from app.practice.models import EvaluationStatus
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
from app.students.models import StudentProfile
from app.users.models import User
from tests.practice.conftest import (
    PracticeContent,
    practice_bearer,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)


def _create_question(
    session: Session,
    content: PracticeContent,
    concept: Concept,
    problem_type: ProblemType,
    *,
    text: str,
    correct_answer: str = "A",
    difficulty: float = 0.35,
    status: QuestionStatus = QuestionStatus.APPROVED,
) -> Question:
    teacher = session.query(User).filter_by(email="teacher@practice.local").first()
    q = Question(
        subject_id=content.subject.id,
        content=text,
        question_type=QuestionType.MULTIPLE_CHOICE,
        difficulty=difficulty,
        correct_answer=correct_answer,
        explanation="Detailed test explanation",
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
    q.concept_links = [QuestionConcept(concept_id=concept.id, weight=1.0)]
    q.problem_type_links = [
        QuestionProblemType(problem_type_id=problem_type.id, weight=1.0, is_primary=True)
    ]
    q.learning_outcome_links = [
        QuestionLearningOutcome(
            learning_outcome_id=content.learning_outcome.id, weight=1.0
        )
    ]
    session.add(q)
    session.flush()
    return q


def _create_diagnosis(
    session: Session,
    content: PracticeContent,
    student_id: UUID,
    *,
    diagnosis_type: RootCauseDiagnosisType = RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
    root_concept_id: UUID | None = None,
    target_problem_type_id: UUID | None = None,
    candidate_concept_id: UUID | None = None,
    candidate_problem_type_id: UUID | None = None,
) -> RootCauseDiagnosis:
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

    session.add(
        LearningEvidenceConcept(
            event_id=ev.id,
            concept_id=root_concept_id or content.concept.id,
            weight=1.0,
        )
    )
    session.add(
        LearningEvidenceProblemType(
            event_id=ev.id,
            problem_type_id=target_problem_type_id or content.problem_type.id,
            weight=1.0,
            is_primary=True,
        )
    )
    session.flush()

    diag = RootCauseDiagnosis(
        learning_evidence_event_id=ev.id,
        student_id=student_id,
        subject_id=content.subject.id,
        target_problem_type_id=target_problem_type_id or content.problem_type.id,
        diagnosis_type=diagnosis_type,
        status=RootCauseDiagnosisStatus.HYPOTHESIS,
        root_concept_id=root_concept_id or content.concept.id,
        confidence=0.75,
        supporting_evidence_count=2,
        reason_code="PREREQUISITE_LOW_MASTERY_REPEATED_ERRORS",
    )
    session.add(diag)
    session.flush()

    if diagnosis_type != RootCauseDiagnosisType.INSUFFICIENT_EVIDENCE:
        cand = RootCauseCandidate(
            diagnosis_id=diag.id,
            rank=1,
            candidate_type=diagnosis_type,
            concept_id=candidate_concept_id or root_concept_id or content.concept.id,
            problem_type_id=candidate_problem_type_id or target_problem_type_id or content.problem_type.id,
            score=0.85,
            confidence=0.80,
            mastery_deficit_signal=0.70,
            recent_error_signal=0.80,
            structural_signal=0.90,
            misconception_signal=0.0,
            evidence_volume_signal=0.5,
            supporting_event_count=2,
            conflicting_event_count=0,
            reason_codes=["PREREQUISITE_GAP_OBSERVED"],
        )
        session.add(cand)
        session.flush()

    session.commit()
    return diag


def test_verification_lifecycle_prerequisite_gap_supported(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    # 1. Prerequisite concept & 2 probe questions
    prereq_concept = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.CALC.PREREQ.01",
        name="Prerequisite Basic Derivative",
        description="Foundational derivative concept",
    )
    db_session.add(prereq_concept)
    db_session.flush()

    q1 = _create_question(
        db_session,
        practice_content,
        prereq_concept,
        practice_content.problem_type,
        text="Probe 1: What is derivative of x^2?",
        correct_answer="A",
        difficulty=0.35,
    )
    q2 = _create_question(
        db_session,
        practice_content,
        prereq_concept,
        practice_content.problem_type,
        text="Probe 2: What is derivative of 3x?",
        correct_answer="A",
        difficulty=0.35,
    )

    diag = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        diagnosis_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        root_concept_id=prereq_concept.id,
        candidate_concept_id=prereq_concept.id,
    )

    service = RootCauseVerificationService(db_session)

    # 2. Start verification
    res = service.start_verification(student_profile.id, diag.id)
    assert res.status == RootCauseVerificationStatus.ACTIVE
    assert res.required_probe_count == 2
    assert res.completed_probe_count == 0
    assert len(res.targets) == 1

    target = res.targets[0]
    assert target.target_type == RootCauseVerificationTargetType.CONCEPT
    assert target.target_concept_id == prereq_concept.id
    assert target.outcome == RootCauseVerificationOutcome.PENDING
    assert len(target.items) == 2

    # Verify no answer leakage before attempt!
    item1 = target.items[0]
    item2 = target.items[1]
    assert item1.explanation is None
    assert item1.student_answer is None
    assert item1.is_attempted is False

    # 3. Submit first probe answer (INCORRECT)
    ans1 = service.submit_verification_answer(
        student_profile.id,
        diag.id,
        item1.id,
        RootCauseVerificationAnswerSubmit(student_answer="B"),
    )
    assert ans1.is_correct is False
    assert ans1.score == 0.0
    assert ans1.explanation == "Detailed test explanation"
    # Even after 1 error, outcome MUST be INCONCLUSIVE (min 2 probes required!)
    assert ans1.target_outcome == RootCauseVerificationOutcome.INCONCLUSIVE
    assert ans1.verification_status == RootCauseVerificationStatus.ACTIVE

    # 4. Submit second probe answer (INCORRECT) -> average 0.0 <= 0.50 -> SUPPORTED
    ans2 = service.submit_verification_answer(
        student_profile.id,
        diag.id,
        item2.id,
        RootCauseVerificationAnswerSubmit(student_answer="B"),
    )
    assert ans2.is_correct is False
    assert ans2.target_outcome == RootCauseVerificationOutcome.SUPPORTED
    assert ans2.verification_status == RootCauseVerificationStatus.COMPLETED

    # 5. Check updated verification read
    final_ver = service.get_verification(student_profile.id, diag.id)
    assert final_ver.status == RootCauseVerificationStatus.COMPLETED
    assert final_ver.completed_probe_count == 2
    assert final_ver.targets[0].outcome == RootCauseVerificationOutcome.SUPPORTED
    assert final_ver.targets[0].average_score == 0.0
    assert final_ver.targets[0].correct_count == 0

    # 6. Verify evidence pipeline updated Mastery
    mastery = db_session.get(
        StudentConceptMastery, (student_profile.id, prereq_concept.id)
    )
    assert mastery is not None
    assert mastery.attempt_count >= 2


def test_verification_disproved_not_supported(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    prereq = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.CALC.DISPROVE.01",
        name="Candidate Concept To Disprove",
    )
    db_session.add(prereq)
    db_session.flush()

    q1 = _create_question(
        db_session,
        practice_content,
        prereq,
        practice_content.problem_type,
        text="Disprove Q1",
        correct_answer="A",
    )
    q2 = _create_question(
        db_session,
        practice_content,
        prereq,
        practice_content.problem_type,
        text="Disprove Q2",
        correct_answer="A",
    )

    diag = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        diagnosis_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        root_concept_id=prereq.id,
        candidate_concept_id=prereq.id,
    )

    service = RootCauseVerificationService(db_session)
    ver = service.start_verification(student_profile.id, diag.id)
    items = ver.targets[0].items

    # Student answers both correctly
    service.submit_verification_answer(
        student_profile.id, diag.id, items[0].id, RootCauseVerificationAnswerSubmit(student_answer="A")
    )
    ans2 = service.submit_verification_answer(
        student_profile.id, diag.id, items[1].id, RootCauseVerificationAnswerSubmit(student_answer="A")
    )

    assert ans2.is_correct is True
    assert ans2.target_outcome == RootCauseVerificationOutcome.NOT_SUPPORTED
    assert ans2.verification_status == RootCauseVerificationStatus.COMPLETED


def test_verification_idempotency_returns_same_frozen_session(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    c = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.IDEM.01",
        name="Idempotency Concept",
    )
    db_session.add(c)
    db_session.flush()

    _create_question(db_session, practice_content, c, practice_content.problem_type, text="Idem Q1")
    _create_question(db_session, practice_content, c, practice_content.problem_type, text="Idem Q2")

    diag = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=c.id,
        candidate_concept_id=c.id,
    )

    service = RootCauseVerificationService(db_session)
    first = service.start_verification(student_profile.id, diag.id)
    second = service.start_verification(student_profile.id, diag.id)

    assert first.id == second.id
    assert first.practice_session_id == second.practice_session_id
    assert [it.id for it in first.targets[0].items] == [it.id for it in second.targets[0].items]


def test_verification_prevents_duplicate_probe_attempt(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    c = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.DUP.01",
        name="Dup Attempt Concept",
    )
    db_session.add(c)
    db_session.flush()

    _create_question(db_session, practice_content, c, practice_content.problem_type, text="Dup Q1")
    _create_question(db_session, practice_content, c, practice_content.problem_type, text="Dup Q2")

    diag = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=c.id,
        candidate_concept_id=c.id,
    )

    service = RootCauseVerificationService(db_session)
    ver = service.start_verification(student_profile.id, diag.id)
    item_id = ver.targets[0].items[0].id

    service.submit_verification_answer(
        student_profile.id, diag.id, item_id, RootCauseVerificationAnswerSubmit(student_answer="A")
    )

    with pytest.raises(Exception) as exc_info:
        service.submit_verification_answer(
            student_profile.id, diag.id, item_id, RootCauseVerificationAnswerSubmit(student_answer="A")
        )
    assert getattr(exc_info.value, "code", None) == "ITEM_ALREADY_ATTEMPTED"


def test_verification_multi_factor_verifies_two_targets(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    c1 = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.MULTI.C1",
        name="Multi Concept 1",
    )
    pt2 = ProblemType(
        topic_id=practice_content.problem_type.topic_id,
        code="MATH.12.MULTI.PT2",
        name="Multi Problem Type 2",
        order_index=1,
        is_active=True,
    )
    db_session.add_all([c1, pt2])
    db_session.flush()

    _create_question(db_session, practice_content, c1, practice_content.problem_type, text="C1 Q1")
    _create_question(db_session, practice_content, c1, practice_content.problem_type, text="C1 Q2")
    _create_question(db_session, practice_content, practice_content.concept, pt2, text="PT2 Q1")
    _create_question(db_session, practice_content, practice_content.concept, pt2, text="PT2 Q2")

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
        diagnosis_type=RootCauseDiagnosisType.MULTI_FACTOR_GAP,
        status=RootCauseDiagnosisStatus.HYPOTHESIS,
        root_concept_id=practice_content.concept.id,
        confidence=0.70,
        supporting_evidence_count=2,
        reason_code="AMBIGUOUS_MULTIPLE_CAUSES",
    )
    db_session.add(diag)
    db_session.flush()

    cand1 = RootCauseCandidate(
        diagnosis_id=diag.id,
        rank=1,
        candidate_type=RootCauseDiagnosisType.DIRECT_CONCEPT_GAP,
        concept_id=c1.id,
        problem_type_id=None,
        score=0.80,
        confidence=0.75,
        mastery_deficit_signal=0.7,
        recent_error_signal=0.8,
        structural_signal=0.8,
        misconception_signal=0.0,
        evidence_volume_signal=0.5,
        supporting_event_count=2,
        conflicting_event_count=0,
        reason_codes=["FACTOR_1"],
    )
    cand2 = RootCauseCandidate(
        diagnosis_id=diag.id,
        rank=2,
        candidate_type=RootCauseDiagnosisType.PROBLEM_TYPE_PROCEDURE_GAP,
        concept_id=None,
        problem_type_id=pt2.id,
        score=0.75,
        confidence=0.70,
        mastery_deficit_signal=0.6,
        recent_error_signal=0.7,
        structural_signal=0.7,
        misconception_signal=0.0,
        evidence_volume_signal=0.5,
        supporting_event_count=2,
        conflicting_event_count=0,
        reason_codes=["FACTOR_2"],
    )
    db_session.add_all([cand1, cand2])
    db_session.commit()

    service = RootCauseVerificationService(db_session)
    ver = service.start_verification(student_profile.id, diag.id)

    assert len(ver.targets) == 2
    assert ver.targets[0].target_type == RootCauseVerificationTargetType.CONCEPT
    assert ver.targets[0].target_concept_id == c1.id
    assert ver.targets[1].target_type == RootCauseVerificationTargetType.PROBLEM_TYPE
    assert ver.targets[1].target_problem_type_id == pt2.id
    assert ver.required_probe_count == 4


def test_verification_zero_questions_marks_unavailable(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    empty_concept = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.EMPTY.01",
        name="Empty Question Concept",
    )
    db_session.add(empty_concept)
    db_session.flush()

    diag = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        root_concept_id=empty_concept.id,
        candidate_concept_id=empty_concept.id,
    )

    service = RootCauseVerificationService(db_session)
    ver = service.start_verification(student_profile.id, diag.id)

    assert ver.status == RootCauseVerificationStatus.UNAVAILABLE
    assert ver.required_probe_count == 0
    assert ver.targets[0].outcome == RootCauseVerificationOutcome.UNAVAILABLE


def test_verification_insufficient_evidence_cannot_be_verified(
    db_session: Session,
    practice_content: PracticeContent,
    student_profile: StudentProfile,
) -> None:
    diag = _create_diagnosis(
        db_session,
        practice_content,
        student_profile.id,
        diagnosis_type=RootCauseDiagnosisType.INSUFFICIENT_EVIDENCE,
    )

    service = RootCauseVerificationService(db_session)
    with pytest.raises(Exception) as exc:
        service.start_verification(student_profile.id, diag.id)
    assert getattr(exc.value, "code", None) == "CANNOT_VERIFY_INSUFFICIENT_EVIDENCE"


def test_verification_endpoints_via_api(
    db_client: TestClient,
    db_session: Session,
    practice_content: PracticeContent,
    practice_students: tuple[User, User],
    practice_bearer,
) -> None:
    student_user = practice_students[0]
    profile = db_session.query(StudentProfile).filter_by(user_id=student_user.id).one()

    prereq = Concept(
        subject_id=practice_content.subject.id,
        code="MATH.12.API.01",
        name="API Verified Concept",
    )
    db_session.add(prereq)
    db_session.flush()

    _create_question(db_session, practice_content, prereq, practice_content.problem_type, text="API Q1")
    _create_question(db_session, practice_content, prereq, practice_content.problem_type, text="API Q2")
    _create_question(db_session, practice_content, prereq, practice_content.problem_type, text="API Repair Q3", difficulty=0.40)

    diag = _create_diagnosis(
        db_session,
        practice_content,
        profile.id,
        root_concept_id=prereq.id,
        candidate_concept_id=prereq.id,
    )

    headers = practice_bearer(student_user)

    # 1. Start verification via POST
    start_resp = db_client.post(
        f"/students/me/diagnostics/{diag.id}/verification",
        headers=headers,
    )
    assert start_resp.status_code == 200, start_resp.json()
    data = start_resp.json()
    assert data["status"] == "ACTIVE"
    assert data["required_probe_count"] == 2
    items = data["targets"][0]["items"]
    assert len(items) == 2

    # 2. Get verification via GET
    get_resp = db_client.get(
        f"/students/me/diagnostics/{diag.id}/verification",
        headers=headers,
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == data["id"]

    # 3. Check next-action while in progress -> VERIFY_ROOT_CAUSE
    action_resp1 = db_client.get(
        f"/students/me/diagnostics/{diag.id}/next-action",
        headers=headers,
    )
    assert action_resp1.status_code == 200
    assert action_resp1.json()["action"] == NextDiagnosticActionType.VERIFY_ROOT_CAUSE

    # 4. Answer probe items (both fail -> SUPPORTED)
    db_client.post(
        f"/students/me/diagnostics/{diag.id}/verification/items/{items[0]['id']}/answer",
        json={"student_answer": "B"},
        headers=headers,
    )
    ans2_resp = db_client.post(
        f"/students/me/diagnostics/{diag.id}/verification/items/{items[1]['id']}/answer",
        json={"student_answer": "B"},
        headers=headers,
    )
    assert ans2_resp.status_code == 200
    assert ans2_resp.json()["target_outcome"] == "SUPPORTED"
    assert ans2_resp.json()["verification_status"] == "COMPLETED"

    # 5. Check next-action after SUPPORTED -> PRACTICE_REPAIR
    action_resp2 = db_client.get(
        f"/students/me/diagnostics/{diag.id}/next-action",
        headers=headers,
    )
    assert action_resp2.status_code == 200
    action_data = action_resp2.json()
    assert action_data["action"] == NextDiagnosticActionType.PRACTICE_REPAIR
    assert action_data["verified_target"] is not None
    assert action_data["verified_target"]["target_concept_id"] == str(prereq.id)
    assert action_data["verified_target"]["outcome"] == "SUPPORTED"
