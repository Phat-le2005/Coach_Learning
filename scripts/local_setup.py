"""Prepare local .env files and manage this project's private PostgreSQL cluster.

Run with .conda/python.exe scripts/local_setup.py init|start|stop|status.
Only init creates configuration and a database; start/stop never run migrations.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PREFIX = ROOT / ".conda"
LOCAL = ROOT / ".local"
PGDATA = LOCAL / "postgres"
PGBIN = PREFIX / "Library" / "bin"


def configure_postgres_paths() -> None:
    """PostgreSQL's Windows executable lookup requires an ASCII launch path.

    A temporary junction is only an alias; the environment and database remain
    inside the project. Recreate it if Windows has cleaned up the temp folder.
    """
    global PGBIN, PGDATA
    if os.name != "nt" or str(ROOT).isascii():
        return
    suffix = hashlib.sha256(str(ROOT).encode("utf-8")).hexdigest()[:12]
    alias = Path(tempfile.gettempdir()) / f"edums-project-{suffix}"
    if not str(alias).isascii():
        raise RuntimeError("Set TEMP to an ASCII path before starting private PostgreSQL.")
    if not alias.exists():
        quote = lambda path: "'" + str(path).replace("'", "''") + "'"
        command = (f"$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue'; "
                   f"New-Item -ItemType Junction "
                   f"-Path {quote(alias)} -Target {quote(ROOT)} | Out-Null")
        encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive",
                        "-EncodedCommand", encoded], check=True)
    if alias.resolve() != ROOT:
        raise RuntimeError("The temporary PostgreSQL path alias belongs to another directory.")
    PGBIN = alias / ".conda" / "Library" / "bin"
    PGDATA = alias / ".local" / "postgres"


def prepare_env() -> None:
    from dotenv import dotenv_values, set_key

    for example, target, secret_names in (
        (ROOT / "backend/.env.example", ROOT / "backend/.env",
         ("JWT_SECRET_KEY", "SEED_DEMO_PASSWORD", "DATABASE_PASSWORD")),
        (ROOT / "frontend/.env.example", ROOT / "frontend/.env.local",
         ("AUTH_SESSION_SECRET",)),
    ):
        # Existing local configurations belong to the developer; keep them intact.
        if target.exists():
            print(f"Keeping existing {target.relative_to(ROOT)}")
            continue
        target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        for name in secret_names:
            set_key(str(target), name, secrets.token_urlsafe(48))
        if target.parent.name == "backend":
            set_key(str(target), "DATABASE_HOST", "127.0.0.1")
        print(f"Created {target.relative_to(ROOT)} (secrets are not printed)")


def configuration():
    sys.path.insert(0, str(ROOT / "backend"))
    from app.core.config import Settings

    settings = Settings()
    if settings.app_env != "development":
        raise RuntimeError("This helper only manages development databases.")
    if settings.database_host not in ("127.0.0.1", "localhost"):
        raise RuntimeError("Private cluster requires a loopback DATABASE_HOST in backend/.env.")
    return settings


def pg_run(program: str, *arguments: str, check: bool = True):
    executable = PGBIN / f"{program}.exe"
    if not executable.is_file():
        raise RuntimeError(f"Missing {executable}. Recreate environment.yml first.")
    return subprocess.run([str(executable), *arguments], check=check)


def is_running() -> bool:
    return PGDATA.is_dir() and pg_run("pg_ctl", "-D", str(PGDATA), "status", check=False).returncode == 0


def start(settings) -> None:
    if not (PGDATA / "PG_VERSION").is_file():
        raise RuntimeError("Private cluster is missing. Run local_setup.py init first.")
    if is_running():
        return
    # Fail early instead of accidentally connecting to an unrelated PostgreSQL instance.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", settings.database_port))
    pg_run("pg_ctl", "-D", str(PGDATA), "-l", str(PGDATA.parent / "postgres.log"),
           "-o", f"-h 127.0.0.1 -p {settings.database_port}", "-w", "start")


def initialize(settings) -> None:
    import psycopg
    from psycopg import sql

    LOCAL.mkdir(exist_ok=True)
    if not settings.database_password.get_secret_value():
        raise RuntimeError("Set DATABASE_PASSWORD in backend/.env before initializing PostgreSQL.")
    if not (PGDATA / "PG_VERSION").is_file():
        if PGDATA.exists() and any(PGDATA.iterdir()):
            raise RuntimeError("The cluster directory is nonempty; inspect it before retrying initdb.")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=LOCAL,
                                         prefix="pg-password-", delete=False) as password_file:
            password_file.write(settings.database_password.get_secret_value() + "\n")
            password_path = Path(password_file.name)
        try:
            pg_run("initdb", "-D", str(PGDATA), "-U", settings.database_user,
                   "--encoding=UTF8", "--no-locale", "--auth=scram-sha-256",
                   f"--pwfile={PGDATA.parent / password_path.name}")
        finally:
            password_path.unlink(missing_ok=True)
    start(settings)
    credentials = dict(host="127.0.0.1", port=settings.database_port,
                       user=settings.database_user,
                       password=settings.database_password.get_secret_value(), connect_timeout=5)
    with psycopg.connect(dbname="postgres", autocommit=True, **credentials) as connection:
        exists = connection.execute("SELECT 1 FROM pg_database WHERE datname = %s",
                                    (settings.database_name,)).fetchone()
        if not exists:
            connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.database_name)))
    with psycopg.connect(dbname=settings.database_name, autocommit=True, **credentials) as connection:
        connection.execute("CREATE EXTENSION IF NOT EXISTS vector")
        print("Private PostgreSQL is ready; vector extension is available.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "start", "stop", "status"))
    args = parser.parse_args()
    if Path(sys.prefix).resolve() != PREFIX.resolve():
        parser.error("Use this project's .conda/python.exe to run this helper.")
    configure_postgres_paths()
    os.environ["PATH"] = os.pathsep.join((str(PGBIN), str(PREFIX), os.environ.get("PATH", "")))
    if args.action == "init":
        prepare_env()
        initialize(configuration())
    elif args.action == "start":
        start(configuration())
    elif args.action == "stop":
        if is_running():
            pg_run("pg_ctl", "-D", str(PGDATA), "-m", "fast", "-w", "stop")
    elif not is_running():
        print("Private PostgreSQL is stopped.")
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f"Local setup failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
