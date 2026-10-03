from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect

from tests.migrations import load_migration


def test_learning_feedback_migration_upgrade_and_downgrade(db_engine: Engine) -> None:
    migration_38 = load_migration("0038_learning_feedback_loop")
    migration_39 = load_migration("0039_learning_feedback_hardening")
    expected = {"learning_feedback_decisions"}
    with db_engine.begin() as connection:
        assert expected.issubset(set(inspect(connection).get_table_names()))
        with Operations.context(MigrationContext.configure(connection)):
            migration_39.downgrade()
            migration_38.downgrade()
        assert expected.isdisjoint(set(inspect(connection).get_table_names()))
        with Operations.context(MigrationContext.configure(connection)):
            migration_38.upgrade()
            migration_39.upgrade()
        assert expected.issubset(set(inspect(connection).get_table_names()))


def test_learning_feedback_hardening_migration_upgrade_and_downgrade(db_engine: Engine) -> None:
    migration = load_migration("0039_learning_feedback_hardening")
    expected_cols = {"next_target_type", "next_concept_id", "next_problem_type_id", "next_reason_code"}
    with db_engine.begin() as connection:
        cols = {col["name"] for col in inspect(connection).get_columns("learning_feedback_decisions")}
        assert expected_cols.issubset(cols)
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        cols_after_down = {col["name"] for col in inspect(connection).get_columns("learning_feedback_decisions")}
        assert expected_cols.isdisjoint(cols_after_down)
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        cols_after_up = {col["name"] for col in inspect(connection).get_columns("learning_feedback_decisions")}
        assert expected_cols.issubset(cols_after_up)
