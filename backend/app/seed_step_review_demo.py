"""Install a reviewed reference for the existing development OCR sandbox question.

Run ``python -m app.seed_step_review_demo`` from backend. This development-only command installs the fixed sample question when absent,
and never changes production data.
"""

from uuid import UUID

from sqlalchemy import select

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.questions.models import Question, QuestionStatus, QuestionType
from app.subjects.models import Subject
from app.users.models import Role, User


DEMO_QUESTION_ID = UUID("c0000000-0000-0000-0000-000000000001")
DEMO_SUBJECT_CODE = "MATH_G12"
DEMO_TEACHER_ID = UUID("821ffe49-f0f1-5776-b5f0-d7d04c26b659")
DEMO_CONTENT = r"Khảo sát sự biến thiên và vẽ đồ thị hàm số $y = \frac{1}{3}x^3 - x^2 - 3x + 1$."
DEMO_CONTENT_MARKER = r"\frac{1}{3}x^3 - x^2 - 3x + 1"
DEMO_ANSWER = (
    "f'(x)=x^2-2x-3=(x+1)(x-3). "
    "Hàm số đồng biến trên (-∞,-1) và (3,+∞), nghịch biến trên (-1,3). "
    "Cực đại tại (-1,8/3), cực tiểu tại (3,-8). "
    "Đồ thị đi qua (0,1), có điểm uốn (1,-8/3), "
    "nhánh trái xuống -∞ và nhánh phải lên +∞."
)
DEMO_EXPLANATION = (
    "Bước 1: TXĐ R; đạo hàm y'=x²-2x-3=(x+1)(x-3). "
    "Bước 2: y'=0 tại x=-1 và x=3. Dấu y' lần lượt +, -, + trên "
    "(-∞,-1), (-1,3), (3,+∞). "
    "Bước 3: y(-1)=8/3, y(3)=-8. Bảng biến thiên: "
    "-∞ tăng đến 8/3, giảm đến -8, rồi tăng đến +∞. "
    "Bước 4: y(0)=1; y''=2x-2 nên điểm uốn (1,-8/3). "
    "Vẽ đồ thị bậc ba qua các điểm trên, phù hợp chiều biến thiên."
)


def install() -> str:
    if get_settings().app_env not in {"development", "test"}:
        raise RuntimeError("Development sample reference is disabled in production.")
    with get_session_factory()() as session:
        question = session.get(Question, DEMO_QUESTION_ID)
        if question is None:
            subject = session.scalar(select(Subject).where(Subject.code == DEMO_SUBJECT_CODE))
            if subject is None:
                raise RuntimeError(f"Subject {DEMO_SUBJECT_CODE} is missing from database.")
            teacher_id = session.scalar(select(User.id).where(User.id == DEMO_TEACHER_ID))
            if teacher_id is None:
                teacher_id = session.scalar(
                    select(User.id)
                    .where(User.role.in_([Role.TEACHER, Role.ADMIN]), User.is_active.is_(True))
                    .order_by(User.created_at)
                )
            if teacher_id is None:
                raise RuntimeError("No active teacher or admin user found to author sample question.")
            question = Question(
                id=DEMO_QUESTION_ID,
                subject_id=subject.id,
                content=DEMO_CONTENT,
                question_type=QuestionType.OPEN_RESPONSE,
                difficulty=0.5,
                correct_answer=DEMO_ANSWER,
                explanation=DEMO_EXPLANATION,
                source_type="SAMPLE_TEST",
                source_reference="Đề bài mẫu luyện tập tự do Toán 12",
                exam_weight=1.0,
                status=QuestionStatus.APPROVED,
                created_by=teacher_id,
            )
            session.add(question)
            session.commit()
            return "installed"

        if (question.source_type != "SAMPLE_TEST"
                or question.question_type != QuestionType.OPEN_RESPONSE
                or DEMO_CONTENT_MARKER not in question.content):
            raise RuntimeError("The expected development sample question has conflicting attributes.")
        if question.correct_answer not in {None, DEMO_ANSWER}:
            raise RuntimeError("The sample already has a different reviewed answer; no overwrite was made.")
        if (question.status == QuestionStatus.APPROVED
                and question.correct_answer == DEMO_ANSWER
                and question.explanation == DEMO_EXPLANATION):
            return "already_installed"
        question.status = QuestionStatus.APPROVED
        question.correct_answer = DEMO_ANSWER
        question.explanation = DEMO_EXPLANATION
        session.commit()
        return "installed"


if __name__ == "__main__":
    print(f"step_review_demo: {install()} ({DEMO_QUESTION_ID})")
