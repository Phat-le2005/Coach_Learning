from contextlib import contextmanager
import http.client
import json
from pathlib import Path
import re
import threading

import pytest

from pdfmeta.curate import build_batch, decimal_value
from pdfmeta.review_server import create_server
from pdfmeta.review_store import ReviewError, ReviewStore
from pdfmeta.storage import file_hash, read_json, write_json, write_jsonl


@pytest.fixture
def pilot(tmp_path: Path) -> Path:
    write_json(tmp_path / "manifest.json", {"source_sha256": "source"})
    write_jsonl(tmp_path / "questions.enriched.candidates.jsonl", [{
        "question_id": "q1", "source_sha256": "source", "ocr_evidence": [{"block_id": "b1"}]}])
    (tmp_path / "review.html").write_text('<script id="review-config" type="application/json">{"writable":false}</script>')
    return tmp_path


def payload(revision=0, status="DRAFT"):
    return {"question_id": "q1", "expected_revision": revision, "status": status,
            "fields": {"stem_markdown": "Đề $x^2$", "answer_text": "1,4", "solution_markdown": "",
                       "formula_corrections": [{"block_id": "b1", "latex": "x^2"}]},
            "field_checks": {"stem": False, "answer": False, "solution": False},
            "reviewer": "test reviewer", "note": ""}


def test_review_survives_restart_with_history_and_immutable_candidates(pilot):
    before = file_hash(pilot / "questions.enriched.candidates.jsonl")
    store = ReviewStore(pilot)
    result = store.save(payload())
    assert result["review"]["revision"] == 1
    snapshot = ReviewStore(pilot).snapshot()
    assert snapshot["reviews"]["q1"]["fields"]["answer_text"] == "1,4"
    assert snapshot["history_count"] == 1
    assert file_hash(pilot / "questions.enriched.candidates.jsonl") == before
    assert snapshot["reviews"]["q1"]["publishable"] is False


def test_two_tabs_cannot_overwrite_each_other(pilot):
    store = ReviewStore(pilot)
    store.save(payload())
    with pytest.raises(ReviewError) as error:
        store.save(payload())
    assert error.value.status == 409
    assert store.snapshot()["history_count"] == 1


def test_verification_requires_checks_but_never_promotes_academic_status(pilot):
    store = ReviewStore(pilot)
    request = payload(status="SOURCE_VERIFIED")
    with pytest.raises(ReviewError):
        store.save(request)
    request["field_checks"].update(stem=True, answer=True)
    saved = store.save(request)["review"]
    assert saved["status"] == "SOURCE_VERIFIED"
    assert saved["academic_review"] == "PENDING"
    assert saved["grading_support"] == "NOT_ASSESSED"


def test_unknown_formula_and_unrequested_promotion_fields_are_rejected(pilot):
    request = payload()
    request["fields"]["formula_corrections"][0]["block_id"] = "other-question"
    with pytest.raises(ReviewError):
        ReviewStore(pilot).save(request)
    request = payload()
    request["publishable"] = True
    with pytest.raises(ReviewError):
        ReviewStore(pilot).save(request)


def test_source_generation_change_requires_reload(pilot):
    store = ReviewStore(pilot)
    store.save(payload())
    with (pilot / "questions.enriched.candidates.jsonl").open("a") as stream:
        stream.write("\n")
    with pytest.raises(ReviewError) as error:
        store.save(payload(revision=1))
    assert error.value.status == 409
    assert ReviewStore(pilot).snapshot()["reviews"]["q1"]["stale"] is True


@contextmanager
def running_server(pilot):
    server = create_server(pilot, 0)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def request(port, method, path, data=None, headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    connection.request(method, path, body=json.dumps(data) if data is not None else None, headers=headers or {})
    result = connection.getresponse()
    status, body = result.status, result.read().decode()
    connection.close()
    return status, body


def test_http_save_requires_session_token_and_same_origin(pilot):
    with running_server(pilot) as port:
        status, html = request(port, "GET", "/review.html")
        assert status == 200
        config = json.loads(re.search(r'type="application/json">(.*?)</script>', html)[1])
        headers = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{port}",
                   "X-Review-Token": config["token"]}
        assert request(port, "POST", "/api/review", payload(), {**headers, "Origin": "https://external.invalid"})[0] == 403
        assert request(port, "POST", "/api/review", payload(), {"Content-Type": "application/json"})[0] == 403
        assert not ReviewStore(pilot).snapshot()['reviews']
        assert request(port, "POST", "/api/review", payload(), headers)[0] == 200
        assert request(port, "POST", "/api/review", payload(), headers)[0] == 409


