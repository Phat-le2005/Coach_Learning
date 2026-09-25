from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.questions.group_schemas import (
    QuestionGroupCreate,
    QuestionGroupInternalRead,
    QuestionGroupItemInput,
)
from app.questions.group_service import QuestionGroupService
from app.questions.models import (
    CognitiveLevel,
    Question,
    QuestionGroup,
    QuestionGroupItem,
    QuestionGroupScoringPolicy,
    QuestionGroupType,
    QuestionStatus,
    QuestionType,
)
from app.subjects.models import Subject
from app.users.models import Role, User
from tests.migrations import load_migration


UserFactory = Callable[[Role, str], User]


def _subject(db_session: Session, code: str) -> Subject:
    subject = Subject(code=code, name=f"Subject {code}", grade_level=12)
    db_session.add(subject)
    db_session.flush()
    return subject


def _questions(
    db_session: Session,
    actor: User,
    subject: Subject,
    *,
    count: int = 4,
    question_type: QuestionType = QuestionType.TRUE_FALSE,
    answer: str | None = None,
    status: QuestionStatus = QuestionStatus.DRAFT,
) -> list[Question]:
    questions = [
        Question(
            subject_id=subject.id,
            content=f"Statement {subject.code} {index} {uuid4().hex}",
            question_type=question_type,
            difficulty=0.5,
            correct_answer=(
                answer
                if answer is not None
                else (" true " if index % 2 == 0 else "FALSE")
            ),
            source_type="TEACHER",
            exam_weight=0.25,
            status=status,
            created_by=actor.id,
        )
        for index in range(count)
    ]
    db_session.add_all(questions)
    db_session.commit()
    return questions


def _items(questions: list[Question]) -> list[QuestionGroupItemInput]:
    return [
        QuestionGroupItemInput(
            question_id=question.id,
            label=label,
            order_index=order_index,
        )
        for question, label, order_index in zip(
            reversed(questions),
            ("d", "c", "b", "a"),
            (3, 2, 1, 0),
            strict=True,
        )
    ]


def _data(
    subject: Subject,
    questions: list[Question],
) -> QuestionGroupCreate:
    return QuestionGroupCreate(
        subject_id=subject.id,
        content="Shared true/false context",
        difficulty=0.6,
        source_type=" teacher ",
        source_reference=" Internal worksheet ",
        source_year=2026,
        cognitive_level=CognitiveLevel.APPLY,
        exam_weight=0.8,
        items=_items(questions),
    )


@pytest.fixture
def group_content(
    db_session: Session,
    question_user_factory: UserFactory,
) -> tuple[User, Subject, list[Question]]:
    actor = question_user_factory(Role.TEACHER, "question-group@example.com")
    subject = _subject(db_session, "QGROUP-MATH12")
    return actor, subject, _questions(db_session, actor, subject)


def test_create_valid_group_is_draft_and_orders_four_children(
    db_session: Session,
    group_content: tuple[User, Subject, list[Question]],
) -> None:
    actor, subject, questions = group_content

    group = QuestionGroupService(db_session).create(
        actor, _data(subject, questions)
    )

    assert group.status == QuestionStatus.DRAFT
    assert group.group_type == QuestionGroupType.TRUE_FALSE_FOUR
    assert group.scoring_policy == QuestionGroupScoringPolicy.MOET_2025_TRUE_FALSE
    assert group.source_type == "TEACHER"
    assert [item.order_index for item in group.items] == [0, 1, 2, 3]
    assert [item.label for item in group.items] == ["a", "b", "c", "d"]
    assert {item.question_id for item in group.items} == {
        question.id for question in questions
    }
    assert all(item.question.question_type == QuestionType.TRUE_FALSE for item in group.items)
    assert QuestionGroupInternalRead.model_validate(group).id == group.id


@pytest.mark.parametrize(
    ("case", "expected_code"),
    [
        ("fewer", "QUESTION_GROUP_ITEM_COUNT_INVALID"),
        ("more", "QUESTION_GROUP_ITEM_COUNT_INVALID"),
        ("duplicate_label", "QUESTION_GROUP_LABELS_INVALID"),
        ("duplicate_order", "QUESTION_GROUP_ORDER_INVALID"),
        ("duplicate_child", "QUESTION_GROUP_CHILD_DUPLICATE"),
    ],
)
def test_service_rejects_invalid_group_shape_before_writing(
    db_session: Session,
    group_content: tuple[User, Subject, list[Question]],
    case: str,
    expected_code: str,
) -> None:
    actor, subject, questions = group_content
    data = _data(subject, questions)
    items = list(data.items)
    if case == "fewer":
        items = items[:3]
    elif case == "more":
        items.append(items[0].model_copy())
    elif case == "duplicate_label":
        items[1] = items[1].model_copy(update={"label": items[0].label})
    elif case == "duplicate_order":
        items[1] = items[1].model_copy(
            update={"order_index": items[0].order_index}
        )
    else:
        items[1] = items[1].model_copy(
            update={"question_id": items[0].question_id}
        )
    invalid = data.model_copy(update={"items": items})

    with pytest.raises(ApplicationError) as error:
        QuestionGroupService(db_session).create(actor, invalid)

    assert error.value.code == expected_code
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupItem)) == 0


