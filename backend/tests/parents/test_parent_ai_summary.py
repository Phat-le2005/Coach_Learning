from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.assignments.models import Assignment, AssignmentStatus, AssignmentType, StudentAssignment, StudentAssignmentStatus
from app.attempts.models import StudySession
from app.concepts.models import Concept, ConceptRelation, RelationType
from app.core.config import get_settings
from app.curriculum.models import Chapter, ProblemType, ProblemTypeConcept, Topic
from app.main import app
from app.mastery.models import StudentConceptMastery, StudentProblemTypeMastery
from app.parents.dashboard_schemas import (
    ParentWeeklyAIInput,
    ParentWeeklyAIOutput,
    ParentWeeklyAISummaryRead,
)
from app.parents.models import ParentProfile, ParentStudentRelationship
from app.parents.parent_ai_service import ParentAISummaryService
from app.parents.portal_router import get_ai_summary_service
from app.planning.study_models import StudyPlan, StudyPlanStatus, StudyTask, StudyTaskReasonCode, StudyTaskStatus, StudyTaskType
from app.practice.models import PracticeSession, PracticeSessionStatus, PracticeSessionType, QuestionAttempt
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User


def _setup_curriculum(
    session: Session, prefix: str = "PAI"
) -> tuple[Subject, Chapter, Topic, ProblemType, Concept]:
    subject = Subject(code=f"{prefix}-MATH", name=f"{prefix} Toán 12", grade_level=12)
    session.add(subject)
    session.flush()

    chapter = Chapter(subject_id=subject.id, code=f"{prefix}-CHP", name=f"{prefix} Khảo sát hàm số", order_index=0)
    session.add(chapter)
    session.flush()

    topic = Topic(chapter_id=chapter.id, code=f"{prefix}-TOP", name=f"{prefix} Tính đơn điệu", order_index=0)
    session.add(topic)
    session.flush()

    pt = ProblemType(
        topic_id=topic.id,
        code=f"{prefix}-PT-PARAM",
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
    concept_prereq = Concept(
        subject_id=subject.id,
        code=f"{prefix}-CON-DERIV",
        name="Đạo hàm hàm số",
        order_index=1,
    )
    session.add_all([pt, concept, concept_prereq])
    session.flush()

    session.add(ProblemTypeConcept(problem_type_id=pt.id, concept_id=concept.id, weight=1.0, is_primary=True))
    session.add(ConceptRelation(source_concept_id=concept_prereq.id, target_concept_id=concept.id, relation_type=RelationType.PREREQUISITE))
    session.flush()
    return subject, chapter, topic, pt, concept


# --------------------------------------------------------------------------
# 1. AI Summary Generation Success (MockAIProvider with Structured Output)
# --------------------------------------------------------------------------

def test_parent_ai_summary_success(
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p_user = parent_user_factory(Role.PARENT, "ai_summary_parent@example.com")
    s_user = parent_user_factory(Role.STUDENT, "ai_summary_student@example.com")
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

    subject, chapter, topic, pt, concept = _setup_curriculum(db_session, "AISUC")

    # Add study session
    now = datetime.now(timezone.utc)
    db_session.add(
        StudySession(
            student_id=s_prof.id,
            started_at=now - timedelta(days=2, minutes=45),
            ended_at=now - timedelta(days=2),
        )
    )
    # Add weak problem type
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_prof.id,
            problem_type_id=pt.id,
            mastery_score=0.35,
            confidence=0.85,
            attempt_count=3,
            correct_count=1,
            last_practiced_at=now,
        )
    )
    db_session.commit()

    # Canned AI Output
    canned = ParentWeeklyAIOutput(
        progress="Tuần này con đã dành 45 phút học tập nghiêm túc và có ý thức rèn luyện môn Toán.",
        current_challenge="Con đang gặp khó khăn ở dạng bài Tìm tham số về tính đơn điệu.",
        next_week="Tuần tới con sẽ tập trung củng cố phương pháp giải bất phương trình đạo hàm.",
        how_parent_can_help=[
            "Khích lệ con duy trì 20 phút học mỗi tối trong không gian yên tĩnh.",
            "Nhắc con xem lại các ví dụ cơ bản trước khi làm bài tập nâng cao.",
        ],
    )
    mock_provider = MockAIProvider(canned_structured=canned)
    gateway = AIGateway(provider=mock_provider, settings=get_settings())
    service = ParentAISummaryService(db_session, gateway=gateway)

    result = service.generate_weekly_summary(p_user.id, s_prof.id)

    assert result.is_fallback is False
    assert result.student_id == s_prof.id
    assert "45 phút" in result.progress
    assert "Tìm tham số về tính đơn điệu" in result.current_challenge
    assert "bất phương trình" in result.next_week
    assert len(result.how_parent_can_help) == 2
    assert "Khích lệ con" in result.how_parent_can_help[0]


