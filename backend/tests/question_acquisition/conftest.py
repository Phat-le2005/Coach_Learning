from pathlib import Path
from typing import Iterator

import pytest

from app.core.config import get_settings
from tests.practice.conftest import (
    PracticeContent,
    practice_bearer,
    practice_content,
    practice_students,
    practice_user_factory,
    student_profile,
)

__all__ = [
    "PracticeContent",
    "practice_bearer",
    "practice_content",
    "practice_students",
    "practice_user_factory",
    "student_profile",
]


@pytest.fixture(autouse=True)
def configure_test_acq_storage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    test_storage_dir = tmp_path / "acq_storage"
    monkeypatch.setenv("QUESTION_ACQUISITION_STORAGE_DIR", str(test_storage_dir))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
