from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect

from tests.migrations import load_migration


def test_teaching_plans_migration_downgrade_and_upgrade(db_engine: Engine) -> None:
    migration = load_migration("0016_teacher_teaching_plans")
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {
                "teaching_plans",
                "teaching_plan_items",
            }
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before
