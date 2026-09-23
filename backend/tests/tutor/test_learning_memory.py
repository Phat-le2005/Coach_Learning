from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.ai.gateway import AIGateway
from app.ai.mock_provider import MockAIProvider
from app.ai.tutor_context_builder import TutorContextBuilder
from app.ai.tutor_schemas import TutorRequest
from app.tutor.memory_validator import MemoryValidator
from app.tutor.models import (
    LearningMemoryType,
    StudentLearningMemory,
    TutorSession,
    TutorSessionStatus,
    TutorSessionSummary,
)
from app.tutor.schemas import (
    MemoryExtractionAIOutput,
    ProposedMemoryItem,
    TutorSessionCreate,
    TutorSessionEndRequest,
)
from app.tutor.service import MemoryService, TutorSessionService
from app.students.models import StudentProfile
from app.users.models import Role, User


# --------------------------------------------------------------------------
# 1. Models & Database Constraints Test
# --------------------------------------------------------------------------

def test_memory_types_and_constraints(
    db_session: Session,
    tutor_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
    academic_curriculum_seed: dict,
) -> None:
    user = tutor_user_factory(Role.STUDENT, "student_constraints@example.com")
    prof = student_profile(user)

    # 1. Verify 5 valid types
    for m_type in LearningMemoryType:
        mem = StudentLearningMemory(
            student_id=prof.id,
            type=m_type,
            value=f"Ký ức hợp lệ cho loại {m_type.value}",
            confidence=0.85,
            is_active=True,
        )
        db_session.add(mem)
    db_session.commit()

    saved = db_session.scalars(
        select(StudentLearningMemory).where(StudentLearningMemory.student_id == prof.id)
    ).all()
    assert len(saved) == 5

    # 2. Check confidence range constraint (< 0.0)
    with pytest.raises(IntegrityError):
        invalid_mem_low = StudentLearningMemory(
            student_id=prof.id,
            type=LearningMemoryType.LEARNING_PREFERENCE,
            value="Confidence invalid low",
            confidence=-0.1,
        )
        db_session.add(invalid_mem_low)
        db_session.commit()
    db_session.rollback()

    # 3. Check confidence range constraint (> 1.0)
    with pytest.raises(IntegrityError):
        invalid_mem_high = StudentLearningMemory(
            student_id=prof.id,
            type=LearningMemoryType.LEARNING_PREFERENCE,
            value="Confidence invalid high",
            confidence=1.1,
        )
        db_session.add(invalid_mem_high)
        db_session.commit()
    db_session.rollback()

    # 4. Check turn_count non-negative constraint on TutorSession
    with pytest.raises(IntegrityError):
        invalid_session = TutorSession(
            student_id=prof.id,
            turn_count=-1,
        )
        db_session.add(invalid_session)
        db_session.commit()
    db_session.rollback()


# --------------------------------------------------------------------------
# 2. AI Memory Extractor Proposal & Schema Output
# --------------------------------------------------------------------------

def test_ai_memory_extractor_proposal_schema() -> None:
    output = MemoryExtractionAIOutput(
        session_summary="Học sinh đã ôn tập về tìm cực trị của hàm số bậc ba.",
        key_takeaways=["Nắm vững dấu đạo hàm bậc nhất", "Hiểu cách lập bảng biến thiên"],
        proposed_memories=[
            ProposedMemoryItem(
                type=LearningMemoryType.LEARNING_PREFERENCE,
                value="Học sinh tiếp thu nhanh hơn khi có đồ thị minh họa hình học",
                confidence=0.90,
                reasoning="Tương tác tích cực khi đưa đồ thị",
            ),
            ProposedMemoryItem(
                type=LearningMemoryType.PERSISTENT_DIFFICULTY,
                value="Thường gặp khó khăn khi xác định điều kiện để tam thức bậc hai có hai nghiệm phân biệt",
                confidence=0.80,
                reasoning="Lúng túng khi tính delta trong 2 bài liên tiếp",
            ),
        ],
    )
    assert len(output.proposed_memories) == 2
    assert output.proposed_memories[0].type == LearningMemoryType.LEARNING_PREFERENCE
    assert output.proposed_memories[1].confidence == 0.80


# --------------------------------------------------------------------------
# 3. Backend Validation - Rejection of Prohibited Categories
# --------------------------------------------------------------------------

