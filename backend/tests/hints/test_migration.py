from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, inspect

from tests.migrations import load_migration


def test_hint_revision_downgrade_and_upgrade(db_engine: Engine) -> None:
    migration = load_migration("0023_hint_system")
    with db_engine.begin() as connection:
        before = set(inspect(connection).get_table_names())
        with Operations.context(MigrationContext.configure(connection)):
            migration.downgrade()
            assert set(inspect(connection).get_table_names()) == before - {
                "question_hints",
                "practice_question_hints",
            }
            migration.upgrade()
        assert set(inspect(connection).get_table_names()) == before
