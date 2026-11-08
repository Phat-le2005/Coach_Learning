"""Exercise import acceptance tests use isolated SQLite and deterministic OCR exports."""
from hashlib import sha256
from io import BytesIO
import base64
import json
from types import SimpleNamespace

import pytest
from pypdf import PdfWriter
from sqlalchemy import select

from app.core.exceptions import ApplicationError
from app.teacher_materials.models import TeacherMaterial, TeacherMaterialStatus
from app.teacher_materials.pdf_import import (
    LocalPdfOcrRunner, TeacherPdfImportService, file_lock, process_import, read_json, write_json,
    PdfOcrRunError, ocr_failure_message,
)
from app.teacher_materials.pdf_schemas import PdfReviewDecision, PdfReviewSubmit
from tests.teacher_materials.test_teacher_materials import setup_domain


def pdf_bytes():
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def record(number, status="OK"):
    def part(text):
        return dict(markdown=text, fragments=[dict(page_number=1, status=status, source_errors=[],
                    visual_flags=["OCR_NOT_SOURCE_VERIFIED", "ROLE_BOUNDARY_HEURISTIC"],
                    source_asset="assets/source.png")])
    return dict(question_id=f"q{number}", collection_number=number, source_number=number,
                question=part(f"Câu {number}. Tính $1+{number}$"), answer=part(str(number + 1)),
                solution=part("Lời giải từ nguồn"), visual_assets=[])


class FakeRunner:
    def preflight(self):
        pass

    def run(self, directory):
        write_json(directory / "ocr/content.draft.pretty.json", [record(1), record(2, "INCOMPLETE")])
        write_json(directory / "ocr/summary.json", dict(processed_pages=1, selected_pages=1,
                    failed_regions=1, input_pdf="PRIVATE_PATH_MUST_NOT_LEAK"))


@pytest.fixture
def env(db_session, tmp_path, monkeypatch):
    domain = setup_domain(db_session, tmp_path)
    monkeypatch.setattr("app.teacher_materials.pdf_import.schedule_import", lambda *args: None)
    runner = FakeRunner()
    service = TeacherPdfImportService(domain.service, tmp_path / "imports", runner)
    draft = service.create(domain.teacher.id, domain.classroom.id, domain.subject.id,
                           "PDF bài tập", "exercise.pdf", pdf_bytes())
    return SimpleNamespace(d=domain, service=service, draft=draft, runner=runner,
                           directory=service._directory(draft.id), session=db_session)


def ready(env):
    process_import(env.directory, env.runner, env.service.root)
    return env.service.get(env.d.teacher.id, env.draft.id)


def review(**changes):
    decision = dict(question_id="q1", accepted=True, source_checked=True,
                    content="Câu 1. Nội dung giáo viên đã sửa", answer="2", explanation="Đã đối chiếu",
                    difficulty_level="THONG_HIEU")
    decision.update(changes)
    return PdfReviewSubmit(title="Bài tập đã duyệt", decisions=[PdfReviewDecision(**decision)])


def test_upload_and_ocr_never_publish_without_teacher_review(env):
    assert env.draft.status == "QUEUED"
    assert env.session.scalar(select(TeacherMaterial)) is None
    draft = ready(env)
    assert draft.status == "NEEDS_REVIEW"
    assert draft.questions[0].suggested is True
    assert draft.questions[1].suggested is False
    assert "INCOMPLETE" in draft.questions[1].warnings
    assert "PRIVATE_PATH" not in draft.model_dump_json()
    assert env.session.scalar(select(TeacherMaterial)) is None
    # The draft is discoverable after navigating away/reconstructing the service.
    restored = TeacherPdfImportService(env.d.service, env.service.root, env.runner)
    assert restored.list(env.d.teacher.id, env.d.classroom.id)[0].id == env.draft.id


