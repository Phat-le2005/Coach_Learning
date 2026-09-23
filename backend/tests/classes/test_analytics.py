from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

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
from app.core.config import Settings
from app.curriculum.models import Chapter, ProblemType, Topic
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
    PracticeSessionProblemType,
    PracticeSessionStatus,
    PracticeSessionType,
    QuestionAttempt,
)
from app.planning.study_models import StudyPlan, StudyPlanStatus, StudyTask, StudyTaskStatus, StudyTaskType
from app.questions.models import Question, QuestionStatus, QuestionType
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

    # T1 creates class
    classroom = Classroom(name="12A1 T1", academic_year="2026-2027", grade_level=12, created_by=t1_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t1_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.commit()

    # T2 tries to access T1's classroom analytics -> 403
    t2_headers = classroom_bearer(t2_user)
    res_forbidden = db_client.get(f"/teacher/classes/{classroom.id}/analytics", headers=t2_headers)
    assert res_forbidden.status_code == 403

    # T1 accesses own classroom analytics -> 200
    t1_headers = classroom_bearer(t1_user)
    res_ok = db_client.get(f"/teacher/classes/{classroom.id}/analytics", headers=t1_headers)
    assert res_ok.status_code == 200
    data = res_ok.json()
    assert data["classroom_id"] == str(classroom.id)
    assert data["student_count"] == 0


# --------------------------------------------------------------------------
# 2. Dashboard Metrics Calculation (Deterministic - No AI)
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

    # Add second problem type (strong)
    pt_strong = ProblemType(
        topic_id=topic.id,
        code="DSH-PT-EASY",
        name="Xét tính đơn điệu hàm đa thức",
        order_index=1,
        is_active=True,
    )
    db_session.add(pt_strong)
    db_session.flush()

    # Create classroom and enroll students
    classroom = Classroom(name="12A3 Dashboard", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add_all([
        StudentEnrollment(student_id=s1_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
        StudentEnrollment(student_id=s2_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
    ])

    now = datetime.now(timezone.utc)

    # Masteries:
    # pt is weak (avg (0.30 + 0.40) / 2 = 0.35 < 0.50)
    # pt_strong is strong (avg (0.80 + 0.90) / 2 = 0.85 >= 0.70)
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

    # Misconception setup
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

    # Study tasks: 2 completed out of 3 assigned
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

    # 1. Student count
    assert data["student_count"] == 2

    # 2. Strong & Weak ProblemTypes
    assert len(data["strong_problem_types"]) >= 1
    assert data["strong_problem_types"][0]["name"] == pt_strong.name
    assert data["strong_problem_types"][0]["average_score"] == 0.85

    assert len(data["weak_problem_types"]) >= 1
    assert data["weak_problem_types"][0]["name"] == pt.name
    assert data["weak_problem_types"][0]["average_score"] == 0.35

    # 3. Common misconceptions
    assert len(data["common_misconceptions"]) >= 1
    misc = data["common_misconceptions"][0]
    assert misc["code"] == "DSH_MISC_01"
    assert misc["affected_students_count"] == 2

    # 4. Study completion
    assert data["study_completion"]["assigned_tasks_count"] == 3
    assert data["study_completion"]["completed_tasks_count"] == 2
    assert data["study_completion"]["completion_rate"] == 66.7


# --------------------------------------------------------------------------
# 3. Multi-view Heatmap (problem_type, concept, topic, chapter)
# --------------------------------------------------------------------------


def test_classroom_heatmap_views(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_heat@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_heat@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, chapter, topic, pt, concept = _setup_curriculum(db_session, "HMP")

    classroom = Classroom(name="12A Heatmap", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    now = datetime.now(timezone.utc)
    db_session.add_all([
        StudentProblemTypeMastery(
            student_id=s_prof.id, problem_type_id=pt.id, mastery_score=0.85, confidence=0.9,
            attempt_count=10, correct_count=9, last_practiced_at=now,
        ),
        StudentConceptMastery(
            student_id=s_prof.id, concept_id=concept.id, mastery_score=0.45, confidence=0.8,
            attempt_count=4, correct_count=2, last_practiced_at=now,
        ),
    ])
    db_session.commit()

    headers = classroom_bearer(t_user)

    # 1. view=problem_type
    res_pt = db_client.get(f"/teacher/classes/{classroom.id}/heatmap?view=problem_type", headers=headers)
    assert res_pt.status_code == 200
    d_pt = res_pt.json()
    assert d_pt["view"] == "problem_type"
    assert len(d_pt["rows"]) == 1
    assert any(c["id"] == str(pt.id) for c in d_pt["columns"])
    pt_cell = next(c for c in d_pt["cells"] if c["column_id"] == str(pt.id))
    assert pt_cell["score"] == 0.85
    assert pt_cell["level"] == MasteryLevel.MASTERED.value

    # 2. view=concept
    res_c = db_client.get(f"/teacher/classes/{classroom.id}/heatmap?view=concept", headers=headers)
    assert res_c.status_code == 200
    d_c = res_c.json()
    assert d_c["view"] == "concept"
    c_cell = next(c for c in d_c["cells"] if c["column_id"] == str(concept.id))
    assert c_cell["score"] == 0.45
    assert c_cell["level"] == MasteryLevel.STRUGGLING.value

    # 3. view=topic (aggregates problem types)
    res_t = db_client.get(f"/teacher/classes/{classroom.id}/heatmap?view=topic", headers=headers)
    assert res_t.status_code == 200
    d_t = res_t.json()
    assert d_t["view"] == "topic"
    t_cell = next(c for c in d_t["cells"] if c["column_id"] == str(topic.id))
    assert t_cell["score"] == 0.85

    # 4. view=chapter (aggregates problem types)
    res_ch = db_client.get(f"/teacher/classes/{classroom.id}/heatmap?view=chapter", headers=headers)
    assert res_ch.status_code == 200
    d_ch = res_ch.json()
    assert d_ch["view"] == "chapter"
    ch_cell = next(c for c in d_ch["cells"] if c["column_id"] == str(chapter.id))
    assert ch_cell["score"] == 0.85


# --------------------------------------------------------------------------
# 4. Intervention Rules: LOW_PROBLEM_TYPE_MASTERY
# --------------------------------------------------------------------------


def test_intervention_rule_low_problem_type_mastery(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_alert1@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_alert1@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, chapter, topic, pt, _ = _setup_curriculum(db_session, "AL1")

    classroom = Classroom(name="Class Alert 1", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Low mastery (< 0.40) with attempt_count >= 3
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_prof.id, problem_type_id=pt.id, mastery_score=0.20, confidence=0.8,
            attempt_count=4, correct_count=0, last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    service = ClassAnalyticsService(db_session)
    alerts_data = service.get_classroom_alerts(t_user.id, classroom.id)

    assert any(a.rule_code == AlertRuleCode.LOW_PROBLEM_TYPE_MASTERY for a in alerts_data.alerts)
    target_alert = next(a for a in alerts_data.alerts if a.rule_code == AlertRuleCode.LOW_PROBLEM_TYPE_MASTERY)
    assert target_alert.severity == AlertSeverity.CRITICAL
    assert target_alert.target_name == pt.name


# --------------------------------------------------------------------------
# 5. Intervention Rules: PREREQUISITE_GAP
# --------------------------------------------------------------------------


def test_intervention_rule_prerequisite_gap(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_alert2@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_alert2@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, _, prereq_concept = _setup_curriculum(db_session, "AL2")

    target_concept = Concept(subject_id=subject.id, code="AL2-CON-MAIN", name="Tính đơn điệu nâng cao", order_index=1)
    db_session.add(target_concept)
    db_session.flush()

    # Link prereq_concept as PREREQUISITE to target_concept
    db_session.add(
        ConceptRelation(
            source_concept_id=prereq_concept.id,
            target_concept_id=target_concept.id,
            relation_type=RelationType.PREREQUISITE,
        )
    )

    classroom = Classroom(name="Class Alert 2", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Prerequisite concept mastery < 0.50
    db_session.add(
        StudentConceptMastery(
            student_id=s_prof.id, concept_id=prereq_concept.id, mastery_score=0.35, confidence=0.85,
            attempt_count=5, correct_count=1, last_practiced_at=datetime.now(timezone.utc),
        )
    )
    db_session.commit()

    service = ClassAnalyticsService(db_session)
    alerts_data = service.get_classroom_alerts(t_user.id, classroom.id)

    assert any(a.rule_code == AlertRuleCode.PREREQUISITE_GAP for a in alerts_data.alerts)
    alert = next(a for a in alerts_data.alerts if a.rule_code == AlertRuleCode.PREREQUISITE_GAP)
    assert alert.severity == AlertSeverity.HIGH
    assert alert.target_name == prereq_concept.name


# --------------------------------------------------------------------------
# 6. Intervention Rules: FAILED_REPAIR
# --------------------------------------------------------------------------


def test_intervention_rule_failed_repair(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_alert4@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_alert4@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, pt, _ = _setup_curriculum(db_session, "AL4")

    classroom = Classroom(name="Class Alert 4", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Create 3 failed repair sessions targeting the same ProblemType
    question = Question(
        subject_id=subject.id, content="Repair q?", content_hash=f"{uuid4().hex}{uuid4().hex}",
        question_type=QuestionType.MULTIPLE_CHOICE, difficulty=0.5, correct_answer="A",
        source_type="TEST", exam_weight=1.0, status=QuestionStatus.APPROVED, created_by=t_user.id,
    )
    db_session.add(question)
    db_session.flush()

    for i in range(3):
        ps = PracticeSession(
            student_id=s_prof.id,
            subject_id=subject.id,
            session_type=PracticeSessionType.REPAIR,
            status=PracticeSessionStatus.COMPLETED,
            completed_at=datetime.now(timezone.utc),
        )
        db_session.add(ps)
        db_session.flush()
        db_session.add(PracticeSessionProblemType(practice_session_id=ps.id, problem_type_id=pt.id))

        # Failed attempt (score 0.0)
        db_session.add(
            QuestionAttempt(
                practice_session_id=ps.id, student_id=s_prof.id, question_id=question.id,
                student_answer="B", is_correct=False, score=0.0, attempt_number=1,
                evaluation_status=EvaluationStatus.AUTO_EVALUATED,
            )
        )

    db_session.commit()

    service = ClassAnalyticsService(db_session)
    alerts_data = service.get_classroom_alerts(t_user.id, classroom.id)

    assert any(a.rule_code == AlertRuleCode.FAILED_REPAIR for a in alerts_data.alerts)
    alert = next(a for a in alerts_data.alerts if a.rule_code == AlertRuleCode.FAILED_REPAIR)
    assert alert.severity == AlertSeverity.CRITICAL
    assert alert.target_name == pt.name


# --------------------------------------------------------------------------
# 7. Intervention Rules: DECLINING_PERFORMANCE
# --------------------------------------------------------------------------


def test_intervention_rule_declining_performance(
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_alert5@example.com")
    s_user = classroom_user_factory(Role.STUDENT, "s_alert5@example.com")
    t_prof = teacher_profile(t_user)
    s_prof = student_profile(s_user)

    subject, _, _, _, _ = _setup_curriculum(db_session, "AL5")

    classroom = Classroom(name="Class Alert 5", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add(StudentEnrollment(student_id=s_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE))

    # Create 6 attempts: First 3 score 1.0, last 3 score 0.3 (drop = 70% >= 20%)
    ps = PracticeSession(student_id=s_prof.id, subject_id=subject.id, session_type=PracticeSessionType.PRACTICE)
    db_session.add(ps)
    db_session.flush()

    base_time = datetime.now(timezone.utc) - timedelta(hours=10)
    for i in range(6):
        score = 1.0 if i < 3 else 0.3
        q = Question(
            subject_id=subject.id, content=f"Q{i}", content_hash=f"{uuid4().hex}{uuid4().hex}",
            question_type=QuestionType.MULTIPLE_CHOICE, difficulty=0.5, correct_answer="A",
            source_type="TEST", exam_weight=1.0, status=QuestionStatus.APPROVED, created_by=t_user.id,
        )
        db_session.add(q)
        db_session.flush()

        att = QuestionAttempt(
            practice_session_id=ps.id, student_id=s_prof.id, question_id=q.id,
            student_answer="A" if score == 1.0 else "B", is_correct=score == 1.0, score=score,
            attempt_number=i + 1, evaluation_status=EvaluationStatus.AUTO_EVALUATED,
            created_at=base_time + timedelta(hours=i),
        )
        db_session.add(att)

    db_session.commit()

    service = ClassAnalyticsService(db_session)
    alerts_data = service.get_classroom_alerts(t_user.id, classroom.id)

    assert any(a.rule_code == AlertRuleCode.DECLINING_PERFORMANCE for a in alerts_data.alerts)
    alert = next(a for a in alerts_data.alerts if a.rule_code == AlertRuleCode.DECLINING_PERFORMANCE)
    assert alert.severity == AlertSeverity.MEDIUM


# --------------------------------------------------------------------------
# 8. Synthetic Data Filtering
# --------------------------------------------------------------------------


def test_synthetic_data_filtering_in_analytics(
    db_client: TestClient,
    db_session: Session,
    classroom_user_factory: Callable[[Role, str], User],
    classroom_bearer: Callable[[User], dict[str, str]],
    teacher_profile: Callable[[User], TeacherProfile],
    student_profile: Callable[[User], StudentProfile],
) -> None:
    t_user = classroom_user_factory(Role.TEACHER, "t_syn@example.com")
    real_user = classroom_user_factory(Role.STUDENT, "real_student@example.com")
    syn_user = classroom_user_factory(Role.STUDENT, "syn_student@example.com")

    t_prof = teacher_profile(t_user)
    real_prof = student_profile(real_user)
    syn_prof = student_profile(syn_user)

    # Mark syn_prof as synthetic
    syn_prof.is_synthetic = True
    syn_prof.synthetic_profile = "WEAK"
    db_session.flush()

    classroom = Classroom(name="Class Syn Test", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()
    db_session.add(TeacherClassroom(teacher_id=t_prof.id, classroom_id=classroom.id, role="OWNER"))
    db_session.add_all([
        StudentEnrollment(student_id=real_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
        StudentEnrollment(student_id=syn_prof.id, classroom_id=classroom.id, status=EnrollmentStatus.ACTIVE),
    ])
    db_session.commit()

    headers = classroom_bearer(t_user)

    # 1. Default (include_synthetic=False): Only 1 real student
    res_default = db_client.get(f"/teacher/classes/{classroom.id}/analytics", headers=headers)
    assert res_default.status_code == 200
    assert res_default.json()["student_count"] == 1

    # 2. include_synthetic=True: Both students included (2)
    res_syn = db_client.get(f"/teacher/classes/{classroom.id}/analytics?include_synthetic=true", headers=headers)
    assert res_syn.status_code == 200
    assert res_syn.json()["student_count"] == 2
