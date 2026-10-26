from types import SimpleNamespace

import pytest

from app import seed_step_review_demo


def test_demo_reference_command_refuses_production(monkeypatch):
    monkeypatch.setattr(seed_step_review_demo, "get_settings", lambda: SimpleNamespace(app_env="production"))
    with pytest.raises(RuntimeError, match="disabled in production"):
        seed_step_review_demo.install()


def test_demo_reference_contains_checkable_step_sequence():
    answer = seed_step_review_demo.DEMO_ANSWER
    explanation = seed_step_review_demo.DEMO_EXPLANATION
    for marker in ("x²-2x-3", "x=-1", "x=3", "8/3", "-8"):
        assert marker in answer + explanation
