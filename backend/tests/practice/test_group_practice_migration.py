from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect

from tests.migrations import load_migration


def test_group_practice_revision_downgrade_and_reupgrade(db_engine: Engine) -> None:
    migration = load_migration("0031_question_group_practice")
    assert migration.revision == "0031_question_group_practice"
    assert migration.down_revision == "0030_question_groups"

    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        assert {"question_group_attempts", "question_group_attempt_items"} <= before
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            downgraded = set(inspect(connection).get_table_names())
            assert "questions" in downgraded
            assert "question_groups" in downgraded
            assert downgraded == before - {
                "question_group_attempts",
                "question_group_attempt_items",
            }
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before


def test_group_attempt_database_contract(db_engine: Engine) -> None:
    inspector = inspect(db_engine)
    assert tuple(
        inspector.get_pk_constraint("question_group_attempts")[
            "constrained_columns"
        ]
    ) == ("id",)
    unique_constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("question_group_attempts")
    }
    checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints("question_group_attempts")
    }
    foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key
        for foreign_key in inspector.get_foreign_keys("question_group_attempts")
    }
    indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("question_group_attempts")
    }

    assert unique_constraints["uq_question_group_attempts_session_group"] == (
        "practice_session_id",
        "question_group_id",
    )
    assert {
        "ck_question_group_attempts_correct_count_range",
        "ck_question_group_attempts_score_range",
        "ck_question_group_attempts_response_time_positive",
    } <= checks.keys()
    assert "BETWEEN 0 AND 4" in checks[
        "ck_question_group_attempts_correct_count_range"
    ]
    assert "BETWEEN 0.0 AND 1.0" in checks[
        "ck_question_group_attempts_score_range"
    ]
    assert "> 0" in checks["ck_question_group_attempts_response_time_positive"]
    assert foreign_keys[("practice_session_id", "student_id")][
        "referred_table"
    ] == "practice_sessions"
    assert foreign_keys[("practice_session_id", "student_id")]["options"][
        "ondelete"
    ] == "CASCADE"
    assert foreign_keys[("question_group_id",)]["referred_table"] == "question_groups"
    assert foreign_keys[("question_group_id",)]["options"]["ondelete"] == "RESTRICT"
    assert indexes["ix_question_group_attempts_student_created"] == (
        "student_id",
        "created_at",
    )
    assert indexes["ix_question_group_attempts_group_created"] == (
        "question_group_id",
        "created_at",
    )


def test_group_attempt_item_database_contract(db_engine: Engine) -> None:
    inspector = inspect(db_engine)
    assert tuple(
        inspector.get_pk_constraint("question_group_attempt_items")[
            "constrained_columns"
        ]
    ) == ("id",)
    unique_constraints = {
        constraint["name"]: tuple(constraint["column_names"])
        for constraint in inspector.get_unique_constraints(
            "question_group_attempt_items"
        )
    }
    checks = {
        constraint["name"]: constraint["sqltext"]
        for constraint in inspector.get_check_constraints(
            "question_group_attempt_items"
        )
    }
    foreign_keys = {
        tuple(foreign_key["constrained_columns"]): foreign_key
        for foreign_key in inspector.get_foreign_keys(
            "question_group_attempt_items"
        )
    }
    indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspector.get_indexes("question_group_attempt_items")
    }

    assert unique_constraints == {
        "uq_question_group_attempt_items_parent_label": (
            "question_group_attempt_id",
            "label",
        ),
        "uq_question_group_attempt_items_parent_order": (
            "question_group_attempt_id",
            "order_index",
        ),
        "uq_question_group_attempt_items_question_attempt": (
            "question_attempt_id",
        ),
    }
    assert {
        "ck_question_group_attempt_items_label_allowed",
        "ck_question_group_attempt_items_order_index_range",
    } <= checks.keys()
    assert "'a', 'b', 'c', 'd'" in checks[
        "ck_question_group_attempt_items_label_allowed"
    ]
    assert "BETWEEN 0 AND 3" in checks[
        "ck_question_group_attempt_items_order_index_range"
    ]
    assert foreign_keys[("question_group_attempt_id",)]["referred_table"] == (
        "question_group_attempts"
    )
    assert foreign_keys[("question_group_attempt_id",)]["options"]["ondelete"] == "CASCADE"
    assert foreign_keys[("question_group_item_id",)]["referred_table"] == (
        "question_group_items"
    )
    assert foreign_keys[("question_group_item_id",)]["options"]["ondelete"] == "RESTRICT"
    assert foreign_keys[("question_attempt_id",)]["referred_table"] == (
        "question_attempts"
    )
    assert foreign_keys[("question_attempt_id",)]["options"]["ondelete"] == "RESTRICT"
    assert indexes["ix_question_group_attempt_items_group_item"] == (
        "question_group_item_id",
    )