def test_create_rejects_missing_subject_before_writing(
    db_session: Session,
    group_content: tuple[User, Subject, list[Question]],
) -> None:
    actor, subject, questions = group_content
    data = _data(subject, questions).model_copy(update={"subject_id": uuid4()})

    with pytest.raises(ApplicationError) as error:
        QuestionGroupService(db_session).create(actor, data)

    assert error.value.code == "QUESTION_GROUP_SUBJECT_NOT_FOUND"
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 0


def test_create_rejects_missing_child_without_partial_rows(
    db_session: Session,
    group_content: tuple[User, Subject, list[Question]],
) -> None:
    actor, subject, questions = group_content
    data = _data(subject, questions)
    items = list(data.items)
    items[0] = items[0].model_copy(update={"question_id": uuid4()})

    with pytest.raises(ApplicationError) as error:
        QuestionGroupService(db_session).create(
            actor, data.model_copy(update={"items": items})
        )

    assert error.value.code == "QUESTION_GROUP_CHILD_NOT_FOUND"
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupItem)) == 0


def test_create_rejects_child_from_another_subject(
    db_session: Session,
    group_content: tuple[User, Subject, list[Question]],
) -> None:
    actor, subject, questions = group_content
    other_subject = _subject(db_session, "QGROUP-OTHER")
    replacement = _questions(db_session, actor, other_subject, count=1)[0]
    items = _items(questions)
    items[0] = items[0].model_copy(update={"question_id": replacement.id})

    with pytest.raises(ApplicationError) as error:
        QuestionGroupService(db_session).create(
            actor, _data(subject, questions).model_copy(update={"items": items})
        )

    assert error.value.code == "QUESTION_GROUP_CHILD_SUBJECT_MISMATCH"


@pytest.mark.parametrize(
    ("question_type", "answer", "status", "expected_code"),
    [
        (
            QuestionType.SHORT_ANSWER,
            "TRUE",
            QuestionStatus.DRAFT,
            "QUESTION_GROUP_CHILD_TYPE_INVALID",
        ),
        (
            QuestionType.TRUE_FALSE,
            "YES",
            QuestionStatus.DRAFT,
            "QUESTION_GROUP_CHILD_ANSWER_INVALID",
        ),
        (
            QuestionType.TRUE_FALSE,
            "TRUE",
            QuestionStatus.ARCHIVED,
            "QUESTION_GROUP_CHILD_ARCHIVED",
        ),
    ],
)
def test_create_rejects_invalid_child_state(
    db_session: Session,
    question_user_factory: UserFactory,
    question_type: QuestionType,
    answer: str,
    status: QuestionStatus,
    expected_code: str,
) -> None:
    actor = question_user_factory(Role.TEACHER, f"{expected_code.lower()}@example.com")
    subject = _subject(db_session, f"QG-{uuid4().hex[:8].upper()}")
    questions = _questions(db_session, actor, subject)
    replacement = _questions(
        db_session,
        actor,
        subject,
        count=1,
        question_type=question_type,
        answer=answer,
        status=status,
    )[0]
    items = _items(questions)
    items[0] = items[0].model_copy(update={"question_id": replacement.id})

    with pytest.raises(ApplicationError) as error:
        QuestionGroupService(db_session).create(
            actor, _data(subject, questions).model_copy(update={"items": items})
        )

    assert error.value.code == expected_code
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 0


def test_create_rejects_child_already_in_another_group(
    db_session: Session,
    group_content: tuple[User, Subject, list[Question]],
) -> None:
    actor, subject, questions = group_content
    service = QuestionGroupService(db_session)
    first = service.create(actor, _data(subject, questions))

    with pytest.raises(ApplicationError) as error:
        service.create(actor, _data(subject, questions))

    assert error.value.code == "QUESTION_GROUP_CHILD_ALREADY_GROUPED"
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 1
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupItem)) == 4
    assert service.get(first.id).id == first.id


