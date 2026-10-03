from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect

from tests.migrations import load_migration


def test_learning_feedback_migration_upgrade_and_downgrade(db_engine: Engine) -> None:
    migration = load_migration("0038_learning_feedback_loop")
    expected = {"learning_feedback_decisions"}
    with db_engine.begin() as connection:
        assert expected.issubset(set(inspect(connection).get_table_names()))
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
        assert expected.isdisjoint(set(inspect(connection).get_table_names()))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
        assert expected.issubset(set(inspect(connection).get_table_names()))