def test_review_persists_edits_and_only_approved_questions_enter_library(env):
    ready(env)
    saved = env.service.save_review(env.d.teacher.id, env.draft.id, review())
    assert saved.review.decisions[0].content == "Câu 1. Nội dung giáo viên đã sửa"
    material = env.service.submit(env.d.teacher.id, env.draft.id, review())
    assert material.status == TeacherMaterialStatus.READY
    assert len(material.items) == 1
    assert material.items[0].content == saved.review.decisions[0].content
    assert material.items[0].raw_metadata["content_reviewed"] is True
    assert material.items[0].evaluation_mode.value == "TEACHER_REVIEW"
    assert material.items[0].difficulty == 0.5
    assert material.items[0].raw_metadata["difficulty_level"] == "THONG_HIEU"
    blob = env.d.service.storage.read(material.storage_key)
    document = json.loads(blob)
    assert material.sha256 == sha256(blob).hexdigest()
    assert [q["reviewed"]["question_id"] for q in document["questions"]] == ["q1"]
    assert b'"q2"' not in blob
    assert env.service.get(env.d.teacher.id, env.draft.id).status == "SUBMITTED"
    # A retried submit is idempotent even if its payload differs.
    assert env.service.submit(env.d.teacher.id, env.draft.id, review(content="Changed retry")).id == material.id
    assert len(env.session.scalars(select(TeacherMaterial)).all()) == 1
    assert len(env.service.get(env.d.teacher.id, env.draft.id).questions) == 2


@pytest.mark.parametrize("data,code", [
    (PdfReviewSubmit(title="Empty", decisions=[]), "NO_APPROVED_QUESTIONS"),
    (review(source_checked=False), "SOURCE_REVIEW_REQUIRED"),
    (review(content="  "), "SOURCE_REVIEW_REQUIRED"),
    (review(difficulty_level=None), "DIFFICULTY_LEVEL_REQUIRED"),
    (review(question_id="forged"), "INVALID_REVIEW_QUESTION"),
    (PdfReviewSubmit(title="Dup", decisions=review().decisions * 2), "INVALID_REVIEW_QUESTION"),
])
def test_invalid_or_unreviewed_selection_cannot_publish(env, data, code):
    ready(env)
    with pytest.raises(ApplicationError) as exc:
        env.service.submit(env.d.teacher.id, env.draft.id, data)
    assert exc.value.code == code
    assert env.session.scalar(select(TeacherMaterial)) is None


def test_pending_job_and_tampered_source_cannot_publish(env):
    with pytest.raises(ApplicationError) as exc:
        env.service.submit(env.d.teacher.id, env.draft.id, review())
    assert exc.value.code == "PDF_NOT_REVIEWABLE"
    ready(env)
    (env.directory / "source.pdf").write_bytes(b"tampered")
    with pytest.raises(ApplicationError) as exc:
        env.service.submit(env.d.teacher.id, env.draft.id, review())
    assert exc.value.code == "PDF_SOURCE_CHANGED"


@pytest.mark.parametrize("level,score", [("NHAN_BIET", 0.25), ("THONG_HIEU", 0.5), ("VAN_DUNG", 0.75), ("VAN_DUNG_CAO", 1.0)])
def test_teacher_difficulty_persists_in_draft_file_and_assignment_preparation(env, level, score):
    draft = ready(env)
    assert draft.questions[0].difficulty_level is None
    pending = env.service.save_review(env.d.teacher.id, env.draft.id, review(difficulty_level=None))
    assert pending.review.decisions[0].difficulty_level is None
    data = review(difficulty_level=level, answer="Đáp án đã sửa", explanation="Lời giải đã sửa")
    saved = env.service.save_review(env.d.teacher.id, env.draft.id, data)
    assert saved.review.decisions[0].difficulty_level.value == level
    material = env.service.submit(env.d.teacher.id, env.draft.id, data)
    assert material.items[0].difficulty == score
    assert material.items[0].correct_answer == data.decisions[0].answer
    assert material.items[0].explanation == data.decisions[0].explanation
    document = json.loads(env.d.service.storage.read(material.storage_key))
    assert document["questions"][0]["reviewed"]["difficulty_level"] == level
    prepared = env.d.service.prepare_for_assignment(env.d.teacher.id, material.id)
    assert prepared.items[0].difficulty == score


def test_unknown_difficulty_values_cannot_be_submitted():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        review(difficulty_level="UNKNOWN_GUESSED_LEVEL")


