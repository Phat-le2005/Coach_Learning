from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect

from tests.migrations import load_migration


def test_diagnostic_revision_downgrade_and_upgrade(db_engine: Engine) -> None:
    migration = load_migration("0013_diagnostic_assessment")
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {
                "diagnostic_assessments",
                "diagnostic_blueprint_items",
            }
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before


def test_diagnostic_attempt_context_migration_downgrade_and_upgrade(db_engine: Engine) -> None:
    migration = load_migration("0015_diagnostic_attempt_context")
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {
                "diagnostic_attempt_contexts",
            }
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before