# --------------------------------------------------------------------------
# 2. Guardrail: Strictly Clamp how_parent_can_help to Max 2
# --------------------------------------------------------------------------

def test_parent_ai_summary_max_2_recommendations_enforced(
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p_user = parent_user_factory(Role.PARENT, "clamp_rec_p@example.com")
    s_user = parent_user_factory(Role.STUDENT, "clamp_rec_s@example.com")
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

    out = ParentWeeklyAIOutput.model_construct(
        progress="Tiến bộ ổn định",
        current_challenge="Dạng bài tham số",
        next_week="Ôn tập bất phương trình",
        how_parent_can_help=[
            "Khuyến nghị 1: Khen ngợi con",
            "Khuyến nghị 2: Tạo góc học tập",
            "Khuyến nghị 3: Kiểm tra bài tập",
            "Khuyến nghị 4: Đăng ký học thêm",
        ],
    )
    mock_provider = MockAIProvider(canned_structured=out)
    gateway = AIGateway(provider=mock_provider, settings=get_settings())
    service = ParentAISummaryService(db_session, gateway=gateway)

    result = service.generate_weekly_summary(p_user.id, s_prof.id)
    assert len(result.how_parent_can_help) <= 2
    assert len(result.how_parent_can_help) == 2
    assert result.how_parent_can_help[0] == "Khuyến nghị 1: Khen ngợi con"
    assert result.how_parent_can_help[1] == "Khuyến nghị 2: Tạo góc học tập"


# --------------------------------------------------------------------------
# 3. Deterministic Fallback when AI Provider Fails / Unavailable
# --------------------------------------------------------------------------

def test_parent_ai_summary_fallback_when_ai_offline(
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p_user = parent_user_factory(Role.PARENT, "fallback_p@example.com")
    s_user = parent_user_factory(Role.STUDENT, "fallback_s@example.com")
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
    subject, chapter, topic, pt, concept = _setup_curriculum(db_session, "AIFALL")

    now = datetime.now(timezone.utc)
    # Add study time
    db_session.add(
        StudySession(
            student_id=s_prof.id,
            started_at=now - timedelta(days=1, minutes=90),
            ended_at=now - timedelta(days=1),
        )
    )
    # Add weak problem type
    db_session.add(
        StudentProblemTypeMastery(
            student_id=s_prof.id,
            problem_type_id=pt.id,
            mastery_score=0.30,
            confidence=0.85,
            attempt_count=3,
            correct_count=1,
            last_practiced_at=now,
        )
    )
    # Add weak prerequisite concept
    db_session.add(
        StudentConceptMastery(
            student_id=s_prof.id,
            concept_id=concept.id,
            mastery_score=0.35,
            confidence=0.85,
            attempt_count=3,
            correct_count=1,
            last_practiced_at=now,
        )
    )
    db_session.commit()

    # Provider configured to fail with 10 failures
    failing_provider = MockAIProvider(service_unavailable_failures=10)
    gateway = AIGateway(provider=failing_provider, settings=get_settings())
    service = ParentAISummaryService(db_session, gateway=gateway)

    result = service.generate_weekly_summary(p_user.id, s_prof.id)

    assert result.is_fallback is True
    assert result.student_id == s_prof.id
    # Check deterministic fallback logic
    assert "90" in result.progress or "phút" in result.progress
    assert pt.name in result.current_challenge
    assert concept.name in result.current_challenge
    assert len(result.how_parent_can_help) <= 2
    assert len(result.how_parent_can_help) > 0


# --------------------------------------------------------------------------
# 4. Content Safety: Zero Tutor Chat Logs in AI Context
# --------------------------------------------------------------------------

def test_parent_ai_summary_input_has_zero_chat_or_tutor_logs(
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p_user = parent_user_factory(Role.PARENT, "privacy_p@example.com")
    s_user = parent_user_factory(Role.STUDENT, "privacy_s@example.com")
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

    service = ParentAISummaryService(db_session)
    context_input, parent_name = service.build_weekly_context(p_user.id, s_prof.id)

    # Check input payload schema
    dumped = context_input.model_dump()
    forbidden_keys = [
        "chat_history",
        "tutor_conversations",
        "raw_messages",
        "conversations",
        "dialogue",
        "transcript",
    ]
    for key in forbidden_keys:
        assert key not in dumped, f"Forbidden key '{key}' found in ParentWeeklyAIInput"

    # Check formatted prompt variables
    prompt_vars = service._format_prompt_variables(context_input, parent_name)
    for var_name, var_value in prompt_vars.items():
        assert "tutor" not in var_value.lower()
        assert "cuộc trò chuyện" not in var_value.lower()


# --------------------------------------------------------------------------
# 5. API Endpoints (GET, POST & Alias /parents/...)
# --------------------------------------------------------------------------

def test_parent_ai_summary_api_endpoints(
    db_client: TestClient,
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_bearer: Callable[[User], dict[str, str]],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p_user = parent_user_factory(Role.PARENT, "api_test_p@example.com")
    s_user = parent_user_factory(Role.STUDENT, "api_test_s@example.com")
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

    headers = parent_bearer(p_user)

    # 1. GET /parent/students/{student_id}/ai-summary
    res_get = db_client.get(f"/parent/students/{s_prof.id}/ai-summary", headers=headers)
    assert res_get.status_code == 200
    data_get = res_get.json()
    assert data_get["student_id"] == str(s_prof.id)
    assert "progress" in data_get
    assert "current_challenge" in data_get
    assert "next_week" in data_get
    assert isinstance(data_get["how_parent_can_help"], list)
    assert len(data_get["how_parent_can_help"]) <= 2

    # 2. POST /parent/students/{student_id}/ai-summary
    res_post = db_client.post(f"/parent/students/{s_prof.id}/ai-summary", headers=headers)
    assert res_post.status_code == 200
    data_post = res_post.json()
    assert data_post["student_id"] == str(s_prof.id)

    # 3. GET /parents/students/{student_id}/ai-summary (alias)
    res_alias_get = db_client.get(f"/parents/students/{s_prof.id}/ai-summary", headers=headers)
    assert res_alias_get.status_code == 200

    # 4. POST /parents/students/{student_id}/ai-summary (alias)
    res_alias_post = db_client.post(f"/parents/students/{s_prof.id}/ai-summary", headers=headers)
    assert res_alias_post.status_code == 200


# --------------------------------------------------------------------------
# 6. Authorization: 403 Forbidden for Unlinked or Inactive Relationships
# --------------------------------------------------------------------------

def test_parent_ai_summary_authorization_checks(
    db_client: TestClient,
    db_session: Session,
    parent_user_factory: Callable[[Role, str], User],
    parent_bearer: Callable[[User], dict[str, str]],
    parent_profile_helper: Callable[[User], ParentProfile],
    student_profile_helper: Callable[[User], StudentProfile],
) -> None:
    p1_user = parent_user_factory(Role.PARENT, "p1_sec@example.com")
    p2_user = parent_user_factory(Role.PARENT, "p2_sec@example.com")
    s1_user = parent_user_factory(Role.STUDENT, "s1_sec@example.com")
    s2_user = parent_user_factory(Role.STUDENT, "s2_sec@example.com")
    teacher_user = parent_user_factory(Role.TEACHER, "teacher_sec@example.com")

    p1_prof = parent_profile_helper(p1_user)
    p2_prof = parent_profile_helper(p2_user)
    s1_prof = student_profile_helper(s1_user)
    s2_prof = student_profile_helper(s2_user)

    # P1 linked to S1 (active)
    db_session.add(
        ParentStudentRelationship(
            parent_id=p1_prof.id,
            student_id=s1_prof.id,
            relationship_type="MOTHER",
            is_active=True,
        )
    )
    # P1 linked to S2 (INACTIVE)
    db_session.add(
        ParentStudentRelationship(
            parent_id=p1_prof.id,
            student_id=s2_prof.id,
            relationship_type="GUARDIAN",
            is_active=False,
        )
    )
    db_session.commit()

    p1_headers = parent_bearer(p1_user)
    p2_headers = parent_bearer(p2_user)
    teacher_headers = parent_bearer(teacher_user)

    # P1 accesses S1 -> 200 OK
    res_ok = db_client.get(f"/parent/students/{s1_prof.id}/ai-summary", headers=p1_headers)
    assert res_ok.status_code == 200

    # P1 accesses S2 (inactive) -> 403 Forbidden
    res_inactive = db_client.get(f"/parent/students/{s2_prof.id}/ai-summary", headers=p1_headers)
    assert res_inactive.status_code == 403
    assert res_inactive.json()["error"]["code"] == "RELATIONSHIP_INACTIVE"

    # P2 accesses S1 (unlinked) -> 403 Forbidden
    res_unlinked = db_client.get(f"/parent/students/{s1_prof.id}/ai-summary", headers=p2_headers)
    assert res_unlinked.status_code == 403
    assert res_unlinked.json()["error"]["code"] == "NOT_LINKED_TO_STUDENT"

    # Teacher accesses parent endpoint -> 403 Forbidden (ROLE_MISMATCH)
    res_teacher = db_client.get(f"/parent/students/{s1_prof.id}/ai-summary", headers=teacher_headers)
    assert res_teacher.status_code == 403

    # No token -> 401 Unauthorized
    res_unauth = db_client.get(f"/parent/students/{s1_prof.id}/ai-summary")
    assert res_unauth.status_code == 401
