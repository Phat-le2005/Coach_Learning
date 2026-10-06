from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.assignments.models import (
    Assignment,
    AssignmentStatus,
    AssignmentType,
    StudentAssignment,
    StudentAssignmentStatus,
)
from app.classes.models import Classroom, EnrollmentStatus, StudentEnrollment
from app.concepts.models import Concept
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
from app.planning.models import TeachingPlan, TeachingPlanStatus
from app.planning.study_models import (
    StudyPlan,
    StudyPlanStatus,
    StudyTask,
    StudyTaskStatus,
    StudyTaskType,
)
from app.practice.models import EvaluationStatus, PracticeSession, PracticeSessionStatus, PracticeSessionType
from app.questions.models import Question, QuestionStatus, QuestionType
from app.repair.models import (
    AdaptiveRepairOutcome,
    AdaptiveRepairPhase,
    AdaptiveRepairSession,
    AdaptiveRepairStatus,
)
from app.review.models import ReviewSchedule
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User
from tests.student_learning_state.helpers import create_curriculum


def _create_classroom(session: Session, created_by: User, name: str = "Lớp 12A") -> Classroom:
    c = Classroom(
        name=name,
        academic_year="2025-2026",
        grade_level=12,
        created_by=created_by.id,
    )
    session.add(c)
    session.flush()
    return c


def _create_question(session: Session, subject_id, created_by_id=None) -> Question:
    if created_by_id is None:
        user = session.scalar(select(User).limit(1))
        created_by_id = user.id if user else uuid4()
    q = Question(
        subject_id=subject_id,
        content="Test Question Content",
        content_hash=f"{uuid4().hex}{uuid4().hex}",
        question_type=QuestionType.MULTIPLE_CHOICE,
        correct_answer="A",
        explanation="Explanation here",
        difficulty=0.5,
        source_type="TEST",
        exam_weight=1.0,
        status=QuestionStatus.APPROVED,
        created_by=created_by_id,
    )
    session.add(q)
    session.flush()
    return q


def _create_practice_session(
    session: Session,
    student_id,
    subject_id,
    session_type: PracticeSessionType = PracticeSessionType.PRACTICE,
    status: PracticeSessionStatus = PracticeSessionStatus.ACTIVE,
) -> PracticeSession:
    ps = PracticeSession(
        student_id=student_id,
        subject_id=subject_id,
        session_type=session_type,
        status=status,
    )
    session.add(ps)
    session.flush()
    return ps


def _create_evidence(
    session: Session,
    student_id,
    subject_id,
    *,
    is_correct: bool = True,
    occurred_at: datetime | None = None,
) -> LearningEvidenceEvent:
    ev = LearningEvidenceEvent(
        student_id=student_id,
        subject_id=subject_id,
        source_kind=LearningEvidenceSourceKind.PRACTICE_QUESTION,
        source_entity_id=uuid4(),
        is_correct=is_correct,
        score=1.0 if is_correct else 0.0,
        evaluation_status=EvaluationStatus.AUTO_EVALUATED,
        occurred_at=occurred_at or datetime.now(timezone.utc),
    )
    session.add(ev)
    session.flush()
    return ev


