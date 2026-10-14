from collections.abc import Iterator
import secrets
import os
from sqlite3 import Connection
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry, StaticPool
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import Settings, get_settings
from app.application import create_app
from app.database.session import get_db
from tests.migrations import upgrade_test_schema


@pytest.fixture(autouse=True)
def isolate_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    get_settings.cache_clear()

    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name.upper(), raising=False)
        monkeypatch.delenv(field_name, raising=False)

    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_NAME", "edums_test")
    monkeypatch.setenv("DATABASE_USER", "test_user")

    yield

    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        debug=False,
        database_name="edums_test",
        database_user="test_user",
        database_password="",
        frontend_url="http://localhost:3000",
        jwt_secret_key=secrets.token_urlsafe(48),
    )


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def sqlite_engine() -> Iterator[Engine]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def configure_sqlite(connection: Connection, record: ConnectionPoolEntry) -> None:
        connection.execute("PRAGMA foreign_keys=ON")
        # Test-only equivalent of the PostgreSQL built-in used by profile backfill.
        connection.create_function("gen_random_uuid", 0, lambda: uuid4().hex)

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_engine(sqlite_engine: Engine) -> Engine:
    with sqlite_engine.begin() as connection:
        upgrade_test_schema(connection)
    return sqlite_engine


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    with Session(db_engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def db_app(settings: Settings, db_engine: Engine) -> FastAPI:
    application = create_app(settings)
    factory = sessionmaker(bind=db_engine, expire_on_commit=False, autoflush=False)

    def override_db() -> Iterator[Session]:
        with factory() as session:
            try:
                yield session
            except Exception:
                session.rollback()
                raise

    application.dependency_overrides[get_db] = override_db
    return application


@pytest.fixture
def db_client(db_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(db_app) as client:
        yield client


@pytest.fixture
def postgres_engine() -> Iterator[Engine]:
    """Optional integration DB; each test owns and removes only its random schema."""
    database_url = os.environ.get("EDUMS_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set EDUMS_TEST_DATABASE_URL to run real PostgreSQL tests")
    url = make_url(database_url)
    if url.drivername != "postgresql+psycopg":
        pytest.fail("EDUMS_TEST_DATABASE_URL must use postgresql+psycopg")
    engine = create_engine(url, isolation_level="READ COMMITTED", hide_parameters=True, connect_args={"connect_timeout": 5})
    schema = f"edums_test_{uuid4().hex}"

    @event.listens_for(engine, "connect")
    def configure_search_path(dbapi_connection, connection_record) -> None:
        with dbapi_connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}", public')

    translated = engine.execution_options(schema_translate_map={None: schema})
    created = False
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        created = True
        with translated.begin() as connection:
            # Alembic ALTER COLUMN operations do not consistently honor
            # schema_translate_map, so keep unqualified DDL inside this test's
            # isolated schema as well.
            # pgvector installs its `vector` type in public. Keep the isolated
            # schema first while allowing migrations to resolve extension types.
            connection.exec_driver_sql(
                f'SET LOCAL search_path TO "{schema}", public'
            )
            upgrade_test_schema(connection)
        yield translated
    finally:
        if created:
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()
