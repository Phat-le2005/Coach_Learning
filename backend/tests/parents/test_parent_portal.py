from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.assignments.models import Assignment, AssignmentStatus, AssignmentType, StudentAssignment, StudentAssignmentStatus
from app.attempts.models import StudySession
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.parents.models import ParentProfile, ParentStudentRelationship
from app.planning.study_models import StudyPlan, StudyPlanStatus, StudyTask, StudyTaskReasonCode, StudyTaskStatus, StudyTaskType
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType, QuestionAttempt
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User


def _setup_curriculum(
    session: Session, prefix: str = "PAR"
) -> tuple[Subject, Chapter, Topic, ProblemType, Concept]:
    subject = Subject(code=f"{prefix}-MATH", name=f"{prefix} Toan 12", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{prefix}-CHP1", name=f"{prefix} Giai Tich", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{prefix}-TOP1", name=f"{prefix} Tinh don dieu", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT-PARAM",
        name="Tim tham so ve tinh don dieu",
        order_index=0,
        is_active=True,
    )
    concept = Concept(
        subject_id=subject.id,
        code=f"{prefix}-CON-INEQ",
        name="Giai bat phuong trinh",
        order_index=0,
    )
    session.add_all([pt, concept])
    session.flush()

    session.add(ProblemTypeConcept(problem_type_id=pt.id, concept_id=concept.id, weight=1.0, is_primary=True))
    session.flush()
    return subject, chapter, topic, pt, concept


# --------------------------------------------------------------------------
# 1. Authorization Tests (Rất kỹ)
# --------------------------------------------------------------------------