def test_submitted_material_can_be_revised_without_overwriting_previous_content(env):
    ready(env)
    records = read_json(env.directory / "ocr/content.draft.pretty.json")
    records[0]["visual_assets"] = [dict(path="visual_assets/question.png")]
    image = env.directory / "ocr/visual_assets/question.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"original-visual")
    write_json(env.directory / "ocr/content.draft.pretty.json", records)
    original = env.service.submit(env.d.teacher.id, env.draft.id, review())
    original_bytes = env.d.service.storage.read(original.storage_key)
    revision = env.service.revise(env.d.teacher.id, env.draft.id)
    assert revision.status == "NEEDS_REVIEW" and revision.revision_of == original.id
    assert len(revision.questions) == 2
    assert revision.review.decisions[0].content == original.items[0].content
    assert env.service.revise(env.d.teacher.id, env.draft.id).id == revision.id
    revision_directory = env.service._directory(revision.id)
    assert not (revision_directory / "ocr").exists()  # Reuse original source images, no OCR rerun.
    changed = review(content="Đề bài mới", answer="Đáp án mới", explanation="Lời giải mới", difficulty_level="VAN_DUNG_CAO")
    material = env.service.submit(env.d.teacher.id, revision.id, changed)
    assert material.id != original.id
    assert material.items[0].difficulty == 1.0
    assert material.items[0].content == "Đề bài mới"
    index = material.items[0].raw_metadata["visual_assets"][0]
    assert env.service.material_asset(env.d.teacher.id, material.id, index).read_bytes() == b"original-visual"
    previous = env.d.service.get(env.d.teacher.id, original.id)
    assert previous.items[0].content != "Đề bài mới"
    assert env.d.service.storage.read(previous.storage_key) == original_bytes
    document = json.loads(env.d.service.storage.read(material.storage_key))
    assert document["revision_of"] == str(original.id)
    assert base64.b64decode(document["assets"][0]["data_base64"]) == b"original-visual"


def test_revision_requires_owner_and_an_already_submitted_material(env):
    ready(env)
    with pytest.raises(ApplicationError) as exc:
        env.service.revise(env.d.teacher.id, env.draft.id)
    assert exc.value.code == "PDF_NOT_SUBMITTED"
    env.service.submit(env.d.teacher.id, env.draft.id, review())
    with pytest.raises(ApplicationError) as exc:
        env.service.revise(env.d.outsider.id, env.draft.id)
    assert exc.value.status_code == 403


def test_image_upload_review_source_revision_and_deletion(env, db_app, db_client):
    from PIL import Image
    from app.auth.dependencies import get_current_user
    from app.teacher_materials.router import get_pdf_service, get_service
    output = BytesIO(); Image.new("RGB", (160, 80), "white").save(output, "PNG")
    data = output.getvalue()
    db_app.dependency_overrides[get_current_user] = lambda: env.d.teacher
    db_app.dependency_overrides[get_pdf_service] = lambda: env.service
    db_app.dependency_overrides[get_service] = lambda: env.d.service
    uploaded = db_client.post("/teacher-materials/pdf-imports", data=dict(
        classroom_id=str(env.d.classroom.id), subject_id=str(env.d.subject.id), title="Ảnh câu hỏi"),
        files={"file": ("exercise.png", data, "image/png")})
    assert uploaded.status_code == 202, uploaded.text
    job = uploaded.json()
    assert job["source_kind"] == "IMAGE" and job["source_mime_type"] == "image/png"
    from uuid import UUID
    job_id = UUID(job["id"])
    directory = env.service._directory(job_id)
    assert read_json(directory / "job.json")["upload_sha256"] == sha256(data).hexdigest()
    assert env.service.create(env.d.teacher.id, env.d.classroom.id, env.d.subject.id, "Same image", "copy.png", data).id == job_id
    assert (directory / "source.pdf").read_bytes().startswith(b"%PDF-")
    base = f"/teacher-materials/pdf-imports/{job_id}"
    original = db_client.get(base + "/source")
    assert original.headers["content-type"] == "image/png" and original.content == data
    process_import(directory, env.runner, env.service.root)
    submitted = db_client.post(base + "/submit", json=review().model_dump())
    assert submitted.status_code == 200, submitted.text
    material_id = submitted.json()["id"]
    revision = db_client.post(base + "/revise")
    assert revision.status_code == 201
    revision_id = UUID(revision.json()["id"])
    assert env.service.source(env.d.teacher.id, revision_id).read_bytes() == data
    # Only the selected library version is deleted; its revision remains usable.
    deleted = db_client.delete(f"/teacher-materials/{material_id}")
    assert deleted.status_code == 204
    assert db_client.delete(f"/teacher-materials/{material_id}").status_code == 204
    assert db_client.get(f"/teacher-materials/{material_id}").status_code == 410
    assert db_client.get(base).status_code == 410
    assert db_client.get(base + "/source").status_code == 410
    assert all(str(m.id) != material_id for m in env.d.service.list(env.d.teacher.id, env.d.classroom.id))
    assert env.service.get(env.d.teacher.id, revision_id).status == "NEEDS_REVIEW"
    assert env.service.source(env.d.teacher.id, revision_id).read_bytes() == data


