from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.admission.models import AdmissionTargetType


# --------------------------------------------------------------------------
# 1. University Schemas
# --------------------------------------------------------------------------

class UniversityBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="Mã trường đại học (e.g. BKHN, QHI, FTU)")
    name: str = Field(..., min_length=1, max_length=300, description="Tên đầy đủ của trường đại học")
    short_name: str | None = Field(default=None, max_length=100)
    description: str | None = None
    website: str | None = Field(default=None, max_length=500)
    region: str | None = Field(default=None, max_length=100, description="Khu vực địa lý (e.g. MIEN_BAC, MIEN_NAM, MIEN_TRUNG)")
    is_active: bool = True


class UniversityCreate(UniversityBase):
    pass


class UniversityRead(UniversityBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    majors_count: int = 0
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# 2. Major Schemas
# --------------------------------------------------------------------------

class MajorBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="Mã ngành / mã xét tuyển (e.g. IT1, 7480201)")
    name: str = Field(..., min_length=1, max_length=300, description="Tên ngành đào tạo")
    description: str | None = None
    is_active: bool = True


class MajorCreate(MajorBase):
    university_id: UUID


class MajorRead(MajorBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    university_id: UUID
    created_at: datetime
    updated_at: datetime


class MajorDetailRead(MajorRead):
    university: UniversityRead | None = None


# --------------------------------------------------------------------------
# 3. Admission Method Schemas
# --------------------------------------------------------------------------

class AdmissionMethodBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=50, description="Mã phương thức (e.g. THPT, DGNL_HSA, XET_HOC_BA)")
    name: str = Field(..., min_length=1, max_length=250, description="Tên phương thức tuyển sinh")
    description: str | None = None
    is_active: bool = True


class AdmissionMethodCreate(AdmissionMethodBase):
    pass


class AdmissionMethodRead(AdmissionMethodBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# 4. Admission Data Source Schemas
# --------------------------------------------------------------------------

class AdmissionDataSourceBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=300)
    source_type: str = Field(default="OFFICIAL_PORTAL", max_length=100)
    source_url: str | None = Field(default=None, max_length=1000)
    publisher: str | None = Field(default=None, max_length=300)
    published_year: int = Field(..., ge=2000, le=2100)
    verified_at: datetime | None = None
    verified_by: UUID | None = None


class AdmissionDataSourceCreate(AdmissionDataSourceBase):
    pass


class AdmissionDataSourceRead(AdmissionDataSourceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# 5. Admission Rule Schemas (Versioned by Year)
# --------------------------------------------------------------------------

class AdmissionRuleBase(BaseModel):
    university_id: UUID
    major_id: UUID
    year: int = Field(..., ge=2000, le=2100, description="Năm tuyển sinh được áp dụng")
    method_id: UUID
    subject_combination: str = Field(..., min_length=1, max_length=100, description="Tổ hợp môn xét tuyển (e.g. A00, A01, D01)")
    requirements: dict[str, Any] = Field(default_factory=dict, description="Điều kiện cụ thể: điểm sàn, ngoại ngữ, v.v.")
    quota: int | None = Field(default=None, ge=0, description="Chỉ tiêu tuyển sinh")
    historical_score: float | None = Field(default=None, ge=0.0, description="Điểm chuẩn tham khảo năm trước")
    source_reference: str | None = Field(default=None, max_length=1000, description="Trích dẫn đề án hoặc văn bản chính thức")
    data_source_id: UUID | None = None
    verified_at: datetime | None = None
    verified_by: UUID | None = None
    is_active: bool = True


class AdmissionRuleCreate(AdmissionRuleBase):
    pass


class AdmissionRuleUpdate(BaseModel):
    subject_combination: str | None = Field(default=None, min_length=1, max_length=100)
    requirements: dict[str, Any] | None = None
    quota: int | None = Field(default=None, ge=0)
    historical_score: float | None = Field(default=None, ge=0.0)
    source_reference: str | None = None
    data_source_id: UUID | None = None
    verified_at: datetime | None = None
    is_active: bool | None = None


class AdmissionRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    university_id: UUID
    university_name: str = ""
    major_id: UUID
    major_name: str = ""
    year: int
    method_id: UUID
    method_code: str = ""
    method_name: str = ""
    subject_combination: str
    requirements: dict[str, Any] = Field(default_factory=dict)
    quota: int | None = None
    historical_score: float | None = None
    source_reference: str | None = None
    data_source_id: UUID | None = None
    verified_at: datetime | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# --------------------------------------------------------------------------
# 6. Student Admission Target Schemas
# --------------------------------------------------------------------------

class AdmissionTargetCreate(BaseModel):
    university_id: UUID
    major_id: UUID
    target_type: AdmissionTargetType = Field(
        ...,
        description="Phân loại nguyện vọng do học sinh tự chọn: DREAM (mơ ước), TARGET (mục tiêu chính), SAFE (an toàn).",
    )
    target_year: int = Field(default=2026, ge=2020, le=2100)
    priority_order: int = Field(default=1, ge=1, description="Thứ tự ưu tiên nguyện vọng 1, 2, 3...")
    notes: str | None = Field(default=None, max_length=1000)


class AdmissionTargetUpdate(BaseModel):
    target_type: AdmissionTargetType | None = None
    priority_order: int | None = Field(default=None, ge=1)
    notes: str | None = Field(default=None, max_length=1000)


class AdmissionTargetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    university_id: UUID
    university_code: str
    university_name: str
    major_id: UUID
    major_code: str
    major_name: str
    target_type: AdmissionTargetType
    target_year: int
    priority_order: int
    notes: str | None = None
    created_at: datetime
    updated_at: datetime
