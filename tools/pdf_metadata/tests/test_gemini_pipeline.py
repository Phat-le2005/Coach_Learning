from copy import deepcopy
import json
from pathlib import Path
import zipfile

import httpx
import pytest
import pypdfium2 as pdfium

from pdfmeta.gemini_client import GeminiClient, GeminiConfig, GeminiError, provider_schema, read_env
from pdfmeta.gemini_contracts import REVIEW_SCHEMA, WINDOW_SCHEMA, filter_context_units, validate_question_package, validate_review, validate_window
from pdfmeta.gemini_jobs import execute_job, writer_lock
from pdfmeta.corpus import make_windows, plan, run
from pdfmeta.storage import file_hash


def result():
    return {"question_id": "q1", "verdict": "CONSISTENT", "source_transcription": {
        "stem_markdown": "Đề", "answer_text": "2", "solution_markdown": "Vậy x=2"},
        "steps": [{"order": 1, "kind": "CONCLUSION", "title": "Kết luận", "content_markdown": "x=2",
                   "formulas_latex": ["x=2"], "conditions": [], "evidence_ids": ["solution:1"],
                   "basis": "VISIBLE_SOURCE", "uncertain": False}], "issues": [],
        "missing_source_content": False, "unreadable_source": False}


def response(data=None, *, finish="STOP"):
    return {"candidates": [{"finishReason": finish, "content": {"parts": [{"text": json.dumps(data or result())}]}}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 50, "totalTokenCount": 150}}


def client(tmp_path, handler, **kwargs):
    return GeminiClient(GeminiConfig("secret-test-key", "gemini-3.6-flash", **kwargs), tmp_path / "usage.jsonl",
                        transport=httpx.MockTransport(handler), sleeper=lambda _: None)


def test_env_is_literal_not_executable_and_repr_redacts_key(tmp_path):
    env = tmp_path / ".env"
    env.write_text('GEMINI_API_KEY="$(do-not-execute)"\nGEMINI_MODEL=gemini-3.6-flash # note\n', encoding="utf-8")
    assert read_env(env)["GEMINI_API_KEY"] == "$(do-not-execute)"
    assert read_env(env)["GEMINI_MODEL"] == "gemini-3.6-flash"
    assert "secret-test-key" not in repr(GeminiConfig("secret-test-key"))


def test_auth_failure_is_redacted_and_never_retried(tmp_path):
    c = client(tmp_path, lambda _: httpx.Response(403, json={"error": "secret-test-key"}))
    with pytest.raises(GeminiError, match="GEMINI_HTTP_403"):
        c.generate([], REVIEW_SCHEMA, "instructions", "job")
    assert c.calls == 1
    assert "secret-test-key" not in (tmp_path / "usage.jsonl").read_text()
    c.close()


def test_quota_retry_is_bounded_and_usage_tracked(tmp_path):
    statuses = iter([429, 200])
    def handler(_):
        status = next(statuses)
        return httpx.Response(status, json=response() if status == 200 else {})
    c = client(tmp_path, handler, max_calls=2)
    assert c.generate([], REVIEW_SCHEMA, "instructions", "job")["result"] == result()
    assert c.calls == 2 and c.tokens == 150
    with pytest.raises(GeminiError, match="RUN_BUDGET_REACHED"):
        c.generate([], REVIEW_SCHEMA, "instructions", "second")
    c.close()


