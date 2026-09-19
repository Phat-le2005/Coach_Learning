import pytest
from pydantic import SecretStr

from app.core.config import Settings


@pytest.fixture
def seed_settings(settings: Settings) -> Settings:
    return settings.model_copy(update={"seed_demo_password": SecretStr("Synthetic-Seed-Password-2026!")})