def test_review_history_is_not_a_static_public_asset(pilot):
    ReviewStore(pilot).save(payload())
    with running_server(pilot) as port:
        assert request(port, "GET", "/%72eviews/state.json")[0] == 403
        assert request(port, "HEAD", "/reviews/state.json")[0] == 403
        assert request(port, "GET", "/api/review/state", headers={"Host": "external.invalid"})[0] == 403


@pytest.mark.parametrize("raw,expected", [("1,4", "1.4"), ("1.400", "1.4"), ("20", "20"),
                                          ("-0.0", "0"), ("1/2", None), ("NaN", None), ("1,2,3", None), ("1e3", None)])
def test_numeric_answer_candidates_are_typed_without_eval(raw, expected):
    assert decimal_value(raw) == expected


def test_twenty_item_export_preserves_source_conflict_and_student_separation(tmp_path):
    config = read_json(Path(__file__).parents[1] / "fixtures" / "pilot20-editorial.json")
    write_json(tmp_path / "manifest.json", {"source_sha256": config["source_sha256"]})
    records = []
    for item in config["items"]:
        span = {"page_number": 1, "bbox": [0, 0, 10, 10], "block_ids": [], "asset_path": f"assets/q{item['number']}-stem.png"}
        records.append({"question_id": f"q{item['number']}", "source_sha256": config["source_sha256"],
                        "source_number": item["number"], "stem": {"source_spans": [span]},
                        "answer": {"text_raw": item["expected_source_answer"], "source_spans": []},
                        "solution": {"source_spans": []}, "reference_steps": [], "ocr_evidence": []})
    write_jsonl(tmp_path / "questions.enriched.candidates.jsonl", records)
    report = build_batch(tmp_path)
    assert report["batch_size"] == 20 and report["publishable_count"] == 0
    exported = [json.loads(s) for s in (tmp_path / "exports/pilot20.authoring.jsonl").read_text(encoding="utf8").splitlines()]
    conflict = next(item for item in exported if item["source_number"] == 260)
    assert conflict["answer_spec"]["expected_decimal"] == "6"
    assert conflict["review"]["source_issues"][0]["proposed_answer_candidate"] == "3"
    student = read_json(tmp_path / "exports/pilot20.student-preview.json")
    assert all(set(item) == {"question_id", "source_number", "content_markdown", "assets", "visual_required", "preview_only"} for item in student)


def test_authored_export_does_not_leak_pdf_private_glyphs(tmp_path):
    config = read_json(Path(__file__).parents[1] / "fixtures" / "pilot20-editorial.json")
    write_json(tmp_path / "manifest.json", {"source_sha256": config["source_sha256"]})
    records = []
    for item in config["items"]:
        records.append({"question_id": f"q{item['number']}", "source_sha256": config["source_sha256"],
                        "source_number": item["number"], "stem": {"source_spans": []},
                        "answer": {"text_raw": item["expected_source_answer"], "source_spans": []},
                        "solution": {"source_spans": []}, "reference_steps": [], "ocr_evidence": []})
    original = "G\uf03dx2"
    records[0]["reference_steps"] = [{"step_id": "s1", "kind_candidate": "UNCLASSIFIED", "text_raw": original,
                                      "source_spans": [{"page_number": 1, "bbox": [0, 0, 10, 10], "block_ids": ["b1"]}]}]
    write_json(tmp_path / "pages/page-001.json", {"page_number": 1, "blocks": [
        {"block_id": "b1", "text_raw": original, "glyphs": [{"text": "\uf03d", "font": "SymbolMT"}]}]})
    write_jsonl(tmp_path / "questions.enriched.candidates.jsonl", records)
    before = file_hash(tmp_path / "questions.enriched.candidates.jsonl")
    report = build_batch(tmp_path)
    exported = read_json(tmp_path / "exports/pilot20.authoring.pretty.json")
    step = exported[0]["reference_solution"]["step_candidates"][0]
    assert step["text_candidate"] == "G=x2" and "text_raw" not in step
    assert exported[0]["schema_version"] == "assessment-authoring/v2"
    assert report["private_use_or_replacement_characters_in_clean_export"] == 0
    raw = json.loads((tmp_path / "exports/pilot20.raw-evidence.jsonl").read_text(encoding="utf8").splitlines()[0])
    assert raw["step_candidates_raw"][0]["text_raw"] == original
    assert file_hash(tmp_path / "questions.enriched.candidates.jsonl") == before
