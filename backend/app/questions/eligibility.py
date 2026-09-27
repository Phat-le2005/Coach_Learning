from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.sql.elements import ColumnElement

from app.questions.models import Question, QuestionGroupItem


def standalone_question_only(
    question_id: ColumnElement[object] = Question.id,
) -> ColumnElement[bool]:
    """Exclude internal QuestionGroup children from standalone selection paths."""
    return ~exists(
        select(QuestionGroupItem.id).where(
            QuestionGroupItem.question_id == question_id
        )
    )