def test_validation_rejects_casual_conversation(db_session: Session) -> None:
    casual_samples = [
        "Chào bạn, hôm nay thế nào rồi",
        "Cảm ơn thầy rất nhiều ạ, chúc thầy vui vẻ",
        "Okie haha hẹn gặp lại nhé",
        "Ăn cơm chưa bạn ơi",
    ]
    for text in casual_samples:
        item = ProposedMemoryItem(
            type=LearningMemoryType.LEARNING_PREFERENCE,
            value=text,
            confidence=0.85,
        )
        res = MemoryValidator.validate(item, db_session)
        assert not res.is_valid, f"Expected reject for casual talk: {text}"
        assert "casual conversation" in res.reason


def test_validation_rejects_temporary_emotion(db_session: Session) -> None:
    emotion_samples = [
        "Hôm nay em đang mệt mỏi quá thầy ơi",
        "Em cảm thấy buồn ngủ và chán học rồi",
        "Hôm nay tâm trạng không tốt lắm ạ",
        "Đau đầu quá không tập trung được",
    ]
    for text in emotion_samples:
        item = ProposedMemoryItem(
            type=LearningMemoryType.LEARNING_PREFERENCE,
            value=text,
            confidence=0.85,
        )
        res = MemoryValidator.validate(item, db_session)
        assert not res.is_valid, f"Expected reject for emotion: {text}"
        assert "temporary emotion" in res.reason


def test_validation_rejects_sensitive_and_irrelevant_data(db_session: Session) -> None:
    sensitive_samples = [
        "Số điện thoại của học sinh là 0912345678 để tiện liên hệ",
        "Em đang crush bạn gái cùng lớp chuyên Toán",
        "Mật khẩu tài khoản ngân hàng của em là secret123",
        "Nhà ở số 123 đường Lê Lợi quận 1",
    ]
    for text in sensitive_samples:
        item = ProposedMemoryItem(
            type=LearningMemoryType.LEARNING_PREFERENCE,
            value=text,
            confidence=0.85,
        )
        res = MemoryValidator.validate(item, db_session)
        assert not res.is_valid, f"Expected reject for sensitive data: {text}"
        assert "thông tin đời tư hoặc dữ liệu nhạy cảm" in res.reason


def test_validation_rejects_raw_chat_transcripts(db_session: Session) -> None:
    chat_samples = [
        "Học sinh: Cho em hỏi bài này giải sao ạ?\nAI: Em hãy tính đạo hàm trước nhé.",
        "User: Explain quadratic formula step by step.",
        "Em vừa hỏi thầy ơi bài này đáp án A hay B vậy?",
    ]
    for text in chat_samples:
        item = ProposedMemoryItem(
            type=LearningMemoryType.LEARNING_PREFERENCE,
            value=text,
            confidence=0.85,
        )
        res = MemoryValidator.validate(item, db_session)
        assert not res.is_valid, f"Expected reject for raw chat: {text}"
        assert "raw chat transcript" in res.reason


def test_validation_rejects_low_confidence_and_invalid_references(
    db_session: Session, academic_curriculum_seed: dict
) -> None:
    # 1. Low confidence
    item_low_conf = ProposedMemoryItem(
        type=LearningMemoryType.LEARNING_PREFERENCE,
        value="Thích học theo ví dụ minh họa trực quan",
        confidence=0.40,  # below 0.50 threshold
    )
    res = MemoryValidator.validate(item_low_conf, db_session)
    assert not res.is_valid
    assert "dưới ngưỡng tối thiểu" in res.reason

    # 2. Non-existent problem_type_id
    fake_pt_id = uuid4()
    item_fake_pt = ProposedMemoryItem(
        type=LearningMemoryType.PERSISTENT_DIFFICULTY,
        value="Khó khăn khi giải phương trình lượng giác",
        confidence=0.85,
        problem_type_id=fake_pt_id,
    )
    res_fake = MemoryValidator.validate(item_fake_pt, db_session)
    assert not res_fake.is_valid
    assert "không tồn tại" in res_fake.reason


# --------------------------------------------------------------------------
# 4. Backend Validation - Acceptance & Persistence of Valid Memories
# --------------------------------------------------------------------------

