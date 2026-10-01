from dataclasses import dataclass
import re
import unicodedata

from app.core.exceptions import ApplicationError
from app.practice.models import EvaluationStatus
from app.questions.models import Question, QuestionType


@dataclass(frozen=True, slots=True)
class AnswerEvaluation:
    is_correct: bool | None
    score: float | None
    status: EvaluationStatus


class AnswerEvaluationService:
    """Evaluate objective answers without AI or route-level grading rules."""

    _WHITESPACE = re.compile(r"\s+")

    def evaluate(self, question: Question, student_answer: str) -> AnswerEvaluation:
        return self.evaluate_values(
            question.question_type,
            question.correct_answer,
            student_answer,
            option_labels=[option.label for option in question.options],
        )

    def evaluate_values(
        self,
        question_type: QuestionType,
        correct_answer: str | None,
        student_answer: str,
        *,
        option_labels: list[str] | None = None,
    ) -> AnswerEvaluation:
        answer = self.normalize(student_answer)
        if not answer:
            raise ApplicationError(422, "ANSWER_REQUIRED", "Student answer cannot be blank.")

        if question_type == QuestionType.OPEN_RESPONSE:
            return AnswerEvaluation(None, None, EvaluationStatus.NEEDS_EVALUATION)

        expected = self.normalize(correct_answer or "")
        if not expected:
            return AnswerEvaluation(None, None, EvaluationStatus.NEEDS_TEACHER_REVIEW)

        if question_type == QuestionType.MULTIPLE_CHOICE:
            labels = {self.normalize(label) for label in (option_labels or [])}
            if expected not in labels:
                return AnswerEvaluation(None, None, EvaluationStatus.NEEDS_TEACHER_REVIEW)
            if answer not in labels:
                raise ApplicationError(
                    422,
                    "INVALID_MULTIPLE_CHOICE_ANSWER",
                    "Student answer must match one of the question option labels.",
                )
        elif question_type == QuestionType.TRUE_FALSE:
            if expected not in {"true", "false"}:
                return AnswerEvaluation(None, None, EvaluationStatus.NEEDS_TEACHER_REVIEW)
            if answer not in {"true", "false"}:
                raise ApplicationError(
                    422,
                    "INVALID_TRUE_FALSE_ANSWER",
                    "Student answer must be TRUE or FALSE.",
                )

        correct = answer == expected
        return AnswerEvaluation(
            is_correct=correct,
            score=1.0 if correct else 0.0,
            status=EvaluationStatus.AUTO_EVALUATED,
        )

    @classmethod
    def normalize(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        return cls._WHITESPACE.sub(" ", normalized.strip()).casefold()
