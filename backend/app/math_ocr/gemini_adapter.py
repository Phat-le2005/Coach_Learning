"""Gemini-powered Handwritten Math Stylus OCR Adapter.

Adopts the ultra-fast pipeline techniques from backend/math-ocr-pipeline:
1. 1-Tile WebP & Grayscale optimization (<= 600px).
2. Digital Ink Stroke Telemetry fusion (line clusters, horizontal bars, dots).
3. Zero-thinking latency via ThinkingConfig(thinking_level="MINIMAL") or thinking_budget=0.
4. Low MediaResolution to minimize Vision Token budget and latency.
5. Persistent genai.Client caching for HTTP/2 & TLS keep-alive.
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.exceptions import ApplicationError
from app.math_ink.schemas import InkStroke
from app.math_ocr.adapter import MathOCRAdapter, MockMathOCRAdapter
from app.math_ocr.schemas import OCRRecognizeResponse
from app.math_solutions.schemas import StepKind

logger = logging.getLogger(__name__)

# Cache genai.Client by API key to reuse TLS / HTTP/2 connection
_CLIENT_CACHE: dict[str, Any] = {}
_MODEL_STRATEGY_CACHE: dict[str, str] = {}
_LAST_WORKING_MODEL: str | None = None


def _get_genai_client(api_key: str) -> Any:
    client = _CLIENT_CACHE.get(api_key)
    if client is None:
        try:
            from google import genai

            client = genai.Client(api_key=api_key)
            _CLIENT_CACHE[api_key] = client
        except Exception as exc:
            logger.error("Failed to initialize google.genai Client: %s", exc)
            raise ApplicationError(
                503,
                "OCR_INITIALIZATION_FAILED",
                f"Không thể khởi tạo Gemini OCR Client: {exc}",
            ) from exc
    return client


class GeminiOCRJsonOutput(BaseModel):
    latex: str = Field(description="Mã LaTeX của toàn bộ công thức nhận diện được")
    raw_text: str = Field(default="", description="Văn bản gốc tiếng Việt hoặc ký hiệu")
    explanation_text: str | None = Field(
        default=None, description="Lời giải thích tiếng Việt đi kèm nếu có"
    )
    suggested_step_type: str = Field(
        default="CUSTOM",
        description="Loại bước: DERIVATIVE_CALCULATION, ROOT_FINDING, VARIATION_TABLE, CONCLUSION, EXPLANATION, CUSTOM",
    )
    detected_symbols: list[str] = Field(
        default_factory=list, description="Danh sách các ký hiệu toán học chính"
    )
    confidence: float = Field(default=0.98, ge=0.0, le=1.0)
    alternative_latex: list[str] = Field(
        default_factory=list, description="Cách đọc thay thế khả dĩ nếu có"
    )


GEMINI_OCR_SYSTEM_INSTRUCTION = """Bạn là công cụ nhận diện chữ viết tay toán học (Handwritten Math Stylus OCR) tốc độ cao, bám sát 100% nét chữ của học sinh.
Nhiệm vụ: Chuyển đổi hình ảnh nét viết tay toán học và siêu dữ liệu nét vẽ (Stroke Telemetry) thành JSON bám sát chính xác từng nét chữ.

CÁC NGUYÊN TẮC BẮT BUỘC:
1. KHÔNG giải toán, KHÔNG sửa lỗi sai của học sinh (Ví dụ: học sinh viết 2+2=5 thì giữ nguyên 2+2=5 để hệ thống chấm điểm sư phạm).
2. Trường `latex`: Trả về công thức toán học định dạng LaTeX chuẩn (KHÔNG bọc ký hiệu $$). Các từ tiếng Việt nằm trong \\text{...}.
3. Phân biệt rõ ràng:
   - Dấu gạch ngang giữa 2 số là gạch phân số \\frac{a}{b} hoặc dấu trừ.
   - Chữ x, biến số, và dấu nhân (\\cdot).
   - Đạo hàm y' hoặc f'(x), cực trị, bảng xét dấu/biến thiên.
4. Trường `suggested_step_type`: Phân loại chính xác 1 trong các giá trị:
   - DERIVATIVE_CALCULATION: Tính đạo hàm bậc nhất hoặc bậc hai.
   - ROOT_FINDING: Giải phương trình f'(x) = 0 tìm nghiệm/điểm tới hạn.
   - VARIATION_TABLE: Bảng biến thiên hoặc bảng xét dấu.
   - CONCLUSION: Kết luận khoảng đồng biến, nghịch biến, cực đại, cực tiểu.
   - EXPLANATION: Lập luận giải thích bằng lời văn, giả thiết.
   - CUSTOM: Các phép biến đổi thông thường khác.