def quota_response(quota_id, delay="12s"):
    return {"error": {"message": "secret-test-key should never be logged", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
            {"quotaMetric": "generate_content_free_tier_requests", "quotaId": quota_id, "quotaValue": "20"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": delay}]}}


def test_daily_quota_stops_without_retries_and_logs_only_safe_diagnostics(tmp_path):
    c = client(tmp_path, lambda _: httpx.Response(429, json=quota_response("GenerateRequestsPerDayPerProjectPerModel-FreeTier")))
    with pytest.raises(GeminiError, match="DAILY_QUOTA_EXHAUSTED"):
        c.generate([], REVIEW_SCHEMA, "instructions", "job")
    assert c.calls == 1
    saved = (tmp_path / "usage.jsonl").read_text()
    assert "secret-test-key" not in saved and '"quotaValue": "20"' in saved
    c.close()


def test_retry_info_delay_is_honored_and_long_cooldowns_are_not_blocking(tmp_path):
    responses = iter([httpx.Response(429, json=quota_response("GenerateRequestsPerMinute", "12s")),
                      httpx.Response(200, json=response())])
    c = client(tmp_path, lambda _: next(responses))
    waited = []
    c.sleep = waited.append
    assert c.generate([], REVIEW_SCHEMA, "instructions", "job")["status"] == "RESPONSE_RECEIVED"
    assert waited == [12]
    c.close()
    c = client(tmp_path, lambda _: httpx.Response(429, json=quota_response("GenerateRequestsPerMinute", "90s")))
    c.sleep = lambda _: pytest.fail("Should not block on a long provider cooldown")
    with pytest.raises(GeminiError, match="LONG_COOLDOWN"):
        c.generate([], REVIEW_SCHEMA, "instructions", "job")
    c.close()


def test_timeout_is_unknown_not_automatic_replay(tmp_path):
    def timeout(request):
        raise httpx.ReadTimeout("secret-test-key", request=request)
    c = client(tmp_path, timeout)
    with pytest.raises(GeminiError, match="NETWORK_ERROR_USAGE_UNKNOWN"):
        c.generate([], REVIEW_SCHEMA, "instructions", "job")
    assert c.calls == 1
    c.close()


def test_incomplete_response_is_not_accepted(tmp_path):
    c = client(tmp_path, lambda _: httpx.Response(200, json=response(finish="MAX_TOKENS")))
    assert c.generate([], REVIEW_SCHEMA, "instructions", "job")["status"] == "INCOMPLETE_OR_BLOCKED"
    c.close()


def test_source_ids_and_step_sequence_checked_locally():
    refs = [{"evidence_id": "solution:1"}]
    r = result()
    assert validate_review(r, "q1", refs) == []
    r["steps"][0]["evidence_ids"] = ["another-question"]
    with pytest.raises(ValueError, match="UNKNOWN_EVIDENCE_ID"):
        validate_review(r, "q1", refs)
    r = result()
    r["steps"][0]["order"] = 2
    with pytest.raises(ValueError, match="SEQUENCE"):
        validate_review(r, "q1", refs)
    r = result()
    r["steps"][0]["basis"] = "PROPOSED_ADDITION"
    assert "UNCERTAIN_OR_ADDED_STEPS" in validate_review(r, "q1", refs)


def test_schema_cannot_approve_or_assign_grade():
    r = result()
    r["publishable"] = True
    with pytest.raises(Exception):
        validate_review(r, "q1", [{"evidence_id": "solution:1"}])


def test_completed_checkpoint_skips_api_and_source_changes_invalidate(tmp_path):
    asset = tmp_path / "source.png"
    asset.write_bytes(b"image-one")
    package = {"references": [{"evidence_id": "solution:1", "page_number": 1, "part": "solution",
                              "asset_path": "source.png", "sha256": file_hash(asset)}]}
    c = client(tmp_path, lambda _: httpx.Response(200, json=response()))
    check = lambda r: validate_review(r, "q1", package["references"])
    a, cache = execute_job(c, tmp_path, package, REVIEW_SCHEMA, "instructions", check)
    assert not cache and not a["publishable"] and a["academic_review"] == "PENDING"
    b, cache = execute_job(c, tmp_path, package, REVIEW_SCHEMA, "instructions", check)
    assert cache and a == b and c.calls == 1
    revised, cache = execute_job(c, tmp_path, package, REVIEW_SCHEMA, "instructions", lambda _: ["NEW_SOURCE_GATE"])
    assert cache and c.calls == 1 and revised["ai_review_status"] == "AI_FLAGGED"
    assert revised["validation_rechecks"][-1]["new_flags"] == ["NEW_SOURCE_GATE"]
    asset.write_bytes(b"image-two")
    with pytest.raises(ValueError, match="SOURCE_IMAGE_CHANGED"):
        execute_job(c, tmp_path, package, REVIEW_SCHEMA, "instructions", check)
    c.close()


def test_unknown_remote_state_blocks_resume_without_explicit_retry(tmp_path):
    asset = tmp_path / "source.png"
    asset.write_bytes(b"img")
    package = {"references": [{"evidence_id": "solution:1", "page_number": 1, "part": "solution",
                              "asset_path": "source.png", "sha256": file_hash(asset)}]}
    def timeout(request):
        raise httpx.ReadTimeout("unknown", request=request)
    c = client(tmp_path, timeout)
    check = lambda r: validate_review(r, "q1", package["references"])
    record, _ = execute_job(c, tmp_path, package, REVIEW_SCHEMA, "instructions", check)
    assert record["status"] == "UNKNOWN_REMOTE_STATE"
    with pytest.raises(GeminiError, match="UNKNOWN_REMOTE_STATE"):
        execute_job(c, tmp_path, package, REVIEW_SCHEMA, "instructions", check)
    assert c.calls == 1
    c.close()


def test_writer_lock_prevents_concurrent_mutation_and_releases(tmp_path):
    with writer_lock(tmp_path):
        with pytest.raises(GeminiError, match="OUTPUT_LOCKED"):
            with writer_lock(tmp_path):
                pass
    assert not (tmp_path / ".writer.lock").exists()


@pytest.mark.parametrize("page_count", [1, 2, 3, 57, 1228])
def test_windows_cover_each_owner_page_exactly_once_with_context(page_count):
    windows = make_windows(page_count)
    assert [p for w in windows for p in w["core_pages"]] == list(range(1, page_count + 1))
    for w in windows:
        assert set(w["core_pages"]).issubset(w["context_pages"])
        assert min(w["context_pages"]) >= 1 and max(w["context_pages"]) <= page_count
    if page_count > 3:
        assert set(windows[0]["context_pages"]) & set(windows[1]["context_pages"])


def test_window_rejects_question_owned_by_context_page():
    refs = [{"evidence_id": "page:1", "page_number": 1}, {"evidence_id": "page:2", "page_number": 2}]
    unit = {"kind": "QUESTION", "source_label": "Câu 1", "source_number": "1", "start_page": 1, "end_page": 2,
            "complete": True, "continuation_from_previous": False, "continues_after_window": False,
            "question_type": "OPEN_RESPONSE", "title": "Bài", "content_markdown": "Đề", "options": [],
            "source_answer": "2", "source_solution_markdown": "x=2", "steps": [], "evidence_ids": ["page:1"], "issues": []}
    with pytest.raises(ValueError, match="OUTSIDE_OWNER_WINDOW"):
        validate_window({"units": [unit], "window_issues": [], "unreadable_source": False}, refs, [2])


def test_provider_schema_has_explicit_enum_types_but_local_keeps_strict_limits():
    remote = provider_schema(REVIEW_SCHEMA)
    assert remote["properties"]["verdict"]["type"] == "string"
    assert "additionalProperties" not in remote
    assert REVIEW_SCHEMA["additionalProperties"] is False
    assert REVIEW_SCHEMA["properties"]["steps"]["maxItems"] == 40


def test_added_parameter_sign_cannot_silently_pass_source_review():
    r = result()
    r["steps"][0]["conditions"] = [{"text": "c > 0", "evidence_ids": ["solution:1"], "basis": "VISIBLE_SOURCE"}]
    package = {"question_id": "q1", "references": [{"evidence_id": "solution:1"}],
               "local_source_candidate": {"native_lossy": [{"text_lossy": "c là hằng số, v > 6"}]},
               "prior_source_issues": [{"code": "PARAMETER_SIGN_REVIEW"}]}
    flags = validate_question_package(r, package)
    assert "CONDITION_NOT_FOUND_IN_NATIVE_SOURCE_REVIEW_REQUIRED" in flags
    assert "PREEXISTING_SOURCE_ISSUE_UNRESOLVED" in flags
    r["steps"][0]["conditions"][0]["basis"] = "PROPOSED_ADDITION"
    assert "ADDED_ASSUMPTIONS" in validate_question_package(r, package)


def test_condition_must_cite_the_region_that_actually_contains_it():
    r = result()
    r["steps"][0]["conditions"] = [{"text": "v > 6", "evidence_ids": ["stem:1"], "basis": "VISIBLE_SOURCE"}]
    package = {"question_id": "q1", "references": [{"evidence_id": "solution:1"}, {"evidence_id": "stem:1"}],
               "local_source_candidate": {"native_lossy": [{"evidence_id": "stem:1", "text_lossy": "v là vận tốc"},
                                                          {"evidence_id": "solution:1", "text_lossy": "Điều kiện v > 6"}]}}
    assert "CONDITION_EVIDENCE_MISMATCH_REVIEW_REQUIRED" in validate_question_package(r, package)


def make_pdf(path, count):
    pdf = pdfium.PdfDocument.new()
    try:
        for _ in range(count):
            page = pdf.new_page(600, 800)
            page.close()
        pdf.save(str(path))
    finally:
        pdf.close()


def test_zip_paths_are_not_extraction_destinations_and_sources_unchanged(tmp_path):
    pdf = tmp_path / "original.pdf"
    make_pdf(pdf, 3)
    original = file_hash(pdf)
    archive = tmp_path / "input.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(pdf, "../../outside.pdf")
        z.write(pdf, "duplicate.pdf")
    archive_hash = file_hash(archive)
    output = tmp_path / "corpus"
    report = plan(archive, output)
    assert report["document_count"] == 1 and report["page_count"] == 3
    assert not (tmp_path.parent / "outside.pdf").exists()
    assert file_hash(pdf) == original and file_hash(archive) == archive_hash
    source = json.loads((output / "plan.json").read_text())["documents"][0]
    assert Path(source["path"]).is_relative_to(output)


def test_corpus_restarts_make_progress_without_duplicate_api_or_staging(tmp_path, monkeypatch):
    import pdfmeta.corpus as module
    import pdfmeta.gemini_view as viewer
    pdf = tmp_path / "source.pdf"
    make_pdf(pdf, 3)
    output = tmp_path / "corpus"
    plan(pdf, output)
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=dummy\nGEMINI_MODEL=gemini-3.6-flash\n")
    generations = []
    def handler(request):
        if request.method == "GET":
            return httpx.Response(200, json={"models": [{"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]}]})
        payload = json.loads(request.content)
        package = json.loads(payload["contents"][0]["parts"][0]["text"].split("\n", 1)[1])
        first = package["core_pages"][0]
        generations.append(first)
        data = {"units": [{"kind": "KNOWLEDGE", "source_label": f"Mục {first}", "source_number": "", "start_page": first, "end_page": first,
            "complete": True, "continuation_from_previous": False, "continues_after_window": False,
            "question_type": "NOT_APPLICABLE", "title": "Lý thuyết", "content_markdown": f"Nội dung {first}",
            "options": [], "source_answer": "", "source_solution_markdown": "", "steps": [],
            "evidence_ids": [f"page:{first}"], "issues": []}], "window_issues": [], "unreadable_source": False}
        return httpx.Response(200, json=response(data))
    real = GeminiClient
    monkeypatch.setattr(module, "GeminiClient", lambda config, ledger: real(config, ledger, transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(viewer, "build_view", lambda *_: None)
    a = run(output, env_file=env, limit=1)
    b = run(output, env_file=env, limit=1)
    c = run(output, env_file=env, limit=1)
    assert generations == [1, 3]
    assert a["unit_count"] == 1 and b["unit_count"] == c["unit_count"] == 2
    assert c["api_attempts_this_run"] == 0 and c["cache_hits_this_run"] == 2
    units = [json.loads(line) for line in (output / "staging" / "content.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len({u["unit_id"] for u in units}) == 2
    assert all(not u["publishable"] and u["academic_review"] == "PENDING" for u in units)


def test_context_filter_keeps_audit_and_revalidates_raw_response_without_another_call(tmp_path):
    asset = tmp_path / "source.png"
    asset.write_bytes(b"image")
    refs = [{"evidence_id": f"page:{n}", "page_number": n, "part": "full_page",
             "asset_path": "source.png", "sha256": file_hash(asset)} for n in [1, 2]]
    unit = {"kind": "KNOWLEDGE", "source_label": "Mục", "source_number": "", "start_page": 1, "end_page": 1,
            "complete": True, "continuation_from_previous": False, "continues_after_window": False,
            "question_type": "NOT_APPLICABLE", "title": "Lý thuyết", "content_markdown": "Nội dung",
            "options": [], "source_answer": "", "source_solution_markdown": "", "steps": [],
            "evidence_ids": ["page:1"], "issues": []}
    owned = {**deepcopy(unit), "start_page": 2, "end_page": 2, "evidence_ids": ["page:2"]}
    data = {"units": [unit, owned], "window_issues": [], "unreadable_source": False}
    c = client(tmp_path, lambda _: httpx.Response(200, json=response(data)))
    package = {"references": refs}
    check = lambda r: validate_window(r, refs, [2])
    failed, _ = execute_job(c, tmp_path, package, WINDOW_SCHEMA, "instructions", check)
    assert failed["status"] == "FAILED"
    raw_path = tmp_path / "jobs" / failed["job_key"] / "response.json"
    before = file_hash(raw_path)
    normalized, cached = execute_job(c, tmp_path, package, WINDOW_SCHEMA, "instructions", check,
        revalidate=True, normalizer=lambda r: filter_context_units(r, refs, [2]))
    assert cached and c.calls == 1
    assert normalized["result"]["units"] == [owned]
    assert normalized["normalization_audit"][0]["unit"] == unit
    assert file_hash(raw_path) == before
    broken = deepcopy(data)
    broken["units"][0]["start_page"] = 99
    with pytest.raises(ValueError, match="UNKNOWN_OR_INVERTED"):
        filter_context_units(broken, refs, [2])
    c.close()
