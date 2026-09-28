from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.questions.models import (
    Question,
    QuestionConcept,
    QuestionGroup,
    QuestionGroupItem,
    QuestionGroupScoringPolicy,
    QuestionGroupType,
    QuestionLearningOutcome,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.subjects.models import Subject
from app.users.models import User
from tests.practice.conftest import PracticeContent


@dataclass(frozen=True)
class GroupPracticeContent:
    group: QuestionGroup
    children: tuple[Question, Question, Question, Question]


def create_group(
    session: Session,
    content: PracticeContent,
    author: User,
    *,
    group_status: QuestionStatus = QuestionStatus.APPROVED,
    child_status: QuestionStatus = QuestionStatus.APPROVED,
    child_type: QuestionType = QuestionType.TRUE_FALSE,
    missing_mapping: str | None = None,
    child_subject_id: UUID | None = None,
    group_subject_id: UUID | None = None,
    label_orders: tuple[tuple[str, int], ...] = (
        ("a", 0),
        ("b", 1),
        ("c", 2),
        ("d", 3),
    ),
) -> GroupPracticeContent:
    suffix = uuid4().hex[:8]
    children: list[Question] = []
    answers = ("TRUE", "FALSE", "TRUE", "FALSE")
    for index, answer in enumerate(answers):
        question = Question(
            subject_id=child_subject_id or content.subject.id,
            content=f"Grouped statement {index + 1} ({suffix})",
            question_type=child_type,
            difficulty=0.5,
            correct_answer=answer,
            explanation="Group practice fixture",
            source_type="TEST",
            source_reference="group-practice-suite",
            exam_weight=0.0,
            status=child_status,
            created_by=author.id,
        )
        if missing_mapping != "concept":
            question.concept_links = [
                QuestionConcept(concept_id=content.concept.id, weight=1.0)
            ]
        if missing_mapping != "problem_type":
            question.problem_type_links = [
                QuestionProblemType(
                    problem_type_id=content.problem_type.id,
                    weight=1.0,
                    is_primary=True,
                )
            ]
        if missing_mapping != "learning_outcome":
            question.learning_outcome_links = [
                QuestionLearningOutcome(
                    learning_outcome_id=content.learning_outcome.id,
                    weight=1.0,
                )
            ]
        children.append(question)

    group = QuestionGroup(
        subject_id=group_subject_id or content.subject.id,
        content=f"Evaluate four statements ({suffix})",
        group_type=QuestionGroupType.TRUE_FALSE_FOUR,
        scoring_policy=QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE,
        difficulty=0.5,
        source_type="TEST",
        source_reference="group-practice-suite",
        exam_weight=1.0,
        status=group_status,
        created_by=author.id,
    )
    group.items = [
        QuestionGroupItem(
            question=question,
            label=label,
            order_index=order_index,
        )
        for question, (label, order_index) in zip(
            children, label_orders, strict=True
        )
    ]
    session.add(group)
    session.commit()
    return GroupPracticeContent(group=group, children=tuple(children))


def create_other_subject(session: Session) -> Subject:
    subject = Subject(
        code=f"OTHER-{uuid4().hex[:8].upper()}",
        name="Other group practice subject",
        grade_level=12,
    )
    session.add(subject)
    session.commit()
    return subject
