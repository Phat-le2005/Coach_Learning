"""Disposable QA server for the two-context browser acceptance test.

Uses a fresh schema in a dedicated *_qa PostgreSQL DB. Never seeds a normal DB.
Run from backend with LIVE_QA_DATABASE_URL / LIVE_QA_ARTIFACT_DIR set.
"""
import json
import os
from pathlib import Path
import secrets
from uuid import uuid4

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema

from app.application import create_app
from app.core.config import Settings
from app.database.session import get_db
from app.users.models import User
from tests.migrations import upgrade_test_schema
from tests.math_solutions.test_ink_postgres_concurrency import _create_attempt, PASSWORD


def create_harness():
    url = make_url(os.environ["LIVE_QA_DATABASE_URL"])
    if not url.database.endswith("_qa") or url.host not in ("127.0.0.1", "localhost"):
        raise RuntimeError("Dedicated loopback *_qa DB required")
    schema = "live_qa_" + uuid4().hex
    engine = create_engine(url, hide_parameters=True)
    @event.listens_for(engine, "connect")
    def search_path(connection, record):
        # Persist search_path across pool rollback, including read-only requests.
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute(f'SET search_path TO "{schema}", public')
        connection.autocommit = False
    with engine.begin() as connection:
        # Keep the extension out of disposable schemas so another QA run can
        # create tables too. This database is explicitly dedicated to this harness.
        connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public")
        extension_schema = connection.exec_driver_sql("SELECT n.nspname FROM pg_extension e JOIN pg_namespace n ON e.extnamespace=n.oid WHERE e.extname='vector'").scalar_one()
        if extension_schema != "public":
            if not extension_schema.startswith(("live_qa_", "edums_test_")):
                raise RuntimeError("Refusing to move an extension owned by an unrelated schema")
            connection.exec_driver_sql("ALTER EXTENSION vector SET SCHEMA public")
        connection.execute(CreateSchema(schema))
        connection.exec_driver_sql(f'SET LOCAL search_path TO "{schema}", public')
        upgrade_test_schema(connection)
    factory = sessionmaker(engine, expire_on_commit=False, autoflush=False)
    with factory() as db:
        owner, attempt = _create_attempt(db)
        email = db.get(User, owner).email
    directory = Path(os.environ["LIVE_QA_ARTIFACT_DIR"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "qa-session.json").write_text(json.dumps({"attemptId": str(attempt), "email": email,
        "password": PASSWORD, "schema": schema, "source": "DISPOSABLE_QA_POINTER_REPLAY"}), encoding="utf8")
    settings = Settings(_env_file=None, app_env="test", database_name=url.database, database_user=url.username,
        database_password=url.password, database_host=url.host, database_port=url.port,
        jwt_secret_key=secrets.token_urlsafe(48), frontend_url=os.environ.get("LIVE_QA_FRONTEND_ORIGIN", "http://127.0.0.1:3050"))
    app = create_app(settings)
    def db_session():
        with factory() as db:
            try:
                yield db
            except Exception:
                db.rollback()
                raise
    app.dependency_overrides[get_db] = db_session
    return app


if __name__ == "__main__":
    import uvicorn
    bind = os.environ.get("LIVE_QA_BIND_HOST", "127.0.0.1")
    if bind not in ("127.0.0.1", "0.0.0.0"):
        raise RuntimeError("Unsupported QA bind host")
    uvicorn.run(create_harness(), host=bind, port=8050, ws_max_size=300000)
