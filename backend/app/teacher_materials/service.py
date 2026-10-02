from hashlib import sha256
from pathlib import Path
from uuid import UUID
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload
from app.classes.models import TeacherClassroom
from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, LearningOutcome, ProblemType, Topic
from app.planning.models import TeachingPlan
from app.practice.evaluation import AnswerEvaluationService
from app.questions.models import QuestionType
from app.subjects.models import Subject
from app.teachers.models import TeacherProfile
from app.teacher_materials.extraction import TeacherMaterialExtractor
from app.teacher_materials.models import MaterialEvaluationMode, MaterialItemExtractionStatus, MaterialMappingSource, MaterialMappingStatus, TeacherMaterial, TeacherMaterialItem, TeacherMaterialItemConcept, TeacherMaterialItemLearningOutcome, TeacherMaterialItemOption, TeacherMaterialItemProblemType, TeacherMaterialStatus
from app.teacher_materials.schemas import MappingCreate, TeacherMaterialItemUpdate
from app.teacher_materials.storage import TeacherMaterialStorage

ALLOWED_MIME = {"application/pdf": ".pdf", "text/plain": ".txt"}
EXECUTABLE_SUFFIXES = {".exe", ".com", ".bat", ".cmd", ".ps1", ".js", ".msi", ".scr"}

