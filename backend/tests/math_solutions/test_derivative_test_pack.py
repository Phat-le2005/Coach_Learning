"""Local derivative pack: source integrity, additive install and workspace isolation."""
from contextlib import nullcontext
import json
from uuid import UUID

import pytest
import sympy as sp
from sqlalchemy import func, select

from app import seed_derivative_test_pack as seed
from app.math_solutions.answer_reference import resolve_answer_reference
from app.math_solutions.models import SolutionAttempt, SolutionRubric
from app.questions.models import Question, QuestionType
from tests.math_solutions.test_v2_api import auth_headers, create_payload, v2_domain


def raw_pack():
    return json.loads(seed.PACK_FILE.read_text(encoding="utf-8"))["questions"]


@pytest.mark.skipif(not (seed.DEFAULT_SOURCE / seed.METADATA).is_file(), reason="Optional source PDF handoff is installed separately")
def test_all_ten_exercises_bind_to_unchanged_supplied_package():
    items = seed.load_pack()
    assert len(items) == 10
    assert len({x["id"] for x in items}) == 10
    assert all(x["reference_solution"].strip() for x in items)


def test_production_refused_before_reading_source(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(seed, "get_settings", lambda: SimpleNamespace(app_env="production"))
    monkeypatch.setattr(seed, "load_pack", lambda *_: pytest.fail("Must not read source"))
    with pytest.raises(RuntimeError, match="disabled in production"):
        seed.install(apply=True)


@pytest.fixture
def pack_db(db_session, v2_domain, monkeypatch):
    base = v2_domain.question
    base.source_type = "SAMPLE_TEST"
    db_session.commit()
    monkeypatch.setattr(seed, "DEMO_QUESTION_ID", base.id)
    monkeypatch.setattr(seed, "get_session_factory", lambda: lambda: nullcontext(db_session))
    monkeypatch.setattr(seed, "load_pack", lambda *_: raw_pack())
    monkeypatch.setattr(seed, "write_reference_booklet", lambda *_: None)
    return base


def test_preview_then_install_is_additive_and_idempotent(db_session, pack_db):
    original = (pack_db.content, pack_db.explanation, pack_db.correct_answer)
    before = db_session.scalar(select(func.count()).select_from(Question))
    assert seed.install()["pending_insert"] == 10
    assert db_session.scalar(select(func.count()).select_from(Question)) == before
    assert seed.install(apply=True)["inserted"] == 10
    assert seed.install(apply=True)["inserted"] == 0
    assert db_session.scalar(select(func.count()).select_from(Question)) == before + 10
    assert (pack_db.content, pack_db.explanation, pack_db.correct_answer) == original
    for item in raw_pack():
        row = db_session.get(Question, UUID(item["id"]))
        assert row.correct_answer is None and row.question_type == QuestionType.OPEN_RESPONSE
        assert row.explanation == item["reference_solution"]
        assert row.concept_links == row.problem_type_links == row.learning_outcome_links == []
        assert row.exam_weight == 0
        assert db_session.scalar(select(SolutionRubric).where(SolutionRubric.question_id == row.id)) is None


def test_late_id_conflict_does_not_partially_install(db_session, pack_db):
    last = raw_pack()[-1]
    db_session.add(Question(id=UUID(last["id"]), subject_id=pack_db.subject_id,
        created_by=pack_db.created_by, content="Existing unrelated question",
        difficulty=0.5, exam_weight=0, source_type="TEST",
        question_type=QuestionType.OPEN_RESPONSE))
    db_session.commit()
    before = db_session.scalar(select(func.count()).select_from(Question))
    with pytest.raises(RuntimeError, match="nothing was overwritten"):
        seed.install(apply=True)
    assert db_session.scalar(select(func.count()).select_from(Question)) == before


@pytest.mark.skipif(not (seed.DEFAULT_SOURCE / seed.METADATA).is_file(), reason="Optional source PDF handoff is installed separately")
def test_changed_source_evidence_is_rejected(monkeypatch, tmp_path):
    pack = json.loads(seed.PACK_FILE.read_text(encoding="utf-8"))
    pack["questions"][0]["source_fragments"]["question"][0]["page_number"] += 1
    changed = tmp_path / "pack.json"
    changed.write_text(json.dumps(pack), encoding="utf-8")
    monkeypatch.setattr(seed, "PACK_FILE", changed)
    with pytest.raises(ValueError, match="evidence changed"):
        seed.load_pack()


def test_all_ten_open_with_real_workspace_contract_without_solution_leak(
    db_client, db_session, v2_domain, auth_headers, pack_db,
):
    seed.install(apply=True)
    headers = auth_headers(v2_domain.student)
    outsider_headers = auth_headers(v2_domain.outsider)
    for index, item in enumerate(raw_pack()):
        payload = create_payload(v2_domain, key=f"derivative-pack-{index}")
        payload["question_id"] = item["id"]
        created = db_client.post("/api/v2/math-solutions/attempts", json=payload, headers=headers)
        assert created.status_code == 201, created.text
        attempt_id = created.json()["id"]
        response = db_client.get(f"/api/v2/math-solutions/attempts/{attempt_id}/problem", headers=headers)
        assert response.status_code == 200, response.text
        problem = response.json()
        assert problem["content"] == item["content"]
        assert "correct_answer" not in problem and "explanation" not in problem
        availability = db_client.get(f"/api/v3/math-solutions/attempts/{attempt_id}/ai-review", headers=headers)
        assert availability.status_code == 200 and availability.json()["available"] is True
        assert availability.json()["reason_code"] is None
        attempt = db_session.get(SolutionAttempt, UUID(attempt_id))
        reference = resolve_answer_reference(db_session, attempt, require_submitted=False)
        assert reference.reference_solution == item["reference_solution"]
        assert reference.correct_answer == ""
        assert reference.allow_legacy_ai_backdrop is False
        denied = db_client.get(f"/api/v2/math-solutions/attempts/{attempt_id}/problem", headers=outsider_headers)
        assert denied.status_code in {403, 404}


def test_reference_calculations_and_domains():
    x = sp.Symbol("x", real=True)
    # Polynomial sign changes and critical points.
    assert sp.expand(sp.diff(2*x**3-9*x**2-24*x+1, x)-6*(x-4)*(x+1)) == 0
    assert sp.limit((-2*x+1)/(x+1), x, sp.oo) == -2
    assert sp.limit((-2*x+1)/(x+1), x, -sp.oo) == -2
    bacteria = 1000 + 100*x/(100+x**2)
    assert sp.simplify(sp.diff(bacteria, x)-100*(100-x**2)/(100+x**2)**2) == 0
    assert bacteria.subs(x,10) == 1005
    volume = x*(30-2*x)*(80-2*x)
    assert sp.solve(sp.diff(volume,x), x) == [sp.Rational(20,3),30]
    assert volume.subs(x,sp.Rational(20,3)) == sp.Rational(200000,27)
    assert volume.subs(x,5) < volume.subs(x,sp.Rational(20,3)) > volume.subs(x,10)
    fence = 2*x+200/x
    assert fence.subs(x,10) == 40 and sp.diff(fence,x).subs(x,10) == 0
    cost = x/sp.Integer(10000)+sp.Rational(1,5)+10000/x
    assert sp.diff(cost,x).subs(x,10000) == 0 and cost.subs(x,10000) == sp.Rational(11,5)
    assert sp.limit(30*x/(200+x),x,sp.oo) == 30
    profit = -x**3+3*x**2+240*x-500
    assert sp.solve(sp.diff(profit,x),x) == [-8,10]
    assert [profit.subs(x,n) for n in [1,10,18]] == [-258,1200,-1040]
    population = 25/(sp.Rational(1,4)+sp.exp(-3*x/4))
    assert population.subs(x,0) == 20
    assert sp.diff(population,x).subs(x,0) == 12
    assert sp.limit(population,x,sp.oo) == 100
    height = 2+sp.Rational(49,2)*x-sp.Rational(49,10)*x**2
    assert sp.diff(height,x).subs(x,2) == sp.Rational(49,10)
    assert height.subs(x,sp.Rational(5,2)) == sp.Rational(261,8)
    landing = (sp.Rational(49,2)+sp.sqrt(sp.Rational(12789,20)))/sp.Rational(49,5)
    assert sp.simplify(height.subs(x,landing)) == 0
