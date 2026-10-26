"""Paper OCR is a suggestion layer; only a student's later confirmation saves steps."""

import asyncio
import json

import httpx
from app.core.config import get_settings
from app.math_paper.ocr import GeminiPaperTranscriber, PaperOcrOutput, PaperOcrSuggestion
from tests.math_solutions.test_paper_upload import png_bytes
from tests.math_solutions.test_v2_api import auth_headers, create_payload, mutation, v2_domain


def test_gemini_paper_transcriber_sends_image_not_answer(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "gemini")
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_MODEL_FAST", "gemini-test")
    get_settings.cache_clear()
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        assert request.url.path.endswith("/gemini-test:generateContent")
        assert body["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "image/png"
        assert "correct_answer" not in json.dumps(body)
        answer = {"suggestions": [{"page_number": 1, "kind": "TABLE",
                                   "text": "x: -1, 3\ny': +, -, +", "uncertain": True}]}
        return httpx.Response(200, json={"candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"text": json.dumps(answer)}],
        }}]})

    try:
        transcriber = GeminiPaperTranscriber(transport=httpx.MockTransport(handler))
        result = asyncio.run(transcriber.transcribe(png_bytes(), "image/png"))
        assert len(result.suggestions) == 1
        assert result.suggestions[0].kind == "TABLE"
        assert len(seen) == 1
    finally:
        get_settings.cache_clear()


def test_paper_ocr_requires_owner_and_never_creates_steps(
    db_client, v2_domain, auth_headers, tmp_path, monkeypatch,
):
    monkeypatch.setenv("MATH_PAPER_STORAGE_DIR", str(tmp_path / "paper"))
    get_settings.cache_clear()
    student = auth_headers(v2_domain.student)
    outsider = auth_headers(v2_domain.outsider)
    created = db_client.post("/api/v2/math-solutions/attempts", json=create_payload(v2_domain), headers=student)
    assert created.status_code == 201, created.text
    attempt_id = created.json()["id"]
    path = f"/api/v3/math-solutions/attempts/{attempt_id}/paper"
    uploaded = db_client.post(path, files={"file": ("work.png", png_bytes(), "image/png")}, headers=student)
    assert uploaded.status_code == 201, uploaded.text
    ocr_path = f"{path}/{uploaded.json()['id']}/ocr"

    async def transcribe(_self, data: bytes, mime: str) -> PaperOcrOutput:
        assert data == png_bytes() and mime == "image/png"
        return PaperOcrOutput(suggestions=[PaperOcrSuggestion(
            page_number=1, kind="FORMULA", text="y'=x^2-2x-3", uncertain=False,
        )])

    monkeypatch.setattr(GeminiPaperTranscriber, "transcribe", transcribe)
    assert db_client.post(ocr_path, headers=outsider).status_code in {403, 404}
    result = db_client.post(ocr_path, headers=student)
    assert result.status_code == 200, result.text
    assert result.json()["file_sha256"] == uploaded.json()["sha256"]
    assert result.json()["suggestions"][0]["text"] == "y'=x^2-2x-3"
    assert db_client.get(f"/api/v2/math-solutions/attempts/{attempt_id}", headers=student).json()["steps"] == []

    step = db_client.post(f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=mutation(created.json()["attempt_revision_number"], step_type="EXPLANATION",
                      explanation_text="The student confirmed this text."), headers=student)
    assert step.status_code == 201, step.text
    submitted = db_client.post(f"/api/v2/math-solutions/attempts/{attempt_id}/submit",
        json=mutation(step.json()["attempt_revision_number"]), headers=student)
    assert submitted.status_code == 200, submitted.text
    assert db_client.post(ocr_path, headers=student).status_code == 409


def test_paper_ocr_rejects_nonexistent_page(db_client, v2_domain, auth_headers, tmp_path, monkeypatch):
    monkeypatch.setenv("MATH_PAPER_STORAGE_DIR", str(tmp_path / "paper"))
    get_settings.cache_clear()
    student = auth_headers(v2_domain.student)
    created = db_client.post("/api/v2/math-solutions/attempts", json=create_payload(v2_domain), headers=student)
    attempt_id = created.json()["id"]
    path = f"/api/v3/math-solutions/attempts/{attempt_id}/paper"
    uploaded = db_client.post(path, files={"file": ("work.png", png_bytes(), "image/png")}, headers=student)

    async def transcribe(_self, _data: bytes, _mime: str) -> PaperOcrOutput:
        return PaperOcrOutput(suggestions=[PaperOcrSuggestion(
            page_number=2, kind="TEXT", text="not on this page", uncertain=False,
        )])

    monkeypatch.setattr(GeminiPaperTranscriber, "transcribe", transcribe)
    result = db_client.post(f"{path}/{uploaded.json()['id']}/ocr", headers=student)
    assert result.status_code == 503
    assert result.json()["error"]["code"] == "PAPER_OCR_INVALID"
