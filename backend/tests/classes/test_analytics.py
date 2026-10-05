from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment,
    AssignmentConcept,
    AssignmentProblemType,
    AssignmentStatus,
    AssignmentType,
    StudentAssignment,
    StudentAssignmentStatus,
)
from app.classes.analytics_schemas import (
    AlertRuleCode,
    AlertSeverity,
    ClassroomAlertsRead,
    ClassroomAnalyticsDashboardRead,
    ClassroomHeatmapRead,
    HeatmapView,
    MasteryLevel,
)
from app.classes.analytics_service import ClassAnalyticsService
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.curriculum.models import Chapter, ProblemType, Topic
from app.knowledge_gap.models import (
    RootCauseDiagnosis,
    RootCauseDiagnosisStatus,
    RootCauseDiagnosisType,
    RootCauseVerification,
    RootCauseVerificationOutcome,
    RootCauseVerificationStatus,
    RootCauseVerificationTarget,
    RootCauseVerificationTargetType,
)
from app.learning_evidence.models import (
    LearningEvidenceConcept,
    LearningEvidenceEvent,
    LearningEvidenceProblemType,
    LearningEvidenceSourceKind,
)
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.misconceptions.models import (
    MisconceptionCategory,
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.planning.models import TeachingPlan, TeachingPlanItem, TeachingPlanStatus
from app.planning.study_models import StudyPlan, StudyPlanStatus, StudyTask, StudyTaskStatus, StudyTaskType
from app.practice.models import EvaluationStatus, PracticeSession, PracticeSessionType, QuestionAttempt
from app.questions.models import Question, QuestionStatus, QuestionType
from app.repair.models import AdaptiveRepairOutcome, AdaptiveRepairPhase, AdaptiveRepairSession, AdaptiveRepairStatus
from app.review.models import ReviewSchedule
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.users.models import Role, User
from tests.classes.conftest import (
    classroom_bearer,
    classroom_user_factory,
    student_profile,
    teacher_profile,
)


def _setup_curriculum(session: Session, prefix: str = "ANA") -> tuple[Subject, Chapter, Topic, ProblemType, Concept]:
    subject = Subject(code=f"{prefix}-SUB", name=f"{prefix} Toán 12", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{prefix}-CHP", name="Chương 1: Khảo sát hàm số", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{prefix}-TOP", name="Chủ đề: Tính đơn điệu", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT-MONO",
        name="Tìm tham số về tính đơn điệu",
        order_index=0,
        is_active=True,
    )
    concept = Concept(
        subject_id=subject.id,
        code=f"{prefix}-CON-INEQ",
        name="Giải bất phương trình",
        order_index=0,
    )
    session.add_all([pt, concept])
    session.flush()
    return subject, chapter, topic, pt, concept


# --------------------------------------------------------------------------
# 1. Authorization: Teacher isolation
# --------------------------------------------------------------------------


def test_teacher_authorization_only_allows_own_classroom(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
) -> None:
    t1_user = classroom_user_factory(Role.TEACHER, "owner_t1@example.com")
    t2_user = classroom_user_factory(Role.TEACHER, "other_t2@example.com")
    t1_prof = teacher_profile(t1_user)
    t2_prof = teacher_profile(t2_user)

    classroom = Classroom(name="12A1 T1", academic_year="2026-2027", grade_level=12, created_by=t1_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t1_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.commit()

    t2_headers = classroom_bearer(t2_user)
    # Analytics
    assert db_client.get(f"/teacher/classes/{classroom.id}/analytics", headers=t2_headers).status_code == 403
    # Heatmap
    assert db_client.get(f"/teacher/classes/{classroom.id}/heatmap", headers=t2_headers).status_code == 403
    # Alerts
    assert db_client.get(f"/teacher/classes/{classroom.id}/alerts", headers=t2_headers).status_code == 403
    # Student drilldown
    assert db_client.get(f"/teacher/classes/{classroom.id}/students/{uuid4()}/analytics", headers=t2_headers).status_code == 403
    # Assignment analytics
    assert db_client.get(f"/teacher/classes/{classroom.id}/assignments/{uuid4()}/analytics", headers=t2_headers).status_code == 403

    # T1 owner accesses own classroom analytics -> 200
    t1_headers = classroom_bearer(t1_user)
    res_ok = db_client.get(f"/teacher/classes/{classroom.id}/analytics", headers=t1_headers)
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert data["classroom_id"] == str(classroom.id)
    assert data["student_count"] == 0


# --------------------------------------------------------------------------
# 2. Dashboard Deterministic Metrics
# --------------------------------------------------------------------------


def test_classroom_dashboard_deterministic_metrics(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_dash@example.com")
    s1_user = classroom_user_factory(Role.STUDENT, "s1_dash@example.com")
    s2_user = classroom_user_factory(Role.STUDENT, "s2_dash@example.com")
    t_prof = teacher_profile(t_user)
    s1_prof = student_profile(s1_user)
    s2_prof = student_profile(s2_user)

    subject, chapter, topic, pt, concept = _setup_curriculum(db_session, "DSH")

    pt_strong = ProblemType(
        topic_id=topic.id,
        code="DSH-PT-EASY",
        name="Xét tính đơn điệu hàm đa thức",
        order_index=1,
        is_active=True,
    )
    db_session.add(pt_strong)
    db_session.flush()

    classroom = Classroom(name="12A3 Dashboard", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add_all([
        StudentEnrollment(student_id=s1_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
        StudentEnrollment(student_id=s2_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
    ])

    now = datetime.now(timezone.utc)

    db_session.add_all([
        StudentProblemTypeMastery(
            student_id=s1_prof.id, problem_type_id=pt.id, mastery_score=0.30, confidence=0.8,
            attempt_count=5, correct_count=1, last_practiced_at=now,
        ),
        StudentProblemTypeMastery(
            student_id=s2_prof.id, problem_type_id=pt.id, mastery_score=0.40, confidence=0.8,
            attempt_count=4, correct_count=1, last_practiced_at=now,
        ),
        StudentProblemTypeMastery(
            student_id=s1_prof.id, problem_type_id=pt_strong.id, mastery_score=0.80, confidence=0.9,
            attempt_count=6, correct_count=5, last_practiced_at=now,
        ),
        StudentProblemTypeMastery(
            student_id=s2_prof.id, problem_type_id=pt_strong.id, mastery_score=0.90, confidence=0.9,
            attempt_count=6, correct_count=6, last_practiced_at=now,
        ),
    ])

    m_def = MisconceptionDefinition(
        code="DSH_MISC_01",
        concept_id=concept.id,
        problem_type_id=pt.id,
        name="Quên đổi chiều bất phương trình",
        description="Quên đổi chiều khi chia số âm.",
        category=MisconceptionCategory.CONCEPTUAL,
        is_active=True,
    )
    db_session.add(m_def)
    db_session.flush()

    db_session.add_all([
        StudentMisconception(
            student_id=s1_prof.id, misconception_definition_id=m_def.id, confidence=0.85,
            occurrence_count=2, status=StudentMisconceptionStatus.CONFIRMED, first_detected_at=now, last_detected_at=now,
        ),
        StudentMisconception(
            student_id=s2_prof.id, misconception_definition_id=m_def.id, confidence=0.75,
            occurrence_count=1, status=StudentMisconceptionStatus.SUSPECTED, first_detected_at=now, last_detected_at=now,
        ),
    ])

    plan = StudyPlan(student_id=s1_prof.id, start_date=date.today(), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()
    db_session.add_all([
        StudyTask(study_plan_id=plan.id, task_type=StudyTaskType.PRACTICE, status=StudyTaskStatus.COMPLETED, planned_date=date.today(), estimated_duration_minutes=20, priority=10, reason_code="TEST"),
        StudyTask(study_plan_id=plan.id, task_type=StudyTaskType.PRACTICE, status=StudyTaskStatus.COMPLETED, planned_date=date.today(), estimated_duration_minutes=20, priority=10, reason_code="TEST"),
        StudyTask(study_plan_id=plan.id, task_type=StudyTaskType.PRACTICE, status=StudyTaskStatus.PENDING, planned_date=date.today(), estimated_duration_minutes=20, priority=10, reason_code="TEST"),
    ])

    db_session.commit()

    headers = classroom_bearer(t_user)
    res = db_client.get(f"/teacher/classes/{classroom.id}/analytics", headers=headers)
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["student_count"] == 2
    assert len(data["strong_problem_types"]) >= 1
    assert data["strong_problem_types"][0]["name"] == pt_strong.name
    assert data["strong_problem_types"][0]["average_score"] == 0.85
    assert len(data["weak_problem_types"]) >= 1
    assert data["weak_problem_types"][0]["name"] == pt.name
    assert data["weak_problem_types"][0]["average_score"] == 0.35
    assert len(data["common_misconceptions"]) >= 1
    assert data["common_misconceptions"][0]["code"] == "DSH_MISC_01"
    assert data["study_completion"]["assigned_tasks_count"] == 3
    assert data["study_completion"]["completed_tasks_count"] == 2
    assert data["study_completion"]["completion_rate"] == 66.7


# --------------------------------------------------------------------------
# 3. Learning Evidence Trends (Sections 64, 65, 66, 82)
# --------------------------------------------------------------------------


def test_learning_evidence_trend_across_sources_and_unscored(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_ev_trend@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_ev_trend@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, _ = _setup_curriculum(db_session, "EVT")

    classroom = Classroom(name="Class EV Trend", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    now = datetime.now(timezone.utc)

    # 1. PRACTICE_QUESTION (evaluated, score 1.0)
    ev1 = LearningEvidenceEvent(
        student_id=s_prof.id, subject_id=subject.id, classroom_id=classroom.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION, source_entity_id=uuid4(),
        is_correct=True, score=1.0, evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=now - timedelta(days=2),
    )
    # 2. ASSIGNMENT_CANONICAL_QUESTION (evaluated, score 0.8)
    ev2 = LearningEvidenceEvent(
        student_id=s_prof.id, subject_id=subject.id, classroom_id=classroom.id,
        source_kind=LearningEvidenceSourceKind.ASSIGNMENT_CANONICAL_QUESTION, source_entity_id=uuid4(),
        is_correct=True, score=0.8, evaluation_status=EvaluationStatus.EVALUATED,
        occurred_at=now - timedelta(days=1),
    )
    # 3. TEACHER_MATERIAL_ITEM (unscored / NEEDS_TEACHER_REVIEW)
    ev3 = LearningEvidenceEvent(
        student_id=s_prof.id, subject_id=subject.id, classroom_id=classroom.id,
        source_kind=LearningEvidenceSourceKind.TEACHER_MATERIAL_ITEM, source_entity_id=uuid4(),
        is_correct=None, score=None, evaluation_status=EvaluationStatus.NEEDS_TEACHER_REVIEW,
        occurred_at=now - timedelta(hours=5),
    )
    db_session.add_all([ev1, ev2, ev3])
    db_session.commit()

    service = ClassAnalyticsService(db_session)
    dashboard = service.get_classroom_dashboard(t_user.id, classroom.id)

    # All 3 count toward activity
    assert dashboard.recent_trends.total_evidence_past_7_days == 3
    assert dashboard.evidence_sources.practice_count == 1
    assert dashboard.evidence_sources.assignment_question_count == 1
    assert dashboard.evidence_sources.teacher_material_count == 1
    assert dashboard.evidence_sources.total_count == 3

    # Only scored records count toward average_score: (1.0 + 0.8) / 2 = 0.90
    assert dashboard.recent_trends.scored_evidence_past_7_days == 2
    assert dashboard.recent_trends.recent_average_score == 0.90
    assert dashboard.evidence_summary.needs_teacher_review_count == 1
    assert dashboard.evidence_summary.total_events == 3
    assert dashboard.evidence_summary.scored_events == 2


def test_question_attempt_alone_does_not_affect_evidence_metrics(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_no_qa@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_no_qa@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, _, _ = _setup_curriculum(db_session, "NQA")

    classroom = Classroom(name="Class No QA", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Add QuestionAttempt without LearningEvidenceEvent
    ps = PracticeSession(student_id=s_prof.id, subject_id=subject.id, session_type=PracticeSessionType.PRACTICE)
    db_session.add(ps)
    db_session.flush()

    q = Question(
        subject_id=subject.id, content="Standalone question?", content_hash=f"{uuid4().hex}{uuid4().hex}",
        question_type=QuestionType.MULTIPLE_CHOICE, difficulty=0.5, correct_answer="A",
        source_type="TEST", exam_weight=1.0, status=QuestionStatus.APPROVED, created_by=t_user.id,
    )
    db_session.add(q)
    db_session.flush()

    att = QuestionAttempt(
        practice_session_id=ps.id, student_id=s_prof.id, question_id=q.id,
        student_answer="A", is_correct=True, score=1.0, attempt_number=1,
        evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(att)
    db_session.commit()

    service = ClassAnalyticsService(db_session)
    dashboard = service.get_classroom_dashboard(t_user.id, classroom.id)

    # Activity must remain 0 because no LearningEvidenceEvent exists!
    assert dashboard.recent_trends.total_evidence_past_7_days == 0
    assert dashboard.recent_trends.scored_evidence_past_7_days == 0
    assert dashboard.evidence_sources.total_count == 0


# --------------------------------------------------------------------------
# 4. Verified Root Cause Alerts & Prerequisite Verification (Sections 67, 68)
# --------------------------------------------------------------------------


def test_verified_prerequisite_root_cause_alert_and_metric(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_vprereq@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_vprereq@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, concept = _setup_curriculum(db_session, "VPR")

    classroom = Classroom(name="Class Verified Prereq", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Evidence event
    ev = LearningEvidenceEvent(
        student_id=s_prof.id, subject_id=subject.id, classroom_id=classroom.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION, source_entity_id=uuid4(),
        is_correct=False, score=0.0, evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=datetime.now(timezone.utc),
    )
    db_session.add(ev)
    db_session.flush()

    # Diagnosis with PREREQUISITE_CONCEPT_GAP
    diag = RootCauseDiagnosis(
        learning_evidence_event_id=ev.id,
        student_id=s_prof.id,
        subject_id=subject.id,
        classroom_id=classroom.id,
        diagnosis_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        status=RootCauseDiagnosisStatus.STRONG_HYPOTHESIS,
        root_concept_id=concept.id,
        confidence=0.88,
        supporting_evidence_count=3,
        reason_code="PREREQ_GAP_DETECTED",
    )
    db_session.add(diag)
    db_session.flush()

    # Verification: COMPLETED
    ps = PracticeSession(student_id=s_prof.id, subject_id=subject.id, session_type=PracticeSessionType.ROOT_CAUSE_VERIFICATION)
    db_session.add(ps)
    db_session.flush()

    verif = RootCauseVerification(
        diagnosis_id=diag.id,
        practice_session_id=ps.id,
        status=RootCauseVerificationStatus.COMPLETED,
        required_probe_count=3,
        completed_probe_count=3,
    )
    db_session.add(verif)
    db_session.flush()

    # Target: SUPPORTED
    v_target = RootCauseVerificationTarget(
        verification_id=verif.id,
        target_type=RootCauseVerificationTargetType.CONCEPT,
        target_concept_id=concept.id,
        priority_order=1,
        outcome=RootCauseVerificationOutcome.SUPPORTED,
        probe_count=3,
        correct_count=0,
        average_score=0.0,
    )
    db_session.add(v_target)
    db_session.commit()

    service = ClassAnalyticsService(db_session)
    alerts_data = service.get_classroom_alerts(t_user.id, classroom.id)

    assert any(a.rule_code == AlertRuleCode.PREREQUISITE_GAP for a in alerts_data.alerts)
    prereq_alert = next(a for a in alerts_data.alerts if a.rule_code == AlertRuleCode.PREREQUISITE_GAP)
    assert prereq_alert.severity == AlertSeverity.HIGH
    assert prereq_alert.target_name == concept.name

    dashboard = service.get_classroom_dashboard(t_user.id, classroom.id)
    assert len(dashboard.verified_root_causes) == 1
    assert dashboard.verified_root_causes[0].target_name == concept.name
    assert dashboard.verified_root_causes[0].affected_student_count == 1


def test_unverified_hypothesis_does_not_trigger_prerequisite_alert(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_unver@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_unver@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, _, concept = _setup_curriculum(db_session, "UNV")

    classroom = Classroom(name="Class Unverified", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    ev = LearningEvidenceEvent(
        student_id=s_prof.id, subject_id=subject.id, classroom_id=classroom.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION, source_entity_id=uuid4(),
        is_correct=False, score=0.0, evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=datetime.now(timezone.utc),
    )
    db_session.add(ev)
    db_session.flush()

    # Diagnosis alone (hypothesis, no completed SUPPORTED verification)
    diag = RootCauseDiagnosis(
        learning_evidence_event_id=ev.id,
        student_id=s_prof.id,
        subject_id=subject.id,
        classroom_id=classroom.id,
        diagnosis_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        status=RootCauseDiagnosisStatus.HYPOTHESIS,
        root_concept_id=concept.id,
        confidence=0.55,
        supporting_evidence_count=1,
        reason_code="HYPOTHESIS_ONLY",
    )
    db_session.add(diag)
    db_session.commit()

    service = ClassAnalyticsService(db_session)
    alerts_data = service.get_classroom_alerts(t_user.id, classroom.id)

    # MUST NOT trigger alert for unverified hypothesis
    assert not any(a.rule_code == AlertRuleCode.PREREQUISITE_GAP for a in alerts_data.alerts)


# --------------------------------------------------------------------------
# 5. Adaptive Repair Outcomes (Sections 69, 70)
# --------------------------------------------------------------------------


def test_adaptive_repair_failed_outcomes_trigger_alert(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_rep_fail@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_rep_fail@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, _ = _setup_curriculum(db_session, "RPF")

    classroom = Classroom(name="Class Repair Fail", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    ev = LearningEvidenceEvent(
        student_id=s_prof.id, subject_id=subject.id, classroom_id=classroom.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION, source_entity_id=uuid4(),
        is_correct=False, score=0.0, evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=datetime.now(timezone.utc),
    )
    db_session.add(ev)
    db_session.flush()

    diag = RootCauseDiagnosis(
        learning_evidence_event_id=ev.id, student_id=s_prof.id, subject_id=subject.id, classroom_id=classroom.id,
        diagnosis_type=RootCauseDiagnosisType.PROBLEM_TYPE_PROCEDURE_GAP, status=RootCauseDiagnosisStatus.STRONG_HYPOTHESIS,
        target_problem_type_id=pt.id, confidence=0.9, supporting_evidence_count=3, reason_code="PROC_GAP",
    )
    db_session.add(diag)
    db_session.flush()

    ps_v = PracticeSession(student_id=s_prof.id, subject_id=subject.id, session_type=PracticeSessionType.ROOT_CAUSE_VERIFICATION)
    db_session.add(ps_v)
    db_session.flush()
    verif = RootCauseVerification(diagnosis_id=diag.id, practice_session_id=ps_v.id, status=RootCauseVerificationStatus.COMPLETED)
    db_session.add(verif)
    db_session.flush()

    vt = RootCauseVerificationTarget(
        verification_id=verif.id, target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        target_problem_type_id=pt.id, outcome=RootCauseVerificationOutcome.SUPPORTED,
    )
    db_session.add(vt)
    db_session.flush()

    now = datetime.now(timezone.utc)
    outcomes = [AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE, AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE, AdaptiveRepairOutcome.BANK_EXHAUSTED]
    for idx, outcome in enumerate(outcomes, start=1):
        ps = PracticeSession(student_id=s_prof.id, subject_id=subject.id, session_type=PracticeSessionType.REPAIR)
        db_session.add(ps)
        db_session.flush()
        ars = AdaptiveRepairSession(
            practice_session_id=ps.id, student_id=s_prof.id, subject_id=subject.id,
            diagnosis_id=diag.id, verification_id=verif.id, verification_target_id=vt.id,
            target_type=RootCauseVerificationTargetType.PROBLEM_TYPE, target_problem_type_id=pt.id,
            target_name=pt.name, status=AdaptiveRepairStatus.COMPLETED, phase=AdaptiveRepairPhase.TARGET_PRACTICE,
            outcome=outcome, repair_cycle_index=idx, initial_difficulty=0.5, current_difficulty=0.5,
            target_exit_difficulty=0.7, completed_at=now,
        )
        db_session.add(ars)

    db_session.commit()

    service = ClassAnalyticsService(db_session)
    alerts_data = service.get_classroom_alerts(t_user.id, classroom.id)

    assert any(a.rule_code == AlertRuleCode.FAILED_REPAIR for a in alerts_data.alerts)
    alert = next(a for a in alerts_data.alerts if a.rule_code == AlertRuleCode.FAILED_REPAIR)
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.target_name == pt.name

    dashboard = service.get_classroom_dashboard(t_user.id, classroom.id)
    assert dashboard.repair_summary.completed_count == 3
    assert dashboard.repair_summary.needs_more_practice_count == 2
    assert dashboard.repair_summary.bank_exhausted_count == 1
    assert dashboard.repair_summary.resolution_rate == 0.0


def test_adaptive_repair_resolved_outcome_clears_failed_repair(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_rep_res@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_rep_res@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, _ = _setup_curriculum(db_session, "RPR")

    classroom = Classroom(name="Class Repair Res", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    ev = LearningEvidenceEvent(
        student_id=s_prof.id, subject_id=subject.id, classroom_id=classroom.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION, source_entity_id=uuid4(),
        is_correct=False, score=0.0, evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=datetime.now(timezone.utc),
    )
    db_session.add(ev)
    db_session.flush()

    diag = RootCauseDiagnosis(
        learning_evidence_event_id=ev.id, student_id=s_prof.id, subject_id=subject.id, classroom_id=classroom.id,
        diagnosis_type=RootCauseDiagnosisType.PROBLEM_TYPE_PROCEDURE_GAP, status=RootCauseDiagnosisStatus.STRONG_HYPOTHESIS,
        target_problem_type_id=pt.id, confidence=0.9, supporting_evidence_count=3, reason_code="PROC_GAP",
    )
    db_session.add(diag)
    db_session.flush()

    ps_v = PracticeSession(student_id=s_prof.id, subject_id=subject.id, session_type=PracticeSessionType.ROOT_CAUSE_VERIFICATION)
    db_session.add(ps_v)
    db_session.flush()
    verif = RootCauseVerification(diagnosis_id=diag.id, practice_session_id=ps_v.id, status=RootCauseVerificationStatus.COMPLETED)
    db_session.add(verif)
    db_session.flush()

    vt = RootCauseVerificationTarget(
        verification_id=verif.id, target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        target_problem_type_id=pt.id, outcome=RootCauseVerificationOutcome.SUPPORTED,
    )
    db_session.add(vt)
    db_session.flush()

    now = datetime.now(timezone.utc)
    # 2 failed cycles followed by 1 RESOLVED cycle
    outcomes = [AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE, AdaptiveRepairOutcome.NEEDS_MORE_PRACTICE, AdaptiveRepairOutcome.RESOLVED]
    for idx, outcome in enumerate(outcomes, start=1):
        ps = PracticeSession(student_id=s_prof.id, subject_id=subject.id, session_type=PracticeSessionType.REPAIR)
        db_session.add(ps)
        db_session.flush()
        ars = AdaptiveRepairSession(
            practice_session_id=ps.id, student_id=s_prof.id, subject_id=subject.id,
            diagnosis_id=diag.id, verification_id=verif.id, verification_target_id=vt.id,
            target_type=RootCauseVerificationTargetType.PROBLEM_TYPE, target_problem_type_id=pt.id,
            target_name=pt.name, status=AdaptiveRepairStatus.COMPLETED, phase=AdaptiveRepairPhase.TARGET_PRACTICE,
            outcome=outcome, repair_cycle_index=idx, initial_difficulty=0.5, current_difficulty=0.5,
            target_exit_difficulty=0.7, completed_at=now,
        )
        db_session.add(ars)

    db_session.commit()

    service = ClassAnalyticsService(db_session)
    alerts_data = service.get_classroom_alerts(t_user.id, classroom.id)

    # Resolved outcome clears the failed repair alert!
    assert not any(a.rule_code == AlertRuleCode.FAILED_REPAIR for a in alerts_data.alerts)

    dashboard = service.get_classroom_dashboard(t_user.id, classroom.id)
    assert dashboard.repair_summary.resolved_count == 1
    assert dashboard.repair_summary.resolution_rate == 33.3


# --------------------------------------------------------------------------
# 6. Spaced Review Schedules & Alerts (Section 71)
# --------------------------------------------------------------------------


def test_review_due_summary_and_review_overdue_alerts(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_rev@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_rev@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, concept = _setup_curriculum(db_session, "REV")

    classroom = Classroom(name="Class Review", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    now = datetime.now(timezone.utc)

    # 3 schedules due now (past or today) -> triggers REVIEW_OVERDUE (MEDIUM)
    db_session.add_all([
        ReviewSchedule(student_id=s_prof.id, problem_type_id=pt.id, next_review_at=now - timedelta(days=2)),
        ReviewSchedule(student_id=s_prof.id, concept_id=concept.id, next_review_at=now - timedelta(hours=1)),
    ])
    # Add second concept for third due schedule
    c2 = Concept(subject_id=subject.id, code="REV-CON-2", name="Đạo hàm hàm hợp", order_index=1)
    db_session.add(c2)
    db_session.flush()
    db_session.add(ReviewSchedule(student_id=s_prof.id, concept_id=c2.id, next_review_at=now))

    # 1 schedule due in next 3 days
    c3 = Concept(subject_id=subject.id, code="REV-CON-3", name="Khảo sát hàm số", order_index=2)
    db_session.add(c3)
    db_session.flush()
    db_session.add(ReviewSchedule(student_id=s_prof.id, concept_id=c3.id, next_review_at=now + timedelta(days=2)))

    # 1 schedule due after 5 days
    c4 = Concept(subject_id=subject.id, code="REV-CON-4", name="Tích phân", order_index=3)
    db_session.add(c4)
    db_session.flush()
    db_session.add(ReviewSchedule(student_id=s_prof.id, concept_id=c4.id, next_review_at=now + timedelta(days=5)))

    db_session.commit()

    service = ClassAnalyticsService(db_session)
    dashboard = service.get_classroom_dashboard(t_user.id, classroom.id)

    assert dashboard.review_due.due_now_count == 3
    assert dashboard.review_due.due_next_3_days_count == 1
    assert dashboard.review_due.students_due_count == 1
    assert dashboard.review_due.problem_type_due_count == 1
    assert dashboard.review_due.concept_due_count == 2

    alerts = service.get_classroom_alerts(t_user.id, classroom.id).alerts
    assert any(a.rule_code == AlertRuleCode.REVIEW_OVERDUE for a in alerts)
    rev_alert = next(a for a in alerts if a.rule_code == AlertRuleCode.REVIEW_OVERDUE)
    assert rev_alert.severity == AlertSeverity.MEDIUM


# --------------------------------------------------------------------------
# 7. Assignment Completion & Overdue Alerts (Sections 72, 73)
# --------------------------------------------------------------------------


def test_assignment_completion_and_assignment_overdue_alert(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_asgn_c@example.com")
    s1_user = classroom_user_factory(Role.STUDENT, "s1_asgn_c@example.com")
    s2_user = classroom_user_factory(Role.STUDENT, "s2_asgn_c@example.com")
    t_prof = teacher_profile(t_user)
    s1_prof = student_profile(s1_user)
    s2_prof = student_profile(s2_user)

    subject, _, _, _, _ = _setup_curriculum(db_session, "ASC")

    classroom = Classroom(name="Class Asgn Comp", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add_all([
        StudentEnrollment(student_id=s1_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
        StudentEnrollment(student_id=s2_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
    ])

    now = datetime.now(timezone.utc)
    # Assignment 1: Overdue, due 2 days ago
    asgn1 = Assignment(
        classroom_id=classroom.id, subject_id=subject.id, title="Bài tập 1",
        assignment_type=AssignmentType.SAME_SET, status=AssignmentStatus.PUBLISHED,
        question_count=5, due_at=now - timedelta(days=2), created_by=t_user.id,
    )
    # Assignment 2: Ongoing, due in 2 days
    asgn2 = Assignment(
        classroom_id=classroom.id, subject_id=subject.id, title="Bài tập 2",
        assignment_type=AssignmentType.SAME_SET, status=AssignmentStatus.PUBLISHED,
        question_count=5, due_at=now + timedelta(days=2), created_by=t_user.id,
    )
    db_session.add_all([asgn1, asgn2])
    db_session.flush()

    # S1: NOT_STARTED on asgn1 (overdue!) and SUBMITTED on asgn2 (completed)
    # S2: GRADED on asgn1 (completed with score 0.9) and IN_PROGRESS on asgn2
    db_session.add_all([
        StudentAssignment(assignment_id=asgn1.id, student_id=s1_prof.id, status=StudentAssignmentStatus.NOT_STARTED),
        StudentAssignment(assignment_id=asgn2.id, student_id=s1_prof.id, status=StudentAssignmentStatus.SUBMITTED, score=0.8),
        StudentAssignment(assignment_id=asgn1.id, student_id=s2_prof.id, status=StudentAssignmentStatus.GRADED, score=0.9),
        StudentAssignment(assignment_id=asgn2.id, student_id=s2_prof.id, status=StudentAssignmentStatus.IN_PROGRESS),
    ])
    db_session.commit()

    service = ClassAnalyticsService(db_session)
    dashboard = service.get_classroom_dashboard(t_user.id, classroom.id)

    ac = dashboard.assignment_completion
    assert ac.assignment_count == 2
    assert ac.assigned_student_count == 4
    assert ac.not_started_count == 1
    assert ac.in_progress_count == 1
    assert ac.submitted_count == 1
    assert ac.graded_count == 1
    assert ac.overdue_count == 1  # Only S1 on asgn1 is overdue
    assert ac.completion_rate == 50.0  # 2 completed / 4 assigned
    assert ac.average_score == 0.85

    # S1 gets ASSIGNMENT_OVERDUE alert (1 overdue -> MEDIUM)
    alerts = service.get_classroom_alerts(t_user.id, classroom.id).alerts
    assert any(a.rule_code == AlertRuleCode.ASSIGNMENT_OVERDUE and a.student_id == s1_prof.id for a in alerts)
    s1_alert = next(a for a in alerts if a.rule_code == AlertRuleCode.ASSIGNMENT_OVERDUE and a.student_id == s1_prof.id)
    assert s1_alert.severity == AlertSeverity.MEDIUM


# --------------------------------------------------------------------------
# 8. Subject & Classroom Isolation (Sections 74, 75, 76)
# --------------------------------------------------------------------------


def test_subject_and_classroom_isolation(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_iso@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_iso@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    math_sub, _, _, math_pt, _ = _setup_curriculum(db_session, "MTH")
    phys_sub, _, _, phys_pt, _ = _setup_curriculum(db_session, "PHY")

    # Classroom A
    class_a = Classroom(name="Class A", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    # Classroom B
    class_b = Classroom(name="Class B", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add_all([class_a, class_b])
    db_session.flush()
    db_session.add_all([
        TeacherClassroom(teacher_id=t_prof.id, classroom_id=class_a.id, role="OWNER"),
        TeacherClassroom(teacher_id=t_prof.id, classroom_id=class_b.id, role="OWNER"),
        StudentEnrollment(student_id=s_prof.id, classroom_id=class_a.id, status=EnrollmentStatus.ACTIVE),
        StudentEnrollment(student_id=s_prof.id, classroom_id=class_b.id, status=EnrollmentStatus.ACTIVE),
    ])

    now = datetime.now(timezone.utc)
    # Math evidence in Class A
    ev_math = LearningEvidenceEvent(
        student_id=s_prof.id, subject_id=math_sub.id, classroom_id=class_a.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION, source_entity_id=uuid4(),
        is_correct=True, score=1.0, evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=now,
    )
    # Physics evidence in Class A
    ev_phys = LearningEvidenceEvent(
        student_id=s_prof.id, subject_id=phys_sub.id, classroom_id=class_a.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION, source_entity_id=uuid4(),
        is_correct=False, score=0.0, evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=now,
    )
    # Math evidence in Class B
    ev_class_b = LearningEvidenceEvent(
        student_id=s_prof.id, subject_id=math_sub.id, classroom_id=class_b.id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION, source_entity_id=uuid4(),
        is_correct=True, score=1.0, evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=now,
    )
    db_session.add_all([ev_math, ev_phys, ev_class_b])
    db_session.commit()

    headers = classroom_bearer(t_user)

    # 1. Subject isolation: query Class A with subject_id=math_sub.id
    res_math = db_client.get(f"/teacher/classes/{class_a.id}/analytics?subject_id={math_sub.id}", headers=headers)
    assert res_math.status_code == 200
    d_math = res_math.json()
    assert d_math["evidence_sources"]["total_count"] == 1
    assert len(d_math["subject_progress"]) == 1
    assert d_math["subject_progress"][0]["subject_id"] == str(math_sub.id)

    # 2. Classroom isolation: query Class A without subject filter -> sees ev_math and ev_phys, but NOT ev_class_b
    res_a = db_client.get(f"/teacher/classes/{class_a.id}/analytics", headers=headers)
    assert res_a.status_code == 200
    assert res_a.json()["evidence_sources"]["total_count"] == 2

    # 3. Invalid subject_id -> 404
    res_bad_sub = db_client.get(f"/teacher/classes/{class_a.id}/analytics?subject_id={uuid4()}", headers=headers)
    assert res_bad_sub.status_code == 404


# --------------------------------------------------------------------------
# 9. Heatmap Views, Confidence & Sparse Coverage (Sections 78, 79)
# --------------------------------------------------------------------------


def test_heatmap_views_confidence_and_sparse_coverage(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_hconf@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_hconf@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, chapter, topic, pt1, _ = _setup_curriculum(db_session, "HCF")
    pt2 = ProblemType(topic_id=topic.id, code="HCF-PT-2", name="Dạng 2", order_index=1, is_active=True)
    pt3 = ProblemType(topic_id=topic.id, code="HCF-PT-3", name="Dạng 3", order_index=2, is_active=True)
    db_session.add_all([pt2, pt3])
    db_session.flush()

    classroom = Classroom(name="Class Heatmap Conf", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    now = datetime.now(timezone.utc)
    # Student has mastery for ONLY 1 of 3 problem types
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_prof.id, problem_type_id=pt1.id, mastery_score=0.85, confidence=0.92,
            attempt_count=8, correct_count=7, last_practiced_at=now,
        )
    )
    db_session.commit()

    headers = classroom_bearer(t_user)

    # 1. ProblemType View
    res_pt = db_client.get(f"/teacher/classes/{classroom.id}/heatmap?view=problem_type", headers=headers)
    assert res_pt.status_code == 200
    d_pt = res_pt.json()
    cells = d_pt["cells"]
    c1 = next(c for c in cells if c["column_id"] == str(pt1.id))
    c2 = next(c for c in cells if c["column_id"] == str(pt2.id))
    c3 = next(c for c in cells if c["column_id"] == str(pt3.id))

    assert c1["score"] == 0.85
    assert c1["confidence"] == 0.92
    assert c1["level"] == MasteryLevel.MASTERED.value
    # Sparse cells are NOT_STARTED and None score (not 0!)
    assert c2["score"] is None
    assert c2["confidence"] is None
    assert c2["level"] == MasteryLevel.NOT_STARTED.value
    assert c3["score"] is None
    assert c3["confidence"] is None
    assert c3["level"] == MasteryLevel.NOT_STARTED.value

    # 2. Topic View (aggregates observed items only)
    res_top = db_client.get(f"/teacher/classes/{classroom.id}/heatmap?view=topic", headers=headers)
    assert res_top.status_code == 200
    top_cell = res_top.json()["cells"][0]
    assert top_cell["score"] == 0.85
    assert top_cell["confidence"] == 0.92
    assert top_cell["observed_target_count"] == 1
    assert top_cell["total_target_count"] == 3


# --------------------------------------------------------------------------
# 10. Student Drilldown & Assignment Analytics Endpoints (Sections 80, 81)
# --------------------------------------------------------------------------


def test_student_drilldown_and_assignment_analytics_endpoints(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_drill@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_drill@example.com")
    outsider_student = classroom_user_factory(Role.STUDENT, "outsider@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)
    out_prof = student_profile(outsider_student)

    subject, chapter, topic, pt, concept = _setup_curriculum(db_session, "DRL")

    classroom = Classroom(name="Class Drilldown", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    other_classroom = Classroom(name="Other Class", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add_all([classroom, other_classroom])
    db_session.flush()
    db_session.add_all([
        TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"),
        TeacherClassroom(teacher_id=t_prof.id, classroom_id=other_classroom.id, role="OWNER"),
        StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
    ])

    now = datetime.now(timezone.utc)
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_prof.id, problem_type_id=pt.id, mastery_score=0.75, confidence=0.85,
            attempt_count=5, correct_count=4, last_practiced_at=now,
        )
    )

    asgn = Assignment(
        classroom_id=classroom.id, subject_id=subject.id, title="Kiểm tra 15p",
        assignment_type=AssignmentType.SAME_SET, status=AssignmentStatus.PUBLISHED,
        question_count=5, due_at=now + timedelta(days=1), created_by=t_user.id,
    )
    foreign_asgn = Assignment(
        classroom_id=other_classroom.id, subject_id=subject.id, title="Bài lớp khác",
        assignment_type=AssignmentType.SAME_SET, status=AssignmentStatus.PUBLISHED,
        question_count=5, due_at=now + timedelta(days=1), created_by=t_user.id,
    )
    db_session.add_all([asgn, foreign_asgn])
    db_session.flush()

    sa = StudentAssignment(
        assignment_id=asgn.id, student_id=s_prof.id, status=StudentAssignmentStatus.SUBMITTED,
        score=0.9, started_at=now - timedelta(hours=1), submitted_at=now,
    )
    db_session.add(sa)
    db_session.commit()

    headers = classroom_bearer(t_user)

    # 1. Student Drilldown
    res_st = db_client.get(f"/teacher/classes/{classroom.id}/students/{s_prof.id}/analytics", headers=headers)
    assert res_st.status_code == 200, res_st.text
    d_st = res_st.json()
    assert d_st["student_id"] == str(s_prof.id)
    assert len(d_st["problem_type_mastery"]) == 1
    assert d_st["problem_type_mastery"][0]["target_name"] == pt.name
    assert d_st["assignment_summary"]["total_assigned"] == 1
    assert d_st["assignment_summary"]["submitted_count"] == 1

    # Student not enrolled in class -> 404
    res_out = db_client.get(f"/teacher/classes/{classroom.id}/students/{out_prof.id}/analytics", headers=headers)
    assert res_out.status_code == 404

    # 2. Assignment Analytics
    res_asgn = db_client.get(f"/teacher/classes/{classroom.id}/assignments/{asgn.id}/analytics", headers=headers)
    assert res_asgn.status_code == 200, res_asgn.text
    d_asgn = res_asgn.json()
    assert d_asgn["assignment_id"] == str(asgn.id)
    assert d_asgn["assigned_count"] == 1
    assert d_asgn["submitted_count"] == 1
    assert len(d_asgn["student_rows"]) == 1
    assert d_asgn["student_rows"][0]["student_id"] == str(s_prof.id)
    assert d_asgn["student_rows"][0]["score"] == 0.9

    # Assignment from other classroom -> 404
    res_foreign = db_client.get(f"/teacher/classes/{classroom.id}/assignments/{foreign_asgn.id}/analytics", headers=headers)
    assert res_foreign.status_code == 404


# --------------------------------------------------------------------------
# 11. Read-Only Invariance: Analytics Calls Never Mutate Database (Section 83)
# --------------------------------------------------------------------------


def test_analytics_endpoints_are_read_only(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_ro@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_ro@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, concept = _setup_curriculum(db_session, "ROA")

    classroom = Classroom(name="Class Read Only", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    asgn = Assignment(
        classroom_id=classroom.id, subject_id=subject.id, title="Test",
        assignment_type=AssignmentType.SAME_SET, status=AssignmentStatus.PUBLISHED,
        question_count=5, created_by=t_user.id,
    )
    db_session.add(asgn)
    db_session.commit()

    # Capture record counts before queries
    count_tp = db_session.scalar(select(func.count(TeachingPlan.id))) or 0
    count_st = db_session.scalar(select(func.count(StudyTask.id))) or 0
    count_asgn = db_session.scalar(select(func.count(Assignment.id))) or 0
    count_ptm = db_session.scalar(select(func.count(StudentProblemTypeMastery.student_id))) or 0
    count_rs = db_session.scalar(select(func.count(ReviewSchedule.id))) or 0
    count_ars = db_session.scalar(select(func.count(AdaptiveRepairSession.id))) or 0

    headers = classroom_bearer(t_user)
    # Execute all analytics reads
    db_client.get(f"/teacher/classes/{classroom.id}/analytics", headers=headers)
    db_client.get(f"/teacher/classes/{classroom.id}/heatmap", headers=headers)
    db_client.get(f"/teacher/classes/{classroom.id}/alerts", headers=headers)
    db_client.get(f"/teacher/classes/{classroom.id}/students/{s_prof.id}/analytics", headers=headers)
    db_client.get(f"/teacher/classes/{classroom.id}/assignments/{asgn.id}/analytics", headers=headers)

    # Verify counts remain identical
    assert (db_session.scalar(select(func.count(TeachingPlan.id))) or 0) == count_tp
    assert (db_session.scalar(select(func.count(StudyTask.id))) or 0) == count_st
    assert (db_session.scalar(select(func.count(Assignment.id))) or 0) == count_asgn
    assert (db_session.scalar(select(func.count(StudentProblemTypeMastery.student_id))) or 0) == count_ptm
    assert (db_session.scalar(select(func.count(ReviewSchedule.id))) or 0) == count_rs
    assert (db_session.scalar(select(func.count(AdaptiveRepairSession.id))) or 0) == count_ars