# -----------------------------------------------------------------------------
# 1. Empty student state
# -----------------------------------------------------------------------------
def test_learning_state_empty_student_is_valid_idle_state(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    student_user = user_factory(Role.STUDENT, "empty_student@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    assert res.headers.get("Cache-Control") == "no-store"

    data = res.json()
    assert data["student_id"] == str(student.id)
    assert data["available_subjects"] == []
    assert data["focus_subject_id"] is None
    assert data["current_action"]["action_type"] == "IDLE"
    assert data["current_action"]["reason_code"] == "IDLE"

    mastery = data["mastery_summary"]
    assert mastery["problem_type_started_count"] == 0
    assert mastery["concept_started_count"] == 0
    assert mastery["mastered_problem_type_count"] == 0
    assert mastery["weak_problem_type_count"] == 0
    assert mastery["average_problem_type_mastery"] is None
    assert mastery["average_concept_mastery"] is None
    assert mastery["weak_problem_types"] == []
    assert mastery["weak_concepts"] == []

    assert data["priority_targets"] == []
    assert data["verified_root_causes"] == []
    assert data["repair"] is None
    assert data["review"]["due_now_count"] == 0
    assert data["review"]["upcoming_count"] == 0
    assert data["review"]["due_targets"] == []
    assert data["assignments"]["overdue_count"] == 0
    assert data["assignments"]["in_progress_count"] == 0
    assert data["assignments"]["pending_count"] == 0
    assert data["assignments"]["upcoming"] == []
    assert data["today_plan"] is None
    assert data["latest_feedback"] is None

    # Zero mutation in DB
    assert db_session.scalar(select(StudyPlan).where(StudyPlan.student_id == student.id)) is None


# -----------------------------------------------------------------------------
# 2. Precedence: Active repair wins over all lower states
# -----------------------------------------------------------------------------
def test_active_repair_precedence(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "repair_prec@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, chapter, topic, pt, concept = create_curriculum(db_session, "REP")

    # 1. Evidence
    ev = _create_evidence(
        db_session,
        student.id,
        subject.id,
        is_correct=False,
        occurred_at=now - timedelta(hours=2),
    )

    # 2. Diagnosis
    diag = RootCauseDiagnosis(
        student_id=student.id,
        subject_id=subject.id,
        learning_evidence_event_id=ev.id,
        target_problem_type_id=pt.id,
        diagnosis_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        status=RootCauseDiagnosisStatus.STRONG_HYPOTHESIS,
        confidence=0.85,
        supporting_evidence_count=2,
        reason_code="GAP_DETECTED",
    )
    db_session.add(diag)
    db_session.flush()

    # 3. Verification
    ver_ps = _create_practice_session(db_session, student.id, subject.id, PracticeSessionType.ROOT_CAUSE_VERIFICATION)
    ver = RootCauseVerification(
        diagnosis_id=diag.id,
        practice_session_id=ver_ps.id,
        status=RootCauseVerificationStatus.COMPLETED,
        required_probe_count=3,
        completed_probe_count=3,
        completed_at=now - timedelta(hours=1),
    )
    db_session.add(ver)
    db_session.flush()

    target = RootCauseVerificationTarget(
        verification_id=ver.id,
        target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        target_problem_type_id=pt.id,
        priority_order=1,
        outcome=RootCauseVerificationOutcome.SUPPORTED,
        probe_count=3,
        correct_count=1,
    )
    db_session.add(target)
    db_session.flush()

    # 4. Active Repair Session
    rep_ps = _create_practice_session(db_session, student.id, subject.id, PracticeSessionType.REPAIR)
    repair = AdaptiveRepairSession(
        practice_session_id=rep_ps.id,
        student_id=student.id,
        subject_id=subject.id,
        diagnosis_id=diag.id,
        verification_id=ver.id,
        verification_target_id=target.id,
        target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        target_problem_type_id=pt.id,
        target_name=pt.name,
        target_code=pt.code,
        status=AdaptiveRepairStatus.ACTIVE,
        phase=AdaptiveRepairPhase.TARGET_PRACTICE,
        outcome=AdaptiveRepairOutcome.PENDING,
        repair_cycle_index=1,
        initial_difficulty=0.4,
        current_difficulty=0.5,
        target_exit_difficulty=0.7,
        max_questions=8,
    )
    db_session.add(repair)

    # 5. Overdue assignment
    classroom = _create_classroom(db_session, student_user, "Lớp 12A")
    assign = Assignment(
        classroom_id=classroom.id,
        subject_id=subject.id,
        title="Bài tập quá hạn",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED,
        start_at=now - timedelta(days=2),
        due_at=now - timedelta(days=1),
        created_by=student_user.id,
    )
    db_session.add(assign)
    db_session.flush()
    sa = StudentAssignment(
        assignment_id=assign.id,
        student_id=student.id,
        status=StudentAssignmentStatus.NOT_STARTED,
    )
    db_session.add(sa)

    # 6. Review due
    rev = ReviewSchedule(
        student_id=student.id,
        problem_type_id=pt.id,
        next_review_at=now - timedelta(hours=3),
        review_interval_days=1.0,
        review_count=1,
    )
    db_session.add(rev)

    # 7. Today study task
    plan = StudyPlan(
        student_id=student.id,
        start_date=now.date(),
        status=StudyPlanStatus.ACTIVE,
    )
    db_session.add(plan)
    db_session.flush()
    task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=now.date(),
        problem_type_id=pt.id,
        subject_id=subject.id,
        estimated_duration_minutes=20,
        priority=80,
        order_index=0,
        reason_code="WEAK_PROBLEM_TYPE",
    )
    db_session.add(task)
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["current_action"]["action_type"] == "CONTINUE_REPAIR"
    assert data["current_action"]["reason_code"] == "ACTIVE_REPAIR"
    assert data["current_action"]["adaptive_repair_session_id"] == str(repair.id)
    assert data["current_action"]["target_code"] == pt.code
    assert data["repair"] is not None
    assert data["repair"]["adaptive_repair_session_id"] == str(repair.id)
    assert data["repair"]["phase"] == "TARGET_PRACTICE"


# -----------------------------------------------------------------------------
# 3. Precedence: Active verification wins over assignment, review, today tasks
# -----------------------------------------------------------------------------
def test_verification_precedence(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "ver_prec@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, chapter, topic, pt, concept = create_curriculum(db_session, "VER")

    ev = _create_evidence(
        db_session,
        student.id,
        subject.id,
        is_correct=False,
        occurred_at=now - timedelta(hours=2),
    )

    diag = RootCauseDiagnosis(
        student_id=student.id,
        subject_id=subject.id,
        learning_evidence_event_id=ev.id,
        target_problem_type_id=pt.id,
        diagnosis_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        status=RootCauseDiagnosisStatus.STRONG_HYPOTHESIS,
        confidence=0.85,
        supporting_evidence_count=2,
        reason_code="GAP_DETECTED",
    )
    db_session.add(diag)
    db_session.flush()

    ver_ps = _create_practice_session(db_session, student.id, subject.id, PracticeSessionType.ROOT_CAUSE_VERIFICATION)
    ver = RootCauseVerification(
        diagnosis_id=diag.id,
        practice_session_id=ver_ps.id,
        status=RootCauseVerificationStatus.ACTIVE,
        required_probe_count=3,
        completed_probe_count=1,
    )
    db_session.add(ver)
    db_session.flush()

    target = RootCauseVerificationTarget(
        verification_id=ver.id,
        target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        target_problem_type_id=pt.id,
        priority_order=1,
        outcome=RootCauseVerificationOutcome.PENDING,
        probe_count=1,
        correct_count=0,
    )
    db_session.add(target)

    # Review due
    rev = ReviewSchedule(
        student_id=student.id,
        problem_type_id=pt.id,
        next_review_at=now - timedelta(hours=1),
        review_interval_days=1.0,
    )
    db_session.add(rev)
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["current_action"]["action_type"] == "CONTINUE_VERIFICATION"
    assert data["current_action"]["reason_code"] == "ACTIVE_VERIFICATION"
    assert data["current_action"]["verification_id"] == str(ver.id)


# -----------------------------------------------------------------------------
# 4. Precedence: Active in-progress assignment
# -----------------------------------------------------------------------------
def test_assignment_precedence(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "assign_prec@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, chapter, topic, pt, concept = create_curriculum(db_session, "ASG")

    classroom = _create_classroom(db_session, student_user, "Lớp 12B")
    assign = Assignment(
        classroom_id=classroom.id,
        subject_id=subject.id,
        title="Bài tập đang làm",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED,
        start_at=now - timedelta(days=1),
        due_at=now + timedelta(days=2),
        created_by=student_user.id,
    )
    db_session.add(assign)
    db_session.flush()

    sa = StudentAssignment(
        assignment_id=assign.id,
        student_id=student.id,
        status=StudentAssignmentStatus.IN_PROGRESS,
        started_at=now - timedelta(hours=1),
    )
    db_session.add(sa)

    # Review due also present
    rev = ReviewSchedule(
        student_id=student.id,
        problem_type_id=pt.id,
        next_review_at=now - timedelta(hours=1),
        review_interval_days=1.0,
    )
    db_session.add(rev)
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["current_action"]["action_type"] == "CONTINUE_ASSIGNMENT"
    assert data["current_action"]["reason_code"] == "ASSIGNMENT_IN_PROGRESS"
    assert data["current_action"]["assignment_id"] == str(assign.id)


# -----------------------------------------------------------------------------
# 5. Precedence: Overdue assignment
# -----------------------------------------------------------------------------
def test_overdue_assignment_precedence(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "overdue_prec@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, chapter, topic, pt, concept = create_curriculum(db_session, "OVD")

    classroom = _create_classroom(db_session, student_user, "Lớp 12C")
    assign = Assignment(
        classroom_id=classroom.id,
        subject_id=subject.id,
        title="Bài tập chưa làm và quá hạn",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED,
        start_at=now - timedelta(days=2),
        due_at=now - timedelta(days=1),
        created_by=student_user.id,
    )
    db_session.add(assign)
    db_session.flush()

    sa = StudentAssignment(
        assignment_id=assign.id,
        student_id=student.id,
        status=StudentAssignmentStatus.NOT_STARTED,
    )
    db_session.add(sa)

    # Active normal practice session also present
    ps = _create_practice_session(db_session, student.id, subject.id, PracticeSessionType.PRACTICE)
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["current_action"]["action_type"] == "COMPLETE_OVERDUE_ASSIGNMENT"
    assert data["current_action"]["reason_code"] == "ASSIGNMENT_OVERDUE"
    assert data["current_action"]["assignment_id"] == str(assign.id)


# -----------------------------------------------------------------------------
# 6. Precedence: Normal practice session
# -----------------------------------------------------------------------------
def test_normal_practice_precedence(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "practice_prec@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, chapter, topic, pt, concept = create_curriculum(db_session, "PRC")

    # Active practice session
    ps = _create_practice_session(db_session, student.id, subject.id, PracticeSessionType.PRACTICE)

    # Review due
    rev = ReviewSchedule(
        student_id=student.id,
        problem_type_id=pt.id,
        next_review_at=now - timedelta(hours=1),
        review_interval_days=1.0,
    )
    db_session.add(rev)
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["current_action"]["action_type"] == "CONTINUE_PRACTICE"
    assert data["current_action"]["reason_code"] == "ACTIVE_PRACTICE"
    assert data["current_action"]["practice_session_id"] == str(ps.id)


# -----------------------------------------------------------------------------
# 7. Precedence: Review due
# -----------------------------------------------------------------------------
def test_review_due_precedence(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "review_prec@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, chapter, topic, pt, concept = create_curriculum(db_session, "REV")

    # Review due
    rev = ReviewSchedule(
        student_id=student.id,
        problem_type_id=pt.id,
        next_review_at=now - timedelta(hours=1),
        review_interval_days=1.0,
    )
    db_session.add(rev)

    # Today task
    plan = StudyPlan(student_id=student.id, start_date=now.date(), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()
    task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=now.date(),
        problem_type_id=pt.id,
        subject_id=subject.id,
        estimated_duration_minutes=20,
        priority=70,
        order_index=0,
        reason_code="WEAK_PROBLEM_TYPE",
    )
    db_session.add(task)
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["current_action"]["action_type"] == "REVIEW_DUE"
    assert data["current_action"]["reason_code"] == "REVIEW_DUE"
    assert data["current_action"]["problem_type_id"] == str(pt.id)


# -----------------------------------------------------------------------------
# 8. Precedence: Today study task
# -----------------------------------------------------------------------------
def test_today_task_precedence(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "today_prec@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, chapter, topic, pt, concept = create_curriculum(db_session, "TDY")

    # Student has mastery row so subject is available
    pm = StudentProblemTypeMastery(
        student_id=student.id,
        problem_type_id=pt.id,
        mastery_score=0.45,
        confidence=0.5,
        attempt_count=2,
        correct_count=1,
        last_practiced_at=now,
    )
    db_session.add(pm)

    plan = StudyPlan(student_id=student.id, start_date=now.date(), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()
    task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=now.date(),
        problem_type_id=pt.id,
        subject_id=subject.id,
        estimated_duration_minutes=20,
        priority=90,
        order_index=0,
        reason_code="WEAK_PROBLEM_TYPE",
    )
    db_session.add(task)
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["current_action"]["action_type"] == "TODAY_TASK"
    assert data["current_action"]["study_task_id"] == str(task.id)


# -----------------------------------------------------------------------------
# 9. Precedence: Learning priority fallback
# -----------------------------------------------------------------------------
def test_learning_priority_fallback(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "prio_prec@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, chapter, topic, pt, concept = create_curriculum(db_session, "LPF")

    # Low mastery
    pm = StudentProblemTypeMastery(
        student_id=student.id,
        problem_type_id=pt.id,
        mastery_score=0.2,
        confidence=0.6,
        attempt_count=4,
        correct_count=1,
        last_practiced_at=now,
    )
    db_session.add(pm)
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["current_action"]["action_type"] == "LEARNING_PRIORITY"
    assert data["current_action"]["problem_type_id"] == str(pt.id)
    assert len(data["priority_targets"]) >= 1


# -----------------------------------------------------------------------------
# 10. Read-only guarantee: GET does not create plan or mutate tasks
# -----------------------------------------------------------------------------
def test_read_only_guarantee_no_mutations(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    today = date.today()
    student_user = user_factory(Role.STUDENT, "readonly_test@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, chapter, topic, pt, concept = create_curriculum(db_session, "RO")

    # Add past pending task
    plan = StudyPlan(student_id=student.id, start_date=today - timedelta(days=5), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()

    past_task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=today - timedelta(days=2),
        problem_type_id=pt.id,
        subject_id=subject.id,
        estimated_duration_minutes=20,
        priority=50,
        order_index=0,
        reason_code="WEAK_PROBLEM_TYPE",
    )
    db_session.add(past_task)
    db_session.commit()

    # Call learning state
    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200

    # Ensure past task was NOT marked SKIPPED by GET learning-state!
    db_session.expire_all()
    reloaded_task = db_session.get(StudyTask, past_task.id)
    assert reloaded_task.status == StudyTaskStatus.PENDING

    # Ensure no new tasks generated for today
    today_tasks = list(
        db_session.scalars(
            select(StudyTask).where(
                StudyTask.study_plan_id == plan.id,
                StudyTask.planned_date == today,
            )
        )
    )
    assert len(today_tasks) == 0


# -----------------------------------------------------------------------------
# 11. Subject isolation: Math vs Physics
# -----------------------------------------------------------------------------
def test_subject_isolation_math_vs_physics(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "isolation_test@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    math_sub, math_chp, math_top, math_pt, math_con = create_curriculum(db_session, "MATH")
    phy_sub, phy_chp, phy_top, phy_pt, phy_con = create_curriculum(db_session, "PHYS")

    # Evidence in Math and Physics
    ev_math = _create_evidence(
        db_session,
        student.id,
        math_sub.id,
        is_correct=False,
        occurred_at=now - timedelta(hours=2),
    )
    ev_phy = _create_evidence(
        db_session,
        student.id,
        phy_sub.id,
        is_correct=False,
        occurred_at=now - timedelta(hours=1),
    )

    # Review due for Physics only
    phy_rev = ReviewSchedule(
        student_id=student.id,
        problem_type_id=phy_pt.id,
        next_review_at=now - timedelta(hours=1),
        review_interval_days=1.0,
    )
    db_session.add(phy_rev)

    # Mastery for Math only
    math_m = StudentProblemTypeMastery(
        student_id=student.id,
        problem_type_id=math_pt.id,
        mastery_score=0.3,
        confidence=0.7,
        attempt_count=5,
        correct_count=1,
        last_practiced_at=now,
    )
    db_session.add(math_m)
    db_session.commit()

    # Query explicitly for Math
    res = db_client.get(f"/students/me/learning-state?subject_id={math_sub.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["focus_subject_id"] == str(math_sub.id)
    # Both subjects available
    sub_ids = {s["id"] for s in data["available_subjects"]}
    assert str(math_sub.id) in sub_ids
    assert str(phy_sub.id) in sub_ids

    # Review due for Physics must NOT appear in Math query
    assert data["review"]["due_now_count"] == 0
    assert data["review"]["due_targets"] == []

    # Mastery summary must only contain Math
    assert data["mastery_summary"]["problem_type_started_count"] == 1
    assert data["mastery_summary"]["weak_problem_types"][0]["problem_type_id"] == str(math_pt.id)


# -----------------------------------------------------------------------------
# 12. Unrelated subject returns 409, non-existent returns 404
# -----------------------------------------------------------------------------
def test_unrelated_subject_and_not_found(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "unrelated_test@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    # Student has only Math
    math_sub, _, _, math_pt, _ = create_curriculum(db_session, "SCOPEMATH")
    m = StudentProblemTypeMastery(
        student_id=student.id,
        problem_type_id=math_pt.id,
        mastery_score=0.5,
        confidence=0.5,
        attempt_count=1,
        correct_count=0,
        last_practiced_at=now,
    )
    db_session.add(m)

    # Chemistry exists in DB but student has no data
    chem_sub, _, _, _, _ = create_curriculum(db_session, "CHEMISTRY")
    db_session.commit()

    # 409 for unrelated subject
    res_chem = db_client.get(f"/students/me/learning-state?subject_id={chem_sub.id}", headers=headers)
    assert res_chem.status_code == 409
    assert res_chem.json()["error"]["code"] == "STUDENT_SUBJECT_NOT_IN_SCOPE"

    # 404 for non-existent subject
    random_id = uuid4()
    res_404 = db_client.get(f"/students/me/learning-state?subject_id={random_id}", headers=headers)
    assert res_404.status_code == 404
    assert res_404.json()["error"]["code"] == "SUBJECT_NOT_FOUND"


# -----------------------------------------------------------------------------
# 13. Focus subject resolution: Active repair overrides newer evidence
# -----------------------------------------------------------------------------
def test_focus_subject_active_repair_overrides_newer_evidence(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "focus_repair@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    math_sub, _, _, math_pt, _ = create_curriculum(db_session, "FMATH")
    phy_sub, _, _, phy_pt, _ = create_curriculum(db_session, "FPHYS")

    # Math evidence at T1
    ev_math = _create_evidence(
        db_session,
        student.id,
        math_sub.id,
        is_correct=False,
        occurred_at=now - timedelta(days=2),
    )
    # Physics evidence at T2 (newer!)
    ev_phy = _create_evidence(
        db_session,
        student.id,
        phy_sub.id,
        is_correct=False,
        occurred_at=now - timedelta(minutes=10),
    )

    diag = RootCauseDiagnosis(
        student_id=student.id,
        subject_id=math_sub.id,
        learning_evidence_event_id=ev_math.id,
        target_problem_type_id=math_pt.id,
        diagnosis_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        status=RootCauseDiagnosisStatus.STRONG_HYPOTHESIS,
        confidence=0.8,
        supporting_evidence_count=1,
        reason_code="MATH_GAP",
    )
    db_session.add(diag)
    db_session.flush()

    ver_ps = _create_practice_session(db_session, student.id, math_sub.id, PracticeSessionType.ROOT_CAUSE_VERIFICATION)
    ver = RootCauseVerification(
        diagnosis_id=diag.id,
        practice_session_id=ver_ps.id,
        status=RootCauseVerificationStatus.COMPLETED,
        required_probe_count=2,
        completed_probe_count=2,
    )
    db_session.add(ver)
    db_session.flush()

    target = RootCauseVerificationTarget(
        verification_id=ver.id,
        target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        target_problem_type_id=math_pt.id,
        priority_order=1,
        outcome=RootCauseVerificationOutcome.SUPPORTED,
    )
    db_session.add(target)
    db_session.flush()

    rep_ps = _create_practice_session(db_session, student.id, math_sub.id, PracticeSessionType.REPAIR)
    repair = AdaptiveRepairSession(
        practice_session_id=rep_ps.id,
        student_id=student.id,
        subject_id=math_sub.id,
        diagnosis_id=diag.id,
        verification_id=ver.id,
        verification_target_id=target.id,
        target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        target_problem_type_id=math_pt.id,
        target_name=math_pt.name,
        target_code=math_pt.code,
        status=AdaptiveRepairStatus.ACTIVE,
        phase=AdaptiveRepairPhase.TARGET_PRACTICE,
        outcome=AdaptiveRepairOutcome.PENDING,
        repair_cycle_index=1,
        initial_difficulty=0.4,
        current_difficulty=0.5,
        target_exit_difficulty=0.7,
        max_questions=8,
    )
    db_session.add(repair)
    db_session.commit()

    # Call without subject_id
    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["focus_subject_id"] == str(math_sub.id)
    assert data["current_action"]["action_type"] == "CONTINUE_REPAIR"


# -----------------------------------------------------------------------------
# 14. Focus subject resolution: Latest evidence when no active repair/ver/assignment
# -----------------------------------------------------------------------------
def test_focus_subject_latest_evidence(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "focus_ev@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    math_sub, _, _, _, _ = create_curriculum(db_session, "EMATH")
    phy_sub, _, _, _, _ = create_curriculum(db_session, "EPHYS")

    _create_evidence(
        db_session,
        student.id,
        math_sub.id,
        is_correct=True,
        occurred_at=now - timedelta(hours=2),
    )
    _create_evidence(
        db_session,
        student.id,
        phy_sub.id,
        is_correct=True,
        occurred_at=now - timedelta(hours=1),  # Newer!
    )
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["focus_subject_id"] == str(phy_sub.id)


# -----------------------------------------------------------------------------
# 15. No question answer leak
# -----------------------------------------------------------------------------
def test_no_question_answer_leak(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    student_user = user_factory(Role.STUDENT, "leak_test@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, _, _, pt, _ = create_curriculum(db_session, "LEAK")
    _create_question(db_session, subject.id)
    _create_practice_session(db_session, student.id, subject.id, PracticeSessionType.PRACTICE)
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200

    def assert_no_sensitive_keys(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                assert k not in ("correct_answer", "student_answer", "answer_key", "explanation")
                assert_no_sensitive_keys(v)
        elif isinstance(obj, list):
            for item in obj:
                assert_no_sensitive_keys(item)

    assert_no_sensitive_keys(res.json())


# -----------------------------------------------------------------------------
# 16. Authorization: Student only, missing profile -> 404 STUDENT_PROFILE_NOT_FOUND
# -----------------------------------------------------------------------------
def test_authorization_and_missing_profile(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
):
    # Teacher user
    teacher_user = user_factory(Role.TEACHER, "teacher_sls@example.com")
    t_headers = auth_bearer(teacher_user)

    res_teacher = db_client.get("/students/me/learning-state", headers=t_headers)
    assert res_teacher.status_code == 403

    # Student user whose StudentProfile is deleted
    student_user = user_factory(Role.STUDENT, "deleted_prof@example.com")
    s_headers = auth_bearer(student_user)

    profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == student_user.id))
    db_session.delete(profile)
    db_session.commit()

    res_missing = db_client.get("/students/me/learning-state", headers=s_headers)
    assert res_missing.status_code == 404
    assert res_missing.json()["error"]["code"] == "STUDENT_PROFILE_NOT_FOUND"


# -----------------------------------------------------------------------------
# 17. State transition integration
# -----------------------------------------------------------------------------
def test_state_transition_integration(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "transition@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, chapter, topic, pt, concept = create_curriculum(db_session, "TRAN")

    # Step 1: Weak evidence -> LEARNING_PRIORITY
    pm = StudentProblemTypeMastery(
        student_id=student.id,
        problem_type_id=pt.id,
        mastery_score=0.2,
        confidence=0.5,
        attempt_count=3,
        correct_count=0,
        last_practiced_at=now,
    )
    db_session.add(pm)
    db_session.commit()

    r1 = db_client.get("/students/me/learning-state", headers=headers)
    assert r1.status_code == 200
    assert r1.json()["current_action"]["action_type"] == "LEARNING_PRIORITY"

    # Step 2: Verification ACTIVE -> CONTINUE_VERIFICATION
    ev = _create_evidence(
        db_session,
        student.id,
        subject.id,
        is_correct=False,
    )

    diag = RootCauseDiagnosis(
        student_id=student.id,
        subject_id=subject.id,
        learning_evidence_event_id=ev.id,
        target_problem_type_id=pt.id,
        diagnosis_type=RootCauseDiagnosisType.PREREQUISITE_CONCEPT_GAP,
        status=RootCauseDiagnosisStatus.STRONG_HYPOTHESIS,
        confidence=0.9,
        supporting_evidence_count=1,
        reason_code="GAP",
    )
    db_session.add(diag)
    db_session.flush()

    ver_ps = _create_practice_session(db_session, student.id, subject.id, PracticeSessionType.ROOT_CAUSE_VERIFICATION)
    ver = RootCauseVerification(
        diagnosis_id=diag.id,
        practice_session_id=ver_ps.id,
        status=RootCauseVerificationStatus.ACTIVE,
        required_probe_count=3,
        completed_probe_count=1,
    )
    db_session.add(ver)
    db_session.commit()

    r2 = db_client.get("/students/me/learning-state", headers=headers)
    assert r2.status_code == 200
    assert r2.json()["current_action"]["action_type"] == "CONTINUE_VERIFICATION"

    # Step 3: Verification completed + Repair started -> CONTINUE_REPAIR
    ver.status = RootCauseVerificationStatus.COMPLETED
    ver.completed_probe_count = 3
    ver.completed_at = now

    target = RootCauseVerificationTarget(
        verification_id=ver.id,
        target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        target_problem_type_id=pt.id,
        outcome=RootCauseVerificationOutcome.SUPPORTED,
    )
    db_session.add(target)
    db_session.flush()

    rep_ps = _create_practice_session(db_session, student.id, subject.id, PracticeSessionType.REPAIR)
    repair = AdaptiveRepairSession(
        practice_session_id=rep_ps.id,
        student_id=student.id,
        subject_id=subject.id,
        diagnosis_id=diag.id,
        verification_id=ver.id,
        verification_target_id=target.id,
        target_type=RootCauseVerificationTargetType.PROBLEM_TYPE,
        target_problem_type_id=pt.id,
        target_name=pt.name,
        target_code=pt.code,
        status=AdaptiveRepairStatus.ACTIVE,
        phase=AdaptiveRepairPhase.TARGET_PRACTICE,
        outcome=AdaptiveRepairOutcome.PENDING,
        repair_cycle_index=1,
        initial_difficulty=0.4,
        current_difficulty=0.5,
        target_exit_difficulty=0.7,
        max_questions=8,
    )
    db_session.add(repair)
    db_session.commit()

    r3 = db_client.get("/students/me/learning-state", headers=headers)
    assert r3.status_code == 200
    assert r3.json()["current_action"]["action_type"] == "CONTINUE_REPAIR"

    # Step 4: Repair completed with RESOLVED, Review scheduled -> REVIEW_DUE
    repair.status = AdaptiveRepairStatus.COMPLETED
    repair.outcome = AdaptiveRepairOutcome.RESOLVED
    repair.completed_at = now

    rev = ReviewSchedule(
        student_id=student.id,
        problem_type_id=pt.id,
        next_review_at=now - timedelta(minutes=5),
        review_interval_days=1.0,
    )
    db_session.add(rev)
    db_session.commit()

    r4 = db_client.get("/students/me/learning-state", headers=headers)
    assert r4.status_code == 200
    assert r4.json()["current_action"]["action_type"] == "REVIEW_DUE"


# -----------------------------------------------------------------------------
# 18. StudyTask Subject Isolation & Resolution
# -----------------------------------------------------------------------------
def test_subjectless_problem_type_task_is_resolved_to_its_real_subject(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "sls_pt_leak@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    math_sub, _, _, math_pt, _ = create_curriculum(db_session, "MATHLK")
    phy_sub, _, _, phy_pt, _ = create_curriculum(db_session, "PHYLK")

    # Give student evidence in both subjects so both are available
    _create_evidence(db_session, student.id, math_sub.id, is_correct=True)
    _create_evidence(db_session, student.id, phy_sub.id, is_correct=True)

    # Active StudyPlan
    plan = StudyPlan(student_id=student.id, start_date=now.date(), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()

    # Task with subject_id = NULL, but problem_type_id = Physics PT
    phy_task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=now.date(),
        problem_type_id=phy_pt.id,
        subject_id=None,  # NULL!
        estimated_duration_minutes=25,
        priority=60,
        order_index=0,
        reason_code="PHYSICS_WEAKNESS",
    )
    db_session.add(phy_task)
    db_session.commit()

    # GET learning-state focused on Math
    res = db_client.get(f"/students/me/learning-state?subject_id={math_sub.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()

    # Today plan exists, but Physics task is absent from Math today's plan
    assert data["today_plan"] is not None
    assert all(t["id"] != str(phy_task.id) for t in data["today_plan"]["tasks"])
    assert data["today_plan"]["total_count"] == 0

    # Physics task must NEVER become TODAY_TASK for Math
    assert data["current_action"]["action_type"] != "TODAY_TASK"


def test_subjectless_problem_type_task_is_kept_when_target_matches_focus_subject(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "sls_pt_match@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    math_sub, _, _, math_pt, _ = create_curriculum(db_session, "MATHM")
    _create_evidence(db_session, student.id, math_sub.id, is_correct=True)

    plan = StudyPlan(student_id=student.id, start_date=now.date(), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()

    # Task with subject_id = NULL, problem_type_id = Math PT
    math_task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=now.date(),
        problem_type_id=math_pt.id,
        subject_id=None,  # NULL!
        estimated_duration_minutes=20,
        priority=75,
        order_index=0,
        reason_code="MATH_PRACTICE",
    )
    db_session.add(math_task)
    db_session.commit()

    res = db_client.get(f"/students/me/learning-state?subject_id={math_sub.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["today_plan"] is not None
    assert any(t["id"] == str(math_task.id) for t in data["today_plan"]["tasks"])
    assert data["today_plan"]["total_count"] == 1
    assert data["current_action"]["action_type"] == "TODAY_TASK"
    assert data["current_action"]["study_task_id"] == str(math_task.id)


def test_subjectless_concept_task_resolves_subject_from_concept(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "sls_concept_iso@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    math_sub, _, _, _, math_concept = create_curriculum(db_session, "MCON")
    phy_sub, _, _, _, _ = create_curriculum(db_session, "PCON")

    _create_evidence(db_session, student.id, math_sub.id, is_correct=True)
    _create_evidence(db_session, student.id, phy_sub.id, is_correct=True)

    plan = StudyPlan(student_id=student.id, start_date=now.date(), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()

    # Task with subject_id = NULL, concept_id = Math Concept
    concept_task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.LEARN,
        status=StudyTaskStatus.PENDING,
        planned_date=now.date(),
        concept_id=math_concept.id,
        problem_type_id=None,
        subject_id=None,  # NULL!
        estimated_duration_minutes=15,
        priority=80,
        order_index=0,
        reason_code="CONCEPT_REVIEW",
    )
    db_session.add(concept_task)
    db_session.commit()

    # Math focus: included
    res_math = db_client.get(f"/students/me/learning-state?subject_id={math_sub.id}", headers=headers)
    assert res_math.status_code == 200
    data_math = res_math.json()
    assert any(t["id"] == str(concept_task.id) for t in data_math["today_plan"]["tasks"])
    assert data_math["current_action"]["action_type"] == "TODAY_TASK"

    # Physics focus: excluded
    res_phy = db_client.get(f"/students/me/learning-state?subject_id={phy_sub.id}", headers=headers)
    assert res_phy.status_code == 200
    data_phy = res_phy.json()
    assert all(t["id"] != str(concept_task.id) for t in data_phy["today_plan"]["tasks"])
    assert data_phy["today_plan"]["total_count"] == 0
    assert data_phy["current_action"]["action_type"] != "TODAY_TASK"


def test_subject_specific_state_excludes_unscoped_subjectless_task(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "sls_unscoped@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    math_sub, _, _, math_pt, _ = create_curriculum(db_session, "UNSC")
    _create_evidence(db_session, student.id, math_sub.id, is_correct=True)

    plan = StudyPlan(student_id=student.id, start_date=now.date(), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()

    # Completely unresolvable task: subject_id=NULL, problem_type_id=NULL, concept_id=NULL
    unresolvable_task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=now.date(),
        problem_type_id=None,
        concept_id=None,
        subject_id=None,
        estimated_duration_minutes=30,
        priority=50,
        order_index=0,
        reason_code="GENERAL_STUDY",
    )
    db_session.add(unresolvable_task)
    db_session.commit()

    res = db_client.get(f"/students/me/learning-state?subject_id={math_sub.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["today_plan"] is not None
    assert all(t["id"] != str(unresolvable_task.id) for t in data["today_plan"]["tasks"])
    assert data["today_plan"]["total_count"] == 0
    assert data["current_action"]["action_type"] != "TODAY_TASK"


def test_subjectless_task_with_conflicting_targets_is_excluded(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "sls_conflict@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    math_sub, _, _, math_pt, _ = create_curriculum(db_session, "CONF_M")
    phy_sub, _, _, _, phy_concept = create_curriculum(db_session, "CONF_P")

    _create_evidence(db_session, student.id, math_sub.id, is_correct=True)
    _create_evidence(db_session, student.id, phy_sub.id, is_correct=True)

    plan = StudyPlan(student_id=student.id, start_date=now.date(), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()

    # Conflicting targets: math PT, physics Concept, subject_id=None
    conflict_task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=now.date(),
        problem_type_id=math_pt.id,
        concept_id=phy_concept.id,
        subject_id=None,
        estimated_duration_minutes=20,
        priority=60,
        order_index=0,
        reason_code="CONFLICTING",
    )
    db_session.add(conflict_task)
    db_session.commit()

    # Excluded from both Math and Physics
    res_m = db_client.get(f"/students/me/learning-state?subject_id={math_sub.id}", headers=headers)
    assert res_m.status_code == 200
    assert all(t["id"] != str(conflict_task.id) for t in res_m.json()["today_plan"]["tasks"])

    res_p = db_client.get(f"/students/me/learning-state?subject_id={phy_sub.id}", headers=headers)
    assert res_p.status_code == 200
    assert all(t["id"] != str(conflict_task.id) for t in res_p.json()["today_plan"]["tasks"])


# -----------------------------------------------------------------------------
# 19. Explicit Read-Only Invariant Tests
# -----------------------------------------------------------------------------
def test_learning_state_does_not_create_study_plan(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    student_user = user_factory(Role.STUDENT, "sls_no_plan@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, _, _, pt, _ = create_curriculum(db_session, "NOPLAN")
    _create_evidence(db_session, student.id, subject.id, is_correct=True)
    db_session.commit()

    plans_before = db_session.scalar(
        select(func.count(StudyPlan.id)).where(StudyPlan.student_id == student.id)
    )
    tasks_before = db_session.scalar(select(func.count(StudyTask.id)))
    assert plans_before == 0

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    assert res.json()["today_plan"] is None

    plans_after = db_session.scalar(
        select(func.count(StudyPlan.id)).where(StudyPlan.student_id == student.id)
    )
    tasks_after = db_session.scalar(select(func.count(StudyTask.id)))
    assert plans_after == 0
    assert tasks_after == tasks_before


def test_learning_state_does_not_mark_past_task_skipped(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "sls_no_skip@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, _, _, pt, _ = create_curriculum(db_session, "NOSKIP")
    _create_evidence(db_session, student.id, subject.id, is_correct=True)

    plan = StudyPlan(student_id=student.id, start_date=now.date() - timedelta(days=3), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()

    past_task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=now.date() - timedelta(days=2),
        problem_type_id=pt.id,
        subject_id=subject.id,
        estimated_duration_minutes=20,
        priority=70,
        order_index=0,
        reason_code="PAST_PENDING",
    )
    db_session.add(past_task)
    db_session.commit()

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200

    db_session.refresh(past_task)
    # Must NOT be marked SKIPPED by GET endpoint
    assert past_task.status == StudyTaskStatus.PENDING


def test_learning_state_does_not_recalculate_empty_today(
    db_client: TestClient,
    db_session: Session,
    user_factory,
    auth_bearer,
    student_profile_getter,
):
    now = datetime.now(timezone.utc)
    student_user = user_factory(Role.STUDENT, "sls_empty_today@example.com")
    student = student_profile_getter(student_user)
    headers = auth_bearer(student_user)

    subject, _, _, pt, _ = create_curriculum(db_session, "EMPTYTD")
    _create_evidence(db_session, student.id, subject.id, is_correct=True)

    plan = StudyPlan(student_id=student.id, start_date=now.date(), status=StudyPlanStatus.ACTIVE)
    db_session.add(plan)
    db_session.flush()

    # Tomorrow's task only (today has NO tasks)
    tomorrow_task = StudyTask(
        study_plan_id=plan.id,
        task_type=StudyTaskType.PRACTICE,
        status=StudyTaskStatus.PENDING,
        planned_date=now.date() + timedelta(days=1),
        problem_type_id=pt.id,
        subject_id=subject.id,
        estimated_duration_minutes=20,
        priority=70,
        order_index=0,
        reason_code="TOMORROW",
    )
    db_session.add(tomorrow_task)
    db_session.commit()

    task_count_before = db_session.scalar(
        select(func.count(StudyTask.id)).where(StudyTask.study_plan_id == plan.id)
    )

    res = db_client.get("/students/me/learning-state", headers=headers)
    assert res.status_code == 200
    data = res.json()

    assert data["today_plan"] is not None
    assert data["today_plan"]["total_count"] == 0
    assert len(data["today_plan"]["tasks"]) == 0

    task_count_after = db_session.scalar(
        select(func.count(StudyTask.id)).where(StudyTask.study_plan_id == plan.id)
    )
    # No tasks generated or recalculated
    assert task_count_after == task_count_before

