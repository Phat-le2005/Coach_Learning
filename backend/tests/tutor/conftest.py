from collections.abc import Callable
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.schemas import LoginRequest
from app.auth.service import AuthService
from app.concepts.models import Concept
from app.core.config import Settings
from app.curriculum.models import Chapter, ProblemType, Topic
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.users.models import Role, User
from app.users.schemas import UserCreate
from app.users.service import UserService

TUTOR_TEST_PASSWORD = "Synthetic-Tutor-Learning-Memory-Password-2026!"


@pytest.fixture
def tutor_user_factory(db_session: Session) -> Callable[[Role, str], User]:
    def create(role: Role, email: str) -> User:
        return UserService(db_session).create_user(
            UserCreate(
                email=email,
                password=TUTOR_TEST_PASSWORD,
                full_name=f"{role.value.title()} {email.split('@')[0]}",
                role=role,
            )
        )

    return create


@pytest.fixture
def tutor_bearer(
    db_session: Session, settings: Settings
) -> Callable[[User], dict[str, str]]:
    def headers(user: User) -> dict[str, str]:
        pair = AuthService(db_session, settings).login(
            LoginRequest(email=user.email, password=TUTOR_TEST_PASSWORD)
        )
        return {"Authorization": f"Bearer {pair.access_token}"}

    return headers


@pytest.fixture
def student_profile(db_session: Session) -> Callable[[User], StudentProfile]:
    def get(user: User) -> StudentProfile:
        profile = db_session.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
        assert profile is not None
        return profile

    return get


@pytest.fixture
def academic_curriculum_seed(db_session: Session):
    """Seed math and chemistry subjects, chapters, topics, problem types, and concepts."""
    # 1. Math
    s_math = Subject(code="TUTOR_MATH", name="Toán Học", grade_level=12)
    s_chem = Subject(code="TUTOR_CHEM", name="Hóa Học", grade_level=12)
    db_session.add_all([s_math, s_chem])
    db_session.flush()

    chap_math = Chapter(subject_id=s_math.id, code="T_CHAP_MATH", name="Hàm Số", order_index=1)
    chap_chem = Chapter(subject_id=s_chem.id, code="T_CHAP_CHEM", name="Hóa Hữu Cơ", order_index=1)
    db_session.add_all([chap_math, chap_chem])
    db_session.flush()

    top_math = Topic(chapter_id=chap_math.id, code="T_TOP_MATH", name="Cực Trị", order_index=1)
    top_chem = Topic(chapter_id=chap_chem.id, code="T_TOP_CHEM", name="Este - Lipit", order_index=1)
    db_session.add_all([top_math, top_chem])
    db_session.flush()

    pt_math = ProblemType(topic_id=top_math.id, code="T_PT_MATH", name="Tìm cực trị hàm bậc ba", order_index=1)
    pt_chem = ProblemType(topic_id=top_chem.id, code="T_PT_CHEM", name="Thủy phân este đơn chức", order_index=1)
    db_session.add_all([pt_math, pt_chem])
    db_session.flush()

    c_math = Concept(subject_id=s_math.id, code="T_C_MATH", name="Khái niệm điểm cực trị")
    c_chem = Concept(subject_id=s_chem.id, code="T_C_CHEM", name="Phản ứng xà phòng hóa")
    db_session.add_all([c_math, c_chem])
    db_session.commit()

    return {
        "math_subject": s_math,
        "chem_subject": s_chem,
        "math_pt": pt_math,
        "chem_pt": pt_chem,
        "math_concept": c_math,
        "chem_concept": c_chem,
    }
