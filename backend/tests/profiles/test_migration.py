from uuid import UUID, uuid4

from alembic import op
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Engine, MetaData, Table, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.dml import Insert
import pytest

from app.users.models import Role, User
from tests.migrations import load_migration


def test_profile_migration_backfills_existing_active_and_inactive_users(sqlite_engine: Engine) -> None:
    existing: dict[Role, set[UUID]] = {role: set() for role in Role}
    with sqlite_engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            load_migration("0002_auth_rbac").upgrade()
            for role in Role:
                for active in [True, False]:
                    user_id = uuid4()
                    existing[role].add(user_id)
                    connection.execute(User.__table__.insert().values(
                        id=user_id, email=f"{role.value.lower()}-{int(active)}@example.com",
                        password_hash="migration-test-only-hash", full_name="Existing User", role=role, is_active=active,
                    ))
            load_migration("0003_profiles").upgrade()
    # Inspect the schema as it existed at revision 0003. Current ORM models may
    # legitimately contain columns introduced by later migrations.
    metadata = MetaData()
    tables = {
        Role.STUDENT: Table("student_profiles", metadata, autoload_with=sqlite_engine),
        Role.TEACHER: Table("teacher_profiles", metadata, autoload_with=sqlite_engine),
        Role.PARENT: Table("parent_profiles", metadata, autoload_with=sqlite_engine),
    }
    with sqlite_engine.connect() as connection:
        for role, table in tables.items():
            profiles = connection.execute(select(table)).mappings().all()
            assert {UUID(str(profile["user_id"])) for profile in profiles} == existing[role]
            assert all(profile["created_at"] and profile["updated_at"] for profile in profiles)
        for profile in connection.execute(select(tables[Role.STUDENT])).mappings():
            assert profile["grade_level"] == 12
            assert profile["school_name"] is None and profile["date_of_birth"] is None
    with sqlite_engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            load_migration("0003_profiles").downgrade()
        assert set(inspect(connection).get_table_names()) == {"users", "auth_sessions", "auth_refresh_tokens"}
        assert len(connection.execute(select(User.id)).all()) == 8


def test_backfill_source_and_destination_use_the_isolated_postgres_schema(
    sqlite_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    statements: list[object] = []
    with sqlite_engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            load_migration("0002_auth_rbac").upgrade()
            monkeypatch.setattr(op, "execute", statements.append)
            load_migration("0003_profiles").upgrade()
    assert len(statements) == 3
    for statement in statements:
        assert isinstance(statement, Insert)
        sql = str(statement.compile(
            dialect=postgresql.dialect(),
            schema_translate_map={None: "isolated_profile_test"},
            render_schema_translate=True,
        ))
        assert "FROM isolated_profile_test.users" in sql
        assert f"INSERT INTO isolated_profile_test.{statement.table.name}" in sql