def test_grouping_does_not_mutate_child_questions(
    db_session: Session,
    group_content: tuple[User, Subject, list[Question]],
) -> None:
    actor, subject, questions = group_content
    column_names = [column.name for column in Question.__table__.columns]
    before = {
        question.id: tuple(getattr(question, name) for name in column_names)
        for question in questions
    }

    QuestionGroupService(db_session).create(actor, _data(subject, questions))
    for question in questions:
        db_session.refresh(question)

    assert {
        question.id: tuple(getattr(question, name) for name in column_names)
        for question in questions
    } == before


def test_question_group_revision_and_downgrade_reupgrade(db_engine: Engine) -> None:
    migration = load_migration("0030_question_groups")
    assert migration.revision == "0030_question_groups"
    assert migration.down_revision == "0029_tutor_learning_memory"

    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        assert {"question_groups", "question_group_items"} <= before
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            downgraded = set(inspect(connection).get_table_names())
            assert "questions" in downgraded
            assert downgraded == before - {
                "question_groups",
                "question_group_items",
            }
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before


def test_question_group_item_database_constraints(db_engine: Engine) -> None:
    inspector = inspect(db_engine)
    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints("question_group_items")
    }
    check_constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("question_group_items")
    }
    foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key
        for foreign_key in inspector.get_foreign_keys("question_group_items")
    }

    assert unique_constraints == {
        "uq_question_group_items_group_label",
        "uq_question_group_items_group_order",
        "uq_question_group_items_question",
    }
    assert {
        "ck_question_group_items_label_allowed",
        "ck_question_group_items_order_index_range",
    } <= check_constraints
    assert foreign_keys[("group_id",)]["options"]["ondelete"] == "CASCADE"
    assert foreign_keys[("question_id",)]["options"]["ondelete"] == "RESTRICT"


def test_question_group_query_index_matches_model_and_migration(
    db_engine: Engine,
) -> None:
    indexes = {
        index["name"]: index["column_names"]
        for index in inspect(db_engine).get_indexes("question_groups")
    }

    assert indexes["ix_question_groups_subject_status_type_difficulty"] == [
        "subject_id",
        "status",
        "group_type",
        "difficulty",
    ]
    assert "ix_question_groups_subject_status" not in indexes


class _ConstraintDiagnostic:
    def __init__(self, constraint_name: str | None) -> None:
        self.constraint_name = constraint_name


class _DriverIntegrityError(Exception):
    def __init__(self, constraint_name: str | None) -> None:
        super().__init__("simulated database constraint conflict")
        self.diag = _ConstraintDiagnostic(constraint_name)


@pytest.mark.parametrize(
    ("constraint_name", "expected_code"),
    [
        (
            "uq_question_group_items_question",
            "QUESTION_GROUP_CHILD_ALREADY_GROUPED",
        ),
        ("uq_question_groups_unrelated", "QUESTION_GROUP_CONFLICT"),
        (None, "QUESTION_GROUP_CONFLICT"),
    ],
)
def test_commit_integrity_error_mapping_is_constraint_specific_and_rolls_back(
    db_session: Session,
    group_content: tuple[User, Subject, list[Question]],
    monkeypatch: pytest.MonkeyPatch,
    constraint_name: str | None,
    expected_code: str,
) -> None:
    actor, subject, questions = group_content
    original_rollback = db_session.rollback
    rollback_called = False

    def fail_commit() -> None:
        raise IntegrityError(
            "INSERT INTO question_group_items ...",
            {},
            _DriverIntegrityError(constraint_name),
        )

    def record_rollback() -> None:
        nonlocal rollback_called
        rollback_called = True
        original_rollback()

    monkeypatch.setattr(db_session, "commit", fail_commit)
    monkeypatch.setattr(db_session, "rollback", record_rollback)

    with pytest.raises(ApplicationError) as error:
        QuestionGroupService(db_session).create(actor, _data(subject, questions))

    assert error.value.code == expected_code
    assert isinstance(error.value.__cause__, IntegrityError)
    assert rollback_called is True
    assert db_session.scalar(select(func.count()).select_from(QuestionGroup)) == 0
    assert db_session.scalar(select(func.count()).select_from(QuestionGroupItem)) == 0


def test_question_type_has_no_true_false_group_member() -> None:
    assert "TRUE_FALSE_GROUP" not in QuestionType.__members__
    assert {member.value for member in QuestionType} == {
        "MULTIPLE_CHOICE",
        "TRUE_FALSE",
        "SHORT_ANSWER",
        "OPEN_RESPONSE",
    }
