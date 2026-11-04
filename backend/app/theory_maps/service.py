"""PDF text -> cited draft -> explicit teacher review -> class publication."""
from datetime import datetime, timezone
from hashlib import sha256
import logging
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.classes.models import EnrollmentStatus, StudentEnrollment, TeacherClassroom
from app.core.exceptions import ApplicationError
from app.students.models import StudentProfile
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.teacher_materials.storage import TeacherMaterialStorage
from app.theory_maps.models import TheoryDocument, TheoryMapStatus
from app.theory_maps.local_draft import build_local_draft, needs_reviewed_body, prefill_source_steps
from app.theory_maps.ai_generator import generate_ai_mindmap
from app.theory_maps.pdf_extraction import extract_page_texts, read_pdf_pages
from app.theory_maps.schemas import TheoryMapWrite, TheoryNode

logger = logging.getLogger(__name__)


def _normal(text: str) -> str:
    return " ".join(text.split()).casefold()


def validate_nodes(nodes: list[TheoryNode], page_texts: list[str], *, require_reviewed: bool = False) -> None:
    ids = [node.id for node in nodes]
    if len(set(ids)) != len(ids):
        raise ApplicationError(422, "DUPLICATE_NODE_ID", "Mind-map node IDs must be unique.")
    by_id = {node.id: node for node in nodes}
    parent_ids = {node.parent_id for node in nodes if node.parent_id is not None}
    roots = [node for node in nodes if node.parent_id is None]
    if len(roots) != 1 or roots[0].kind != "ROOT":
        raise ApplicationError(422, "INVALID_MAP_ROOT", "Exactly one ROOT node is required.")
    for node in nodes:
        if not node.title.strip() or not node.source_quote.strip():
            raise ApplicationError(422, "EMPTY_MAP_CONTENT", "Node title and exact source quote are required.")
        if node.parent_id is not None and node.parent_id not in by_id:
            raise ApplicationError(422, "INVALID_MAP_PARENT", "A node references a missing parent.")
        if node.parent_id is not None and node.kind == "ROOT":
            raise ApplicationError(422, "INVALID_MAP_ROOT", "ROOT cannot be a child.")
        if node.source_page > len(page_texts) or _normal(node.source_quote) not in _normal(page_texts[node.source_page - 1]):
            raise ApplicationError(422, "SOURCE_QUOTE_MISMATCH", "A node citation does not match its PDF page.")
        if node.kind == "FORMULA" and not (node.latex or "").strip():
            raise ApplicationError(422, "FORMULA_REQUIRED", "Formula nodes need a LaTeX expression.")
        for step in node.learning_steps:
            if not step.instruction.strip():
                raise ApplicationError(422, "EMPTY_LEARNING_STEP", "Learning steps need an instruction.")
            if step.source_page is not None and step.source_page > len(page_texts):
                raise ApplicationError(422, "INVALID_STEP_SOURCE_PAGE", "A learning step references a missing PDF page.")
            if step.source_quote is not None and (
                step.source_page is None or _normal(step.source_quote) not in _normal(page_texts[step.source_page - 1])
            ):
                raise ApplicationError(422, "STEP_SOURCE_QUOTE_MISMATCH", "A step citation does not match its PDF page.")
        formulas = [node.latex or "", *(step.latex or "" for step in node.learning_steps)]
        if require_reviewed and (any("□" in formula for formula in formulas)
                                 or any("□" in step.instruction for step in node.learning_steps)):
            raise ApplicationError(409, "INCOMPLETE_FORMULA", "Replace all formula placeholders before publication.")
        if require_reviewed and not node.reviewed:
            raise ApplicationError(409, "MAP_NOT_REVIEWED", "Review every node before publication.")
        if require_reviewed and needs_reviewed_body(node.title) and not node.body.strip():
            raise ApplicationError(409, "THEORY_CONTENT_REQUIRED",
                                   "Definitions and theorems need reviewed content before publication.")
        if require_reviewed and node.title.casefold().startswith("dạng "):
            has_steps = bool(node.learning_steps) or any(
                bool(child.learning_steps) for child in nodes if child.parent_id == node.id
            )
            if not has_steps:
                raise ApplicationError(409, "LEARNING_STEPS_REQUIRED",
                                       "Exercise types need reviewed steps before publication.")
        if require_reviewed and node.kind != "ROOT" and node.id not in parent_ids and not (
            node.body.strip() or (node.latex or "").strip() or node.learning_steps
        ):
            raise ApplicationError(409, "LEARNING_CONTENT_REQUIRED",
                                   "Every final branch needs reviewed learning content before publication.")
        seen = {node.id}
        current = node
        while current.parent_id is not None:
            if current.parent_id in seen:
                raise ApplicationError(422, "MAP_CYCLE", "Mind-map hierarchy contains a cycle.")
            seen.add(current.parent_id)
            current = by_id[current.parent_id]
        if current.id != roots[0].id:
            raise ApplicationError(422, "DISCONNECTED_MAP", "Every node must descend from the root.")


