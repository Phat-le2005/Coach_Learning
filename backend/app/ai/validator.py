import json
import logging
import re
from typing import Any, TypeVar
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.ai.exceptions import (
    AIFakeCurriculumCodeError,
    AIInvalidJSONError,
    AIOutputValidationError,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Known canonical prefixes or patterns for curriculum / problem type / concept codes
CANONICAL_CODE_PATTERN = re.compile(r"^[A-Z0-9_]+$")
FAKE_CODE_MARKERS = {"FAKE", "TEST_FAKE", "HALLUCINATED", "DUMMY_CODE", "MOCK_INVALID", "UNKNOWN_CODE"}


class AIOutputValidator:
    """Robust validator for AI-generated outputs.
    
    Guarantees:
    - Pydantic validation of all structured outputs.
    - Strips code blocks and Markdown wrappers safely.
    - Catches malformed / invalid JSON and safely degrades without unhandled 500 crashes.
    - Validates curriculum and concept codes, rejecting fake/hallucinated curriculum codes.
    """

    @staticmethod
    def clean_json_markdown(content: str) -> str:
        """Strip markdown fences, leading/trailing whitespace, and json annotations."""
        if not content:
            return ""
        text = content.strip()
        # Remove markdown code fences: ```json ... ``` or ``` ... ```
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    @classmethod
    def validate_structured(
        cls,
        raw_content: str | dict[str, Any],
        schema: type[T],
        *,
        allow_fallback: bool = False,
        fallback: T | None = None,
    ) -> T:
        """Validate raw AI output string or dictionary against a Pydantic schema.
        
        Args:
            raw_content: Raw string or parsed dict returned by AI provider.
            schema: Target Pydantic model type.
            allow_fallback: If True, returns `fallback` instead of raising on error.
            fallback: Default instance to return if validation fails and allow_fallback=True.
            
        Returns:
            Validated instance of schema `T`.
            
        Raises:
            AIInvalidJSONError: If raw_content is invalid JSON syntax (and fallback not allowed).
            AIOutputValidationError: If structure does not match schema (and fallback not allowed).
        """
        parsed_dict: dict[str, Any]

        if isinstance(raw_content, dict):
            parsed_dict = raw_content
        elif isinstance(raw_content, str):
            cleaned = cls.clean_json_markdown(raw_content)
            if not cleaned:
                if allow_fallback and fallback is not None:
                    logger.warning("ai_output_validator: empty content, returning fallback")
                    return fallback
                raise AIInvalidJSONError("AI response is empty and cannot be parsed as JSON.")
            try:
                parsed_dict = json.loads(cleaned)
                if not isinstance(parsed_dict, dict):
                    if allow_fallback and fallback is not None:
                        return fallback
                    raise AIInvalidJSONError(
                        f"Expected JSON object (dict), but received {type(parsed_dict).__name__}."
                    )
            except json.JSONDecodeError as err:
                logger.warning("ai_output_validator: JSON decode failed: %s (input: %.100s...)", err, cleaned)
                if allow_fallback and fallback is not None:
                    return fallback
                raise AIInvalidJSONError(f"AI output is not valid JSON: {err.msg} at line {err.lineno}") from err
        else:
            if allow_fallback and fallback is not None:
                return fallback
            raise AIInvalidJSONError(f"Unsupported raw_content type: {type(raw_content).__name__}")

        try:
            return schema.model_validate(parsed_dict)
        except ValidationError as val_err:
            logger.warning("ai_output_validator: Pydantic validation failed: %s", val_err)
            if allow_fallback and fallback is not None:
                return fallback
            raise AIOutputValidationError(
                f"AI structured output does not match {schema.__name__}: {val_err.error_count()} errors."
            ) from val_err

    @classmethod
    def validate_curriculum_references(
        cls,
        codes: list[str],
        allowed_codes: set[str] | None = None,
        db_session: Session | None = None,
        *,
        strict: bool = True,
    ) -> list[str]:
        """Validate referenced curriculum, problem type, or concept codes.
        
        Prevents AI from hallucinating fake curriculum nodes or concepts into the learning system.
        
        Args:
            codes: List of codes mentioned in AI output.
            allowed_codes: Optional explicit set of valid canonical codes.
            db_session: Optional DB session to resolve codes against database if allowed_codes is None.
            strict: If True, raises AIFakeCurriculumCodeError on any fake code.
                   If False, returns only the subset of valid codes.
                   
        Returns:
            List of valid canonical codes.
            
        Raises:
            AIFakeCurriculumCodeError: If fake/unknown codes exist and strict=True.
        """
        if not codes:
            return []

        # If db_session provided and allowed_codes is None, populate allowed_codes from DB
        valid_registry: set[str] = set(allowed_codes) if allowed_codes is not None else set()
        if allowed_codes is None and db_session is not None:
            try:
                from app.curriculum.models import Curriculum, Chapter, Topic, ProblemType
                from app.concepts.models import Concept
                
                curr_codes = db_session.query(Curriculum.code).all()
                chap_codes = db_session.query(Chapter.code).all()
                top_codes = db_session.query(Topic.code).all()
                pt_codes = db_session.query(ProblemType.code).all()
                c_codes = db_session.query(Concept.code).all()

                for row in curr_codes + chap_codes + top_codes + pt_codes + c_codes:
                    if row[0]:
                        valid_registry.add(row[0].upper())
            except Exception as db_err:
                logger.warning("ai_output_validator: failed to load curriculum codes from DB: %s", db_err)

        fake_or_unknown: list[str] = []
        valid_codes: list[str] = []

        for code in codes:
            normalized = code.strip().upper()
            # 1. Reject invalid code syntax or suspicious fake markers
            is_suspicious_marker = any(marker in normalized for marker in FAKE_CODE_MARKERS)
            if not CANONICAL_CODE_PATTERN.match(normalized) or is_suspicious_marker:
                fake_or_unknown.append(code)
                continue

            # 2. Check against valid registry if registry is available
            if valid_registry and normalized not in valid_registry:
                fake_or_unknown.append(code)
                continue

            valid_codes.append(normalized)

        if fake_or_unknown:
            logger.warning("ai_output_validator: detected fake/hallucinated curriculum codes: %s", fake_or_unknown)
            if strict:
                raise AIFakeCurriculumCodeError(
                    f"Hallucinated or nonexistent curriculum codes detected: {', '.join(fake_or_unknown)}"
                )

        return valid_codes