@pytest.mark.anyio
async def test_validation_accepts_and_persists_valid_memories(
    db_session: Session,
    settings,
    tutor_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
    academic_curriculum_seed: dict,
) -> None:
    user = tutor_user_factory(Role.STUDENT, "student_accept@example.com")
    prof = student_profile(user)
    pt_math = academic_curriculum_seed["math_pt"]
    c_math = academic_curriculum_seed["math_concept"]

    session_service = TutorSessionService(db_session)
    t_session = session_service.create_session(
        student_id=prof.id,
        payload=TutorSessionCreate(
            subject_id=academic_curriculum_seed["math_subject"].id,
            problem_type_id=pt_math.id,
            concept_id=c_math.id,
        ),
    )
    t_session.turn_count = 4

    # Mock gateway returning valid proposed memories
    canned_output = MemoryExtractionAIOutput(
        session_summary="Phiên học Toán chuyên đề cực trị bậc ba diễn ra hiệu quả.",
        key_takeaways=["Học sinh phân biệt tốt cực đại và cực tiểu"],
        proposed_memories=[
            ProposedMemoryItem(
                type=LearningMemoryType.LEARNING_PREFERENCE,
                value="Học sinh hiểu nhanh hơn khi được phân tích từng bước đạo hàm",
                confidence=0.90,
                reasoning="Rất nhạy bén với từng bước giải chi tiết",
            ),
            ProposedMemoryItem(
                type=LearningMemoryType.PERSISTENT_DIFFICULTY,
                value="Thường quên đổi dấu khi chia cho số âm trong bất phương trình",
                confidence=0.85,
                problem_type_id=pt_math.id,
                concept_id=c_math.id,
                reasoning="Gặp lỗi sai này ở 2 bài toán liên tiếp",
            ),
        ],
    )

    provider = MockAIProvider(canned_structured=canned_output)
    gateway = AIGateway(provider=provider, settings=settings)

    mem_service = MemoryService(db_session)
    summary_text, takeaways, saved = await mem_service.extract_and_persist_async(
        t_session, gateway=gateway
    )

    assert len(saved) == 2
    assert summary_text == "Phiên học Toán chuyên đề cực trị bậc ba diễn ra hiệu quả."

    # Verify all required fields are persisted
    m1 = saved[0]
    assert m1.student_id == prof.id
    assert m1.type == LearningMemoryType.LEARNING_PREFERENCE
    assert m1.value == "Học sinh hiểu nhanh hơn khi được phân tích từng bước đạo hàm"
    assert m1.confidence == 0.90
    assert m1.source_session_id == t_session.id
    assert m1.created_at is not None
    assert m1.last_confirmed_at is not None

    m2 = saved[1]
    assert m2.type == LearningMemoryType.PERSISTENT_DIFFICULTY
    assert m2.problem_type_id == pt_math.id
    assert m2.concept_id == c_math.id


# --------------------------------------------------------------------------
# 5. Memory Deduplication & Confirmation Update Test
# --------------------------------------------------------------------------

@pytest.mark.anyio
async def test_memory_deduplication_and_last_confirmed(
    db_session: Session,
    settings,
    tutor_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
    academic_curriculum_seed: dict,
) -> None:
    user = tutor_user_factory(Role.STUDENT, "student_dedup@example.com")
    prof = student_profile(user)
    pt_math = academic_curriculum_seed["math_pt"]

    mem_service = MemoryService(db_session)
    session_service = TutorSessionService(db_session)
    t_session1 = session_service.create_session(
        student_id=prof.id,
        payload=TutorSessionCreate(problem_type_id=pt_math.id),
    )

    # 1. First encounter
    canned1 = MemoryExtractionAIOutput(
        session_summary="Buổi học số 1.",
        key_takeaways=[],
        proposed_memories=[
            ProposedMemoryItem(
                type=LearningMemoryType.PERSISTENT_DIFFICULTY,
                value="Dễ nhầm lẫn dấu khi giải bất phương trình bậc hai",
                confidence=0.75,
                problem_type_id=pt_math.id,
            )
        ],
    )
    gw1 = AIGateway(provider=MockAIProvider(canned_structured=canned1), settings=settings)
    _, _, saved1 = await mem_service.extract_and_persist_async(t_session1, gateway=gw1)
    assert len(saved1) == 1
    m1_id = saved1[0].id
    m1_conf = saved1[0].confidence
    m1_time = saved1[0].last_confirmed_at

    # 2. Second encounter with same problem_type_id and similar difficulty
    t_session2 = session_service.create_session(
        student_id=prof.id,
        payload=TutorSessionCreate(problem_type_id=pt_math.id),
    )
    canned2 = MemoryExtractionAIOutput(
        session_summary="Buổi học số 2.",
        key_takeaways=[],
        proposed_memories=[
            ProposedMemoryItem(
                type=LearningMemoryType.PERSISTENT_DIFFICULTY,
                value="Dễ nhầm lẫn dấu khi giải bất phương trình bậc hai có chứa tham số",
                confidence=0.88,  # higher confidence
                problem_type_id=pt_math.id,
            )
        ],
    )
    gw2 = AIGateway(provider=MockAIProvider(canned_structured=canned2), settings=settings)
    _, _, saved2 = await mem_service.extract_and_persist_async(t_session2, gateway=gw2)

    assert len(saved2) == 1
    m2 = saved2[0]

    # Verify ID is preserved (no duplicate record), confidence is upgraded, last_confirmed_at is updated
    assert m2.id == m1_id
    assert m2.confidence == 0.88
    assert m2.last_confirmed_at >= m1_time

    # Verify total records in DB for this student remains 1
    all_student_mems = db_session.scalars(
        select(StudentLearningMemory).where(StudentLearningMemory.student_id == prof.id)
    ).all()
    assert len(all_student_mems) == 1


