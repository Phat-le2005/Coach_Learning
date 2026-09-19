"""Optional PostgreSQL concurrency coverage for idempotent seed execution."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from pydantic import SecretStr
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.seed_service import SeedService
from app.users.models import User


def test_concurrent_seed_commands_do_not_create_duplicates(
    postgres_engine: Engine, settings: Settings
) -> None:
    factory = sessionmaker(postgres_engine, expire_on_commit=False, autoflush=False)
    configured = settings.model_copy(
        update={"seed_demo_password": SecretStr("Synthetic-Concurrent-Seed-Password-2026!")}
    )
    barrier = Barrier(2)

    def seed() -> dict[str, dict[str, int]]:
        with factory() as session:
            barrier.wait(timeout=10)
            return SeedService(session, configured).seed().to_dict()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [pool.submit(seed), pool.submit(seed)]
        summaries = [result.result(timeout=60) for result in results]
    assert sorted(summary["users"].get("created", 0) for summary in summaries) == [0, 19]
    with Session(postgres_engine) as session:
        assert session.scalar(select(func.count()).select_from(User)) == 19