def test_unlabelled_image_produces_a_manual_review_candidate(env):
    from PIL import Image
    output = BytesIO(); Image.new("RGB", (160, 80), "white").save(output, "PNG")
    job = env.service.create(env.d.teacher.id, env.d.classroom.id, env.d.subject.id, "Ảnh không số câu", "crop.png", output.getvalue())
    directory = env.service._directory(job.id)
    write_json(directory / "ocr/content.draft.pretty.json", [])
    write_json(directory / "ocr/pages.ocr.pretty.json", [dict(page_number=1, regions=[dict(status="OK", blocks=[
        dict(markdown="Tính $1+1$.", bbox=[0, 0, 20, 10], source_image="assets/crop.png", status="OK")])])])
    metadata = read_json(directory / "job.json"); metadata["status"] = "NEEDS_REVIEW"
    write_json(directory / "job.json", metadata)
    candidate = env.service.get(env.d.teacher.id, job.id).questions[0]
    assert candidate.content == "Tính $1+1$." and candidate.source_number is None
    assert not candidate.suggested
    assert "IMAGE_QUESTION_BOUNDARY_REVIEW_REQUIRED" in candidate.warnings
    assert candidate.answer == "" and candidate.explanation == ""


def test_archived_source_does_not_remove_images_used_by_another_reviewed_version(env):
    ready(env)
    records = read_json(env.directory / "ocr/content.draft.pretty.json")
    records[0]["visual_assets"] = [dict(path="visual_assets/retained.png")]
    asset = env.directory / "ocr/visual_assets/retained.png"
    asset.parent.mkdir(parents=True, exist_ok=True); asset.write_bytes(b"retained-visual")
    write_json(env.directory / "ocr/content.draft.pretty.json", records)
    first = env.service.submit(env.d.teacher.id, env.draft.id, review())
    draft = env.service.revise(env.d.teacher.id, env.draft.id)
    second = env.service.submit(env.d.teacher.id, draft.id, review(content="Revised question"))
    env.d.service.archive(env.d.teacher.id, first.id)
    index = second.items[0].raw_metadata["visual_assets"][0]
    assert env.service.material_asset(env.d.teacher.id, second.id, index).read_bytes() == b"retained-visual"


def test_delete_requires_classroom_access(env, db_app, db_client):
    from app.auth.dependencies import get_current_user
    from app.teacher_materials.router import get_service
    ready(env)
    material = env.service.submit(env.d.teacher.id, env.draft.id, review())
    db_app.dependency_overrides[get_service] = lambda: env.d.service
    for actor in (env.d.outsider, env.d.student):
        def current_actor():
            return actor
        db_app.dependency_overrides[get_current_user] = current_actor
        assert db_client.delete(f"/teacher-materials/{material.id}").status_code == 403
    assert env.d.service.get(env.d.teacher.id, material.id).status == TeacherMaterialStatus.READY


