"""Development Example 7 preserves source gates and never rewrites existing questions."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select
import sympy

from app import seed_dataset_step_review_demo as seed
from app.math_solutions.models import SolutionRubric
from app.questions.models import Question, QuestionType
from tests.math_solutions.test_v2_api import auth_headers, create_payload, v2_domain


def test_example7_install_refuses_production_before_reading_source(monkeypatch):
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(app_env="production"))
    with pytest.raises(RuntimeError, match="disabled in production"):
        seed.install()


def test_changed_dataset_is_rejected_before_database_access(tmp_path, monkeypatch):
    source = tmp_path / "changed.json"
    source.write_text("[]", encoding="utf-8")

    def no_database():
        pytest.fail("A changed source must not access the database")

    monkeypatch.setattr(seed, "get_session_factory", no_database)
    with pytest.raises(RuntimeError, match="Dataset hash changed"):
        seed.install(source, tmp_path / "unused.zip")
    assert source.read_text(encoding="utf-8") == "[]"


@pytest.fixture
def example7(db_session, v2_domain, monkeypatch):
    base = v2_domain.question
    base.source_type = "SAMPLE_TEST"
    base.content = seed.DEMO_CONTENT_MARKER
    db_session.commit()
    monkeypatch.setattr(seed, "DEMO_QUESTION_ID", base.id)
    monkeypatch.setattr(seed, "get_session_factory", lambda: lambda: nullcontext(db_session))
    monkeypatch.setattr(seed, "load_source", lambda *_: (seed.CONTENT, "DEV_ONLY | PDF Example 7 | PDF p.5"))
    return base


def test_example7_install_is_additive_and_idempotent(db_session, example7):
    before_count = db_session.scalar(select(func.count()).select_from(Question))
    original = (example7.content, example7.correct_answer, example7.explanation, example7.status)
    assert seed.install() == "installed"
    assert seed.install() == "already_installed"
    assert db_session.scalar(select(func.count()).select_from(Question)) == before_count + 1
    assert (example7.content, example7.correct_answer, example7.explanation, example7.status) == original
    row = db_session.get(Question, seed.QUESTION_ID)
    assert row.content == seed.CONTENT and row.correct_answer == seed.ANSWER
    assert row.question_type == QuestionType.OPEN_RESPONSE
    assert row.concept_links == row.problem_type_links == row.learning_outcome_links == []
    assert db_session.scalar(select(SolutionRubric).where(SolutionRubric.question_id == row.id)) is None


def test_existing_different_answer_is_never_overwritten(db_session, example7):
    seed.install()
    row = db_session.get(Question, seed.QUESTION_ID)
    row.correct_answer = "An existing answer that requires independent review"
    db_session.commit()
    with pytest.raises(RuntimeError, match="nothing was overwritten"):
        seed.install()
    db_session.refresh(row)
    assert row.correct_answer == "An existing answer that requires independent review"


def test_example7_opens_in_real_workspace_contract_without_answer_leak(
    db_client, db_session, v2_domain, auth_headers, example7,
):
    seed.install()
    headers = auth_headers(v2_domain.student)
    payload = create_payload(v2_domain)
    payload["question_id"] = str(seed.QUESTION_ID)
    result = db_client.post("/api/v2/math-solutions/attempts", json=payload, headers=headers)
    assert result.status_code == 201, result.text
    attempt_id = result.json()["id"]
    problem = db_client.get(f"/api/v2/math-solutions/attempts/{attempt_id}/problem", headers=headers)
    assert problem.status_code == 200, problem.text
    assert problem.json()["content"] == seed.CONTENT
    assert "correct_answer" not in problem.json() and "explanation" not in problem.json()
    review = db_client.get(f"/api/v3/math-solutions/attempts/{attempt_id}/ai-review", headers=headers)
    assert review.status_code == 200 and review.json()["available"] is True
    assert review.json()["reason_code"] is None
    assert seed.EXPLANATION not in review.text


def test_example7_derivative_proves_the_stated_interval():
    x = sympy.Symbol("x", real=True)
    derivative = sympy.diff(x / (x - 1), x)
    assert sympy.simplify(derivative + 1 / (x - 1) ** 2) == 0
    positive_distance = sympy.Symbol("t", positive=True)
    assert sympy.simplify(derivative.subs(x, positive_distance + 1)).is_negative is True