5. Trường `explanation_text`: Lời giải thích tiếng Việt nếu có trong nét viết, hoặc null.
6. Trường `detected_symbols`: Mảng ký hiệu toán học chính (ví dụ: ["y'", "3x^2", "\\int", "="]).
7. Trường `confidence`: Độ tin cậy từ 0.8 đến 1.0."""


class GeminiMathOCRAdapter(MathOCRAdapter):
    """Production Math OCR Adapter powered by Google Gemini 3.8 / Flash."""

    def __init__(
        self,
        api_key: str | None = None,
        model_name: str | None = None,
        fast_mode: bool = True,
    ) -> None:
        settings = get_settings()
        self.api_key = (
            api_key
            or (settings.ai_api_key.get_secret_value() if settings.ai_api_key else "")
            or os.getenv("GEMINI_API_KEY", "")
            or os.getenv("GEMINI_API_KEYS", "").split(",")[0].strip()
        )
        self.model_name = (
            model_name
            or getattr(settings, "gemini_ocr_model", None)
            or settings.ai_model_fast
            or "gemini-3.8-flash"
        )
        self.fast_mode = fast_mode
        self._mock_fallback = MockMathOCRAdapter()

    def recognize(
        self,
        strokes: list[InkStroke],
        hint_topic: str | None = None,
    ) -> OCRRecognizeResponse:
        settings = get_settings()

        # In test environment without an API key, use deterministic mock
        if (settings.app_env == "test" or not self.api_key) and not self.api_key:
            if settings.app_env == "test":
                return self._mock_fallback.recognize(strokes, hint_topic=hint_topic)
            raise ApplicationError(
                503,
                "OCR_NOT_CONFIGURED",
                "Chưa cấu hình GEMINI_API_KEY cho hệ thống nhận diện chữ viết tay toán học.",
            )

        client = _get_genai_client(self.api_key)

        # 1. Rasterize & Optimize to 1-Tile WebP / PNG
        image_bytes, mime_type, telemetry = self._rasterize_and_optimize(strokes)

        # 2. Build Context Prompt with Stroke Telemetry
        prompt_parts: list[Any] = []

        # Image part
        from google.genai import types

        prompt_parts.append(
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        )

        telemetry_note = (
            f"Thông tin nét bút: {telemetry['pen_strokes']} nét vẽ, "
            f"khoảng {telemetry['estimated_lines']} dòng chữ."
        )
        if telemetry.get("horizontal_bars"):
            telemetry_note += f" Phát hiện {telemetry['horizontal_bars']} nét gạch ngang (dấu trừ hoặc gạch phân số)."
        if hint_topic:
            telemetry_note += f" Chủ đề toán học: {hint_topic}."

        prompt_parts.append(
            f"Hãy nhận diện vùng chữ viết tay trong ảnh. {telemetry_note}\n"
            f"Xuất kết quả đúng cấu trúc JSON yêu cầu."
        )

        # 3. Build Turbo Thinking (thinking_budget=0) and Media Resolution Config
        thinking_cfg = None
        if hasattr(types, "ThinkingConfig"):
            try:
                thinking_cfg = types.ThinkingConfig(
                    thinking_budget=0, include_thoughts=False
                )
            except Exception:
                try:
                    thinking_cfg = types.ThinkingConfig(
                        thinking_level="LOW", include_thoughts=False
                    )
                except Exception:
                    thinking_cfg = None

        cfg_kwargs: dict[str, Any] = {
            "system_instruction": GEMINI_OCR_SYSTEM_INSTRUCTION,
            "temperature": 0.0,
            "response_mime_type": "application/json",
            "response_schema": GeminiOCRJsonOutput,
        }
        if thinking_cfg is not None:
            cfg_kwargs["thinking_config"] = thinking_cfg
        if hasattr(types, "MediaResolution"):
            cfg_kwargs["media_resolution"] = types.MediaResolution.MEDIA_RESOLUTION_LOW

        gen_config = types.GenerateContentConfig(**cfg_kwargs)

        # 4. Fallback chain: prioritize cached working model & gemini-3.5-flash (zero 503 delay)
        global _LAST_WORKING_MODEL
        model_candidates = [
            _LAST_WORKING_MODEL,
            "gemini-3.5-flash",
            self.model_name,
            "gemini-3.8-flash",
            "gemini-3.5-flash-lite",
        ]
        # Keep unique non-empty models preserving order
        seen = set()
        model_queue = [m for m in model_candidates if m and not (m in seen or seen.add(m))]

        last_error = None
        for candidate_model in model_queue:
            # Try with configured thinking, fallback to without thinking if rejected
            configs_to_try = [gen_config]
            if thinking_cfg is not None:
                # Also prepare a config without thinking in case model doesn't support the level
                no_think_kwargs = dict(cfg_kwargs)
                no_think_kwargs.pop("thinking_config", None)
                configs_to_try.append(types.GenerateContentConfig(**no_think_kwargs))

            for current_cfg in configs_to_try:
                try:
                    response = client.models.generate_content(
                        model=candidate_model,
                        contents=prompt_parts,
                        config=current_cfg,
                    )
                    text = response.text or ""
                    parsed = json.loads(text)
                    _LAST_WORKING_MODEL = candidate_model
                    return self._to_response(parsed, strokes)
                except Exception as exc:
                    last_error = exc
                    err_str = str(exc).lower()
                    if "thinking" in err_str and current_cfg is not configs_to_try[-1]:
                        logger.info("Retrying %s without thinking_config due to: %s", candidate_model, exc)
                        continue
                    logger.warning(
                        "Gemini OCR model %s failed (%s), attempting next fallback...",
                        candidate_model,
                        exc,
                    )
                    if any(k in err_str for k in ("401", "403", "api_key", "unauthorized")):
                        raise ApplicationError(
                            503,
                            "OCR_API_KEY_INVALID",
                            f"GEMINI_API_KEY không hợp lệ hoặc đã hết hạn: {exc}",
                        ) from exc
                    break

        logger.error("All Gemini OCR models failed. Last error: %s", last_error)
        raise ApplicationError(
            503,
            "OCR_RECOGNITION_FAILED",
            f"Nhận diện chữ viết tay qua Gemini thất bại: {last_error}",
        ) from last_error

    def recognize_with_alternatives(
        self,
        strokes: list[InkStroke],
        hint_topic: str | None = None,
    ) -> OCRRecognizeResponse:
        return self.recognize(strokes, hint_topic=hint_topic)

    def _rasterize_and_optimize(
        self, strokes: list[InkStroke]
    ) -> tuple[bytes, str, dict[str, Any]]:
        """Render vector strokes to high-contrast 1-tile cropped WebP image."""
        try:
            from PIL import Image, ImageDraw, ImageOps
        except ImportError as exc:
            raise ApplicationError(
                503,
                "OCR_LOCAL_DEPENDENCY_MISSING",
                "Local OCR requires Pillow library.",
            ) from exc

        pens = [s for s in strokes if s.tool == "PEN"]
        if not pens:
            raise ApplicationError(
                422, "NO_PEN_STROKES_FOR_OCR", "Không tìm thấy nét bút để nhận diện."
            )

        width_canvas, height_canvas = 794, 1123
        xmin, ymin, xmax, ymax = width_canvas, height_canvas, 0.0, 0.0

        for s in pens:
            for p in s.points:
                x = min(p.x * width_canvas, width_canvas - 1)
                y = min(p.y * height_canvas, height_canvas - 1)
                xmin, ymin = min(xmin, x), min(ymin, y)
                xmax, ymax = max(xmax, x), max(ymax, y)

        margin = 24
        left = max(0, int(xmin) - margin)
        top = max(0, int(ymin) - margin)
        right = min(width_canvas, int(xmax) + margin + 1)
        bottom = min(height_canvas, int(ymax) + margin + 1)

        crop_w = max(4, right - left)
        crop_h = max(4, bottom - top)

        image = Image.new("RGB", (crop_w, crop_h), "white")
        draw = ImageDraw.Draw(image)

        for s in pens:
            coords = [
                (
                    round(min(p.x * width_canvas, width_canvas - 1) - left),
                    round(min(p.y * height_canvas, height_canvas - 1) - top),
                )
                for p in s.points
            ]
            thickness = max(2, min(12, int(round(s.width * 1.5))))
            if len(coords) == 1:
                x, y = coords[0]
                rad = max(1, thickness // 2)
                draw.ellipse((x - rad, y - rad, x + rad, y + rad), fill="black")
            else:
                draw.line(coords, fill="black", width=thickness, joint="curve")
                rad = max(1, thickness // 2)
                for x, y in (coords[0], coords[-1]):
                    draw.ellipse((x - rad, y - rad, x + rad, y + rad), fill="black")

        # 1-Tile Resizing: Keep max dimension <= 600px for instant low-token processing
        max_dim = 600
        if max(crop_w, crop_h) > max_dim:
            scale = max_dim / float(max(crop_w, crop_h))
            final_w = max(16, int(round(crop_w * scale)))
            final_h = max(16, int(round(crop_h * scale)))
            image = image.resize((final_w, final_h), Image.Resampling.BILINEAR)

        # Grayscale & Autocontrast
        gray = ImageOps.grayscale(image)
        gray = ImageOps.autocontrast(gray, cutoff=0)

        # Try WebP format first (Turbo 1-tile), fall back to PNG
        buf = io.BytesIO()
        mime_type = "image/webp"
        try:
            gray.save(buf, format="WEBP", quality=80, method=0)
        except Exception:
            buf = io.BytesIO()
            gray.save(buf, format="PNG", optimize=True)
            mime_type = "image/png"

        # Compute telemetry
        telemetry = self._compute_telemetry(pens, left, top, crop_w, crop_h)
        return buf.getvalue(), mime_type, telemetry

    @staticmethod
    def _compute_telemetry(
        strokes: list[InkStroke], left: int, top: int, width: int, height: int
    ) -> dict[str, Any]:
        """Extract geometric stroke signals to guide Gemini line & symbol recognition."""
        total_pts = sum(len(s.points) for s in strokes)
        horizontal_bars = 0
        dots = 0
        y_centers = []

        for s in strokes:
            if not s.points:
                continue
            xs = [p.x for p in s.points]
            ys = [p.y for p in s.points]
            w = max(xs) - min(xs)
            h = max(ys) - min(ys)
            y_centers.append(sum(ys) / len(ys))

            if len(s.points) <= 2 and max(w, h) < 0.02:
                dots += 1
            elif w > 0.04 and h < 0.02:
                horizontal_bars += 1

        # Simple clustering along Y axis
        estimated_lines = 1
        if len(y_centers) > 2:
            sorted_y = sorted(y_centers)
            gaps = [sorted_y[i + 1] - sorted_y[i] for i in range(len(sorted_y) - 1)]
            avg_gap = sum(gaps) / max(len(gaps), 1)
            line_breaks = sum(1 for g in gaps if g > max(0.04, avg_gap * 1.5))
            estimated_lines = min(10, max(1, line_breaks + 1))

        return {
            "pen_strokes": len(strokes),
            "total_points": total_pts,
            "horizontal_bars": horizontal_bars,
            "dots": dots,
            "estimated_lines": estimated_lines,
        }

    @staticmethod
    def _to_response(
        data: dict[str, Any], strokes: list[InkStroke]
    ) -> OCRRecognizeResponse:
        latex = str(data.get("latex") or "").strip()
        explanation = data.get("explanation_text")
        if explanation:
            explanation = str(explanation).strip() or None

        raw_step_kind = str(data.get("suggested_step_type") or "CUSTOM").upper()
        step_type = StepKind.CUSTOM
        try:
            step_type = StepKind(raw_step_kind)
        except ValueError:
            # Heuristic fallback based on latex content
            if "= 0" in latex or "\\Leftrightarrow" in latex or "x =" in latex:
                step_type = StepKind.ROOT_FINDING
            elif "y'" in latex or "f'(x)" in latex or "\\int" in latex:
                step_type = StepKind.DERIVATIVE_CALCULATION
            elif any(k in latex.lower() for k in ("đồng biến", "nghịch biến")):
                step_type = StepKind.CONCLUSION
            else:
                step_type = StepKind.EXPLANATION

        symbols = [str(s) for s in data.get("detected_symbols") or [] if s]
        alternatives = [str(a) for a in data.get("alternative_latex") or [] if a][:2]
        confidence = float(data.get("confidence", 0.98))
        confidence = max(0.0, min(1.0, confidence))

        return OCRRecognizeResponse(
            latex=latex,
            confidence=confidence,
            suggested_step_type=step_type,
            explanation_text=explanation,
            detected_symbols=symbols,
            alternative_latex=alternatives,
        )
