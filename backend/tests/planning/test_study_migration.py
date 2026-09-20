from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect

from tests.migrations import load_migration


def test_study_planning_migration_downgrade_and_upgrade(db_engine: Engine) -> None:
    migration = load_migration("0019_study_planning_core")
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {
                "study_plans",
                "study_tasks",
            }
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before