def test_draft_source_and_assets_enforce_owner_and_path_boundaries(env):
    for action in [lambda: env.service.get(env.d.outsider.id, env.draft.id),
                   lambda: env.service.source(env.d.outsider.id, env.draft.id),
                   lambda: env.service.retry(env.d.outsider.id, env.draft.id)]:
        with pytest.raises(ApplicationError) as exc:
            action()
        assert exc.value.status_code == 403
    ready(env)
    rows = read_json(env.directory / "ocr/content.draft.pretty.json")
    rows[0]["question"]["fragments"][0]["source_asset"] = "../../outside.png"
    write_json(env.directory / "ocr/content.draft.pretty.json", rows)
    for index in [0, -1, 999]:
        with pytest.raises(ApplicationError) as exc:
            env.service.asset(env.d.teacher.id, env.draft.id, index)
        assert exc.value.status_code == 404


def test_failed_job_can_resume_and_active_job_cannot_be_retried(env):
    class BrokenRunner(FakeRunner):
        def run(self, directory):
            raise RuntimeError("PRIVATE_RUNTIME_PATH")
    process_import(env.directory, BrokenRunner(), env.service.root)
    failed = env.service.get(env.d.teacher.id, env.draft.id)
    assert failed.status == "FAILED" and "PRIVATE_RUNTIME" not in failed.error
    assert env.service.retry(env.d.teacher.id, env.draft.id).status == "QUEUED"
    with file_lock(env.directory / "job.lock"):
        with pytest.raises(ApplicationError) as exc:
            env.service.retry(env.d.teacher.id, env.draft.id)
        assert exc.value.code == "PDF_IMPORT_BUSY"
    assert ready(env).status == "NEEDS_REVIEW"


def test_model_connection_failure_is_explained_without_leaking_process_output(env):
    log = env.directory / "worker.log"
    log.write_text("PRIVATE_PATH\\local_model.ps1: Port 8790 is already occupied; the existing process was preserved.")
    message = ocr_failure_message(log)
    assert "model" in message and "PRIVATE_PATH" not in message
    class BusyRunner(FakeRunner):
        def run(self, directory):
            raise PdfOcrRunError(message)
    process_import(env.directory, BusyRunner(), env.service.root)
    failed = env.service.get(env.d.teacher.id, env.draft.id)
    assert failed.status == "FAILED"
    assert failed.error == message


def test_upload_reuses_private_draft_and_rejects_non_pdf(env):
    same = env.service.create(env.d.teacher.id, env.d.classroom.id, env.d.subject.id,
                              "Same PDF", "copy.pdf", pdf_bytes())
    assert same.id == env.draft.id
    for filename, data in [("x.pdf", b"not a pdf"), ("../x.pdf", pdf_bytes()), ("x.pdf", b"%PDF-broken")]:
        with pytest.raises(ApplicationError):
            env.service.create(env.d.teacher.id, env.d.classroom.id, env.d.subject.id, "Bad", filename, data)


def test_process_crash_after_material_commit_recovers_without_duplicate(env):
    ready(env)
    material = env.service.submit(env.d.teacher.id, env.draft.id, review())
    job = read_json(env.directory / "job.json")
    job.update(status="NEEDS_REVIEW", material_id=None)
    write_json(env.directory / "job.json", job)
    assert env.service.submit(env.d.teacher.id, env.draft.id, review()).id == material.id
    assert len(env.session.scalars(select(TeacherMaterial)).all()) == 1


def test_generated_document_preserves_approved_visuals_only(env):
    ready(env)
    rows = read_json(env.directory / "ocr/content.draft.pretty.json")
    for number, row in enumerate(rows, 1):
        row["visual_assets"] = [dict(path=f"visual_assets/q{number}.png")]
        path = env.directory / f"ocr/visual_assets/q{number}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"png-{number}".encode())
    write_json(env.directory / "ocr/content.draft.pretty.json", rows)
    material = env.service.submit(env.d.teacher.id, env.draft.id, review())
    document = json.loads(env.d.service.storage.read(material.storage_key))
    assert len(document["assets"]) == 1
    assert document["assets"][0]["path"] == "visual_assets/q1.png"
    assert base64.b64decode(document["assets"][0]["data_base64"]) == b"png-1"
    index = material.items[0].raw_metadata["visual_assets"][0]
    assert env.service.material_asset(env.d.teacher.id, material.id, index).read_bytes() == b"png-1"
    with pytest.raises(ApplicationError):
        env.service.material_asset(env.d.teacher.id, material.id, index + 1)


