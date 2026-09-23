from __future__ import annotations

from datetime import datetime
from enum import StrEnum
import json
from typing import Any
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from app.admission.models import AdmissionImportFormat, AdmissionImportStatus


class AdmissionImportAction(StrEnum):
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    NO_CHANGE = "NO_CHANGE"


class AdmissionRuleImportRecord(BaseModel):
    """Normalized record parsed from CSV/JSON payload.

    Supports aliases for English and Vietnamese column names.
    Every record must contain source verification fields.
    """
    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        populate_by_name=True,
    )

    university_code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        validation_alias=AliasChoices("university_code", "ma_truong", "truong", "university"),
    )
    university_name: str | None = Field(
        default=None,
        max_length=300,
        validation_alias=AliasChoices("university_name", "ten_truong"),
    )
    major_code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        validation_alias=AliasChoices("major_code", "ma_nganh", "nganh", "major"),
    )
    major_name: str | None = Field(
        default=None,
        max_length=300,
        validation_alias=AliasChoices("major_name", "ten_nganh"),
    )
    method_code: str = Field(
        ...,
        min_length=1,
        max_length=50,
        validation_alias=AliasChoices("method_code", "ma_pt", "phuong_thuc", "method"),
    )
    method_name: str | None = Field(
        default=None,
        max_length=250,
        validation_alias=AliasChoices("method_name", "ten_phuong_thuc"),
    )
    year: int = Field(
        ...,
        ge=2000,
        le=2100,
        validation_alias=AliasChoices("year", "nam", "nam_tuyen_sinh"),
    )
    subject_combination: str = Field(
        ...,
        min_length=1,
        max_length=100,
        validation_alias=AliasChoices("subject_combination", "to_hop", "to_hop_mon", "combination"),
    )
    requirements: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("requirements", "dieu_kien", "yeu_cau"),
    )
    quota: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("quota", "chi_tieu"),
    )
    historical_score: float | None = Field(
        default=None,
        ge=0.0,
        validation_alias=AliasChoices("historical_score", "diem_chuan", "diem_nam_truoc", "score"),
    )
    source_reference: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        validation_alias=AliasChoices("source_reference", "nguon_trich_dan", "can_cu", "reference"),
    )
    verified_at: datetime = Field(
        ...,
        validation_alias=AliasChoices("verified_at", "ngay_xac_thuc", "verified_date"),
    )
    data_source_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("data_source_id", "ma_nguon_du_lieu"),
    )
    data_source_name: str | None = Field(
        default=None,
        max_length=300,
        validation_alias=AliasChoices("data_source_name", "nguon_du_lieu", "de_an", "source_name"),
    )
    data_source_url: str | None = Field(
        default=None,
        max_length=1000,
        validation_alias=AliasChoices("data_source_url", "link_de_an"),
    )
    data_source_publisher: str | None = Field(
        default=None,
        max_length=300,
        validation_alias=AliasChoices("data_source_publisher", "don_vi_ban_hanh"),
    )
    data_source_type: str = Field(
        default="OFFICIAL_PROSPECTUS",
        max_length=100,
        validation_alias=AliasChoices("data_source_type", "loai_nguon"),
    )

    @field_validator(
        "quota",
        "historical_score",
        "data_source_id",
        "data_source_name",
        "data_source_url",
        "data_source_publisher",
        "university_name",
        "major_name",
        "method_name",
        mode="before",
    )
    @classmethod
    def empty_string_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("university_code", "major_code", "method_code", "subject_combination")
    @classmethod
    def normalize_uppercase_codes(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("requirements", mode="before")
    @classmethod
    def parse_requirements_json(cls, value: Any) -> Any:
        if isinstance(value, str):
            val = value.strip()
            if not val:
                return {}
            try:
                parsed = json.loads(val)
                if isinstance(parsed, dict):
                    return parsed
                return {"raw": parsed}
            except json.JSONDecodeError:
                return {"raw": val}
        if isinstance(value, dict):
            return value
        return {}


class AdmissionImportRowPreview(BaseModel):
    row_number: int
    status: str = "VALID"  # VALID | INVALID
    action: AdmissionImportAction | None = None
    university_code: str
    major_code: str
    method_code: str
    year: int | None = None
    subject_combination: str | None = None
    quota: int | None = None
    historical_score: float | None = None
    source_reference: str | None = None
    verified_at: datetime | None = None
    data_source_name: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class AdmissionImportPreviewResponse(BaseModel):
    batch_id: UUID
    file_name: str
    file_format: AdmissionImportFormat
    status: AdmissionImportStatus
    total_rows: int
    valid_rows: int
    error_rows: int
    insert_count: int
    update_count: int
    no_change_count: int
    target_years: list[int] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    rows: list[AdmissionImportRowPreview] = Field(default_factory=list)


class AdmissionImportExecuteRequest(BaseModel):
    batch_id: UUID
    auto_create_entities: bool = Field(
        default=True,
        description="Tự động khởi tạo trường, ngành hoặc phương thức nếu thông tin cơ bản hợp lệ.",
    )


class AdmissionImportResult(BaseModel):
    batch_id: UUID
    status: AdmissionImportStatus
    total_rows: int
    imported_rows: int
    updated_rows: int
    skipped_rows: int
    error_rows: int
    completed_at: datetime


class AdmissionImportHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    file_name: str
    file_format: AdmissionImportFormat
    status: AdmissionImportStatus
    total_rows: int
    valid_rows: int
    imported_rows: int
    updated_rows: int
    skipped_rows: int
    error_rows: int
    errors: list[dict[str, Any]]
    target_year: int | None = None
    data_source_id: UUID | None = None
    data_source_name: str | None = None
    source_reference: str | None = None
    verified_at: datetime | None = None
    created_by: UUID | None = None
    created_at: datetime
    completed_at: datetime | None = None
