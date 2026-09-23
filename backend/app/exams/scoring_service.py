from __future__ import annotations

import logging
import math
import re
import unicodedata
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.exams.models import Exam, ExamAttempt, ExamAttemptStatus, ExamQuestion, ExamResponse
from app.questions.models import Question, QuestionOption, QuestionType

logger = logging.getLogger(__name__)


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(without_marks.lower().split())


def _try_parse_float(val: str) -> float | None:
    try:
        cleaned = val.replace(",", ".").strip()
        return float(cleaned)
    except (ValueError, AttributeError):
        return None


class ExamScoringService:
    """Deterministic scoring engine for exams.

    Architectural Guarantees:
    - Zero LLM inference: 100% deterministic rule-based evaluation.
    - Robust answer normalization for Vietnamese characters, whitespace, and numeric equivalents.
    - Evaluates questions across MULTIPLE_CHOICE, TRUE_FALSE, and SHORT_ANSWER.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def score_attempt(self, attempt_id: UUID) -> ExamAttempt:
        attempt = self.session.scalar(
            select(ExamAttempt)
            .options(
                selectinload(ExamAttempt.responses),
                selectinload(ExamAttempt.exam).selectinload(Exam.questions),
            )
            .where(ExamAttempt.id == attempt_id)
        )
        if attempt is None:
            raise ValueError(f"ExamAttempt {attempt_id} not found.")

        # Map exam questions by question_id for quick points and details lookup
        exam_questions_by_qid: dict[UUID, ExamQuestion] = {
            eq.question_id: eq for eq in attempt.exam.questions
        }

        # Query all relevant Question entities with options
        q_ids = list(exam_questions_by_qid.keys())
        questions = list(
            self.session.scalars(
                select(Question)
                .options(selectinload(Question.options))
                .where(Question.id.in_(q_ids))
            ).all()
        )
        questions_by_id: dict[UUID, Question] = {q.id: q for q in questions}

        total_points = sum(eq.points for eq in attempt.exam.questions)
        earned_score = 0.0
        correct_count = 0

        # Existing responses mapped by question_id
        responses_by_qid: dict[UUID, ExamResponse] = {
            r.question_id: r for r in attempt.responses
        }

        for qid, eq in exam_questions_by_qid.items():
            question = questions_by_id.get(qid)
            resp = responses_by_qid.get(qid)

            if resp is None:
                # Student did not answer this question
                resp = ExamResponse(
                    attempt_id=attempt.id,
                    question_id=qid,
                    student_answer=None,
                    is_correct=False,
                    score_awarded=0.0,
                    order_answered=0,
                )
                self.session.add(resp)
                continue

            if question is None or not resp.student_answer:
                resp.is_correct = False
                resp.score_awarded = 0.0
                continue

            # Deterministic check
            is_correct = self._evaluate_question(question, resp)
            resp.is_correct = is_correct
            resp.score_awarded = eq.points if is_correct else 0.0

            if is_correct:
                earned_score += eq.points
                correct_count += 1

        total_questions = len(attempt.exam.questions)
        accuracy = (correct_count / total_questions) if total_questions > 0 else 0.0

        attempt.score = round(earned_score, 2)
        attempt.total_points = round(total_points, 2)
        attempt.accuracy = round(accuracy, 4)
        if attempt.status != ExamAttemptStatus.TIMED_OUT:
            attempt.status = ExamAttemptStatus.GRADED

        self.session.flush()
        return attempt

    def _evaluate_question(self, question: Question, response: ExamResponse) -> bool:
        ans_raw = response.student_answer.strip() if response.student_answer else ""
        if not ans_raw:
            return False

        if question.question_type == QuestionType.MULTIPLE_CHOICE:
            # 1. Option matching by ID
            if response.selected_option_id:
                for opt in question.options:
                    if opt.id == response.selected_option_id:
                        ans_norm = _normalize_text(opt.label)
                        corr_norm = _normalize_text(question.correct_answer)
                        return ans_norm == corr_norm or _normalize_text(opt.content) == corr_norm

            # 2. Match label (A, B, C, D)
            ans_norm = _normalize_text(ans_raw)
            corr_norm = _normalize_text(question.correct_answer)
            if ans_norm == corr_norm:
                return True

            # 3. Match option content
            for opt in question.options:
                if _normalize_text(opt.label) == corr_norm and _normalize_text(opt.content) == ans_norm:
                    return True
                if _normalize_text(opt.label) == ans_norm and _normalize_text(opt.content) == corr_norm:
                    return True

            return False

        elif question.question_type == QuestionType.TRUE_FALSE:
            ans_norm = _normalize_text(ans_raw)
            corr_norm = _normalize_text(question.correct_answer)

            # Map boolean variations
            truthy = {"dung", "true", "t", "1", "yes", "y", "chinh xac"}
            falsy = {"sai", "false", "f", "0", "no", "n", "khong dung"}

            if ans_norm in truthy and corr_norm in truthy:
                return True
            if ans_norm in falsy and corr_norm in falsy:
                return True
            return ans_norm == corr_norm

        elif question.question_type == QuestionType.SHORT_ANSWER:
            ans_norm = _normalize_text(ans_raw)
            corr_norm = _normalize_text(question.correct_answer)

            if ans_norm == corr_norm:
                return True

            # Numeric comparison with tolerance
            f_ans = _try_parse_float(ans_raw)
            f_corr = _try_parse_float(question.correct_answer or "")
            if f_ans is not None and f_corr is not None:
                return math.isclose(f_ans, f_corr, rel_tol=1e-4, abs_tol=1e-4)

            return False

        # Open response or other fallback
        return _normalize_text(ans_raw) == _normalize_text(question.correct_answer)
