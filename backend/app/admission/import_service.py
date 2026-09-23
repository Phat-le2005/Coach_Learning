from __future__ import annotations

import csv
from datetime import datetime, timezone
import io
import json
import logging
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.admission.import_schemas import (
    AdmissionImportAction,
    AdmissionImportHistoryRead,
    AdmissionImportPreviewResponse,
    AdmissionImportResult,
    AdmissionImportRowPreview,
    AdmissionRuleImportRecord,
)
from app.admission.models import (
    AdmissionDataSource,
    AdmissionImportFormat,
    AdmissionImportHistory,
    AdmissionImportStatus,
    AdmissionMethod,
    AdmissionRule,
    Major,
    University,
)
from app.core.exceptions import ApplicationError

logger = logging.getLogger(__name__)


class AdmissionImportService:
    """Pipeline for importing admission rules with verification and provenance tracking.

    Stages:
    1. Parse (CSV / JSON)
    2. Validate (Types, bounds, JSON structure)
    3. Normalize (Codes, casing, datetimes)
    4. Source Verification Fields (year, source_reference, verified_at, data source)
    5. Preview (Diff against existing catalog & rules, create preview history)
    6. Import (Idempotent upsert, year isolation guarantee, complete provenance audit)
    """

    MAX_FILE_BYTES = 10 * 1024 * 1024  # 10MB
    MAX_ROWS = 10000

    def __init__(self, session: Session) -> None:
        self.session = session

    # --------------------------------------------------------------------------
    # 1. PARSE STAGE
    # --------------------------------------------------------------------------

    def parse_content(
        self,
        file_format: AdmissionImportFormat,
        content: bytes,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        if not content:
            raise ApplicationError(422, "EMPTY_FILE", "Uploaded file content is empty.")
        if len(content) > self.MAX_FILE_BYTES:
            raise ApplicationError(413, "FILE_TOO_LARGE", f"File size exceeds maximum allowed of {self.MAX_FILE_BYTES} bytes.")

        if file_format == AdmissionImportFormat.CSV:
            return self._parse_csv(content)
        elif file_format in (AdmissionImportFormat.JSON, AdmissionImportFormat.DIRECT_FEED):
            return self._parse_json(content)
        else:
            raise ApplicationError(400, "UNSUPPORTED_FORMAT", f"Unsupported file format: {file_format}")

    def _parse_csv(self, content: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        text = None
        for enc in ("utf-8-sig", "utf-8", "latin1"):
            try:
                text = content.decode(enc)
                break
            except UnicodeDecodeError:
                continue

        if text is None:
            raise ApplicationError(422, "INVALID_ENCODING", "Could not decode CSV file using UTF-8 or Latin1.")

        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ApplicationError(422, "INVALID_CSV", "CSV file contains no headers.")

        rows: list[dict[str, Any]] = []
        for raw in reader:
            cleaned = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in raw.items() if k}
            if any(cleaned.values()):
                rows.append(cleaned)

        if len(rows) > self.MAX_ROWS:
            raise ApplicationError(422, "TOO_MANY_ROWS", f"File exceeds maximum row limit of {self.MAX_ROWS}.")

        return {}, rows

    def _parse_json(self, content: bytes) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        try:
            data = json.loads(content.decode("utf-8"))
        except Exception as e:
            raise ApplicationError(422, "INVALID_JSON", f"Malformed JSON content: {e}")

        envelope: dict[str, Any] = {}
        rows: list[dict[str, Any]] = []

        if isinstance(data, list):
            rows = [item for item in data if isinstance(item, dict)]
        elif isinstance(data, dict):
            for candidate_key in ("rules", "data", "records", "items"):
                if candidate_key in data and isinstance(data[candidate_key], list):
                    rows = [item for item in data[candidate_key] if isinstance(item, dict)]
                    envelope = {k: v for k, v in data.items() if k != candidate_key and not isinstance(v, (list, dict))}
                    break
            if not rows and "major_code" in data:
                rows = [data]
        else:
            raise ApplicationError(422, "INVALID_JSON_STRUCTURE", "JSON must be an array of objects or an envelope dictionary.")

        if len(rows) > self.MAX_ROWS:
            raise ApplicationError(422, "TOO_MANY_ROWS", f"JSON exceeds maximum row limit of {self.MAX_ROWS}.")

        return envelope, rows

    # --------------------------------------------------------------------------
    # 2, 3, 4. VALIDATE, NORMALIZE & SOURCE VERIFICATION STAGES
    # --------------------------------------------------------------------------

    def validate_and_normalize(
        self,
        raw_rows: list[dict[str, Any]],
        envelope_metadata: dict[str, Any] | None = None,
    ) -> tuple[list[tuple[int, AdmissionRuleImportRecord]], list[dict[str, Any]]]:
        env = envelope_metadata or {}
        valid_records: list[tuple[int, AdmissionRuleImportRecord]] = []
        errors: list[dict[str, Any]] = []

        for idx, row in enumerate(raw_rows, start=1):
            merged = {**env, **row}

            try:
                record = AdmissionRuleImportRecord.model_validate(merged)
            except ValidationError as ve:
                field_errors = [f"{err['loc'][-1]}: {err['msg']}" for err in ve.errors()]
                errors.append({
                    "row_number": idx,
                    "code": "VALIDATION_FAILED",
                    "message": "; ".join(field_errors),
                    "raw_data": row,
                })
                continue

            # Stage 4: Strict Source Verification Fields Check
            source_errors = self._verify_source_fields(record)
            if source_errors:
                errors.append({
                    "row_number": idx,
                    "code": "SOURCE_VERIFICATION_FAILED",
                    "message": "; ".join(source_errors),
                    "raw_data": row,
                })
                continue

            valid_records.append((idx, record))

        return valid_records, errors

    def _verify_source_fields(self, record: AdmissionRuleImportRecord) -> list[str]:
        errs: list[str] = []
        if not record.year or record.year < 2000:
            errs.append("Field 'year' must be a valid year >= 2000")
        if not record.source_reference or not record.source_reference.strip():
            errs.append("Field 'source_reference' is mandatory and must not be blank")
        if not record.verified_at:
            errs.append("Field 'verified_at' is mandatory and must be a valid timestamp")
        if not record.data_source_id and not (record.data_source_name and record.data_source_name.strip()):
            errs.append("Record must have either 'data_source_id' or non-empty 'data_source_name'")
        return errs

    # --------------------------------------------------------------------------
    # 5. PREVIEW STAGE
    # --------------------------------------------------------------------------

    def preview(
        self,
        actor_id: UUID | None,
        file_name: str,
        file_format: AdmissionImportFormat,
        content: bytes,
    ) -> AdmissionImportPreviewResponse:
        envelope, raw_rows = self.parse_content(file_format, content)
        valid_tuples, parse_errors = self.validate_and_normalize(raw_rows, envelope)

        row_previews: list[AdmissionImportRowPreview] = []
        insert_count = 0
        update_count = 0
        no_change_count = 0
        target_years_set: set[int] = set()

        # Pre-load universities, majors, methods, rules for diffing
        universities = {u.code: u for u in self.session.scalars(select(University)).all()}
        majors_by_univ_and_code = {
            (m.university_id, m.code): m for m in self.session.scalars(select(Major)).all()
        }
        methods = {m.code: m for m in self.session.scalars(select(AdmissionMethod)).all()}

        # Build error map for invalid rows
        error_by_row = {e["row_number"]: e["message"] for e in parse_errors}

        valid_records_for_storage: list[dict[str, Any]] = []

        for row_num, rec in valid_tuples:
            target_years_set.add(rec.year)
            valid_records_for_storage.append(rec.model_dump(mode="json"))

            # Check entity existence and determine proposed action
            univ = universities.get(rec.university_code)
            major = majors_by_univ_and_code.get((univ.id, rec.major_code)) if univ else None
            method = methods.get(rec.method_code)

            action = AdmissionImportAction.INSERT
            warnings: list[str] = []

            if not univ:
                warnings.append(f"University '{rec.university_code}' will be auto-created.")
            if not major:
                warnings.append(f"Major '{rec.major_code}' will be auto-created.")
            if not method:
                warnings.append(f"Method '{rec.method_code}' will be auto-created.")

            if univ and major and method:
                # Query exact existing rule
                existing_rule = self.session.scalar(
                    select(AdmissionRule).where(
                        AdmissionRule.major_id == major.id,
                        AdmissionRule.year == rec.year,
                        AdmissionRule.method_id == method.id,
                        AdmissionRule.subject_combination == rec.subject_combination,
                    )
                )
                if existing_rule:
                    # Compare if identical
                    is_identical = (
                        existing_rule.quota == rec.quota
                        and (existing_rule.historical_score == rec.historical_score or (existing_rule.historical_score is None and rec.historical_score is None))
                        and (existing_rule.requirements or {}) == (rec.requirements or {})
                        and (existing_rule.source_reference or "").strip() == (rec.source_reference or "").strip()
                    )
                    if is_identical:
                        action = AdmissionImportAction.NO_CHANGE
                        no_change_count += 1
                    else:
                        action = AdmissionImportAction.UPDATE
                        update_count += 1
                else:
                    action = AdmissionImportAction.INSERT
                    insert_count += 1
            else:
                action = AdmissionImportAction.INSERT
                insert_count += 1

            row_previews.append(
                AdmissionImportRowPreview(
                    row_number=row_num,
                    status="VALID",
                    action=action,
                    university_code=rec.university_code,
                    major_code=rec.major_code,
                    method_code=rec.method_code,
                    year=rec.year,
                    subject_combination=rec.subject_combination,
                    quota=rec.quota,
                    historical_score=rec.historical_score,
                    source_reference=rec.source_reference,
                    verified_at=rec.verified_at,
                    data_source_name=rec.data_source_name,
                    warnings=warnings,
                )
            )

        # Append invalid row previews
        for row_num, raw in enumerate(raw_rows, start=1):
            if row_num in error_by_row:
                row_previews.append(
                    AdmissionImportRowPreview(
                        row_number=row_num,
                        status="INVALID",
                        action=None,
                        university_code=str(raw.get("university_code") or raw.get("ma_truong") or "UNKNOWN"),
                        major_code=str(raw.get("major_code") or raw.get("ma_nganh") or "UNKNOWN"),
                        method_code=str(raw.get("method_code") or raw.get("phuong_thuc") or "UNKNOWN"),
                        year=int(raw["year"]) if "year" in raw and str(raw["year"]).isdigit() else None,
                        errors=[error_by_row[row_num]],
                    )
                )

        row_previews.sort(key=lambda r: r.row_number)

        target_years = sorted(list(target_years_set))
        single_target_year = target_years[0] if len(target_years) == 1 else None

        # Create history entry in PREVIEWED state
        history = AdmissionImportHistory(
            file_name=file_name,
            file_format=file_format,
            status=AdmissionImportStatus.PREVIEWED,
            total_rows=len(raw_rows),
            valid_rows=len(valid_tuples),
            imported_rows=0,
            updated_rows=0,
            skipped_rows=0,
            error_rows=len(parse_errors),
            errors=parse_errors,
            preview_data={
                "valid_records": valid_records_for_storage,
                "target_years": target_years,
            },
            target_year=single_target_year,
            created_by=actor_id,
            verified_at=datetime.now(timezone.utc),
            import_metadata={"envelope": envelope},
        )
        self.session.add(history)
        self.session.commit()
        self.session.refresh(history)

        return AdmissionImportPreviewResponse(
            batch_id=history.id,
            file_name=file_name,
            file_format=file_format,
            status=history.status,
            total_rows=len(raw_rows),
            valid_rows=len(valid_tuples),
            error_rows=len(parse_errors),
            insert_count=insert_count,
            update_count=update_count,
            no_change_count=no_change_count,
            target_years=target_years,
            errors=parse_errors,
            rows=row_previews,
        )

    # --------------------------------------------------------------------------
    # 6. IMPORT STAGE (Idempotent Commit & Provenance)
    # --------------------------------------------------------------------------

    def execute_import(
        self,
        batch_id: UUID,
        actor_id: UUID | None,
        auto_create_entities: bool = True,
    ) -> AdmissionImportResult:
        history = self.session.get(AdmissionImportHistory, batch_id)
        if not history:
            raise ApplicationError(404, "IMPORT_BATCH_NOT_FOUND", "Import batch was not found.")

        # If already completed, return existing completed stats (Idempotence)
        if history.status == AdmissionImportStatus.COMPLETED:
            return AdmissionImportResult(
                batch_id=history.id,
                status=history.status,
                total_rows=history.total_rows,
                imported_rows=history.imported_rows,
                updated_rows=history.updated_rows,
                skipped_rows=history.skipped_rows,
                error_rows=history.error_rows,
                completed_at=history.completed_at or datetime.now(timezone.utc),
            )

        preview_data = history.preview_data or {}
        valid_records_raw = preview_data.get("valid_records", [])
        if not valid_records_raw:
            history.status = AdmissionImportStatus.COMPLETED
            history.completed_at = datetime.now(timezone.utc)
            self.session.commit()
            return AdmissionImportResult(
                batch_id=history.id,
                status=history.status,
                total_rows=history.total_rows,
                imported_rows=0,
                updated_rows=0,
                skipped_rows=0,
                error_rows=history.error_rows,
                completed_at=history.completed_at,
            )

        imported_rows = 0
        updated_rows = 0
        skipped_rows = 0

        # Catalogs
        universities = {u.code: u for u in self.session.scalars(select(University)).all()}
        majors_by_univ_and_code = {
            (m.university_id, m.code): m for m in self.session.scalars(select(Major)).all()
        }
        methods = {m.code: m for m in self.session.scalars(select(AdmissionMethod)).all()}
        data_sources_by_name_and_year = {
            (ds.name, ds.published_year): ds for ds in self.session.scalars(select(AdmissionDataSource)).all()
        }

        for raw_item in valid_records_raw:
            rec = AdmissionRuleImportRecord.model_validate(raw_item)

            # 1. Resolve or auto-create University
            univ = universities.get(rec.university_code)
            if not univ:
                if not auto_create_entities:
                    raise ApplicationError(400, "UNIVERSITY_NOT_FOUND", f"University '{rec.university_code}' does not exist.")
                univ = University(
                    code=rec.university_code,
                    name=rec.university_name or f"Trường {rec.university_code}",
                )
                self.session.add(univ)
                self.session.flush()
                universities[univ.code] = univ

            # 2. Resolve or auto-create Major
            major = majors_by_univ_and_code.get((univ.id, rec.major_code))
            if not major:
                if not auto_create_entities:
                    raise ApplicationError(400, "MAJOR_NOT_FOUND", f"Major '{rec.major_code}' does not exist for {univ.code}.")
                major = Major(
                    university_id=univ.id,
                    code=rec.major_code,
                    name=rec.major_name or f"Ngành {rec.major_code}",
                )
                self.session.add(major)
                self.session.flush()
                majors_by_univ_and_code[(univ.id, major.code)] = major

            # 3. Resolve or auto-create AdmissionMethod
            method = methods.get(rec.method_code)
            if not method:
                if not auto_create_entities:
                    raise ApplicationError(400, "METHOD_NOT_FOUND", f"Admission method '{rec.method_code}' does not exist.")
                method = AdmissionMethod(
                    code=rec.method_code,
                    name=rec.method_name or f"Phương thức {rec.method_code}",
                )
                self.session.add(method)
                self.session.flush()
                methods[method.code] = method

            # 4. Resolve or auto-create AdmissionDataSource
            data_source_id = rec.data_source_id
            if not data_source_id and rec.data_source_name:
                key = (rec.data_source_name, rec.year)
                ds = data_sources_by_name_and_year.get(key)
                if not ds:
                    ds = AdmissionDataSource(
                        name=rec.data_source_name,
                        source_type=rec.data_source_type or "OFFICIAL_PROSPECTUS",
                        source_url=rec.data_source_url,
                        publisher=rec.data_source_publisher or univ.name,
                        published_year=rec.year,
                        verified_at=rec.verified_at,
                        verified_by=actor_id,
                    )
                    self.session.add(ds)
                    self.session.flush()
                    data_sources_by_name_and_year[key] = ds
                data_source_id = ds.id

            # 5. Idempotent Upsert for AdmissionRule
            # STRICT GUARANTEE: Match on (major_id, year, method_id, subject_combination)
            # NEVER modifies records from other years!
            existing_rule = self.session.scalar(
                select(AdmissionRule).where(
                    AdmissionRule.major_id == major.id,
                    AdmissionRule.year == rec.year,
                    AdmissionRule.method_id == method.id,
                    AdmissionRule.subject_combination == rec.subject_combination,
                )
            )

            if existing_rule:
                # Update rule in-place
                existing_rule.quota = rec.quota
                existing_rule.historical_score = rec.historical_score
                existing_rule.requirements = rec.requirements
                existing_rule.source_reference = rec.source_reference
                existing_rule.data_source_id = data_source_id
                existing_rule.verified_at = rec.verified_at
                existing_rule.verified_by = actor_id
                existing_rule.import_history_id = history.id
                updated_rows += 1
            else:
                new_rule = AdmissionRule(
                    university_id=univ.id,
                    major_id=major.id,
                    year=rec.year,
                    method_id=method.id,
                    subject_combination=rec.subject_combination,
                    requirements=rec.requirements,
                    quota=rec.quota,
                    historical_score=rec.historical_score,
                    source_reference=rec.source_reference,
                    data_source_id=data_source_id,
                    verified_at=rec.verified_at,
                    verified_by=actor_id,
                    import_history_id=history.id,
                )
                self.session.add(new_rule)
                imported_rows += 1

        completed_at = datetime.now(timezone.utc)
        history.status = AdmissionImportStatus.COMPLETED
        history.imported_rows = imported_rows
        history.updated_rows = updated_rows
        history.skipped_rows = skipped_rows
        history.completed_at = completed_at

        self.session.commit()
        self.session.refresh(history)

        return AdmissionImportResult(
            batch_id=history.id,
            status=history.status,
            total_rows=history.total_rows,
            imported_rows=imported_rows,
            updated_rows=updated_rows,
            skipped_rows=skipped_rows,
            error_rows=history.error_rows,
            completed_at=completed_at,
        )

    # --------------------------------------------------------------------------
    # History & Provenance Queries
    # --------------------------------------------------------------------------

    def list_history(self, offset: int = 0, limit: int = 50) -> list[AdmissionImportHistoryRead]:
        stmt = (
            select(AdmissionImportHistory)
            .order_by(AdmissionImportHistory.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        histories = self.session.scalars(stmt).all()
        return [AdmissionImportHistoryRead.model_validate(h) for h in histories]

    def get_history_detail(self, history_id: UUID) -> AdmissionImportHistoryRead:
        history = self.session.get(AdmissionImportHistory, history_id)
        if not history:
            raise ApplicationError(404, "IMPORT_BATCH_NOT_FOUND", "Import batch was not found.")
        return AdmissionImportHistoryRead.model_validate(history)