# --------------------------------------------------------------------------
# 6. TutorContextBuilder Relevant Memory Selection Test
# --------------------------------------------------------------------------

@pytest.mark.anyio
async def test_tutor_context_builder_filters_only_relevant_memories(
    db_session: Session,
    tutor_user_factory: Callable[[Role, str], User],
    student_profile: Callable[[User], StudentProfile],
    academic_curriculum_seed: dict,
) -> None:
    user = tutor_user_factory(Role.STUDENT, "student_relevance@example.com")
    prof = student_profile(user)

    s_math = academic_curriculum_seed["math_subject"]
    pt_math = academic_curriculum_seed["math_pt"]
    c_math = academic_curriculum_seed["math_concept"]

    s_chem = academic_curriculum_seed["chem_subject"]
    pt_chem = academic_curriculum_seed["chem_pt"]

    # 1. Seed general preferences
    mem_pref = StudentLearningMemory(
        student_id=prof.id,
        type=LearningMemoryType.LEARNING_PREFERENCE,
        value="Thích giải thích qua hình ảnh và đồ thị trực quan",
        confidence=0.92,
    )
    mem_tutor_pref = StudentLearningMemory(
        student_id=prof.id,
        type=LearningMemoryType.TUTORING_PREFERENCE,
        value="Muốn gia sư AI đặt câu hỏi gợi mở, không đưa ngay đáp án",
        confidence=0.88,
    )

    # 2. Seed Math difficulty
    mem_math_diff = StudentLearningMemory(
        student_id=prof.id,
        type=LearningMemoryType.PERSISTENT_DIFFICULTY,
        value="Khó khăn khi xét dấu y' để tìm khoảng đồng biến nghịch biến",
        confidence=0.85,
        problem_type_id=pt_math.id,
        concept_id=c_math.id,
    )

    # 3. Seed Chemistry difficulty (Unrelated to Math)
    mem_chem_diff = StudentLearningMemory(
        student_id=prof.id,
        type=LearningMemoryType.PERSISTENT_DIFFICULTY,
        value="Thường quên cân bằng tỉ lệ phản ứng thủy phân este",
        confidence=0.89,
        problem_type_id=pt_chem.id,
    )

    db_session.add_all([mem_pref, mem_tutor_pref, mem_math_diff, mem_chem_diff])
    db_session.commit()

    # Build context for a Math inquiry
    builder = TutorContextBuilder(db_session)
    request = TutorRequest(
        message="Em chưa hiểu cách lập bảng biến thiên hàm bậc ba",
        problem_type_id=pt_math.id,
        concept_id=c_math.id,
    )

    ctx_data = await builder.build_context(user, request)

    # Check prompt variables
    vars_dict = ctx_data.to_prompt_variables()
    assert "learning_memory_context" in vars_dict
    mem_context = vars_dict["learning_memory_context"]

    # Must contain General and Tutoring Preferences
    assert "Thích giải thích qua hình ảnh và đồ thị trực quan" in mem_context
    assert "Muốn gia sư AI đặt câu hỏi gợi mở" in mem_context

    # Must contain Math difficulty
    assert "Khó khăn khi xét dấu y'" in mem_context

    # Must NOT leak Chemistry difficulty
    assert "thủy phân este" not in mem_context

    # Verify no raw chat transcript keywords leaked
    assert "User:" not in mem_context
    assert "AI:" not in mem_context


