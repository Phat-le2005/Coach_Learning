from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AdmissionFactItem(BaseModel):
    """Verified factual admission regulation or benchmark.

    Strict Guarantee: Must contain year and source_reference.
    """
    model_config = ConfigDict(extra="ignore")

    institution_major: str = Field(description="Tên trường và tên ngành (e.g. Đại học Bách Khoa Hà Nội - Khoa học Máy tính)")
    year: int = Field(ge=2000, le=2100, description="Năm tuyển sinh áp dụng")
    method: str = Field(description="Phương thức tuyển sinh (e.g. THPT, ĐGNL HSA)")
    subject_combination: str = Field(description="Tổ hợp môn (e.g. A00, A01)")
    criteria_summary: str = Field(description="Tóm tắt điều kiện, chỉ tiêu, điểm sàn")
    historical_score: float | None = Field(default=None, description="Điểm chuẩn tham khảo năm trước nếu có")
    source_reference: str = Field(..., min_length=1, description="Trích dẫn đề án hoặc văn bản chính thức")


class AdmissionEstimateItem(BaseModel):
    """Realistic comparative estimate between student performance and admission cutoffs.

    Strict Guarantee: No false certainty ('chắc chắn đậu').
    """
    model_config = ConfigDict(extra="ignore")

    target_type: str = Field(description="Phân loại nguyện vọng: DREAM, TARGET, hoặc SAFE")
    institution_major: str = Field(description="Trường và ngành mục tiêu")
    subject_combination: str = Field(description="Tổ hợp môn xét tuyển")
    current_estimated_total_score: float | None = Field(default=None, description="Điểm ước tính hiện tại của tổ hợp")
    historical_benchmark: float | None = Field(default=None, description="Điểm chuẩn tham khảo")
    gap_analysis: str = Field(description="Khoảng cách điểm số và phân tích chênh lệch")
    feasibility_assessment: str = Field(description="Đánh giá mức độ khả thi một cách khách quan, có tính xác suất")
    missing_information_note: str | None = Field(default=None, description="Lưu ý về các dữ liệu còn thiếu")


class AdmissionRecommendationItem(BaseModel):
    """Actionable and strategic recommendation for test preparation."""
    model_config = ConfigDict(extra="ignore")

    target_focus: str = Field(description="Nguyện vọng hoặc môn học trọng tâm")
    subject_or_chapter: str = Field(description="Môn học hoặc chương kiến thức cần ưu tiên")
    action_plan: str = Field(description="Hành động cụ thể (dạng bài cần luyện, phương pháp nâng điểm)")
    strategic_advice: str = Field(description="Lời khuyên chiến lược (phương thức thi, phân bổ thời gian)")


class AdmissionAIStructuredOutput(BaseModel):
    """Structured output expected from the AI Gateway."""
    model_config = ConfigDict(extra="ignore")

    facts: list[AdmissionFactItem] = Field(default_factory=list)
    estimates: list[AdmissionEstimateItem] = Field(default_factory=list)
    recommendations: list[AdmissionRecommendationItem] = Field(default_factory=list)
    missing_data_summary: list[str] = Field(default_factory=list)
    student_friendly_advice: str = Field(default="")


class AdmissionAIInputContext(BaseModel):
    """Compact context gathered from the Student Digital Twin and relational models.

    Strict Guarantee: Does NOT include the full raw mastery graph.
    """
    model_config = ConfigDict(extra="ignore")

    student_id: UUID
    student_name: str
    student_grade: str
    academic_goals: list[dict[str, Any]] = Field(default_factory=list)
    admission_targets: list[dict[str, Any]] = Field(default_factory=list)
    verified_rules: list[dict[str, Any]] = Field(default_factory=list)
    subject_performances: list[dict[str, Any]] = Field(default_factory=list)
    recent_mock_exams: list[dict[str, Any]] = Field(default_factory=list)
    missing_data_notices: list[str] = Field(default_factory=list)


class AdmissionAssistantRequest(BaseModel):
    target_id: UUID | None = Field(default=None, description="Tùy chọn ID nguyện vọng cụ thể cần tập trung tư vấn")
    focus_year: int | None = Field(default=None, description="Năm tuyển sinh cần tập trung (mặc định 2026)")
    user_query: str | None = Field(default=None, max_length=1000, description="Câu hỏi hoặc băn khoăn cụ thể của học sinh")


class AdmissionAssistantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: UUID
    facts: list[AdmissionFactItem]
    estimates: list[AdmissionEstimateItem]
    recommendations: list[AdmissionRecommendationItem]
    missing_data_summary: list[str]
    student_friendly_advice: str
    is_fallback: bool = False
    generated_at: datetime
