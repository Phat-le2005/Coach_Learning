from io import BytesIO

from PIL import Image
from pypdf import PdfWriter

from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.math_paper.service import validate_paper
from tests.math_solutions.test_v2_api import auth_headers, create_payload, mutation, v2_domain


def png_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (400, 600), "white").save(output, format="PNG")
    return output.getvalue()


def test_private_paper_upload_deduplicates_and_locks_after_submission(
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
    image = png_bytes()
    uploaded = db_client.post(path, files={"file": ("homework.png", image, "image/png")}, headers=student)
    assert uploaded.status_code == 201, uploaded.text
    paper_id = uploaded.json()["id"]
    assert db_client.post(path, files={"file": ("again.png", image, "image/png")}, headers=student).json()["id"] == paper_id
    assert len(db_client.get(path, headers=student).json()) == 1
    assert db_client.get(f"{path}/{paper_id}", headers=student).content == image
    assert db_client.get(path, headers=outsider).status_code in {403, 404}
    assert db_client.get(f"{path}/{paper_id}", headers=outsider).status_code in {403, 404}
    step = db_client.post(f"/api/v2/math-solutions/attempts/{attempt_id}/steps",
        json=mutation(created.json()["attempt_revision_number"], step_type="EXPLANATION",
                      explanation_text="A confirmed written step from the uploaded paper."), headers=student)
    assert step.status_code == 201, step.text
    submitted = db_client.post(f"/api/v2/math-solutions/attempts/{attempt_id}/submit",
        json=mutation(step.json()["attempt_revision_number"]), headers=student)
    assert submitted.status_code == 200, submitted.text
    assert db_client.post(path, files={"file": ("new.png", image, "image/png")}, headers=student).status_code == 409
    assert db_client.delete(f"{path}/{paper_id}", headers=student).status_code == 409
    assert db_client.get(f"{path}/{paper_id}", headers=student).content == image


def test_paper_validator_rejects_invalid_and_accepts_pdf():
    import pytest
    with pytest.raises(ApplicationError):
        validate_paper(b"not a scan", "image/png")
    with pytest.raises(ApplicationError):
        validate_paper(png_bytes(), "application/pdf")
    with pytest.raises(ApplicationError):
        validate_paper(b"%PDF-" + b"x" * (10 * 1024 * 1024), "application/pdf")
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    writer.write(output)
    assert validate_paper(output.getvalue(), "application/pdf") == ("application/pdf", "pdf")