class TeacherMaterialService:
    def __init__(self, session: Session, storage: TeacherMaterialStorage, max_bytes: int, extractor: TeacherMaterialExtractor | None = None) -> None:
        self.session, self.storage, self.max_bytes = session, storage, max_bytes
        self.extractor = extractor or TeacherMaterialExtractor()

    def upload(self, user_id: UUID, classroom_id: UUID, subject_id: UUID, title: str, file_name: str, mime_type: str, data: bytes, teaching_plan_id: UUID | None = None) -> TeacherMaterial:
        self._authorize(user_id, classroom_id)
        if not data: raise ApplicationError(422, "EMPTY_MATERIAL", "Uploaded material is empty.")
        if len(data) > self.max_bytes: raise ApplicationError(413, "MATERIAL_TOO_LARGE", "Uploaded material exceeds configured size limit.")
        if mime_type not in ALLOWED_MIME: raise ApplicationError(415, "UNSUPPORTED_MATERIAL_TYPE", "Only PDF and plain text are supported.")
        clean_name = Path(file_name).name
        if clean_name != file_name or Path(clean_name).suffix.casefold() in EXECUTABLE_SUFFIXES: raise ApplicationError(422, "UNSAFE_FILE_NAME", "Unsafe material filename.")
        if self.session.get(Subject, subject_id) is None: raise ApplicationError(404, "SUBJECT_NOT_FOUND", "Subject was not found.")
        if teaching_plan_id:
            plan = self.session.get(TeachingPlan, teaching_plan_id)
            if plan is None or plan.classroom_id != classroom_id or plan.subject_id != subject_id: raise ApplicationError(422, "TEACHING_PLAN_SCOPE_MISMATCH", "Teaching plan must match classroom and subject.")
        digest = sha256(data).hexdigest()
        if self.session.scalar(select(TeacherMaterial).where(TeacherMaterial.classroom_id == classroom_id, TeacherMaterial.sha256 == digest)):
            raise ApplicationError(409, "MATERIAL_DUPLICATE", "This file already exists in the classroom.")
        key = f"{classroom_id}/{digest}{ALLOWED_MIME[mime_type]}"
        material = TeacherMaterial(classroom_id=classroom_id, subject_id=subject_id, teaching_plan_id=teaching_plan_id, uploaded_by=user_id, title=title.strip(), original_file_name=clean_name, mime_type=mime_type, storage_key=key, sha256=digest, file_size_bytes=len(data), status=TeacherMaterialStatus.UPLOADED)
        try:
            self.storage.save(key, data); self.session.add(material); self.session.flush()
            result = self.extractor.extract(data, mime_type); material.page_count = result.page_count
            if result.text_empty:
                material.status = TeacherMaterialStatus.NEEDS_REVIEW; material.parse_error = "No extractable text; OCR is not enabled."
            else:
                material.status = TeacherMaterialStatus.PARSED if all(x.confident for x in result.items) else TeacherMaterialStatus.NEEDS_REVIEW
                for x in result.items:
                    self.session.add(TeacherMaterialItem(teacher_material_id=material.id, order_index=x.order_index, page_start=x.page_start, page_end=x.page_end, content=x.content, content_hash=x.content_hash, extraction_status=MaterialItemExtractionStatus.EXTRACTED if x.confident else MaterialItemExtractionStatus.NEEDS_REVIEW, evaluation_mode=MaterialEvaluationMode.TEACHER_REVIEW, raw_metadata={"segmentation_confident": x.confident, "content_reviewed": False}))
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback(); self.storage.delete(key); raise ApplicationError(409, "MATERIAL_DUPLICATE", "This file already exists in the classroom.") from exc
        except Exception:
            self.session.rollback(); self.storage.delete(key); raise
        return self.get(user_id, material.id)

    def get(self, user_id: UUID, material_id: UUID) -> TeacherMaterial:
        row = self.session.scalar(select(TeacherMaterial).execution_options(populate_existing=True).options(
            selectinload(TeacherMaterial.items).selectinload(TeacherMaterialItem.options),
            selectinload(TeacherMaterial.items).selectinload(TeacherMaterialItem.problem_type_mappings),
            selectinload(TeacherMaterial.items).selectinload(TeacherMaterialItem.concept_mappings),
            selectinload(TeacherMaterial.items).selectinload(TeacherMaterialItem.learning_outcome_mappings),
        ).where(TeacherMaterial.id == material_id))
        if row is None: raise ApplicationError(404, "MATERIAL_NOT_FOUND", "Teacher material was not found.")
        self._authorize(user_id, row.classroom_id); return row

    def list(self, user_id: UUID, classroom_id: UUID) -> list[TeacherMaterial]:
        self._authorize(user_id, classroom_id); return list(self.session.scalars(select(TeacherMaterial).where(TeacherMaterial.classroom_id == classroom_id).order_by(TeacherMaterial.created_at.desc())))

    def update_item(
        self,
        user_id: UUID,
        item_id: UUID,
        data: TeacherMaterialItemUpdate,
    ) -> TeacherMaterialItem:
        item = self._item(user_id, item_id)
        was_ready = item.extraction_status == MaterialItemExtractionStatus.READY
        changes = data.model_dump(exclude_unset=True)
        semantic_fields = {
            "content", "question_type", "correct_answer", "difficulty",
            "evaluation_mode", "options",
        }
        semantic_change = any(
            field in changes and changes[field] != getattr(item, field, None)
            for field in semantic_fields - {"options"}
        ) or ("options" in changes and data.options is not None)
        content_changed = data.content is not None and data.content != item.content

        if data.archive:
            item.extraction_status = MaterialItemExtractionStatus.ARCHIVED
        if content_changed:
            item.content = data.content
            item.content_hash = sha256(data.content.encode("utf-8")).hexdigest()
            # Old taxonomy may no longer describe the rewritten question.
            for mapping in (
                *item.problem_type_mappings,
                *item.concept_mappings,
                *item.learning_outcome_mappings,
            ):
                if mapping.status == MaterialMappingStatus.CONFIRMED:
                    mapping.status = MaterialMappingStatus.SUGGESTED
        for field in (
            "question_type", "correct_answer", "explanation",
            "difficulty", "evaluation_mode",
        ):
            if field in changes:
                setattr(item, field, getattr(data, field))
        if data.options is not None:
            item.options.clear()
            self.session.flush()
            item.options.extend(
                TeacherMaterialItemOption(
                    label=option.label,
                    content=option.content,
                    order_index=option.order_index,
                )
                for option in data.options
            )
        if semantic_change and was_ready:
            item.raw_metadata = {**item.raw_metadata, "content_reviewed": False}
            item.extraction_status = MaterialItemExtractionStatus.NEEDS_REVIEW
            item.material.status = TeacherMaterialStatus.NEEDS_REVIEW
        elif data.content_reviewed is not None:
            item.raw_metadata = {
                **item.raw_metadata,
                "content_reviewed": data.content_reviewed,
            }
            item.extraction_status = MaterialItemExtractionStatus.EXTRACTED
            item.material.status = TeacherMaterialStatus.MAPPING_PENDING
        if data.archive:
            item.extraction_status = MaterialItemExtractionStatus.ARCHIVED
            item.material.status = TeacherMaterialStatus.NEEDS_REVIEW
        self.session.commit()
        return self._item(user_id, item_id)

    def add_mapping(
        self, user_id: UUID, item_id: UUID, kind: str, data: MappingCreate
    ) -> TeacherMaterialItemProblemType | TeacherMaterialItemConcept | TeacherMaterialItemLearningOutcome:
        item = self._item(user_id, item_id)
        model, target_model, target_field = self._mapping_spec(kind)
        target = self.session.get(target_model, data.target_id)
        if target is None:
            raise ApplicationError(
                404, "MAPPING_TARGET_NOT_FOUND", "Canonical mapping target was not found."
            )
        if kind == "problem-types":
            subject_id = self.session.scalar(
                select(Chapter.subject_id)
                .join(Topic, Topic.chapter_id == Chapter.id)
                .join(ProblemType, ProblemType.topic_id == Topic.id)
                .where(ProblemType.id == target.id)
            )
        else:
            subject_id = target.subject_id
        if subject_id != item.material.subject_id:
            raise ApplicationError(
                422, "MAPPING_SUBJECT_MISMATCH",
                "Mapping target must belong to material subject.",
            )
        row = model(
            item_id=item.id,
            **{target_field: target.id},
            weight=data.weight,
            confidence=data.confidence,
            is_primary=data.is_primary,
            source=MaterialMappingSource.TEACHER,
            status=MaterialMappingStatus.CONFIRMED,
            rationale=data.rationale,
        )
        self.session.add(row)
        self._invalidate_mapping_readiness(item)
        self.session.commit()
        return row

    def change_mapping(
        self,
        user_id: UUID,
        item_id: UUID,
        kind: str,
        target_id: UUID,
        status: MaterialMappingStatus,
    ) -> TeacherMaterialItemProblemType | TeacherMaterialItemConcept | TeacherMaterialItemLearningOutcome:
        item = self._item(user_id, item_id)
        model, _, field = self._mapping_spec(kind)
        row = self.session.scalar(
            select(model).where(
                model.item_id == item.id,
                getattr(model, field) == target_id,
            )
        )
        if row is None:
            raise ApplicationError(404, "MAPPING_NOT_FOUND", "Material mapping was not found.")
        row.status = status
        if status == MaterialMappingStatus.CONFIRMED:
            row.source = MaterialMappingSource.TEACHER
        self._invalidate_mapping_readiness(item)
        self.session.commit()
        return row

    def set_primary_problem_type(
        self, user_id: UUID, item_id: UUID, target_id: UUID
    ) -> TeacherMaterialItemProblemType:
        item = self._item(user_id, item_id)
        mappings = list(
            self.session.scalars(
                select(TeacherMaterialItemProblemType).where(
                    TeacherMaterialItemProblemType.item_id == item.id
                )
            )
        )
        target = next(
            (
                mapping
                for mapping in mappings
                if mapping.problem_type_id == target_id
                and mapping.status == MaterialMappingStatus.CONFIRMED
            ),
            None,
        )
        if target is None:
            raise ApplicationError(
                422, "CONFIRMED_MAPPING_REQUIRED",
                "Only a confirmed ProblemType mapping can be primary.",
            )
        for mapping in mappings:
            mapping.is_primary = mapping.id == target.id
        self._invalidate_mapping_readiness(item)
        self.session.commit()
        return target

    @staticmethod
    def _invalidate_mapping_readiness(item: TeacherMaterialItem) -> None:
        item.extraction_status = MaterialItemExtractionStatus.NEEDS_REVIEW
        item.material.status = TeacherMaterialStatus.MAPPING_PENDING

    def mark_ready(self, user_id: UUID, material_id: UUID) -> TeacherMaterial:
        material = self.get(user_id, material_id)
        eligible = [
            item
            for item in material.items
            if item.extraction_status != MaterialItemExtractionStatus.ARCHIVED
        ]
        if not eligible:
            raise ApplicationError(
                422, "NO_ELIGIBLE_ITEMS", "Material has no assignment-eligible items."
            )
        for item in eligible:
            if not item.raw_metadata.get("content_reviewed"):
                raise ApplicationError(
                    422, "ITEM_CONTENT_NOT_REVIEWED", "Every item content must be reviewed."
                )
            if not any(
                mapping.status == MaterialMappingStatus.CONFIRMED
                for mapping in item.problem_type_mappings
            ) or not any(
                mapping.status == MaterialMappingStatus.CONFIRMED
                for mapping in item.concept_mappings
            ):
                raise ApplicationError(
                    422, "CONFIRMED_MAPPINGS_REQUIRED",
                    "Every item requires confirmed ProblemType and Concept mappings.",
                )
            if item.evaluation_mode == MaterialEvaluationMode.OBJECTIVE_AUTO:
                if item.question_type not in {
                    QuestionType.MULTIPLE_CHOICE,
                    QuestionType.TRUE_FALSE,
                    QuestionType.SHORT_ANSWER,
                } or not item.correct_answer:
                    raise ApplicationError(
                        422, "INVALID_OBJECTIVE_CONFIGURATION",
                        "Objective items require supported type and correct answer.",
                    )
                if item.question_type == QuestionType.MULTIPLE_CHOICE and not item.options:
                    raise ApplicationError(
                        422, "MCQ_OPTIONS_REQUIRED", "Multiple-choice items require options."
                    )
                expected = AnswerEvaluationService.normalize(item.correct_answer)
                if not expected:
                    raise ApplicationError(
                        422, "INVALID_OBJECTIVE_CONFIGURATION",
                        "Objective answer cannot be blank.",
                    )
                if item.question_type == QuestionType.MULTIPLE_CHOICE:
                    labels = {
                        AnswerEvaluationService.normalize(option.label)
                        for option in item.options
                    }
                    if expected not in labels:
                        raise ApplicationError(
                            422, "INVALID_OBJECTIVE_CONFIGURATION",
                            "Multiple-choice answer must match an option label.",
                        )
                if item.question_type == QuestionType.TRUE_FALSE and expected not in {
                    "true", "false"
                }:
                    raise ApplicationError(
                        422, "INVALID_OBJECTIVE_CONFIGURATION",
                        "True/false answer must be TRUE or FALSE.",
                    )
            item.extraction_status = MaterialItemExtractionStatus.READY
        material.status = TeacherMaterialStatus.READY
        self.session.commit()
        return self.get(user_id, material_id)

    def _item(self,user_id:UUID,item_id:UUID)->TeacherMaterialItem:
        row = self.session.scalar(
            select(TeacherMaterialItem)
            .execution_options(populate_existing=True)
            .options(
                selectinload(TeacherMaterialItem.material),
                selectinload(TeacherMaterialItem.options),
                selectinload(TeacherMaterialItem.problem_type_mappings),
                selectinload(TeacherMaterialItem.concept_mappings),
                selectinload(TeacherMaterialItem.learning_outcome_mappings),
            )
            .where(TeacherMaterialItem.id == item_id)
        )
        if row is None: raise ApplicationError(404,"MATERIAL_ITEM_NOT_FOUND","Material item was not found.")
        self._authorize(user_id,row.material.classroom_id); return row

    @staticmethod
    def _mapping_spec(kind:str):
        specs={"problem-types":(TeacherMaterialItemProblemType,ProblemType,"problem_type_id"),"concepts":(TeacherMaterialItemConcept,Concept,"concept_id"),"learning-outcomes":(TeacherMaterialItemLearningOutcome,LearningOutcome,"learning_outcome_id")}
        if kind not in specs: raise ApplicationError(404,"MAPPING_KIND_NOT_FOUND","Unknown taxonomy mapping kind.")
        return specs[kind]

    def _authorize(self,user_id:UUID,classroom_id:UUID)->TeacherProfile:
        teacher=self.session.scalar(select(TeacherProfile).where(TeacherProfile.user_id==user_id))
        if teacher is None: raise ApplicationError(404,"PROFILE_NOT_FOUND","Teacher profile was not found.")
        if self.session.get(TeacherClassroom,(teacher.id,classroom_id)) is None: raise ApplicationError(403,"CLASSROOM_ACCESS_DENIED","Teacher is not assigned to this classroom.")
        return teacher
