from pathlib import Path
from types import ModuleType

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import Connection

from app.database.base import Base


def migration_scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")))


def load_migration(revision: str) -> ModuleType:
    script = migration_scripts().get_revision(revision)
    assert script is not None
    return script.module


def upgrade_test_schema(connection: Connection) -> None:
    # Manual Operations-driven tests skip Alembic's command runner, which
    # normally creates its version bookkeeping table. Historical revision 0022
    # widens alembic_version.version_num on PostgreSQL; ensure the isolated
    # *test schema* has the original Alembic table before applying migrations.
    # SQLite tests must retain the prior exact-table-count expectations.
    if connection.dialect.name == "postgresql":
        connection.exec_driver_sql(
            "CREATE TABLE IF NOT EXISTS alembic_version "
            "(version_num VARCHAR(32) NOT NULL PRIMARY KEY)"
        )
    context = MigrationContext.configure(connection, opts={"target_metadata": Base.metadata})
    with Operations.context(context):
        for script in reversed(list(migration_scripts().walk_revisions())):
            script.module.upgrade()


def downgrade_test_schema(connection: Connection) -> None:
    with Operations.context(MigrationContext.configure(connection)):
        for script in migration_scripts().walk_revisions():
            script.module.downgrade()
