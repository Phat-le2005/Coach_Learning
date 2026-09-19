from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import (
    Chapter,
    CurriculumVersion,
    LearningOutcome,
    ProblemType,
    Topic,
)
from app.questions.duplicate_detection import (
    ExactContentHashDuplicateDetector,
    QuestionDuplicateDetector,
)
from app.questions.import_schemas import (
    QuestionImportBatchRead,
    QuestionImportRecord,
    QuestionImportReport,
    QuestionImportRowRead,
)
from app.questions.models import (
    ImportBatchStatus,
    ImportFileFormat,
    ImportRowStatus,
    Question,
    QuestionConcept,
    QuestionLearningOutcome,
    QuestionImportBatch,
    QuestionImportRow,
    QuestionOption,
    QuestionProblemType,
    QuestionStatus,
    QuestionType,
)
from app.subjects.models import Subject
from app.users.models import Role, User

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _ParsedRow:
    row_number: int
    raw_data: dict[str, object]
    record: QuestionImportRecord


@dataclass(frozen=True, slots=True)
class _ReferenceCatalog:
    concepts: dict[tuple[UUID, str], Concept]
    problem_types: dict[tuple[UUID, str], ProblemType]
    learning_outcomes: dict[tuple[UUID, str], LearningOutcome]


class QuestionImportService:
    MAX_FILE_BYTES = 5 * 1024 * 1024
    MAX_ROWS = 5000

    def __init__(
        self,
        session: Session,
        duplicate_detector: QuestionDuplicateDetector | None = None,
    ) -> None:
        self.session = session
        self.duplicate_detector = duplicate_detector or ExactContentHashDuplicateDetector()

    def preview(
        self,
        actor: User,
        *,
        file_name: str,
        content: bytes,
        trusted_seed_data: bool = False,
    ) -> QuestionImportBatchRead:
        if trusted_seed_data and actor.role != Role.ADMIN:
            raise ApplicationError(
                403,
                "TRUSTED_IMPORT_FORBIDDEN",
                "Only an admin can import trusted seed data.",
            )
        if not content:
            raise ApplicationError(422, "EMPTY_IMPORT_FILE", "Import file cannot be empty.")
        if len(content) > self.MAX_FILE_BYTES:
            raise ApplicationError(
                413,
                "IMPORT_FILE_TOO_LARGE",
                f"Import file cannot exceed {self.MAX_FILE_BYTES} bytes.",
            )

        safe_name = Path(file_name or "upload").name[:255]
        file_format = self._file_format(safe_name)
        raw_rows = self._parse(content, file_format)
        if not raw_rows:
            raise ApplicationError(422, "EMPTY_IMPORT_FILE", "Import file contains no question rows.")
        if len(raw_rows) > self.MAX_ROWS:
            raise ApplicationError(
                422,
                "IMPORT_ROW_LIMIT_EXCEEDED",
                f"Import file cannot contain more than {self.MAX_ROWS} rows.",
            )

        batch = QuestionImportBatch(
            created_by=actor.id,
            file_name=safe_name,
            file_format=file_format,
            trusted_seed_data=trusted_seed_data,
        )
        rows = self._validate_rows(raw_rows)
        validated_rows: list[QuestionImportRow] = []
        for row in rows:
            batch.rows.append(row)
            if row.status == ImportRowStatus.VALID:
                validated_rows.append(row)

        self._mark_duplicates(validated_rows)
        self.session.add(batch)
        self.session.commit()
        logger.info(
            "Question import preview created (batch_id=%s, actor_id=%s, rows=%s)",
            batch.id,
            actor.id,
            len(batch.rows),
        )
        return self._view(batch)

    def confirm(self, actor: User, batch_id: UUID) -> QuestionImportBatchRead:
        batch = self._batch_for_update(batch_id)
        if batch.created_by != actor.id:
            raise ApplicationError(
                403,
                "QUESTION_IMPORT_ACCESS_DENIED",
                "You do not own this import batch.",
            )
        if batch.status == ImportBatchStatus.IMPORTED:
            return self._view(batch)

        self._lock_imports()
        valid_rows = [row for row in batch.rows if row.status == ImportRowStatus.VALID]
        reference_errors = self._staged_reference_errors(valid_rows)
        for row in valid_rows:
            reference_error = reference_errors.get(row.id)
            if reference_error is not None:
                row.status = ImportRowStatus.INVALID
                row.errors = [reference_error]
        valid_rows = [row for row in valid_rows if row.status == ImportRowStatus.VALID]
        self._mark_duplicates(valid_rows)
        target_status = (
            QuestionStatus.APPROVED if batch.trusted_seed_data else QuestionStatus.DRAFT
        )
        imported = 0
        for row in valid_rows:
            if row.status != ImportRowStatus.VALID or row.normalized_data is None:
                continue
            question = self._build_question(row.normalized_data, actor.id, target_status)
            self.session.add(question)
            self.session.flush()
            row.status = ImportRowStatus.IMPORTED
            row.imported_question_id = question.id
            imported += 1

        batch.status = ImportBatchStatus.IMPORTED
        batch.confirmed_at = datetime.now(UTC)
        self.session.commit()
        logger.info(
            "Question import confirmed (batch_id=%s, actor_id=%s, imported=%s)",
            batch.id,
            actor.id,
            imported,
        )
        return self._view(batch)

    def _validate_rows(
        self, raw_rows: list[tuple[int, dict[str, object]]]
    ) -> list[QuestionImportRow]:
        results: list[QuestionImportRow | None] = [None] * len(raw_rows)
        parsed: list[tuple[int, _ParsedRow]] = []
        for position, (row_number, raw_data) in enumerate(raw_rows):
            if "_row_error" in raw_data:
                results[position] = self._invalid_row(
                    row_number, raw_data, str(raw_data["_row_error"])
                )
                continue
            try:
                record = QuestionImportRecord.model_validate(raw_data)
            except ValidationError as error:
                results[position] = QuestionImportRow(
                    row_number=row_number,
                    status=ImportRowStatus.INVALID,
                    raw_data=raw_data,
                    errors=self._validation_messages(error),
                )
                continue
            parsed.append((position, _ParsedRow(row_number, raw_data, record)))

        subject_candidates = self._load_subject_candidates(
            {item.record.subject_code for _, item in parsed}
        )
        resolved: list[tuple[int, _ParsedRow, Subject]] = []
        for position, item in parsed:
            candidates = subject_candidates.get(item.record.subject_code, [])
            if item.record.curriculum_version_code is not None:
                candidates = [
                    subject
                    for subject, version_code in candidates
                    if version_code == item.record.curriculum_version_code
                ]
            else:
                candidates = [subject for subject, _ in candidates]
            if not candidates:
                results[position] = self._invalid_row(
                    item.row_number,
                    item.raw_data,
                    f"subject_code: unknown subject code '{item.record.subject_code}'",
                )
            elif len(candidates) > 1:
                results[position] = self._invalid_row(
                    item.row_number,
                    item.raw_data,
                    "subject_code: ambiguous across curriculum versions; provide "
                    "curriculum_version_code",
                )
            else:
                resolved.append((position, item, candidates[0]))

        catalog = self._load_reference_catalog(resolved)
        for position, item, subject in resolved:
            results[position] = self._validate_references(item, subject, catalog)

        assert all(row is not None for row in results)
        return [row for row in results if row is not None]

    def _load_subject_candidates(
        self, subject_codes: set[str]
    ) -> dict[str, list[tuple[Subject, str]]]:
        if not subject_codes:
            return {}
        rows = self.session.execute(
            select(Subject, CurriculumVersion.code)
            .join(
                CurriculumVersion,
                CurriculumVersion.id == Subject.curriculum_version_id,
            )
            .where(Subject.code.in_(subject_codes))
            .order_by(Subject.id)
        )
        by_code: dict[str, list[tuple[Subject, str]]] = {}
        for subject, version_code in rows:
            by_code.setdefault(subject.code, []).append((subject, version_code))
        return by_code

    def _load_reference_catalog(
        self, rows: list[tuple[int, _ParsedRow, Subject]]
    ) -> _ReferenceCatalog:
        subject_ids = {subject.id for _, _, subject in rows}
        concept_codes = {
            link.code for _, item, _ in rows for link in item.record.concepts
        }
        problem_codes = {
            link.code for _, item, _ in rows for link in item.record.problem_types
        }
        outcome_codes = {
            link.code for _, item, _ in rows for link in item.record.learning_outcomes
        }
        concepts = (
            list(
                self.session.scalars(
                    select(Concept).where(
                        Concept.subject_id.in_(subject_ids),
                        Concept.code.in_(concept_codes),
                    )
                )
            )
            if subject_ids and concept_codes
            else []
        )
        problem_rows = (
            list(
                self.session.execute(
                    select(Chapter.subject_id, ProblemType)
                    .join(Topic, Topic.chapter_id == Chapter.id)
                    .join(ProblemType, ProblemType.topic_id == Topic.id)
                    .where(
                        Chapter.subject_id.in_(subject_ids),
                        ProblemType.code.in_(problem_codes),
                    )
                )
            )
            if subject_ids and problem_codes
            else []
        )
        outcomes = (
            list(
                self.session.scalars(
                    select(LearningOutcome).where(
                        LearningOutcome.subject_id.in_(subject_ids),
                        LearningOutcome.code.in_(outcome_codes),
                    )
                )
            )
            if subject_ids and outcome_codes
            else []
        )
        return _ReferenceCatalog(
            concepts={(item.subject_id, item.code): item for item in concepts},
            problem_types={
                (subject_id, item.code): item for subject_id, item in problem_rows
            },
            learning_outcomes={(item.subject_id, item.code): item for item in outcomes},
        )

    def _validate_references(
        self,
        row: _ParsedRow,
        subject: Subject,
        catalog: _ReferenceCatalog,
    ) -> QuestionImportRow:
        record = row.record
        concepts_by_code = {
            item.code: catalog.concepts[(subject.id, item.code)]
            for item in record.concepts
            if (subject.id, item.code) in catalog.concepts
        }
        missing = sorted({item.code for item in record.concepts} - concepts_by_code.keys())
        if missing:
            return self._invalid_row(
                row.row_number,
                row.raw_data,
                f"concepts: unknown concept code(s) for subject {subject.code}: {', '.join(missing)}",
            )
        problems_by_code = {
            item.code: catalog.problem_types[(subject.id, item.code)]
            for item in record.problem_types
            if (subject.id, item.code) in catalog.problem_types
        }
        missing_problems = sorted(
            {item.code for item in record.problem_types} - problems_by_code.keys()
        )
        if missing_problems:
            return self._invalid_row(
                row.row_number,
                row.raw_data,
                f"problem_types: unknown problem type code(s) for subject "
                f"{subject.code}: {', '.join(missing_problems)}",
            )
        outcomes_by_code = {
            item.code: catalog.learning_outcomes[(subject.id, item.code)]
            for item in record.learning_outcomes
            if (subject.id, item.code) in catalog.learning_outcomes
        }
        missing_outcomes = sorted(
            {item.code for item in record.learning_outcomes} - outcomes_by_code.keys()
        )
        if missing_outcomes:
            return self._invalid_row(
                row.row_number,
                row.raw_data,
                f"learning_outcomes: unknown learning outcome code(s) for subject "
                f"{subject.code}: {', '.join(missing_outcomes)}",
            )

        normalized: dict[str, object] = {
            "subject_id": str(subject.id),
            "subject_code": subject.code,
            "content": record.content,
            "question_type": record.question_type.value,
            "difficulty": record.difficulty,
            "correct_answer": record.correct_answer,
            "explanation": record.explanation,
            "source_type": record.source,
            "source_reference": record.source_reference,
            "source_year": record.source_year,
            "cognitive_level": (
                record.cognitive_level.value if record.cognitive_level is not None else None
            ),
            "exam_weight": record.exam_weight,
            "options": [item.model_dump(mode="json") for item in record.options],
            "concepts": [
                {
                    "concept_id": str(concepts_by_code[item.code].id),
                    "code": item.code,
                    "weight": item.weight,
                }
                for item in record.concepts
            ],
            "problem_types": [
                {
                    "problem_type_id": str(problems_by_code[item.code].id),
                    "code": item.code,
                    "weight": item.weight,
                    "is_primary": item.is_primary,
                }
                for item in record.problem_types
            ],
            "learning_outcomes": [
                {
                    "learning_outcome_id": str(outcomes_by_code[item.code].id),
                    "code": item.code,
                    "weight": item.weight,
                }
                for item in record.learning_outcomes
            ],
        }
        return QuestionImportRow(
            row_number=row.row_number,
            status=ImportRowStatus.VALID,
            raw_data=row.raw_data,
            normalized_data=normalized,
            content_hash=self.duplicate_detector.fingerprint(record.content),
            errors=[],
        )

    def _mark_duplicates(self, rows: list[QuestionImportRow]) -> None:
        candidates = [self._content(row) for row in rows]
        matches = self.duplicate_detector.detect(self.session, candidates)
        for index, match in matches.items():
            row = rows[index]
            row.status = ImportRowStatus.DUPLICATE
            if match.existing_question_id is not None:
                row.errors = [
                    f"Duplicate content: matches existing question {match.existing_question_id}."
                ]
            else:
                assert match.duplicate_of_index is not None
                original = rows[match.duplicate_of_index]
                row.errors = [
                    f"Duplicate content: matches import row {original.row_number}."
                ]

    def _build_question(
        self,
        data: dict[str, object],
        created_by: UUID,
        status: QuestionStatus,
    ) -> Question:
        options = data.get("options", [])
        concepts = data.get("concepts", [])
        problem_types = data.get("problem_types", [])
        learning_outcomes = data.get("learning_outcomes", [])
        question = Question(
            subject_id=UUID(str(data["subject_id"])),
            content=str(data["content"]),
            question_type=QuestionType(str(data["question_type"])),
            difficulty=float(data["difficulty"]),
            correct_answer=self._optional_string(data.get("correct_answer")),
            explanation=self._optional_string(data.get("explanation")),
            source_type=str(data["source_type"]),
            source_reference=self._optional_string(data.get("source_reference")),
            source_year=(
                int(data["source_year"]) if data.get("source_year") is not None else None
            ),
            cognitive_level=self._optional_string(data.get("cognitive_level")),
            exam_weight=float(data["exam_weight"]),
            status=status,
            created_by=created_by,
        )
        assert (
            isinstance(options, list)
            and isinstance(concepts, list)
            and isinstance(problem_types, list)
            and isinstance(learning_outcomes, list)
        )
        question.options = [
            QuestionOption(
                label=str(option["label"]),
                content=str(option["content"]),
                order_index=int(option["order_index"]),
            )
            for option in options
            if isinstance(option, dict)
        ]
        question.concept_links = [
            QuestionConcept(
                concept_id=UUID(str(link["concept_id"])),
                weight=float(link["weight"]),
            )
            for link in concepts
            if isinstance(link, dict)
        ]
        question.problem_type_links = [
            QuestionProblemType(
                problem_type_id=UUID(str(link["problem_type_id"])),
                weight=(float(link["weight"]) if link.get("weight") is not None else None),
                is_primary=bool(link.get("is_primary", False)),
            )
            for link in problem_types
            if isinstance(link, dict)
        ]
        question.learning_outcome_links = [
            QuestionLearningOutcome(
                learning_outcome_id=UUID(str(link["learning_outcome_id"])),
                weight=(float(link["weight"]) if link.get("weight") is not None else None),
            )
            for link in learning_outcomes
            if isinstance(link, dict)
        ]
        return question

    def _batch_for_update(self, batch_id: UUID) -> QuestionImportBatch:
        batch = self.session.scalar(
            select(QuestionImportBatch)
            .options(selectinload(QuestionImportBatch.rows))
            .where(QuestionImportBatch.id == batch_id)
            .with_for_update()
        )
        if batch is None:
            raise ApplicationError(
                404,
                "QUESTION_IMPORT_NOT_FOUND",
                "Question import batch was not found.",
            )
        return batch

    def _lock_imports(self) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            self.session.execute(
                select(func.pg_advisory_xact_lock(func.hashtext("edums:question-import")))
            )

    def _staged_reference_errors(
        self, rows: list[QuestionImportRow]
    ) -> dict[UUID, str]:
        subject_ids: set[UUID] = set()
        concept_ids: set[UUID] = set()
        problem_type_ids: set[UUID] = set()
        outcome_ids: set[UUID] = set()
        for row in rows:
            data = row.normalized_data
            if data is None:
                continue
            subject_ids.add(UUID(str(data["subject_id"])))
            for link in data.get("concepts", []):
                if isinstance(link, dict):
                    concept_ids.add(UUID(str(link["concept_id"])))
            for link in data.get("problem_types", []):
                if isinstance(link, dict):
                    problem_type_ids.add(UUID(str(link["problem_type_id"])))
            for link in data.get("learning_outcomes", []):
                if isinstance(link, dict):
                    outcome_ids.add(UUID(str(link["learning_outcome_id"])))

        existing_subject_ids = (
            set(
                self.session.scalars(
                    select(Subject.id).where(Subject.id.in_(subject_ids))
                )
            )
            if subject_ids
            else set()
        )
        concept_subjects = (
            {
                concept_id: subject_id
                for concept_id, subject_id in self.session.execute(
                    select(Concept.id, Concept.subject_id).where(
                        Concept.id.in_(concept_ids)
                    )
                )
            }
            if concept_ids
            else {}
        )
        problem_subjects = (
            {
                problem_id: subject_id
                for problem_id, subject_id in self.session.execute(
                    select(ProblemType.id, Chapter.subject_id)
                    .join(Topic, Topic.id == ProblemType.topic_id)
                    .join(Chapter, Chapter.id == Topic.chapter_id)
                    .where(ProblemType.id.in_(problem_type_ids))
                )
            }
            if problem_type_ids
            else {}
        )
        outcome_subjects = (
            {
                outcome_id: subject_id
                for outcome_id, subject_id in self.session.execute(
                    select(LearningOutcome.id, LearningOutcome.subject_id).where(
                        LearningOutcome.id.in_(outcome_ids)
                    )
                )
            }
            if outcome_ids
            else {}
        )
        errors: dict[UUID, str] = {}
        for row in rows:
            error = self._staged_reference_error(
                row,
                existing_subject_ids,
                concept_subjects,
                problem_subjects,
                outcome_subjects,
            )
            if error is not None:
                errors[row.id] = error
        return errors

    @staticmethod
    def _staged_reference_error(
        row: QuestionImportRow,
        existing_subject_ids: set[UUID],
        concept_subjects: dict[UUID, UUID],
        problem_subjects: dict[UUID, UUID],
        outcome_subjects: dict[UUID, UUID],
    ) -> str | None:
        data = row.normalized_data
        if data is None:
            return "Staged row has no normalized data."
        subject_id = UUID(str(data["subject_id"]))
        if subject_id not in existing_subject_ids:
            return "subject_code: subject was removed after preview."
        concepts = data.get("concepts", [])
        if not isinstance(concepts, list):
            return "concepts: staged concept data is invalid."
        for link in concepts:
            if not isinstance(link, dict):
                return "concepts: staged concept data is invalid."
            concept_id = UUID(str(link["concept_id"]))
            concept_subject_id = concept_subjects.get(concept_id)
            if concept_subject_id is None:
                return f"concepts: concept '{link.get('code', 'unknown')}' was removed after preview."
            if concept_subject_id != subject_id:
                return f"concepts: concept '{link.get('code', 'unknown')}' no longer belongs to the subject."
        problem_types = data.get("problem_types", [])
        if not isinstance(problem_types, list):
            return "problem_types: staged problem type data is invalid."
        for link in problem_types:
            if not isinstance(link, dict):
                return "problem_types: staged problem type data is invalid."
            problem_id = UUID(str(link["problem_type_id"]))
            mapped_subject = problem_subjects.get(problem_id)
            if mapped_subject is None:
                return f"problem_types: problem type '{link.get('code', 'unknown')}' was removed after preview."
            if mapped_subject != subject_id:
                return f"problem_types: problem type '{link.get('code', 'unknown')}' no longer belongs to the subject."
        outcomes = data.get("learning_outcomes", [])
        if not isinstance(outcomes, list):
            return "learning_outcomes: staged learning outcome data is invalid."
        for link in outcomes:
            if not isinstance(link, dict):
                return "learning_outcomes: staged learning outcome data is invalid."
            outcome_id = UUID(str(link["learning_outcome_id"]))
            outcome_subject_id = outcome_subjects.get(outcome_id)
            if outcome_subject_id is None:
                return f"learning_outcomes: outcome '{link.get('code', 'unknown')}' was removed after preview."
            if outcome_subject_id != subject_id:
                return f"learning_outcomes: outcome '{link.get('code', 'unknown')}' no longer belongs to the subject."
        return None

    @staticmethod
    def _file_format(file_name: str) -> ImportFileFormat:
        suffix = Path(file_name).suffix.lower()
        if suffix == ".csv":
            return ImportFileFormat.CSV
        if suffix == ".json":
            return ImportFileFormat.JSON
        raise ApplicationError(
            422,
            "UNSUPPORTED_IMPORT_FORMAT",
            "Question import file must use a .csv or .json extension.",
        )

    def _parse(
        self, content: bytes, file_format: ImportFileFormat
    ) -> list[tuple[int, dict[str, object]]]:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ApplicationError(
                422, "IMPORT_ENCODING_ERROR", "Import file must be UTF-8 encoded."
            ) from error
        if file_format == ImportFileFormat.JSON:
            return self._parse_json(text)
        return self._parse_csv(text)

    @staticmethod
    def _parse_json(text: str) -> list[tuple[int, dict[str, object]]]:
        try:
            payload = json.loads(
                text,
                parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError(f"invalid numeric constant {value}")
                ),
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise ApplicationError(
                422, "IMPORT_PARSE_ERROR", f"Invalid JSON file: {error}."
            ) from error
        if isinstance(payload, dict) and set(payload) == {"questions"}:
            payload = payload["questions"]
        if not isinstance(payload, list):
            raise ApplicationError(
                422,
                "IMPORT_PARSE_ERROR",
                "JSON import must be an array or an object containing only a questions array.",
            )
        rows: list[tuple[int, dict[str, object]]] = []
        for index, item in enumerate(payload, start=1):
            if isinstance(item, dict) and all(isinstance(key, str) for key in item):
                rows.append((index, item))
            else:
                rows.append((index, {"_row_error": "Row must be a JSON object."}))
        return rows

    @staticmethod
    def _parse_csv(text: str) -> list[tuple[int, dict[str, object]]]:
        try:
            reader = csv.DictReader(io.StringIO(text), strict=True)
            if not reader.fieldnames:
                raise ApplicationError(
                    422, "IMPORT_PARSE_ERROR", "CSV import must contain a header row."
                )
            normalized_headers = [header.strip() for header in reader.fieldnames]
            if len(set(normalized_headers)) != len(normalized_headers):
                raise ApplicationError(
                    422, "IMPORT_PARSE_ERROR", "CSV header names must be unique."
                )
            rows: list[tuple[int, dict[str, object]]] = []
            for row_number, source in enumerate(reader, start=2):
                row: dict[str, object] = {}
                for key, value in source.items():
                    if key is None:
                        row["_extra_columns"] = value
                    else:
                        row[key.strip()] = value
                rows.append((row_number, row))
            return rows
        except csv.Error as error:
            raise ApplicationError(
                422, "IMPORT_PARSE_ERROR", f"Invalid CSV file: {error}."
            ) from error

    @staticmethod
    def _validation_messages(error: ValidationError) -> list[str]:
        messages: list[str] = []
        for detail in error.errors(include_url=False, include_input=False):
            location = ".".join(str(part) for part in detail["loc"])
            prefix = f"{location}: " if location else ""
            messages.append(f"{prefix}{detail['msg']}")
        return messages

    @staticmethod
    def _invalid_row(
        row_number: int, raw_data: dict[str, object], message: str
    ) -> QuestionImportRow:
        return QuestionImportRow(
            row_number=row_number,
            status=ImportRowStatus.INVALID,
            raw_data=raw_data,
            errors=[message],
        )

    @staticmethod
    def _content(row: QuestionImportRow) -> str:
        assert row.normalized_data is not None
        return str(row.normalized_data["content"])

    @staticmethod
    def _optional_string(value: object) -> str | None:
        return None if value is None else str(value)

    @staticmethod
    def _view(batch: QuestionImportBatch) -> QuestionImportBatchRead:
        valid = sum(
            row.status in {ImportRowStatus.VALID, ImportRowStatus.IMPORTED}
            for row in batch.rows
        )
        report = QuestionImportReport(
            total=len(batch.rows),
            valid=valid,
            invalid=sum(row.status == ImportRowStatus.INVALID for row in batch.rows),
            duplicate=sum(row.status == ImportRowStatus.DUPLICATE for row in batch.rows),
            imported=sum(row.status == ImportRowStatus.IMPORTED for row in batch.rows),
        )
        return QuestionImportBatchRead(
            batch_id=batch.id,
            file_name=batch.file_name,
            file_format=batch.file_format,
            trusted_seed_data=batch.trusted_seed_data,
            status=batch.status,
            created_at=batch.created_at,
            confirmed_at=batch.confirmed_at,
            report=report,
            rows=[
                QuestionImportRowRead(
                    row_number=row.row_number,
                    status=row.status,
                    errors=row.errors,
                    data=row.normalized_data if row.normalized_data is not None else row.raw_data,
                    imported_question_id=row.imported_question_id,
                )
                for row in batch.rows
            ],
        )
