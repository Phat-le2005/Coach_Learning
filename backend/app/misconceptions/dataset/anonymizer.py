from __future__ import annotations

import hashlib
import re
from typing import Any


class PIISanitizationError(ValueError):
    """Raised when critical unredacted PII is detected and cannot be safely exported."""


class PIISanitizer:
    """Detects and scrubs personally identifiable information (PII) including:
    - Personal names
    - Emails
    - Phone numbers (VN standard and international)
    - School-specific references
    - Parent / family metadata.
    """

    # Email pattern
    EMAIL_PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    )

    # Phone number pattern (Vietnam 10-11 digits and international +84)
    PHONE_PATTERN = re.compile(
        r"(?:\+?84|0)(?:3[2-9]|5[689]|7[06-9]|8[1-9]|9[0-9])[\s.-]?\d{3}[\s.-]?\d{4}\b"
    )

    # School identifiers
    SCHOOL_PATTERN = re.compile(
        r"\b(?:Trường\s+(?:THPT|THCS|Tiểu\s+học|Đại\s+học|Cao\s+đẳng)|THPT|THCS)\s+[\w\sÀ-ỹ]+?(?=[,.\n]|$)",
        re.IGNORECASE,
    )

    # Student / Parent name declaration patterns
    NAME_DECLARATION_PATTERN = re.compile(
        r"\b(?:Họ\s+và\s+tên|Học\s+sinh|Em\s+tên\s+là|Phụ\s+huynh|Cha\/mẹ)\s*:\s*[\w\sÀ-ỹ]+?(?=[,.\n]|$)",
        re.IGNORECASE,
    )

    @classmethod
    def sanitize_text(cls, text: str) -> str:
        """Sanitize a text field by redacting any discovered PII."""
        if not text:
            return ""

        redacted = text
        redacted = cls.EMAIL_PATTERN.sub("[REDACTED_EMAIL]", redacted)
        redacted = cls.PHONE_PATTERN.sub("[REDACTED_PHONE]", redacted)
        redacted = cls.NAME_DECLARATION_PATTERN.sub("[REDACTED_NAME]", redacted)
        redacted = cls.SCHOOL_PATTERN.sub("[REDACTED_SCHOOL]", redacted)
        return redacted

    @classmethod
    def contains_pii(cls, text: str) -> bool:
        """Check whether unredacted PII patterns exist in the text."""
        if not text:
            return False
        if cls.EMAIL_PATTERN.search(text):
            return True
        if cls.PHONE_PATTERN.search(text):
            return True
        if cls.NAME_DECLARATION_PATTERN.search(text):
            return True
        if cls.SCHOOL_PATTERN.search(text):
            return True
        return False

    @classmethod
    def generate_anonymous_sample_id(cls, content_key: str) -> str:
        """Generate a deterministic, pseudonymized sample identifier."""
        digest = hashlib.sha256(content_key.encode("utf-8")).hexdigest()[:12]
        return f"smp_{digest}"

    @classmethod
    def sanitize_sample_dict(cls, raw: dict[str, Any]) -> dict[str, Any]:
        """Strip forbidden PII keys and sanitize all text values."""
        forbidden_keys = {
            "name",
            "full_name",
            "student_name",
            "email",
            "phone",
            "phone_number",
            "school",
            "school_name",
            "parent",
            "parent_id",
            "parent_name",
            "parent_email",
            "parent_phone",
            "user_id",
            "student_id",
        }

        sanitized: dict[str, Any] = {}
        for k, v in raw.items():
            if k.lower() in forbidden_keys:
                continue
            if isinstance(v, str):
                sanitized[k] = cls.sanitize_text(v)
            else:
                sanitized[k] = v

        return sanitized
