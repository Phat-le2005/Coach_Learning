"""Keep test-only AI reviews out of the development runtime cache."""
import asyncio

import pytest


@pytest.fixture(autouse=True)
def isolate_step_review_cache(monkeypatch, tmp_path):
    from app.math_solutions import ai_review_router

    monkeypatch.setattr(ai_review_router, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(ai_review_router, "_CACHE_FILE", tmp_path / "ai_review_cache.json")
    monkeypatch.setattr(ai_review_router, "_REVIEW_CACHE", {})
    monkeypatch.setattr(ai_review_router, "_IN_FLIGHT_REVIEWS", {})
    monkeypatch.setattr(ai_review_router, "_COALESCE_LOCK", asyncio.Lock())