def test_local_runner_calls_the_shared_tool_and_accepts_partial_results(tmp_path, monkeypatch):
    runner = LocalPdfOcrRunner(tmp_path / "runtime", "CPU", 8790)
    monkeypatch.setattr(runner, "preflight", lambda: None)
    monkeypatch.setattr("subprocess.CREATE_NO_WINDOW", 0, raising=False)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        write_json(tmp_path / "ocr/content.draft.pretty.json", [])
        return SimpleNamespace(returncode=2)
    monkeypatch.setattr("app.teacher_materials.pdf_import.subprocess.run", run)
    runner.run(tmp_path)
    assert calls[0][calls[0].index("-File") + 1].endswith("ocr_pdf_direct.ps1")
    assert calls[0][calls[0].index("-Runtime") + 1] == str((tmp_path / "runtime").resolve())
    assert "-Open" not in calls[0]


def test_http_upload_review_submit_and_download_are_teacher_scoped(env, db_app, db_client):
    from app.auth.dependencies import get_current_user
    from app.teacher_materials.router import get_pdf_service, get_service
    db_app.dependency_overrides[get_current_user] = lambda: env.d.teacher
    db_app.dependency_overrides[get_pdf_service] = lambda: env.service
    db_app.dependency_overrides[get_service] = lambda: env.d.service
    response = db_client.post("/teacher-materials/pdf-imports", data=dict(
        classroom_id=str(env.d.classroom.id), subject_id=str(env.d.subject.id), title="HTTP PDF"),
        files={"file": ("exercise.pdf", pdf_bytes(), "application/pdf")})
    assert response.status_code == 202, response.text
    assert response.json()["id"] == str(env.draft.id)
    base = f"/teacher-materials/pdf-imports/{env.draft.id}"
    assert db_client.get(base + "/source").content == pdf_bytes()
    ready(env)
    assert db_client.put(base + "/review", json=review().model_dump()).status_code == 200
    submitted = db_client.post(base + "/submit", json=review().model_dump())
    assert submitted.status_code == 200, submitted.text
    material_id = submitted.json()["id"]
    download = db_client.get(f"/teacher-materials/{material_id}/document")
    assert download.status_code == 200 and len(download.json()["questions"]) == 1
    assert "attachment" in download.headers["content-disposition"]
    revision = db_client.post(base + "/revise")
    assert revision.status_code == 201, revision.text
    assert revision.json()["revision_of"] == material_id
    db_app.dependency_overrides[get_current_user] = lambda: env.d.student
    assert db_client.get(base).status_code == 403
    assert db_client.get(base + "/source").status_code == 403
    assert db_client.get(f"/teacher-materials/{material_id}/document").status_code == 403


def test_colleague_can_read_submitted_source_but_cannot_edit_the_owners_draft(env):
    from app.classes.models import TeacherClassroom
    from app.teachers.models import TeacherProfile
    colleague = env.session.scalar(select(TeacherProfile).where(TeacherProfile.user_id == env.d.outsider.id))
    env.session.add(TeacherClassroom(teacher_id=colleague.id, classroom_id=env.d.classroom.id, role="MEMBER"))
    env.session.commit()
    ready(env)
    with pytest.raises(ApplicationError):
        env.service.get(env.d.outsider.id, env.draft.id)
    material = env.service.submit(env.d.teacher.id, env.draft.id, review())
    assert env.service.get(env.d.outsider.id, env.draft.id).material_id == material.id
    assert env.service.source(env.d.outsider.id, env.draft.id).is_file()
    for action in [lambda: env.service.retry(env.d.outsider.id, env.draft.id),
                   lambda: env.service.save_review(env.d.outsider.id, env.draft.id, review()),
                   lambda: env.service.submit(env.d.outsider.id, env.draft.id, review())]:
        with pytest.raises(ApplicationError) as exc:
            action()
        assert exc.value.status_code == 403
