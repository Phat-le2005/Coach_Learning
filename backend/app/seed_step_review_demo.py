"""Install a reviewed reference for the existing development OCR sandbox question.

Run ``python -m app.seed_step_review_demo`` from backend. This command never
creates a new academic question or changes production data.
"""

from uuid import UUID

from app.core.config import get_settings
from app.database.session import get_session_factory
from app.questions.models import Question, QuestionStatus, QuestionType


DEMO_QUESTION_ID = UUID("c0000000-0000-0000-0000-000000000001")
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
        if (question is None or question.source_type != "SAMPLE_TEST"
                or question.question_type != QuestionType.OPEN_RESPONSE
                or question.status != QuestionStatus.APPROVED
                or DEMO_CONTENT_MARKER not in question.content):
            raise RuntimeError("The expected development sample question is missing or changed.")
        if question.correct_answer not in {None, DEMO_ANSWER}:
            raise RuntimeError("The sample already has a different reviewed answer; no overwrite was made.")
        if question.correct_answer == DEMO_ANSWER and question.explanation == DEMO_EXPLANATION:
            return "already_installed"
        question.correct_answer = DEMO_ANSWER
        question.explanation = DEMO_EXPLANATION
        session.commit()
        return "installed"


if __name__ == "__main__":
    print(f"step_review_demo: {install()} ({DEMO_QUESTION_ID})")
