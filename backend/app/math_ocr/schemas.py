from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from app.math_solutions.schemas import StepKind


class OCRRecognizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    page_index: int = Field(ge=0, le=29, description="Chỉ số trang chứa nét vẽ cần nhận diện (0-29)")
    stroke_ids: list[UUID] | None = Field(default=None, description="Danh sách ID nét vẽ được chọn để nhận diện, hoặc None để nhận diện cả trang")
    hint_topic: str | None = Field(default=None, max_length=200, description="Gợi ý chủ đề bài toán để tăng độ chính xác của mô hình")


class OCRRecognizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    latex: str = Field(description="Công thức LaTeX toán học được nhận diện từ nét vẽ")
    confidence: float = Field(ge=0, le=1, description="Độ tin cậy của kết quả nhận diện (0.0 - 1.0)")
    suggested_step_type: StepKind = Field(description="Loại bước giải được gợi ý (TRANSFORMATION, CALCULATION, CONCLUSION, DEDUCTION)")
    explanation_text: str | None = Field(default=None, description="Văn bản diễn giải tiếng Việt kèm theo (nếu phát hiện)")
    detected_symbols: list[str] = Field(default_factory=list, description="Các ký hiệu toán học chính được phát hiện trong nét vẽ")
