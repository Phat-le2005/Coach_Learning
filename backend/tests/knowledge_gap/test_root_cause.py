from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.concepts.graph_service import ConceptGraphService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.knowledge_gap.models import (
    RootCauseCandidate,
    RootCauseDiagnosis,
    RootCauseDiagnosisStatus,
    RootCauseDiagnosisType,
)
from app.knowledge_gap.root_cause import (
    AdvisorySignal,
    RootCauseDiagnosticService,
    RootCauseScoringPolicy,
)
from app.learning_evidence.models import (
    LearningEvidenceConcept,
    LearningEvidenceEvent,
    LearningEvidenceProblemType,
    LearningEvidenceSourceKind,
)
from app.learning_evidence.publisher import LearningEvidencePayload, LearningEvidencePublisher
from app.mastery.evidence import WeightedConceptEvidence, WeightedProblemTypeEvidence
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.practice.models import (
    EvaluationStatus,
    PracticeSession,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from tests.practice.conftest import (
    PracticeContent,
    practice_content,
    practice_bearer,
    practice_students,
    practice_user_factory,
    student_profile,
)


def _mastery(
    session: Session,
    student_id: UUID,
    target_id: UUID,
    *,
    concept: bool,
    score: float,
    confidence: float = 0.8,
    attempts: int = 5,
) -> None:
    now = datetime.now(timezone.utc)
    model = StudentConceptMastery if concept else StudentProblemTypeMastery
    key = "concept_id" if concept else "problem_type_id"
    session.merge(
        model(
            student_id=student_id,
            **{key: target_id},
            mastery_score=score,
            confidence=confidence,
            attempt_count=attempts,
            correct_count=min(attempts, round(attempts * score)),
            last_practiced_at=now,
        )
    )
    session.flush()


def _history(
    session: Session,
    content: PracticeContent,
    student_id: UUID,
    *,
    concept_id: UUID | None = None,
    problem_type_id: UUID | None = None,
    wrong: bool,
    offset: int,
) -> LearningEvidenceEvent:
    event = LearningEvidenceEvent(
        student_id=student_id,
        subject_id=content.subject.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION,
        source_entity_id=uuid4(),
        is_correct=not wrong,
        score=0.0 if wrong else 1.0,
        difficulty=0.5,
        hint_count=0,
        evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=datetime.now(timezone.utc) - timedelta(minutes=offset),
    )
    session.add(event)
    session.flush()
    if concept_id:
        session.add(
            LearningEvidenceConcept(event_id=event.id, concept_id=concept_id, weight=1.0)
        )
    if problem_type_id:
        session.add(
            LearningEvidenceProblemType(
                event_id=event.id,
                problem_type_id=problem_type_id,
                weight=1.0,
                is_primary=True,
            )
        )
    session.flush()
    return event


def _publish_practice(
    session: Session,
    content: PracticeContent,
    student: StudentProfile,
    *,
    is_correct: bool | None = False,
    score: float | None = 0.0,
    status: EvaluationStatus = EvaluationStatus.AUTO_EVALUATED,
    concept_ids: tuple[UUID, ...] | None = None,
    student_answer: str = "A",
) -> tuple[LearningEvidenceEvent, RootCauseDiagnosis | None]:
    practice_session = PracticeSession(
        student_id=student.id,
        subject_id=content.subject.id,
        session_type=PracticeSessionType.PRACTICE,
        status=PracticeSessionStatus.ACTIVE,
    )
    session.add(practice_session)
    session.flush()
    attempt = QuestionAttempt(
        practice_session_id=practice_session.id,
        student_id=student.id,
        question_id=content.mcq.id,
        student_answer=student_answer,
        is_correct=is_correct,
        score=score,
        attempt_number=1,
        evaluation_status=status,
    )
    session.add(attempt)
    session.flush()
    concepts = concept_ids or (content.concept.id,)
    event = LearningEvidencePublisher().publish(
        LearningEvidencePayload(
            student_id=student.id,
            subject_id=content.subject.id,
            source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION,
            source_entity_id=attempt.id,
            is_correct=is_correct,
            score=score,
            difficulty=0.5,
            response_time_seconds=None,
            hint_count=0,
            evaluation_status=status,
            occurred_at=datetime.now(timezone.utc),
            concepts=tuple(
                WeightedConceptEvidence(concept_id, 1.0 / len(concepts))
                for concept_id in concepts
            ),
            problem_types=(
                WeightedProblemTypeEvidence(content.problem_type.id, 1.0, True),
            ),
        ),
        session,
    )
    session.flush()
    diagnosis = session.scalar(
        select(RootCauseDiagnosis).where(
            RootCauseDiagnosis.learning_evidence_event_id == event.id
        )
    )
    return event, diagnosis


def _prerequisite(
    session: Session, content: PracticeContent, code: str = "RC-PREREQ"
) -> Concept:
    concept = Concept(
        subject_id=content.subject.id,
        code=code,
        name=code,
        grade_level=12,
        order_index=10,
    )
    session.add(concept)
    session.flush()
    session.add(
        ConceptRelation(
            source_concept_id=concept.id,
            target_concept_id=content.concept.id,
            relation_type=RelationType.PREREQUISITE,
        )
    )
    session.flush()
    return concept


def test_single_wrong_is_low_confidence_and_idempotent(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    event, diagnosis = _publish_practice(db_session, practice_content, student_profile)
    assert diagnosis is not None
    assert diagnosis.diagnosis_type == RootCauseDiagnosisType.INSUFFICIENT_EVIDENCE
    assert diagnosis.status == RootCauseDiagnosisStatus.INSUFFICIENT_EVIDENCE
    assert diagnosis.confidence <= 0.35
    mastery_before = db_session.get(
        StudentConceptMastery, (student_profile.id, practice_content.concept.id)
    ).attempt_count
    before = db_session.scalar(select(func.count()).select_from(RootCauseCandidate))
    same = RootCauseDiagnosticService(db_session).diagnose_event(event.id)
    assert same is not None and same.id == diagnosis.id
    assert db_session.scalar(select(func.count()).select_from(RootCauseDiagnosis)) == 1
    assert db_session.scalar(select(func.count()).select_from(RootCauseCandidate)) == before
    assert db_session.get(
        StudentConceptMastery, (student_profile.id, practice_content.concept.id)
    ).attempt_count == mastery_before


def test_correct_and_pending_evidence_do_not_create_diagnosis(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    _publish_practice(
        db_session, practice_content, student_profile, is_correct=True, score=1.0
    )
    _publish_practice(
        db_session,
        practice_content,
        student_profile,
        is_correct=None,
        score=None,
        status=EvaluationStatus.NEEDS_TEACHER_REVIEW,
    )
    assert db_session.scalar(select(func.count()).select_from(RootCauseDiagnosis)) == 0


def test_direct_concept_gap_uses_repeated_history(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    for offset in range(1, 4):
        _history(
            db_session,
            practice_content,
            student_profile.id,
            concept_id=practice_content.concept.id,
            wrong=True,
            offset=offset,
        )
    _mastery(
        db_session,
        student_profile.id,
        practice_content.concept.id,
        concept=True,
        score=0.2,
    )
    _, diagnosis = _publish_practice(db_session, practice_content, student_profile)
    assert diagnosis is not None
    assert diagnosis.diagnosis_type == RootCauseDiagnosisType.DIRECT_CONCEPT_GAP
    assert diagnosis.root_concept_id == practice_content.concept.id
    assert diagnosis.candidates[0].mastery_deficit_signal > 0
    assert diagnosis.candidates[0].recent_error_signal > 0


def test_prerequisite_gap_requires_direct_evidence(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    prerequisite = _prerequisite(db_session, practice_content)
    _mastery(
        db_session,
        student_profile.id,
        practice_content.concept.id,
        concept=True,
        score=0.85,
    )
    _mastery(
        db_session,
        student_profile.id,
        prerequisite.id,
        concept=True,
        score=0.2,
    )
    for offset in range(1, 5):
        _history(
            db_session,
            practice_content,
            student_profile.id,
            concept_id=prerequisite.id,
            wrong=True,
            offset=offset,
        )
    _, diagnosis = _publish_practice(db_session, practice_content, student_profile)
    assert diagnosis is not None
    assert diagnosis.diagnosis_type == RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP
    assert diagnosis.root_concept_id == prerequisite.id


def test_unknown_prerequisite_is_not_treated_as_zero_mastery(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    prerequisite = _prerequisite(db_session, practice_content)
    _, diagnosis = _publish_practice(db_session, practice_content, student_profile)
    assert diagnosis is not None
    candidate = next(
        row for row in diagnosis.candidates if row.concept_id == prerequisite.id
    )
    assert candidate.mastery_deficit_signal == 0
    assert diagnosis.diagnosis_type == RootCauseDiagnosisType.INSUFFICIENT_EVIDENCE


def test_problem_type_procedure_gap_with_strong_components(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    prerequisite = _prerequisite(db_session, practice_content)
    for concept_id in (practice_content.concept.id, prerequisite.id):
        _mastery(
            db_session,
            student_profile.id,
            concept_id,
            concept=True,
            score=0.85,
        )
    _mastery(
        db_session,
        student_profile.id,
        practice_content.problem_type.id,
        concept=False,
        score=0.2,
    )
    for offset in range(1, 5):
        _history(
            db_session,
            practice_content,
            student_profile.id,
            problem_type_id=practice_content.problem_type.id,
            wrong=True,
            offset=offset,
        )
    _, diagnosis = _publish_practice(db_session, practice_content, student_profile)
    assert diagnosis is not None
    assert diagnosis.diagnosis_type == RootCauseDiagnosisType.PROBLEM_TYPE_PROCEDURE_GAP


def test_close_supported_candidates_produce_multi_factor(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    second = Concept(
        subject_id=practice_content.subject.id,
        code="RC-SECOND",
        name="Second direct concept",
        grade_level=12,
        order_index=11,
    )
    db_session.add(second)
    db_session.flush()
    for concept_id in (practice_content.concept.id, second.id):
        _mastery(
            db_session, student_profile.id, concept_id, concept=True, score=0.3
        )
        for offset in range(1, 4):
            _history(
                db_session,
                practice_content,
                student_profile.id,
                concept_id=concept_id,
                wrong=True,
                offset=offset,
            )
    _, diagnosis = _publish_practice(
        db_session,
        practice_content,
        student_profile,
        concept_ids=(practice_content.concept.id, second.id),
    )
    assert diagnosis is not None
    assert diagnosis.diagnosis_type == RootCauseDiagnosisType.MULTI_FACTOR_GAP


def test_repeated_scoped_misconception_is_hypothesis_only(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    definition = MisconceptionDefinition(
        code="RC-SIGN-CONFUSION",
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        name="Sign confusion",
        description="Repeated sign-direction confusion.",
        category=MisconceptionCategory.CONCEPTUAL,
        is_active=True,
    )
    db_session.add(definition)
    db_session.flush()
    now = datetime.now(timezone.utc)
    db_session.add(
        StudentMisconception(
            student_id=student_profile.id,
            misconception_definition_id=definition.id,
            confidence=0.9,
            occurrence_count=3,
            status=StudentMisconceptionStatus.CONFIRMED,
            first_detected_at=now,
            last_detected_at=now,
        )
    )
    db_session.flush()
    _, diagnosis = _publish_practice(db_session, practice_content, student_profile)
    assert diagnosis is not None
    assert diagnosis.diagnosis_type == RootCauseDiagnosisType.MISCONCEPTION_HYPOTHESIS
    assert diagnosis.status in {
        RootCauseDiagnosisStatus.HYPOTHESIS,
        RootCauseDiagnosisStatus.STRONG_HYPOTHESIS,
    }
    assert diagnosis.misconception_definition_id == definition.id


def test_conflicting_correct_evidence_reduces_confidence(
    db_session: Session,
    student_profile: StudentProfile,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
) -> None:
    other = db_session.scalar(
        select(StudentProfile).where(StudentProfile.user_id == practice_students[1].id)
    )
    for learner in (student_profile, other):
        _mastery(
            db_session,
            learner.id,
            practice_content.concept.id,
            concept=True,
            score=0.2,
        )
    for offset in range(1, 5):
        _history(
            db_session,
            practice_content,
            student_profile.id,
            concept_id=practice_content.concept.id,
            wrong=True,
            offset=offset,
        )
        _history(
            db_session,
            practice_content,
            other.id,
            concept_id=practice_content.concept.id,
            wrong=offset <= 2,
            offset=offset,
        )
    _, consistent = _publish_practice(db_session, practice_content, student_profile)
    _, conflicting = _publish_practice(db_session, practice_content, other)
    assert consistent is not None and conflicting is not None
    assert consistent.confidence > conflicting.confidence


def test_advisor_failure_and_invalid_taxonomy_cannot_change_result(
    db_session: Session,
    student_profile: StudentProfile,
    practice_content: PracticeContent,
) -> None:
    definition = MisconceptionDefinition(
        code="RC-ADVISORY-SCOPE",
        concept_id=practice_content.concept.id,
        problem_type_id=practice_content.problem_type.id,
        name="Advisory scope",
        description="Scoped definition for advisory boundary tests.",
        category=MisconceptionCategory.OTHER,
        is_active=True,
    )
    db_session.add(definition)
    db_session.flush()
    # Build the trigger without the publisher so custom advisors can process it.
    event, auto = _publish_practice(
        db_session,
        practice_content,
        student_profile,
        student_answer="Em trình bày nhiều bước suy luận nhưng chưa xác định được bước sai.",
    )
    assert auto is not None
    db_session.delete(auto)
    db_session.flush()

    class FailingAdvisor:
        called = False

        def advise(self, *args, **kwargs):
            self.called = True
            raise RuntimeError("provider timeout")

    failing_advisor = FailingAdvisor()
    deterministic = RootCauseDiagnosticService(
        db_session, advisor=failing_advisor
    ).diagnose_event(event.id)
    assert deterministic is not None
    assert failing_advisor.called
    assert deterministic.diagnosis_type == RootCauseDiagnosisType.INSUFFICIENT_EVIDENCE

    # A second event receives an invented concept; it is ignored, not persisted.
    event2, auto2 = _publish_practice(
        db_session,
        practice_content,
        student_profile,
        student_answer="Em tiếp tục trình bày các bước nhưng vẫn chưa tìm được lỗi.",
    )
    assert auto2 is not None
    db_session.delete(auto2)
    db_session.flush()

    invalid_concept_id = uuid4()

    class InvalidAdvisor:
        called = False

        def advise(self, *args, **kwargs):
            self.called = True
            return AdvisorySignal(concept_id=invalid_concept_id, observations=("invented",))

    class AdvisoryTestPolicy(RootCauseScoringPolicy):
        AMBIGUITY_MARGIN = 1.0

    invalid_advisor = InvalidAdvisor()
    result = RootCauseDiagnosticService(
        db_session, advisor=invalid_advisor, policy=AdvisoryTestPolicy
    ).diagnose_event(event2.id)
    assert result is not None
    assert invalid_advisor.called
    assert all(row.concept_id != invalid_concept_id for row in result.candidates)
    assert all("SCOPED_ADVISORY_SUPPORT" not in row.reason_codes for row in result.candidates)


def test_bounded_prerequisite_graph_is_shortest_cycle_safe_and_subject_scoped(
    db_session: Session, practice_content: PracticeContent
) -> None:
    c1 = _prerequisite(db_session, practice_content, "RC-D1")
    c2 = Concept(
        subject_id=practice_content.subject.id,
        code="RC-D2",
        name="D2",
        grade_level=12,
        order_index=12,
    )
    c3 = Concept(
        subject_id=practice_content.subject.id,
        code="RC-D3",
        name="D3",
        grade_level=12,
        order_index=13,
    )
    c4 = Concept(
        subject_id=practice_content.subject.id,
        code="RC-D4",
        name="D4",
        grade_level=12,
        order_index=14,
    )
    db_session.add_all([c2, c3, c4])
    db_session.flush()
    other_subject = Subject(code="RC-OTHER-SUBJECT", name="Other", grade_level=12)
    db_session.add(other_subject)
    db_session.flush()
    cross_subject = Concept(
        subject_id=other_subject.id,
        code="RC-CROSS-SUBJECT",
        name="Cross subject",
        grade_level=12,
        order_index=0,
    )
    db_session.add(cross_subject)
    db_session.flush()
    db_session.add_all(
        [
            ConceptRelation(source_concept_id=c2.id, target_concept_id=c1.id, relation_type=RelationType.PREREQUISITE),
            ConceptRelation(source_concept_id=c3.id, target_concept_id=c2.id, relation_type=RelationType.PREREQUISITE),
            ConceptRelation(source_concept_id=c4.id, target_concept_id=c3.id, relation_type=RelationType.PREREQUISITE),
            # Malformed cycle and a shorter path must not loop or overwrite shortest distance.
            ConceptRelation(source_concept_id=c1.id, target_concept_id=c3.id, relation_type=RelationType.PREREQUISITE),
            ConceptRelation(source_concept_id=c3.id, target_concept_id=practice_content.concept.id, relation_type=RelationType.PREREQUISITE),
            ConceptRelation(source_concept_id=cross_subject.id, target_concept_id=practice_content.concept.id, relation_type=RelationType.PREREQUISITE),
        ]
    )
    db_session.flush()
    first = ConceptGraphService(db_session).get_prerequisite_distances(
        {practice_content.concept.id}, practice_content.subject.id, max_depth=3
    )
    second = ConceptGraphService(db_session).get_prerequisite_distances(
        {practice_content.concept.id}, practice_content.subject.id, max_depth=3
    )
    assert first == second
    assert first[c1.id] == 1
    assert first[c3.id] == 1
    assert first[c2.id] == 2
    assert first[c4.id] == 2
    assert cross_subject.id not in first
    assert max(first.values()) <= 3


def test_diagnostic_api_student_and_teacher_authorization(
    db_session: Session,
    db_client: TestClient,
    student_profile: StudentProfile,
    practice_students: tuple[User, User],
    practice_content: PracticeContent,
    practice_bearer,
    practice_user_factory,
) -> None:
    _, diagnosis = _publish_practice(db_session, practice_content, student_profile)
    assert diagnosis is not None
    teacher_user = db_session.get(User, practice_content.mcq.created_by)
    teacher = db_session.scalar(
        select(TeacherProfile).where(TeacherProfile.user_id == teacher_user.id)
    )
    classroom = Classroom(
        name="Root-cause access",
        academic_year="2026-2027",
        grade_level=12,
        created_by=teacher_user.id,
    )
    db_session.add(classroom)
    db_session.flush()
    db_session.add_all(
        [
            TeacherClassroom(
                teacher_id=teacher.id, classroom_id=classroom.id, role="OWNER"
            ),
            StudentEnrollment(
                student_id=student_profile.id,
                classroom_id=classroom.id,
                status=EnrollmentStatus.ACTIVE,
            ),
        ]
    )
    outsider_teacher_user = practice_user_factory(
        Role.TEACHER, "root-cause-outsider-teacher@example.com"
    )
    db_session.commit()

    student_headers = practice_bearer(practice_students[0])
    outsider_student_headers = practice_bearer(practice_students[1])
    teacher_headers = practice_bearer(teacher_user)
    outsider_teacher_headers = practice_bearer(outsider_teacher_user)
    recent = db_client.get(
        "/students/me/diagnostics/recent", headers=student_headers
    )
    assert recent.status_code == 200
    assert recent.json()[0]["id"] == str(diagnosis.id)
    assert recent.json()[0]["explanation"]
    assert db_client.get(
        f"/students/me/diagnostics/{diagnosis.id}", headers=outsider_student_headers
    ).status_code == 404
    teacher_result = db_client.get(
        f"/teacher/students/{student_profile.id}/diagnostics",
        headers=teacher_headers,
    )
    assert teacher_result.status_code == 200
    assert teacher_result.json()[0]["id"] == str(diagnosis.id)
    assert db_client.get(
        f"/teacher/students/{student_profile.id}/diagnostics",
        headers=outsider_teacher_headers,
    ).status_code == 403