def test_parent_authorization_strict_checks(
    db_client: TestClient,
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_bearer: Callable[[User], dict[str, str]],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p1_user = parent_user_factory(Role.PARENT, "p1_auth@example.com")
    p2_user = parent_user_factory(Role.PARENT, "p2_auth@example.com")
    s1_user = parent_user_factory(Role.STUDENT, "s1_auth@example.com")
    s2_user = parent_user_factory(Role.STUDENT, "s2_auth@example.com")
    t_user = parent_user_factory(Role.TEACHER, "t_auth@example.com")

    p1_prof = parent_profile_helper(p1_user)
    p2_prof = parent_profile_helper(p2_user)
    s1_prof = student_profile_helper(s1_user)
    s2_prof = student_profile_helper(s2_user)

    # Relationship: P1 is mother of S1 (active)
    rel_p1_s1 = ParentStudentRelationship(
        parent_id=p1_prof.id,
        student_id=s1_prof.id,
        relationship_type="MOTHER",
        is_active=True,
    )
    # Relationship: P1 was guardian of S2 but is now INACTIVE
    rel_p1_s2_inactive = ParentStudentRelationship(
        parent_id=p1_prof.id,
        student_id=s2_prof.id,
        relationship_type="GUARDIAN",
        is_active=False,
    )
    # Relationship: P2 is father of S2 (active)
    rel_p2_s2 = ParentStudentRelationship(
        parent_id=p2_prof.id,
        student_id=s2_prof.id,
        relationship_type="FATHER",
        is_active=True,
    )
    db_session.add_all([rel_p1_s1, rel_p1_s2_inactive, rel_p2_s2])
    db_session.commit()

    p1_headers = parent_bearer(p1_user)
    p2_headers = parent_bearer(p2_user)
    s_headers = parent_bearer(s1_user)
    t_headers = parent_bearer(t_user)

    # 1. Unauthenticated request -> 401
    res_unauth = db_client.get("/parent/students")
    assert res_unauth.status_code == 401

    # 2. Student or Teacher calling parent endpoint -> 403
    assert db_client.get("/parent/students", headers=s_headers).status_code == 403
    assert db_client.get("/parent/students", headers=t_headers).status_code == 403

    # 3. P1 lists students -> only S1 returned (S2 is inactive)
    res_p1_list = db_client.get("/parent/students", headers=p1_headers)
    assert res_p1_list.status_code == 200
    p1_students = res_p1_list.json()
    assert len(p1_students) == 1
    assert p1_students[0]["student_id"] == str(s1_prof.id)
    assert p1_students[0]["relationship_type"] == "MOTHER"

    # 4. P1 accesses linked student S1 -> 200 OK
    res_p1_s1_progress = db_client.get(f"/parent/students/{s1_prof.id}/progress", headers=p1_headers)
    assert res_p1_s1_progress.status_code == 200
    assert res_p1_s1_progress.json()["student_id"] == str(s1_prof.id)

    res_p1_s1_weekly = db_client.get(f"/parent/students/{s1_prof.id}/weekly-data", headers=p1_headers)
    assert res_p1_s1_weekly.status_code == 200

    # 5. P1 attempts to access inactive student S2 -> 403 Forbidden
    res_p1_s2_progress = db_client.get(f"/parent/students/{s2_prof.id}/progress", headers=p1_headers)
    assert res_p1_s2_progress.status_code == 403
    assert "RELATIONSHIP_INACTIVE" in res_p1_s2_progress.text

    # 6. P1 attempts to access unlinked random student -> 403 Forbidden
    res_p1_unlinked = db_client.get(f"/parent/students/{uuid4()}/progress", headers=p1_headers)
    assert res_p1_unlinked.status_code == 403
    assert "NOT_LINKED_TO_STUDENT" in res_p1_unlinked.text

    # 7. P2 attempts to access S1 (not P2's child) -> 403 Forbidden
    res_p2_s1 = db_client.get(f"/parent/students/{s1_prof.id}/progress", headers=p2_headers)
    assert res_p2_s1.status_code == 403
    assert "NOT_LINKED_TO_STUDENT" in res_p2_s1.text

    # 8. P2 accesses own child S2 -> 200 OK
    res_p2_s2 = db_client.get(f"/parent/students/{s2_prof.id}/progress", headers=p2_headers)
    assert res_p2_s2.status_code == 200


# --------------------------------------------------------------------------
# 2. Dashboard Aggregate Progress Data & Major Weak Areas Phrasing
# --------------------------------------------------------------------------

def test_parent_dashboard_progress_aggregation_and_phrasing(
    db_client: TestClient,
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_bearer: Callable[[User], dict[str, str]],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p_user = parent_user_factory(Role.PARENT, "p_dash@example.com")
    s_user = parent_user_factory(Role.STUDENT, "s_dash@example.com")
    t_user = parent_user_factory(Role.TEACHER, "t_dash@example.com")

    p_prof = parent_profile_helper(p_user)
    s_prof = student_profile_helper(s_user)

    db_session.add(
        ParentStudentRelationship(
            parent_id=p_prof.id,
            student_id=s_prof.id,
            relationship_type="FATHER",
            is_active=True,
        )
    )

    subject, chapter, topic, pt_param, concept_ineq = _setup_curriculum(db_session, "DASH")

    concept_target = Concept(
        subject_id=subject.id,
        code="DASH-CON-TARGET",
        name="Khao sat ham so",
        order_index=1,
    )
    db_session.add(concept_target)
    db_session.flush()

    # Prerequisite concept relation: concept_ineq is prerequisite for concept_target
    db_session.add(
        ConceptRelation(
            source_concept_id=concept_ineq.id,
            target_concept_id=concept_target.id,
            relation_type=RelationType.PREREQUISITE,
        )
    )

    # 1. Student has low mastery in pt_param: 0.32 (< 0.50, 4 attempts)
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_prof.id,
            problem_type_id=pt_param.id,
            mastery_score=0.32,
            confidence=0.85,
            attempt_count=4,
            correct_count=1,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )

    # 2. Student has low mastery in underlying prerequisite concept_ineq: 0.40 (< 0.50)
    db_session.add(
        StudentConceptMastery(
            student_id=s_prof.id,
            concept_id=concept_ineq.id,
            mastery_score=0.40,
            confidence=0.80,
            attempt_count=5,
            correct_count=2,
            last_practiced_at=datetime.now(timezone.utc),
        )
    )

    # 3. StudyPlan with 4 tasks: 3 completed, 1 pending (75% completion rate)
    plan = StudyPlan(student_id=s_prof.id, status=StudyPlanStatus.ACTIVE, start_date=date.today())
    db_session.add(plan)
    db_session.flush()

    t1 = StudyTask(study_plan_id=plan.id, task_type=StudyTaskType.LEARN, status=StudyTaskStatus.COMPLETED, planned_date=date.today(), estimated_duration_minutes=30, reason_code=StudyTaskReasonCode.GENERAL_PRACTICE)
    t2 = StudyTask(study_plan_id=plan.id, task_type=StudyTaskType.PRACTICE, status=StudyTaskStatus.COMPLETED, planned_date=date.today(), estimated_duration_minutes=30, reason_code=StudyTaskReasonCode.GENERAL_PRACTICE)
    t3 = StudyTask(study_plan_id=plan.id, task_type=StudyTaskType.REVIEW, status=StudyTaskStatus.COMPLETED, planned_date=date.today(), estimated_duration_minutes=30, reason_code=StudyTaskReasonCode.GENERAL_PRACTICE)
    t4 = StudyTask(study_plan_id=plan.id, task_type=StudyTaskType.REPAIR, status=StudyTaskStatus.PENDING, planned_date=date.today(), estimated_duration_minutes=30, reason_code=StudyTaskReasonCode.GENERAL_PRACTICE)
    db_session.add_all([t1, t2, t3, t4])

    # 4. Completed assignment (score 8.5)
    from app.classes.models import Classroom
    classroom = Classroom(name="12A1 Dash", academic_year="2026-2027", grade_level=12, created_by=t_user.id)
    db_session.add(classroom)
    db_session.flush()

    asg = Assignment(
        classroom_id=classroom.id,
        subject_id=subject.id,
        title="Kiem tra 15 phut Dao ham",
        assignment_type=AssignmentType.SAME_SET,
        status=AssignmentStatus.PUBLISHED,
        question_count=5,
        created_by=t_user.id,
    )
    db_session.add(asg)
    db_session.flush()

    sa = StudentAssignment(
        assignment_id=asg.id,
        student_id=s_prof.id,
        status=StudentAssignmentStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
        score=8.5,
    )
    db_session.add(sa)
    db_session.commit()

    p_headers = parent_bearer(p_user)
    res = db_client.get(f"/parent/students/{s_prof.id}/progress", headers=p_headers)
    assert res.status_code == 200
    data = res.json()

    # Verify student identity & relationship
    assert data["student_id"] == str(s_prof.id)
    assert data["relationship_type"] == "FATHER"

    # Verify major weak area phrasing: "Đang gặp khó khăn ở nhóm bài toán..."
    weak_areas = data["major_weak_areas"]
    assert len(weak_areas) >= 1
    weak_item = weak_areas[0]
    assert weak_item["problem_type_name"] == "Tim tham so ve tinh don dieu"
    assert "Đang gặp khó khăn ở nhóm bài toán" in weak_item["parent_friendly_message"]
    assert weak_item["related_concept_name"] == "Giai bat phuong trinh"

    # Verify study plan completion: 3/4 = 75%
    comp = data["study_plan_completion"]
    assert comp["total_tasks"] == 4
    assert comp["completed_tasks"] == 3
    assert comp["completion_rate"] == 0.75

    # Verify exam trend
    exams = data["exam_trend"]
    assert len(exams) >= 1
    assert exams[0]["title"] == "Kiem tra 15 phut Dao ham"
    assert exams[0]["score"] == 8.5

    # Verify important intervention alerts (LOW_PROBLEM_TYPE_MASTERY, PREREQUISITE_GAP)
    alerts = data["important_intervention_alerts"]
    alert_codes = [a["rule_code"] for a in alerts]
    assert "LOW_PROBLEM_TYPE_MASTERY" in alert_codes
    assert "PREREQUISITE_GAP" in alert_codes
    for a in alerts:
        assert len(a["suggested_action_for_parent"]) > 0


# --------------------------------------------------------------------------
# 3. Weekly Data & Daily Study Breakdown
# --------------------------------------------------------------------------

def test_parent_student_weekly_data_breakdown(
    db_client: TestClient,
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_bearer: Callable[[User], dict[str, str]],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p_user = parent_user_factory(Role.PARENT, "p_week@example.com")
    s_user = parent_user_factory(Role.STUDENT, "s_week@example.com")

    p_prof = parent_profile_helper(p_user)
    s_prof = student_profile_helper(s_user)

    db_session.add(
        ParentStudentRelationship(
            parent_id=p_prof.id,
            student_id=s_prof.id,
            relationship_type="MOTHER",
            is_active=True,
        )
    )

    # Create study sessions during the current week:
    # 2 sessions: 45 min and 30 min -> 75 min total
    now = datetime.now(timezone.utc)
    s1 = StudySession(
        student_id=s_prof.id,
        started_at=now - timedelta(hours=3),
        ended_at=now - timedelta(hours=3) + timedelta(minutes=45),
    )
    s2 = StudySession(
        student_id=s_prof.id,
        started_at=now - timedelta(days=1),
        ended_at=now - timedelta(days=1) + timedelta(minutes=30),
    )
    db_session.add_all([s1, s2])
    db_session.commit()

    p_headers = parent_bearer(p_user)
    res = db_client.get(f"/parent/students/{s_prof.id}/weekly-data", headers=p_headers)
    assert res.status_code == 200
    data = res.json()

    assert data["student_id"] == str(s_prof.id)
    assert len(data["daily_study_time"]) == 7
    # Verify daily labels are in Vietnamese
    days = [d["day_of_week"] for d in data["daily_study_time"]]
    assert "Thứ 2" in days
    assert "Chủ nhật" in days

    # Total study time should reflect the recorded sessions (~75 min)
    assert data["total_study_time_minutes"] >= 75
    assert "75" in data["overall_weekly_summary"] or str(data["total_study_time_minutes"]) in data["overall_weekly_summary"]


# --------------------------------------------------------------------------
# 4. Privacy & Safety Guardrails (Zero Private AI Chat, Zero Peer Comparison)
# --------------------------------------------------------------------------

def test_privacy_guardrails_no_private_conversations_or_peer_comparison(
    db_client: TestClient,
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_bearer: Callable[[User], dict[str, str]],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p_user = parent_user_factory(Role.PARENT, "p_privacy@example.com")
    s_user = parent_user_factory(Role.STUDENT, "s_privacy@example.com")

    p_prof = parent_profile_helper(p_user)
    s_prof = student_profile_helper(s_user)

    db_session.add(
        ParentStudentRelationship(
            parent_id=p_prof.id,
            student_id=s_prof.id,
            relationship_type="MOTHER",
            is_active=True,
        )
    )
    db_session.commit()

    p_headers = parent_bearer(p_user)
    res_prog = db_client.get(f"/parent/students/{s_prof.id}/progress", headers=p_headers)
    assert res_prog.status_code == 200
    prog_text = res_prog.text.lower()

    # Guardrails check on response text:
    # 1. No raw AI conversation or prompt tokens
    assert "raw_message" not in prog_text
    assert "conversation" not in prog_text
    assert "prompt" not in prog_text
    # 2. No peer comparison or classmate ranking
    assert "rank" not in prog_text
    assert "xếp hạng" not in prog_text
    assert "so với bạn" not in prog_text
    assert "thứ hạng" not in prog_text
    # 3. No sensitive password or user secrets
    assert "password" not in prog_text
    assert "secret" not in prog_text


# --------------------------------------------------------------------------
# 5. Plural Alias /parents/students Support
# --------------------------------------------------------------------------

def test_parent_plural_alias_endpoints(
    db_client: TestClient,
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_bearer: Callable[[User], dict[str, str]],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p_user = parent_user_factory(Role.PARENT, "p_alias@example.com")
    s_user = parent_user_factory(Role.STUDENT, "s_alias@example.com")

    p_prof = parent_profile_helper(p_user)
    s_prof = student_profile_helper(s_user)

    db_session.add(
        ParentStudentRelationship(
            parent_id=p_prof.id,
            student_id=s_prof.id,
            relationship_type="FATHER",
            is_active=True,
        )
    )
    db_session.commit()

    headers = parent_bearer(p_user)

    # Calling plural /parents/students...
    res_list = db_client.get("/parents/students", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    res_prog = db_client.get(f"/parents/students/{s_prof.id}/progress", headers=headers)
    assert res_prog.status_code == 200
    assert res_prog.json()["student_id"] == str(s_prof.id)

    res_week = db_client.get(f"/parents/students/{s_prof.id}/weekly-data", headers=headers)
    assert res_week.status_code == 200
    assert res_week.json()["student_id"] == str(s_prof.id)


# --------------------------------------------------------------------------
# 6. New Student with Zero Activity - Safe Defaults (No Division by Zero)
# --------------------------------------------------------------------------

def test_new_student_safe_defaults_no_errors(
    db_client: TestClient,
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_bearer: Callable[[User], dict[str, str]],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p_user = parent_user_factory(Role.PARENT, "p_brand_new@example.com")
    s_user = parent_user_factory(Role.STUDENT, "s_brand_new@example.com")

    p_prof = parent_profile_helper(p_user)
    s_prof = student_profile_helper(s_user)

    db_session.add(
        ParentStudentRelationship(
            parent_id=p_prof.id,
            student_id=s_prof.id,
            relationship_type="GUARDIAN",
            is_active=True,
        )
    )
    db_session.commit()

    headers = parent_bearer(p_user)

    res_prog = db_client.get(f"/parent/students/{s_prof.id}/progress", headers=headers)
    assert res_prog.status_code == 200
    data_prog = res_prog.json()
    assert data_prog["study_plan_completion"]["total_tasks"] == 0
    assert data_prog["study_plan_completion"]["completion_rate"] == 0.0
    assert data_prog["major_weak_areas"] == []
    assert data_prog["exam_trend"] == []
    assert data_prog["overall_learning_trend"] in ("STABLE", "IMPROVING", "NEEDS_ATTENTION")

    res_week = db_client.get(f"/parent/students/{s_prof.id}/weekly-data", headers=headers)
    assert res_week.status_code == 200
    data_week = res_week.json()
    assert data_week["total_study_time_minutes"] == 0
    assert len(data_week["daily_study_time"]) == 7
    for day in data_week["daily_study_time"]:
        assert day["study_time_minutes"] == 0
        assert day["questions_attempted"] == 0

