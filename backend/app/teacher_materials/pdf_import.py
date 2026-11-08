"""Durable, private PDF drafts around the shared pdfmeta OCR entry point.

Jobs use the same local-filesystem deployment model as material storage. A file
lock serializes each draft across requests/processes; another serializes model
use. No request-scoped DB session is retained by the OCR worker.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
import base64
import logging
import os
from pathlib import Path
import subprocess
import threading
import time
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import ApplicationError
from app.classes.models import Classroom
from app.questions.models import QuestionType
from app.subjects.models import Subject
from app.teacher_materials.models import (
    MaterialEvaluationMode, MaterialItemExtractionStatus, TeacherMaterial,
    TeacherMaterialItem, TeacherMaterialStatus,
)
from app.teacher_materials.pdf_schemas import PdfImportQuestion, PdfImportRead, PdfReviewDecision, PdfReviewSubmit
from app.teacher_materials.difficulty import DIFFICULTY_SCORES, MaterialDifficultyLevel
from app.teacher_materials.service import TeacherMaterialService
from app.teacher_materials.ocr_source import normalize_source
from app.teacher_materials.visual_schemas import QuestionVisualRead, markdown_image_paths

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(f"{path.name}.{uuid4().hex}.pending")
    try:
        pending.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


@contextmanager
def file_lock(path: Path, *, wait: bool = False):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        stream.seek(0, 2)
        if not stream.tell():
            stream.write(b"0")
            stream.flush()
        acquired = False
        while not acquired:
            stream.seek(0)
            try:
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except OSError as exc:
                if not wait:
                    raise ApplicationError(409, "PDF_IMPORT_BUSY", "Bản PDF đang được xử lý. Vui lòng đợi.") from exc
                time.sleep(0.25)
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


class PdfOcrRunError(RuntimeError):
    """User-safe diagnostics; raw process output stays in the private job log."""


def ocr_failure_message(log_path: Path) -> str:
    with log_path.open("rb") as log:
        log.seek(0, 2)
        log.seek(max(0, log.tell() - 16_384))
        tail = log.read().decode("utf-8", errors="replace")
    if "is already occupied" in tail:
        return "Bộ OCR đang chạy nhưng ứng dụng chưa kết nối được với model. PDF và bố cục đã xử lý vẫn được giữ nguyên."
    if "Running Qwen configuration differs" in tail or "Existing server configuration is not verified" in tail:
        return "Cấu hình model OCR đang chạy khác với cấu hình của ứng dụng. Cần đồng bộ cấu hình trước khi tiếp tục."
    if "Layout acquisition stopped" in tail:
        return "Bộ đọc bố cục PDF chưa hoàn tất. Hãy thử lại để tiếp tục từ phần đã xử lý."
    return "Bộ OCR dừng khi xử lý tệp. PDF và phần đã xử lý vẫn được giữ để thử lại."


class LocalPdfOcrRunner:
    def __init__(self, runtime: Path, device: str, port: int):
        self.runtime, self.device, self.port = Path(runtime).resolve(), device, port

    def preflight(self) -> None:
        manifest = "local-qwen-runtime.gpu.json" if self.device == "GPU" else "local-qwen-runtime.json"
        if os.name != "nt" or not (self.runtime / ".venv/Scripts/python.exe").is_file() or not (self.runtime / manifest).is_file():
            raise ApplicationError(503, "PDF_OCR_NOT_CONFIGURED", "Chưa cấu hình bộ OCR PDF. Hãy thiết lập runtime tools/pdf_metadata và TEACHER_PDF_RUNTIME_DIR trên máy chủ.")

    def run(self, directory: Path) -> None:
        self.preflight()
        command = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(REPO_ROOT / "tools/pdf_metadata/ocr_pdf_direct.ps1"),
            "-Pdf", str(directory / "source.pdf"), "-Runtime", str(self.runtime),
            "-Storage", str(directory), "-Output", str(directory / "ocr"),
            "-Device", self.device, "-Port", str(self.port),
        ]
        # Preserve checkpoints and detailed diagnostics privately, never in API errors.
        with (directory / "worker.log").open("ab") as log:
            result = subprocess.run(command, cwd=REPO_ROOT, stdout=log, stderr=subprocess.STDOUT,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        if result.returncode not in (0, 2) or not (directory / "ocr/content.draft.pretty.json").is_file():
            raise PdfOcrRunError(ocr_failure_message(directory / "worker.log"))


def schedule_import(directory: Path, runner: LocalPdfOcrRunner, root: Path) -> None:
    threading.Thread(target=process_import, args=(directory, runner, root), daemon=True,
                     name=f"teacher-pdf-{directory.name[:8]}").start()


def process_import(directory: Path, runner: LocalPdfOcrRunner, root: Path) -> None:
    try:
        with file_lock(directory / "job.lock"):
            job = read_json(directory / "job.json")
            if not job or job["status"] == "SUBMITTED":
                return
            try:
                # Only one OCR job uses the configured local model at a time.
                with file_lock(root / "model.lock", wait=True):
                    job.update(status="PROCESSING", error=None)
                    write_json(directory / "job.json", job)
                    runner.run(directory)
                job.update(status="NEEDS_REVIEW", error=None)
            except Exception as exc:
                logger.exception("Teacher PDF OCR failed for job %s", directory.name)
                message = str(exc) if isinstance(exc, PdfOcrRunError) else "OCR chưa hoàn tất. Bạn có thể thử lại để tiếp tục từ phần đã xử lý."
                job.update(status="FAILED", error=message)
            write_json(directory / "job.json", job)
    except ApplicationError:
        # A duplicate dispatch must never overwrite the active worker's state.
        return


class TeacherPdfImportService:
    def __init__(self, materials: TeacherMaterialService, root: Path, runner: LocalPdfOcrRunner):
        self.materials, self.root, self.runner = materials, Path(root).resolve(), runner
        self._visual_questions: dict[UUID, list[PdfImportQuestion]] = {}

    def _directory(self, job_id: UUID) -> Path:
        return self.root / str(job_id)

    def _ocr_directory(self, directory: Path) -> Path:
        job = read_json(directory / "job.json", {})
        origin = self._directory(UUID(job["source_job_id"])) if job.get("source_job_id") else directory
        return origin / "ocr"

    def _job(self, user_id: UUID, job_id: UUID, *, owner_only=False) -> tuple[Path, dict]:
        directory = self._directory(job_id)
        job = read_json(directory / "job.json")
        if not job:
            raise ApplicationError(404, "PDF_IMPORT_NOT_FOUND", "Không tìm thấy bản nháp PDF.")
        self.materials._authorize(user_id, UUID(job["classroom_id"]))
        if job["uploaded_by"] != str(user_id) and (owner_only or job["status"] != "SUBMITTED"):
            raise ApplicationError(403, "PDF_IMPORT_ACCESS_DENIED", "Chỉ giáo viên tải PDF được duyệt bản nháp này.")
        if job.get("material_id"):
            self.materials.get(user_id, UUID(job["material_id"]))
        return directory, job

    def create(self, user_id: UUID, classroom_id: UUID, subject_id: UUID, title: str,
               filename: str, data: bytes) -> PdfImportRead:
        self.materials._authorize(user_id, classroom_id)
        subject = self.materials.session.get(Subject, subject_id)
        if subject is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Không tìm thấy môn học.")
        classroom = self.materials.session.get(Classroom, classroom_id)
        if subject.grade_level is not None and subject.grade_level != classroom.grade_level:
            raise ApplicationError(422, "MATERIAL_SUBJECT_GRADE_MISMATCH", "Môn học không phù hợp với khối lớp.")
        if not title.strip() or len(title.strip()) > 255:
            raise ApplicationError(422, "INVALID_MATERIAL_TITLE", "Tên tài liệu phải có từ 1 đến 255 ký tự.")
        if not data:
            raise ApplicationError(422, "EMPTY_MATERIAL", "Tệp tải lên trống.")
        if len(data) > self.materials.max_bytes:
            raise ApplicationError(413, "MATERIAL_TOO_LARGE", "Tệp vượt quá giới hạn dung lượng.")
        if len(filename) > 255 or Path(filename).name != filename or "\\" in filename:
            raise ApplicationError(422, "UNSAFE_FILE_NAME", "Tên tệp tải lên không hợp lệ.")
        source = normalize_source(filename, data)
        self.runner.preflight()
        digest = sha256(data).hexdigest()
        existing = self.materials.session.scalar(select(TeacherMaterial).where(
            TeacherMaterial.classroom_id == classroom_id, TeacherMaterial.sha256 == digest,
            TeacherMaterial.status != TeacherMaterialStatus.ARCHIVED))
        if existing:
            raise ApplicationError(409, "MATERIAL_DUPLICATE", "PDF này đã có trong kho học liệu của lớp.")
        for old in self.list(user_id, classroom_id):
            _, old_job = self._job(user_id, old.id)
            if old_job.get("upload_sha256", old_job["sha256"]) == digest:
                return old
        job_id = uuid4()
        directory = self._directory(job_id)
        directory.mkdir(parents=True)
        (directory / "source.pdf").write_bytes(source.pdf)
        if source.image_name:
            (directory / source.image_name).write_bytes(data)
        job = dict(id=str(job_id), classroom_id=str(classroom_id), subject_id=str(subject_id),
                   uploaded_by=str(user_id), title=title.strip(), original_file_name=filename,
                   sha256=sha256(source.pdf).hexdigest(), upload_sha256=digest,
                   source_kind=source.kind, source_mime_type=source.mime_type,
                   source_image_name=source.image_name,
                   file_size_bytes=len(data), page_count=source.page_count,
                   status="QUEUED", created_at=datetime.now(timezone.utc).isoformat(), error=None,
                   material_id=None)
        write_json(directory / "job.json", job)
        schedule_import(directory, self.runner, self.root)
        return self.get(user_id, job_id)

    def list(self, user_id: UUID, classroom_id: UUID) -> list[PdfImportRead]:
        self.materials._authorize(user_id, classroom_id)
        jobs = []
        for path in self.root.glob("*/job.json"):
            job = read_json(path)
            if job and job["classroom_id"] == str(classroom_id) and job["uploaded_by"] == str(user_id):
                if job.get("material_id"):
                    material = self.materials.session.get(TeacherMaterial, UUID(job["material_id"]))
                    if material is None or material.status == TeacherMaterialStatus.ARCHIVED:
                        continue
                jobs.append(self.get(user_id, UUID(job["id"]), include_questions=False))
        return sorted(jobs, key=lambda row: row.created_at, reverse=True)

    def _questions(self, directory: Path) -> tuple[list[PdfImportQuestion], list[str], list[dict]]:
        records = read_json(self._ocr_directory(directory) / "content.draft.pretty.json", [])
        job = read_json(directory / "job.json", {})
        if not records and job.get("source_kind") == "IMAGE":
            records = self._image_candidate(directory, job)
        assets: list[str] = []

        def asset_index(path):
            if path not in assets:
                assets.append(path)
            return assets.index(path)

        questions = []
        for row in records:
            parts = [row.get(role, {}) for role in ("question", "answer", "solution")]
            fragments = [f for p in parts for f in p.get("fragments", [])]
            warnings = []
            for fragment in fragments:
                if fragment.get("status") not in (None, "OK"):
                    warnings.append(fragment["status"])
                warnings.extend(str(e) for e in fragment.get("source_errors", []))
                warnings.extend(f for f in fragment.get("visual_flags", []) if f not in {
                    "OCR_NOT_SOURCE_VERIFIED", "ROLE_BOUNDARY_HEURISTIC", "SOURCE_VISUAL_PRESERVED"})
            content = row.get("question", {}).get("markdown", "")
            if not content.strip():
                warnings.append("EMPTY_QUESTION")
            questions.append(PdfImportQuestion(
                question_id=row["question_id"], number=row["collection_number"], source_number=row.get("source_number"),
                content=content, answer=row.get("answer", {}).get("markdown", ""),
                explanation=row.get("solution", {}).get("markdown", ""),
                difficulty_level=row.get("difficulty_level") if row.get("difficulty_level") in MaterialDifficultyLevel._value2member_map_ else None,
                pages=sorted({f["page_number"] for f in fragments if f.get("page_number")}),
                warnings=list(dict.fromkeys(warnings)), suggested=not warnings,
                source_assets=list(dict.fromkeys(asset_index(f["source_asset"]) for f in fragments if f.get("source_asset"))),
                visual_assets=list(dict.fromkeys(asset_index(a["path"]) for a in row.get("visual_assets", []) if a.get("path"))),
            ))
            for asset in row.get("visual_assets", []):
                if not asset.get("path"):
                    continue
                index = asset_index(asset["path"])
                role = asset.get("role")
                if role not in {"question", "answer", "solution"}:
                    role = next((name for name in ("question", "answer", "solution")
                                 if asset["path"] in markdown_image_paths(row.get(name, {}).get("markdown", ""))), "question")
                questions[-1].visuals.append(QuestionVisualRead(
                    index=index, path=asset["path"], role=role,
                    url=f"/api/teacher/materials/pdf-imports/{directory.name}/assets/{index}",
                ))
        return questions, assets, records

    def _image_candidate(self, directory: Path, job: dict) -> list[dict]:
        """An unlabelled image is a candidate for manual boundaries, never auto-approved."""
        output = self._ocr_directory(directory)
        fragments = []
        for page in read_json(output / "pages.ocr.pretty.json", []):
            for region in page.get("regions", []):
                for block in region.get("blocks", []):
                    if not block.get("markdown", "").strip():
                        continue
                    fragments.append(dict(markdown=block["markdown"], page_number=page["page_number"],
                        bbox=block.get("bbox"), source_asset=block.get("source_image"),
                        status=block.get("status", region.get("status")), source_errors=block.get("errors", []),
                        visual_flags=["IMAGE_QUESTION_BOUNDARY_REVIEW_REQUIRED", *block.get("flags", [])]))
        if not fragments:
            return []
        empty = dict(markdown="", fragments=[])
        return [dict(question_id=f"{job['sha256'][:24]}:image:q0001", collection_number=1, source_number=None,
                     source=dict(sha256=job["sha256"], name="source.pdf", page_count=1),
                     question=dict(markdown="\n\n".join(f["markdown"] for f in fragments), fragments=fragments),
                     answer=empty, solution=empty, visual_assets=read_json(output / "visual-assets.json", []),
                     academic_review="PENDING", publishable=False)]

    def get(self, user_id: UUID, job_id: UUID, *, include_questions=True) -> PdfImportRead:
        directory, job = self._job(user_id, job_id)
        ocr_directory = self._ocr_directory(directory)
        progress = read_json(ocr_directory / "summary.json") or read_json(ocr_directory / "progress.json", {})
        progress = {k: progress[k] for k in ("processed_pages", "selected_pages", "failed_regions", "review_regions", "questions") if k in progress}
        progress.setdefault("selected_pages", job["page_count"])
        questions = self._questions(directory)[0] if include_questions and job["status"] in {"NEEDS_REVIEW", "SUBMITTED"} else []
        if include_questions and job["status"] in {"NEEDS_REVIEW", "SUBMITTED"}:
            progress["questions"] = len(questions)
        return PdfImportRead(**{k: job[k] for k in PdfImportRead.model_fields if k in job},
                             questions=questions, progress=progress,
                             review=read_json(directory / "review.draft.json") if include_questions else None)

    def retry(self, user_id: UUID, job_id: UUID) -> PdfImportRead:
        directory, job = self._job(user_id, job_id, owner_only=True)
        with file_lock(directory / "job.lock"):
            job = read_json(directory / "job.json")
            if job["status"] == "SUBMITTED":
                raise ApplicationError(409, "PDF_ALREADY_SUBMITTED", "Tài liệu này đã được lưu vào kho.")
            if job.get("revision_of"):
                raise ApplicationError(409, "PDF_REVISION_USES_SOURCE_OCR", "Bản chỉnh sửa dùng kết quả OCR gốc. Hãy chỉnh nội dung trực tiếp trên bản nháp.")
            self.runner.preflight()
            job.update(status="QUEUED", error=None)
            write_json(directory / "job.json", job)
        schedule_import(directory, self.runner, self.root)
        return self.get(user_id, job_id)

    def revise(self, user_id: UUID, job_id: UUID) -> PdfImportRead:
        directory, _ = self._job(user_id, job_id, owner_only=True)
        with file_lock(directory / "job.lock"):
            job = read_json(directory / "job.json")
            if job["status"] != "SUBMITTED" or not job.get("material_id"):
                raise ApplicationError(409, "PDF_NOT_SUBMITTED", "Tài liệu chưa lưu có thể chỉnh trực tiếp trên bản nháp hiện tại.")
            self.materials.get(user_id, UUID(job["material_id"]))
            for pending in self.list(user_id, UUID(job["classroom_id"])):
                pending_job = read_json(self._directory(pending.id) / "job.json", {})
                if pending.status == "NEEDS_REVIEW" and pending_job.get("revision_of") == job["material_id"]:
                    return self.get(user_id, pending.id)
            source = (directory / "source.pdf").read_bytes()
            if sha256(source).hexdigest() != job["sha256"]:
                raise ApplicationError(409, "PDF_SOURCE_CHANGED", "PDF nguồn đã thay đổi. Hãy tải lại đúng tệp nguồn.")
            saved = read_json(directory / "review.draft.json", {})
            saved_decisions = {d["question_id"]: d for d in saved.get("decisions", [])}
            title = job["title"][:235] + " · Bản chỉnh sửa"
            decisions = [PdfReviewDecision.model_validate(saved_decisions.get(q.question_id) or dict(
                question_id=q.question_id, content=q.content, answer=q.answer,
                explanation=q.explanation, difficulty_level=q.difficulty_level,
            )) for q in self._questions(directory)[0]]
            revision_id = uuid4()
            revision_directory = self._directory(revision_id)
            revision_directory.mkdir(parents=True)
            (revision_directory / "source.pdf").write_bytes(source)
            if job.get("source_image_name"):
                (revision_directory / job["source_image_name"]).write_bytes((directory / job["source_image_name"]).read_bytes())
            revision = {**job, "id": str(revision_id), "title": title, "status": "NEEDS_REVIEW",
                        "material_id": None, "error": None, "revision_of": job["material_id"],
                        "source_job_id": job.get("source_job_id") or job["id"],
                        "created_at": datetime.now(timezone.utc).isoformat()}
            write_json(revision_directory / "job.json", revision)
            write_json(revision_directory / "review.draft.json", PdfReviewSubmit(title=title, decisions=decisions).model_dump())
        return self.get(user_id, revision_id)

    def _validate_review(self, directory: Path, data: PdfReviewSubmit) -> dict[str, PdfImportQuestion]:
        questions = {q.question_id: q for q in self._questions(directory)[0]}
        ids = [d.question_id for d in data.decisions]
        if len(ids) != len(set(ids)) or any(i not in questions for i in ids):
            raise ApplicationError(422, "INVALID_REVIEW_QUESTION", "Danh sách duyệt có câu trùng hoặc không thuộc PDF này.")
        if not data.title.strip():
            raise ApplicationError(422, "INVALID_MATERIAL_TITLE", "Vui lòng nhập tên tài liệu.")
        for decision in data.decisions:
            if decision.accepted and (not decision.content.strip() or not decision.source_checked):
                raise ApplicationError(422, "SOURCE_REVIEW_REQUIRED", "Hãy đối chiếu PDF gốc và xác nhận từng câu được giữ lại.")
        return questions

    def save_review(self, user_id: UUID, job_id: UUID, data: PdfReviewSubmit) -> PdfImportRead:
        directory, _ = self._job(user_id, job_id, owner_only=True)
        with file_lock(directory / "job.lock"):
            job = read_json(directory / "job.json")
            if job["status"] != "NEEDS_REVIEW":
                raise ApplicationError(409, "PDF_NOT_REVIEWABLE", "PDF chưa sẵn sàng để duyệt.")
            self._validate_review(directory, data)
            write_json(directory / "review.draft.json", data.model_dump())
        return self.get(user_id, job_id)

    def submit(self, user_id: UUID, job_id: UUID, data: PdfReviewSubmit) -> TeacherMaterial:
        directory, _ = self._job(user_id, job_id, owner_only=True)
        with file_lock(directory / "job.lock"):
            job = read_json(directory / "job.json")
            if job.get("material_id"):
                return self.materials.get(user_id, UUID(job["material_id"]))
            if job["status"] != "NEEDS_REVIEW":
                raise ApplicationError(409, "PDF_NOT_REVIEWABLE", "Hãy đợi OCR hoàn tất trước khi lưu tài liệu.")
            questions = self._validate_review(directory, data)
            accepted = [d for d in data.decisions if d.accepted]
            if not accepted:
                raise ApplicationError(422, "NO_APPROVED_QUESTIONS", "Hãy chọn duyệt ít nhất một câu hỏi.")
            if any(decision.difficulty_level is None for decision in accepted):
                raise ApplicationError(422, "DIFFICULTY_LEVEL_REQUIRED", "Hãy chọn mức độ cho từng câu được duyệt trước khi lưu vào kho.")
            # Preserve PDF order, independently of the browser's filter/sort order.
            accepted.sort(key=lambda d: questions[d.question_id].number)
            key = f"{job['classroom_id']}/{job_id}/reviewed.json"
            existing = self.materials.session.scalar(select(TeacherMaterial).where(TeacherMaterial.storage_key == key))
            if existing:
                provenance = existing.items[0].raw_metadata if existing.items else {}
                if provenance.get("pdf_import_id") != str(job_id):
                    raise ApplicationError(409, "MATERIAL_DUPLICATE", "PDF này đã có trong kho học liệu.")
                material = existing  # Recover a crash after DB commit, before job.json.
            else:
                source = (directory / "source.pdf").read_bytes()
                if sha256(source).hexdigest() != job["sha256"]:
                    raise ApplicationError(409, "PDF_SOURCE_CHANGED", "Tệp PDF gốc đã thay đổi. Hãy tải lại tệp.")
                _, asset_paths, raw_records = self._questions(directory)
                records = {r["question_id"]: r for r in raw_records}
                document = dict(schema_version="teacher-exercise-review.v1", title=data.title.strip(),
                                status="TEACHER_APPROVED",
                                source_sha256=job.get("upload_sha256", job["sha256"]), source_file=job["original_file_name"],
                                source_kind=job.get("source_kind", "PDF"), processing_pdf_sha256=job["sha256"],
                                reviewed_by=str(user_id), reviewed_at=datetime.now(timezone.utc).isoformat(),
                                questions=[dict(source=records[d.question_id], reviewed=d.model_dump()) for d in accepted])
                if job.get("revision_of"):
                    document["revision_of"] = job["revision_of"]
                # Keep visual dependencies in this single downloadable document.
                visual_indexes = sorted({i for d in accepted for i in questions[d.question_id].visual_assets})
                document["assets"] = []
                for index in visual_indexes:
                    image = self._asset_path(directory, index, assets=asset_paths)
                    document["assets"].append(dict(
                        index=index, path=asset_paths[index],
                        mime_type="image/png" if image.suffix.lower() == ".png" else "image/jpeg",
                        data_base64=base64.b64encode(image.read_bytes()).decode("ascii"),
                    ))
                artifact = json.dumps(document, ensure_ascii=False, indent=2).encode("utf-8")
                # One library file contains only accepted questions. The original PDF
                # remains a private review source, and never becomes the submitted file.
                material = TeacherMaterial(
                    classroom_id=UUID(job["classroom_id"]), subject_id=UUID(job["subject_id"]),
                    uploaded_by=user_id, title=data.title.strip(), original_file_name=Path(job["original_file_name"]).stem[:220] + ".reviewed.json",
                    mime_type="application/json", storage_key=key, sha256=sha256(artifact).hexdigest(),
                    file_size_bytes=len(artifact), page_count=job["page_count"], status=TeacherMaterialStatus.READY,
                )
                try:
                    self.materials.storage.save(key, artifact)
                    self.materials.session.add(material)
                    self.materials.session.flush()
                    for index, decision in enumerate(accepted):
                        question = questions[decision.question_id]
                        self.materials.session.add(TeacherMaterialItem(
                            teacher_material_id=material.id, order_index=index, content=decision.content.strip(),
                            content_hash=sha256(decision.content.strip().encode("utf-8")).hexdigest(),
                            page_start=min(question.pages) if question.pages else None,
                            page_end=max(question.pages) if question.pages else None,
                            question_type=QuestionType.OPEN_RESPONSE,
                            correct_answer=decision.answer.strip() or None, explanation=decision.explanation.strip() or None,
                            difficulty=DIFFICULTY_SCORES[decision.difficulty_level],
                            extraction_status=MaterialItemExtractionStatus.READY,
                            evaluation_mode=MaterialEvaluationMode.TEACHER_REVIEW,
                            raw_metadata=dict(content_reviewed=True, pdf_import_id=str(job_id),
                                              source_question_id=decision.question_id,
                                              source_checked=True, ocr_warnings=question.warnings,
                                              difficulty_level=decision.difficulty_level.value,
                                              difficulty_source="TEACHER",
                                              visual_assets=question.visual_assets),
                        ))
                    self.materials.session.commit()
                except Exception as exc:
                    self.materials.session.rollback()
                    self.materials.storage.delete(key)
                    if isinstance(exc, IntegrityError):
                        raise ApplicationError(409, "MATERIAL_DUPLICATE", "PDF này đã có trong kho học liệu.") from exc
                    raise
            job.update(status="SUBMITTED", material_id=str(material.id), title=material.title)
            write_json(directory / "review.draft.json", data.model_dump())
            write_json(directory / "job.json", job)
        return self.materials.get(user_id, material.id)

    def source(self, user_id: UUID, job_id: UUID) -> Path:
        directory, job = self._job(user_id, job_id)
        return directory / (job.get("source_image_name") or "source.pdf")

    def asset(self, user_id: UUID, job_id: UUID, index: int) -> Path:
        directory, _ = self._job(user_id, job_id)
        return self._asset_path(directory, index)

    def material_asset(self, user_id: UUID, material_id: UUID, index: int) -> Path:
        material = self.materials.get(user_id, material_id)
        item = next((i for i in material.items if index in i.raw_metadata.get("visual_assets", [])), None)
        if item is None or not item.raw_metadata.get("pdf_import_id"):
            raise ApplicationError(404, "PDF_ASSET_NOT_FOUND", "Không tìm thấy hình minh họa đã duyệt.")
        return self._asset_path(self._directory(UUID(item.raw_metadata["pdf_import_id"])), index)

    def item_visuals(self, item: TeacherMaterialItem, base_url: str, content: str,
                     *, include_references: bool = False) -> list[QuestionVisualRead]:
        """Recover legacy imports on read; the assigned question text stays immutable."""
        metadata = item.raw_metadata or {}
        if not metadata.get("pdf_import_id") or not metadata.get("visual_assets"):
            return []
        try:
            job_id = UUID(metadata["pdf_import_id"])
        except (ValueError, TypeError):
            return []
        if job_id not in self._visual_questions:
            self._visual_questions[job_id] = self._questions(self._directory(job_id))[0]
        questions = self._visual_questions[job_id]
        source = next((q for q in questions if q.question_id == metadata.get("source_question_id")), None)
        if source is None:
            candidates = [q for q in questions if q.visual_assets == metadata["visual_assets"]]
            source = candidates[0] if len(candidates) == 1 else None
        if source is None:
            return []
        referenced = markdown_image_paths(content)
        seen: set[int] = set()
        result = []
        for visual in source.visuals:
            if visual.index not in metadata["visual_assets"] or visual.index in seen:
                continue
            if not include_references and visual.role != "question" and visual.path not in referenced:
                continue
            seen.add(visual.index)
            result.append(visual.model_copy(update={"url": f"{base_url}/{visual.index}"}))
        return result

    def assigned_asset(self, item: TeacherMaterialItem, index: int, content: str,
                       *, include_references: bool = False) -> Path:
        """The caller must authorize the assigned item before resolving its image."""
        allowed = self.item_visuals(item, "", content, include_references=include_references)
        if not any(visual.index == index for visual in allowed):
            raise ApplicationError(404, "PDF_ASSET_NOT_FOUND", "Không tìm thấy hình minh họa của câu này.")
        return self._asset_path(self._directory(UUID(item.raw_metadata["pdf_import_id"])), index)

    def _asset_path(self, directory: Path, index: int, *, assets: list[str] | None = None) -> Path:
        if assets is None:
            assets = self._questions(directory)[1]
        if index < 0 or index >= len(assets):
            raise ApplicationError(404, "PDF_ASSET_NOT_FOUND", "Không tìm thấy ảnh nguồn.")
        output = self._ocr_directory(directory).resolve()
        path = (output / assets[index]).resolve()
        if not path.is_relative_to(output) or path.suffix.lower() not in {".png", ".jpg", ".jpeg"} or not path.is_file():
            raise ApplicationError(404, "PDF_ASSET_NOT_FOUND", "Không tìm thấy ảnh nguồn.")
        return path
