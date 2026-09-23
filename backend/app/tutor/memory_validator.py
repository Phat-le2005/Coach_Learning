from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING
from uuid import UUID

from app.concepts.models import Concept
from app.curriculum.models import ProblemType
from app.tutor.models import LearningMemoryType
from app.tutor.schemas import ProposedMemoryItem

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Minimum confidence threshold required to persist a memory
MIN_MEMORY_CONFIDENCE = 0.50

# Maximum and minimum length of memory content
MIN_VALUE_LENGTH = 10
MAX_VALUE_LENGTH = 500

# 1. Raw Chat Transcript Regexes (cấm lưu raw chat)
RAW_CHAT_PATTERNS = [
    re.compile(r"^(học sinh|gia sư|ai|user|assistant|tutor|em|thầy|cô)\s*:\s*", re.IGNORECASE),
    re.compile(r"\n\s*(học sinh|gia sư|ai|user|assistant|tutor|em|thầy|cô)\s*:\s*", re.IGNORECASE),
    re.compile(r"\b(em vừa hỏi|thầy vừa nói|câu trả lời của em là|cho em xin đáp án|thầy giải giúp em)\b", re.IGNORECASE),
]

# 2. Casual Conversation Regexes (cấm lưu tán gẫu, chào hỏi)
CASUAL_CONVERSATION_PATTERN = re.compile(
    r"\b(chào bạn|xin chào|hello|hi\b|tạm biệt|goodbye|bye bye|cảm ơn (bạn|thầy|cô|ai)|okie|dạ vâng ạ|haha|hihi|hehe|hôm nay thế nào|thời tiết hôm nay|ăn cơm|uống trà|chơi game|đi chơi|xem phim)\b",
    re.IGNORECASE,
)

# 3. Temporary Emotion Regexes (cấm lưu cảm xúc nhất thời)
TEMPORARY_EMOTION_PATTERN = re.compile(
    r"\b(đang mệt|mệt mỏi quá|buồn ngủ|đang chán|chán học|hơi nản|tâm trạng không tốt|đau đầu|đau bụng|stress quá|vui vẻ|phấn khởi|bực mình|tức giận|hơi lười hôm nay)\b",
    re.IGNORECASE,
)

# 4. Irrelevant Personal Data & Sensitive Regexes (cấm lưu đời tư, nhạy cảm)
SENSITIVE_DATA_PATTERNS = [
    re.compile(r"(\+?84|0)\d{9,10}\b"),  # Phone number
    re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"),  # Email
    re.compile(r"\b(người yêu|bạn gái|bạn trai|crush|tỏ tình|chia tay|hẹn hò)\b", re.IGNORECASE),  # Romance
    re.compile(r"\b(mật khẩu|password|tài khoản ngân hàng|số cccd|chính trị|đảng phái|tôn giáo|lương|tiền lương)\b", re.IGNORECASE),  # Sensitive
    re.compile(r"\b(nhà ở|quê ở|địa chỉ tại|số nhà|quận \d+|phường \d+)\b", re.IGNORECASE),  # Address
]


class MemoryValidationResult:
    def __init__(self, is_valid: bool, reason: str = "") -> None:
        self.is_valid = is_valid
        self.reason = reason


class MemoryValidator:
    """Validates proposed learning memories against strict privacy and academic rules.
    
    Guarantees:
    - Never persists casual conversations or transient moods.
    - Never persists sensitive, personal, or raw conversational chat logs.
    - Strictly checks academic reference validity when problem_type or concept is linked.
    """

    @classmethod
    def validate(
        cls,
        item: ProposedMemoryItem,
        session: Session,
    ) -> MemoryValidationResult:
        val = item.value.strip()

        # 1. Length validation
        if len(val) < MIN_VALUE_LENGTH:
            return MemoryValidationResult(
                False, f"Nội dung quá ngắn ({len(val)} ký tự, tối thiểu {MIN_VALUE_LENGTH})."
            )
        if len(val) > MAX_VALUE_LENGTH:
            return MemoryValidationResult(
                False, f"Nội dung quá dài ({len(val)} ký tự, tối đa {MAX_VALUE_LENGTH})."
            )

        # 2. Confidence threshold
        if item.confidence < MIN_MEMORY_CONFIDENCE:
            return MemoryValidationResult(
                False,
                f"Độ tin cậy {item.confidence:.2f} dưới ngưỡng tối thiểu {MIN_MEMORY_CONFIDENCE:.2f}.",
            )

        # 3. Raw Chat Detection
        for pattern in RAW_CHAT_PATTERNS:
            if pattern.search(val):
                return MemoryValidationResult(
                    False, "Phát hiện định dạng hội thoại hoặc raw chat transcript; từ chối lưu."
                )

        # 4. Casual Conversation Filter
        if CASUAL_CONVERSATION_PATTERN.search(val):
            return MemoryValidationResult(
                False, "Phát hiện hội thoại chào hỏi, tán gẫu (casual conversation); từ chối lưu."
            )

        # 5. Temporary Emotion Filter
        if TEMPORARY_EMOTION_PATTERN.search(val):
            return MemoryValidationResult(
                False, "Phát hiện cảm xúc nhất thời (temporary emotion); từ chối lưu."
            )

        # 6. Sensitive and Irrelevant Personal Data Filter
        for pattern in SENSITIVE_DATA_PATTERNS:
            if pattern.search(val):
                return MemoryValidationResult(
                    False, "Phát hiện thông tin đời tư hoặc dữ liệu nhạy cảm; từ chối lưu."
                )

        # 7. Academic Reference Validation (Optional foreign keys)
        if item.problem_type_id:
            pt = session.get(ProblemType, item.problem_type_id)
            if not pt:
                return MemoryValidationResult(
                    False, f"Mã dạng bài (problem_type_id={item.problem_type_id}) không tồn tại."
                )

        if item.concept_id:
            concept = session.get(Concept, item.concept_id)
            if not concept:
                return MemoryValidationResult(
                    False, f"Mã khái niệm (concept_id={item.concept_id}) không tồn tại."
                )

        # 8. Type-specific semantic checks
        if item.type in (LearningMemoryType.PERSISTENT_DIFFICULTY, LearningMemoryType.PERSISTENT_MISCONCEPTION):
            # Academic difficulties should not be purely generic
            if len(val.split()) < 3:
                return MemoryValidationResult(
                    False, "Khó khăn học tập hoặc hiểu nhầm cần mô tả rõ ràng (tối thiểu 3 từ)."
                )

        return MemoryValidationResult(True, "Hợp lệ")