# --------------------------------------------------------------------------
# 7. Session & Memory API Lifecycle Test
# --------------------------------------------------------------------------

def test_tutor_session_and_memory_apis(
    db_client: TestClient,
    db_session: Session,
    tutor_user_factory: Callable[[Role, str], User],
    tutor_bearer: Callable[[User], dict[str, str]],
    student_profile: Callable[[User], StudentProfile],
    academic_curriculum_seed: dict,
) -> None:
    student_a = tutor_user_factory(Role.STUDENT, "student_api_a@example.com")
    student_b = tutor_user_factory(Role.STUDENT, "student_api_b@example.com")
    teacher = tutor_user_factory(Role.TEACHER, "teacher_api@example.com")

    prof_a = student_profile(student_a)
    prof_b = student_profile(student_b)
    headers_a = tutor_bearer(student_a)
    headers_b = tutor_bearer(student_b)
    headers_teacher = tutor_bearer(teacher)

    pt_math = academic_curriculum_seed["math_pt"]

    # 1. Authorization checks
    res_unauth = db_client.post("/tutor/sessions", json={})
    assert res_unauth.status_code == 401

    res_teacher = db_client.post("/tutor/sessions", json={}, headers=headers_teacher)
    assert res_teacher.status_code == 403

    # 2. Student A starts session
    res_create = db_client.post(
        "/tutor/sessions",
        json={"problem_type_id": str(pt_math.id)},
        headers=headers_a,
    )
    assert res_create.status_code == 201
    session_data = res_create.json()
    session_id = session_data["id"]
    assert session_data["turn_count"] == 0
    assert session_data["status"] == "ACTIVE"

    # 3. Student A increments turn
    res_turn = db_client.post(
        f"/tutor/sessions/{session_id}/turn",
        headers=headers_a,
    )
    assert res_turn.status_code == 200
    assert res_turn.json()["turn_count"] == 1

    # Student B cannot access Student A's session
    res_turn_b = db_client.post(
        f"/tutor/sessions/{session_id}/turn",
        headers=headers_b,
    )
    assert res_turn_b.status_code == 403

    # 4. Student A ends session (fallback extraction)
    res_end = db_client.post(
        f"/tutor/sessions/{session_id}/end",
        json={"summary_text": "Học sinh hiểu bài tốt", "resolved_questions_count": 2},
        headers=headers_a,
    )
    assert res_end.status_code == 200
    summary_data = res_end.json()
    assert summary_data["resolved_questions_count"] == 2
    assert "summary_text" in summary_data

    # 5. Student A checks learning memories
    # Add an explicit memory for Student A
    mem = StudentLearningMemory(
        student_id=prof_a.id,
        type=LearningMemoryType.LEARNING_PREFERENCE,
        value="Ưa chuộng học tập thông qua bản đồ tư duy",
        confidence=0.88,
    )
    db_session.add(mem)
    db_session.commit()

    res_mems_a = db_client.get("/students/me/learning-memories", headers=headers_a)
    assert res_mems_a.status_code == 200
    mems_list = res_mems_a.json()
    assert any(m["value"] == "Ưa chuộng học tập thông qua bản đồ tư duy" for m in mems_list)

    # Student B sees empty memories
    res_mems_b = db_client.get("/students/me/learning-memories", headers=headers_b)
    assert res_mems_b.status_code == 200
    assert not any(m["value"] == "Ưa chuộng học tập thông qua bản đồ tư duy" for m in res_mems_b.json())

    # 6. Student A deletes memory
    target_mem_id = mem.id
    res_del = db_client.delete(f"/students/me/learning-memories/{target_mem_id}", headers=headers_a)
    assert res_del.status_code == 204

    # Verify deleted memory is no longer returned in list
    res_mems_a_after = db_client.get("/students/me/learning-memories", headers=headers_a)
    assert not any(m["id"] == str(target_mem_id) for m in res_mems_a_after.json())