class TheoryMapService:
    def __init__(self, session: Session, storage: TeacherMaterialStorage, max_bytes: int) -> None:
        self.session = session
        self.storage = storage
        self.max_bytes = max_bytes

    def _teacher(self, user_id: UUID, classroom_id: UUID) -> None:
        profile = self.session.scalar(select(TeacherProfile).where(TeacherProfile.user_id == user_id))
        if profile is None or self.session.get(TeacherClassroom, (profile.id, classroom_id)) is None:
            raise ApplicationError(403, "CLASSROOM_ACCESS_DENIED", "Teacher is not assigned to this classroom.")

    def _student(self, user_id: UUID, classroom_id: UUID) -> None:
        profile = self.session.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))
        if profile is None:
            raise ApplicationError(403, "CLASSROOM_ACCESS_DENIED", "Student has no classroom profile.")
        enrollment = self.session.get(StudentEnrollment, (profile.id, classroom_id))
        if enrollment is None or enrollment.status != EnrollmentStatus.ACTIVE:
            raise ApplicationError(403, "CLASSROOM_ACCESS_DENIED", "Student is not enrolled in this classroom.")

    def upload(self, user_id: UUID, classroom_id: UUID, subject_id: UUID, title: str,
               file_name: str, content: bytes) -> TheoryDocument:
        self._teacher(user_id, classroom_id)
        if self.session.get(Subject, subject_id) is None:
            raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        if not title.strip() or len(title.strip()) > 255:
            raise ApplicationError(422, "INVALID_TITLE", "A title of at most 255 characters is required.")
        if Path(file_name).name != file_name or not file_name.lower().endswith(".pdf") or len(file_name) > 255:
            raise ApplicationError(422, "INVALID_FILENAME", "A plain PDF filename is required.")
        if not content.startswith(b"%PDF-"):
            raise ApplicationError(415, "INVALID_PDF", "File is not a PDF.")
        if len(content) > self.max_bytes:
            raise ApplicationError(413, "PDF_TOO_LARGE", "PDF exceeds the configured upload limit.")
        # The original document is useful even when formulas or scans have no
        # reliable text layer. OCR is needed only for the optional cited map.
        page_texts = read_pdf_pages(content)
        digest = sha256(content).hexdigest()
        if self.session.scalar(select(TheoryDocument).where(TheoryDocument.classroom_id == classroom_id, TheoryDocument.sha256 == digest)):
            raise ApplicationError(409, "THEORY_DUPLICATE", "This PDF is already in the classroom.")
        key = f"theory/{classroom_id}/{uuid4()}.pdf"
        row = TheoryDocument(
            classroom_id=classroom_id, subject_id=subject_id, uploaded_by=user_id,
            title=title.strip(), file_name=file_name, storage_key=key, sha256=digest,
            page_count=len(page_texts), page_texts=page_texts, nodes=[],
            status=TheoryMapStatus.DRAFT, revision=1,
        )
        self.storage.save(key, content)
        try:
            self.session.add(row)
            self.session.commit()
            self.session.refresh(row)
        except IntegrityError as exc:
            self.session.rollback()
            self.storage.delete(key)
            raise ApplicationError(409, "THEORY_DUPLICATE", "This PDF is already in the classroom.") from exc
        except Exception:
            self.session.rollback()
            self.storage.delete(key)
            raise
        return row

    def teacher_list(self, user_id: UUID, classroom_id: UUID) -> list[TheoryDocument]:
        self._teacher(user_id, classroom_id)
        return list(self.session.scalars(select(TheoryDocument).where(TheoryDocument.classroom_id == classroom_id).order_by(TheoryDocument.created_at.desc(), TheoryDocument.id.desc())))

    def teacher_get(self, user_id: UUID, document_id: UUID) -> TheoryDocument:
        row = self.session.get(TheoryDocument, document_id)
        if row is None:
            raise ApplicationError(404, "THEORY_NOT_FOUND", "Theory document was not found.")
        self._teacher(user_id, row.classroom_id)
        return row

    def student_list(self, user_id: UUID) -> list[TheoryDocument]:
        profile = self.session.scalar(select(StudentProfile).where(StudentProfile.user_id == user_id))
        if profile is None:
            return []
        return list(self.session.scalars(
            select(TheoryDocument).join(StudentEnrollment, TheoryDocument.classroom_id == StudentEnrollment.classroom_id)
            .where(StudentEnrollment.student_id == profile.id, StudentEnrollment.status == EnrollmentStatus.ACTIVE,
                   or_(TheoryDocument.status == TheoryMapStatus.PUBLISHED,
                       TheoryDocument.source_published_at.is_not(None)))
            .order_by(TheoryDocument.created_at.desc(), TheoryDocument.id.desc())
        ))

    def student_get(self, user_id: UUID, document_id: UUID) -> TheoryDocument:
        row = self.session.get(TheoryDocument, document_id)
        if row is None or (row.status != TheoryMapStatus.PUBLISHED and not row.source_available):
            raise ApplicationError(404, "THEORY_NOT_FOUND", "Published theory document was not found.")
        self._student(user_id, row.classroom_id)
        return row

    def student_source(self, user_id: UUID, document_id: UUID) -> TheoryDocument:
        row = self.student_get(user_id, document_id)
        if not row.source_available:
            raise ApplicationError(404, "THEORY_SOURCE_NOT_SHARED", "Original PDF is not shared with this class.")
        return row

    def set_source_visibility(self, user_id: UUID, document_id: UUID, expected_revision: int,
                              *, visible: bool) -> TheoryDocument:
        row = self.teacher_get(user_id, document_id)
        if expected_revision != row.revision:
            raise ApplicationError(409, "REVISION_CONFLICT", "The document changed; reload before sharing.")
        if row.source_available == visible:
            return row
        if visible:
            try:
                content = self.storage.read(row.storage_key)
            except OSError as exc:
                raise ApplicationError(503, "SOURCE_UNAVAILABLE", "Original PDF is unavailable.") from exc
            if sha256(content).hexdigest() != row.sha256:
                raise ApplicationError(503, "SOURCE_HASH_MISMATCH", "Original PDF failed integrity check.")
        row.source_published_at = datetime.now(timezone.utc) if visible else None
        row.revision += 1
        self.session.commit()
        self.session.refresh(row)
        return row

    def save(self, user_id: UUID, document_id: UUID, data: TheoryMapWrite) -> TheoryDocument:
        row = self.teacher_get(user_id, document_id)
        if data.expected_revision != row.revision:
            raise ApplicationError(409, "REVISION_CONFLICT", "The map changed; reload before saving.")
        validate_nodes(data.nodes, row.page_texts)
        row.nodes = [node.model_dump(mode="json") for node in data.nodes]
        row.status = TheoryMapStatus.DRAFT
        row.published_at = None
        row.revision += 1
        self.session.commit()
        self.session.refresh(row)
        return row

    def publish(self, user_id: UUID, document_id: UUID, expected_revision: int) -> TheoryDocument:
        row = self.teacher_get(user_id, document_id)
        if expected_revision != row.revision:
            raise ApplicationError(409, "REVISION_CONFLICT", "The map changed; reload before publishing.")
        nodes = [TheoryNode.model_validate(node) for node in row.nodes]
        if not nodes:
            raise ApplicationError(409, "EMPTY_MAP", "Create and review a map before publication.")
        validate_nodes(nodes, row.page_texts, require_reviewed=True)
        row.status = TheoryMapStatus.PUBLISHED
        row.published_at = datetime.now(timezone.utc)
        row.revision += 1
        self.session.commit()
        self.session.refresh(row)
        return row

    def unpublish(self, user_id: UUID, document_id: UUID, expected_revision: int) -> TheoryDocument:
        row = self.teacher_get(user_id, document_id)
        if expected_revision != row.revision:
            raise ApplicationError(409, "REVISION_CONFLICT", "The map changed; reload before unpublishing.")
        row.status = TheoryMapStatus.DRAFT
        row.published_at = None
        row.revision += 1
        self.session.commit()
        self.session.refresh(row)
        return row

    def delete(self, user_id: UUID, document_id: UUID) -> None:
        row = self.teacher_get(user_id, document_id)
        try:
            self.storage.delete(row.storage_key)
        except OSError:
            pass
        self.session.delete(row)
        self.session.commit()

    def generate(self, user_id: UUID, document_id: UUID) -> TheoryDocument:
        row = self.teacher_get(user_id, document_id)
        if row.status == TheoryMapStatus.PUBLISHED:
            raise ApplicationError(409, "MAP_PUBLISHED", "Published maps cannot be regenerated; save a draft first.")
        if row.nodes:
            raise ApplicationError(409, "MAP_ALREADY_HAS_NODES", "Save or remove the existing draft before generating a new one.")
        content = None
        try:
            content = self.storage.read(row.storage_key)
        except OSError:
            pass
        if any(not page for page in row.page_texts):
            if not content:
                raise ApplicationError(503, "SOURCE_UNAVAILABLE", "Original PDF is unavailable.")
            if sha256(content).hexdigest() != row.sha256:
                raise ApplicationError(503, "SOURCE_HASH_MISMATCH", "Original PDF failed integrity check.")
            row.page_texts = extract_page_texts(content)
        nodes = build_local_draft(row.title, row.page_texts, content=content)
        validate_nodes(nodes, row.page_texts)
        row.nodes = [node.model_dump(mode="json") for node in nodes]
        row.ai_model = None
        row.revision += 1
        self.session.commit()
        self.session.refresh(row)
        return row

    async def generate_ai(self, user_id: UUID, document_id: UUID, gateway: Any = None) -> TheoryDocument:
        row = self.teacher_get(user_id, document_id)
        if row.status == TheoryMapStatus.PUBLISHED:
            raise ApplicationError(409, "MAP_PUBLISHED", "Published maps cannot be regenerated; save a draft first.")
        if row.nodes:
            raise ApplicationError(409, "MAP_ALREADY_HAS_NODES", "Save or remove the existing draft before generating a new one.")
        content = None
        try:
            content = self.storage.read(row.storage_key)
        except OSError:
            pass
        if any(not page for page in row.page_texts):
            if not content:
                raise ApplicationError(503, "SOURCE_UNAVAILABLE", "Original PDF is unavailable.")
            if sha256(content).hexdigest() != row.sha256:
                raise ApplicationError(503, "SOURCE_HASH_MISMATCH", "Original PDF failed integrity check.")
            row.page_texts = extract_page_texts(content)

        nodes = None
        # 1. Build authoritative Unified AST: 100% page coverage, true document taxonomy
        from app.theory_maps.unified_ast import build_unified_ast, export_mindmap_nodes
        try:
            ast = build_unified_ast(row.title, row.page_texts, content=content)
            nodes = export_mindmap_nodes(ast, row.page_texts)
        except Exception as exc:
            logger.warning("Unified AST generation failed, falling back to local draft: %s", exc)
            nodes = None

        # 2. If AI gateway is available, enrich the verified AST nodes
        if gateway and nodes:
            try:
                from app.theory_maps.pedagogical_enricher import enrich_mindmap_with_ai
                nodes = await enrich_mindmap_with_ai(nodes, row.title, row.page_texts, gateway, user_id=user_id)
                row.ai_model = "gemini_enriched"
            except Exception as exc:
                logger.warning("AI pedagogical enrichment failed, keeping AST draft: %s", exc)
                row.ai_model = "unified_ast"
        elif nodes:
            row.ai_model = "unified_ast"
        else:
            nodes = build_local_draft(row.title, row.page_texts, content=content)
            row.ai_model = "local_heuristic"

        validate_nodes(nodes, row.page_texts)
        row.nodes = [node.model_dump(mode="json") for node in nodes]
        row.revision += 1
        self.session.commit()
        self.session.refresh(row)
        return row

    def regenerate(self, user_id: UUID, document_id: UUID, expected_revision: int) -> TheoryDocument:
        row = self.teacher_get(user_id, document_id)
        if expected_revision != row.revision:
            raise ApplicationError(409, "REVISION_CONFLICT", "The map changed; reload before regenerating.")
        if row.status == TheoryMapStatus.PUBLISHED or any(node.get("reviewed") for node in row.nodes):
            raise ApplicationError(409, "MAP_REVIEWED", "Published or reviewed maps cannot be replaced automatically.")
        content = None
        try:
            content = self.storage.read(row.storage_key)
        except OSError:
            pass
        nodes = build_local_draft(row.title, row.page_texts, content=content)
        old_nodes = [TheoryNode.model_validate(node) for node in row.nodes]
        # Older generated drafts have no learning steps. A new draft may have
        # source-cited steps, but any teacher change must survive regeneration.
        if len(old_nodes) != len(nodes) or any(
            (old.id, old.parent_id, old.kind, old.title, old.source_page, old.source_quote)
            != (new.id, new.parent_id, new.kind, new.title, new.source_page, new.source_quote)
            or old.body or old.latex
            or (old.learning_steps and old.learning_steps != new.learning_steps)
            for old, new in zip(old_nodes, nodes)
        ):
            raise ApplicationError(409, "MAP_EDITED", "This draft contains edits; use source prefill to preserve them.")
        validate_nodes(nodes, row.page_texts)
        row.nodes = [node.model_dump(mode="json") for node in nodes]
        row.ai_model = None
        row.revision += 1
        self.session.commit()
        self.session.refresh(row)
        return row

    async def regenerate_ai(self, user_id: UUID, document_id: UUID, expected_revision: int, gateway: Any = None) -> TheoryDocument:
        row = self.teacher_get(user_id, document_id)
        if expected_revision != row.revision:
            raise ApplicationError(409, "REVISION_CONFLICT", "The map changed; reload before regenerating.")
        if row.status == TheoryMapStatus.PUBLISHED:
            raise ApplicationError(409, "MAP_PUBLISHED", "Published maps cannot be replaced; unpublish first.")

        content = None
        try:
            content = self.storage.read(row.storage_key)
        except OSError:
            pass

        nodes = None
        # 1. Build authoritative Unified AST: 100% page coverage, true document taxonomy
        from app.theory_maps.unified_ast import build_unified_ast, export_mindmap_nodes
        try:
            ast = build_unified_ast(row.title, row.page_texts, content=content)
            nodes = export_mindmap_nodes(ast, row.page_texts)
        except Exception as exc:
            logger.warning("Unified AST regeneration failed, falling back to local draft: %s", exc)
            nodes = None

        # 2. If AI gateway is available, enrich the verified AST nodes
        if gateway and nodes:
            try:
                from app.theory_maps.pedagogical_enricher import enrich_mindmap_with_ai
                nodes = await enrich_mindmap_with_ai(nodes, row.title, row.page_texts, gateway, user_id=user_id)
                row.ai_model = "gemini_enriched"
            except Exception as exc:
                logger.warning("AI pedagogical enrichment failed, keeping AST draft: %s", exc)
                row.ai_model = "unified_ast"
        elif nodes:
            row.ai_model = "unified_ast"
        else:
            nodes = build_local_draft(row.title, row.page_texts, content=content)
            row.ai_model = "local_heuristic"

        validate_nodes(nodes, row.page_texts)
        row.nodes = [node.model_dump(mode="json") for node in nodes]
        row.revision += 1
        self.session.commit()
        self.session.refresh(row)
        return row

    def prefill(self, user_id: UUID, document_id: UUID, expected_revision: int) -> TheoryDocument:
        """Enrich an existing draft without replacing teacher-authored nodes or edits."""
        row = self.teacher_get(user_id, document_id)
        if expected_revision != row.revision:
            raise ApplicationError(409, "REVISION_CONFLICT", "The map changed; reload before prefill.")
        if row.status == TheoryMapStatus.PUBLISHED:
            raise ApplicationError(409, "MAP_PUBLISHED", "Save a draft before adding source steps.")
        if not row.nodes:
            raise ApplicationError(409, "EMPTY_MAP", "Generate a draft before adding source steps.")
        nodes = [TheoryNode.model_validate(node) for node in row.nodes]
        before = [node.model_dump(mode="json") for node in nodes]
        prefill_source_steps(nodes, row.page_texts)
        validate_nodes(nodes, row.page_texts)
        after = [node.model_dump(mode="json") for node in nodes]
        if after != before:
            row.nodes = after
            row.revision += 1
            self.session.commit()
            self.session.refresh(row)
        return row
