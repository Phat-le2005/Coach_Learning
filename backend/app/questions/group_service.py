from __future__ import annotations

import logging
from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ApplicationError
from app.questions.group_schemas import QuestionGroupCreate, QuestionGroupItemInput
from app.questions.models import (
    Question,
    QuestionGroup,
    QuestionGroupItem,
    QuestionStatus,
    QuestionType,
)
from app.subjects.models import Subject
from app.users.models import User

logger = logging.getLogger(__name__)


class QuestionGroupService:
    """Creates and reads four-statement groups without changing child questions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, actor: User, data: QuestionGroupCreate) -> QuestionGroup:
        self._validate_item_shape(data.items)
        if self.session.get(Subject, data.subject_id) is None:
            raise ApplicationError(
                404,
                "QUESTION_GROUP_SUBJECT_NOT_FOUND",
                "Question group subject was not found.",
            )

        question_ids = [item.question_id for item in data.items]
        questions = list(
            self.session.scalars(
                select(Question).where(Question.id.in_(question_ids))
            )
        )
        questions_by_id = {question.id: question for question in questions}
        if set(questions_by_id) != set(question_ids):
            raise ApplicationError(
                404,
                "QUESTION_GROUP_CHILD_NOT_FOUND",
                "One or more question group children were not found.",
            )
        if any(question.subject_id != data.subject_id for question in questions):
            raise ApplicationError(
                422,
                "QUESTION_GROUP_CHILD_SUBJECT_MISMATCH",
                "Every child question must belong to the group subject.",
            )
        if any(
            question.question_type != QuestionType.TRUE_FALSE
            for question in questions
        ):
            raise ApplicationError(
                422,
                "QUESTION_GROUP_CHILD_TYPE_INVALID",
                "Every child question must have type TRUE_FALSE.",
            )
        if any(
            not isinstance(question.correct_answer, str)
            or question.correct_answer.strip().upper() not in {"TRUE", "FALSE"}
            for question in questions
        ):
            raise ApplicationError(
                422,
                "QUESTION_GROUP_CHILD_ANSWER_INVALID",
                "Every child question must have a TRUE or FALSE correct answer.",
            )
        if any(question.status == QuestionStatus.ARCHIVED for question in questions):
            raise ApplicationError(
                409,
                "QUESTION_GROUP_CHILD_ARCHIVED",
                "Archived questions cannot be added to a question group.",
            )

        grouped_child_id = self.session.scalar(
            select(QuestionGroupItem.question_id).where(
                QuestionGroupItem.question_id.in_(question_ids)
            )
        )
        if grouped_child_id is not None:
            raise ApplicationError(
                409,
                "QUESTION_GROUP_CHILD_ALREADY_GROUPED",
                "A child question already belongs to another question group.",
            )

        group = QuestionGroup(
            **data.model_dump(exclude={"items"}),
            status=QuestionStatus.DRAFT,
            created_by=actor.id,
        )
        group.items = [
            QuestionGroupItem(
                question_id=item.question_id,
                label=item.label,
                order_index=item.order_index,
            )
            for item in sorted(data.items, key=lambda item: item.order_index)
        ]
        self.validate_shape(group)
        self.session.add(group)
        try:
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            if self._is_child_membership_unique_violation(error):
                raise ApplicationError(
                    409,
                    "QUESTION_GROUP_CHILD_ALREADY_GROUPED",
                    "A child question already belongs to another question group.",
                ) from error
            raise ApplicationError(
                409,
                "QUESTION_GROUP_CONFLICT",
                "Question group could not be created because of a database "
                "constraint conflict.",
            ) from error
        logger.info(
            "Question group created (group_id=%s, created_by=%s)",
            group.id,
            actor.id,
        )
        return self.get(group.id)

    def get(self, group_id: UUID) -> QuestionGroup:
        group = self.session.scalar(
            select(QuestionGroup)
            .options(
                selectinload(QuestionGroup.items).selectinload(
                    QuestionGroupItem.question
                )
            )
            .where(QuestionGroup.id == group_id)
        )
        if group is None:
            raise ApplicationError(
                404,
                "QUESTION_GROUP_NOT_FOUND",
                "Question group was not found.",
            )
        return group

    def validate_shape(self, group: QuestionGroup) -> None:
        self._validate_item_shape(group.items)

    @staticmethod
    def _validate_item_shape(
        items: Sequence[QuestionGroupItemInput | QuestionGroupItem],
    ) -> None:
        if len(items) != 4:
            raise ApplicationError(
                422,
                "QUESTION_GROUP_ITEM_COUNT_INVALID",
                "A question group must contain exactly four child questions.",
            )
        if {item.label for item in items} != {"a", "b", "c", "d"}:
            raise ApplicationError(
                422,
                "QUESTION_GROUP_LABELS_INVALID",
                "Question group labels must be exactly a, b, c, d.",
            )
        if {item.order_index for item in items} != {0, 1, 2, 3}:
            raise ApplicationError(
                422,
                "QUESTION_GROUP_ORDER_INVALID",
                "Question group order indexes must be exactly 0, 1, 2, 3.",
            )
        if len({item.question_id for item in items}) != 4:
            raise ApplicationError(
                422,
                "QUESTION_GROUP_CHILD_DUPLICATE",
                "Question group child question IDs must be unique.",
            )

    @staticmethod
    def _is_child_membership_unique_violation(error: IntegrityError) -> bool:
        current: BaseException | None = error.orig
        visited: set[int] = set()
        while current is not None and id(current) not in visited:
            visited.add(id(current))
            diagnostic = getattr(current, "diag", None)
            constraint_name = getattr(diagnostic, "constraint_name", None)
            if constraint_name is None:
                constraint_name = getattr(current, "constraint_name", None)
            if constraint_name == "uq_question_group_items_question":
                return True
            current = current.__cause__ or current.__context__
        return False
