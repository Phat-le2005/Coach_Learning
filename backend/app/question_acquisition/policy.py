"""Policy rules for URL normalization, candidate ranking, and acquisition planning."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from urllib.parse import urlparse, urlunparse

from app.core.exceptions import ApplicationError
from app.question_acquisition.models import QuestionAcquisitionStrategy
from app.question_supply.models import (
    QuestionSupplyReasonCode,
    QuestionSupplyTargetType,
    QuestionSupplyUseCase,
)
from app.questions.evaluation_eligibility import is_deterministically_auto_evaluable
from app.questions.models import Question, QuestionStatus, QuestionType


@dataclass
class RankedCandidateInfo:
    question: Question
    difficulty_in_band: bool
    runtime_eligible: bool
    selection_rank: int
    selection_score: float | None = None


@dataclass
class PlannedAcquisitionCounts:
    strategy: QuestionAcquisitionStrategy
    required_new_candidate_count: int
    existing_candidate_count: int
    external_candidate_target_count: int


class QuestionAcquisitionPolicy:
    """Deterministic policy logic for question acquisition."""

    @staticmethod
    def normalize_url(raw_url: str) -> tuple[str, str]:
        """Normalize URL deterministically and compute sha256 hash."""
        url = raw_url.strip()
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https"}:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_INVALID_SCHEME",
                f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.",
            )

        if parsed.username or parsed.password:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_CREDENTIALS_DISALLOWED",
                "Credentials embedded in URLs are not permitted.",
            )

        hostname = (parsed.hostname or "").strip().lower()
        if not hostname:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_INVALID_URL",
                "URL hostname is missing.",
            )

        # Normalize port
        port = parsed.port
        netloc = hostname
        if port is not None:
            if (scheme == "http" and port != 80) or (scheme == "https" and port != 443):
                netloc = f"{hostname}:{port}"

        # Clean path, preserve query, strip fragment
        path = parsed.path or "/"
        normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
        url_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return normalized, url_hash

    @staticmethod
    def rank_existing_candidates(
        candidates: list[Question],
        *,
        difficulty_min: float,
        difficulty_max: float,
        desired_difficulty: float | None = None,
        allowed_types: list[QuestionType] | None = None,
        require_auto_eval: bool = True,
    ) -> list[RankedCandidateInfo]:
        """Sort and rank raw DRAFT/REVIEW pipeline candidates according to deterministic criteria."""
        target_diff = desired_difficulty if desired_difficulty is not None else 0.50

        decorated: list[tuple[tuple, Question, bool, bool]] = []
        for q in candidates:
            diff = q.difficulty if q.difficulty is not None else 0.50
            in_band = difficulty_min <= diff <= difficulty_max
            runtime_eligible = (
                (allowed_types is None or q.question_type in allowed_types)
                and (not require_auto_eval or is_deterministically_auto_evaluable(q))
            )
            # Deterministic rank tuple (lower is better):
            # 1. in_band: True (0) before False (1)
            # 2. runtime_eligible: True (0) before False (1)
            # 3. status: REVIEW (0) before DRAFT (1)
            # 4. distance to desired difficulty: abs(diff - target_diff)
            # 5. deterministic tie-breaker: str(q.id)
            sort_key = (
                0 if in_band else 1,
                0 if runtime_eligible else 1,
                0 if q.status == QuestionStatus.REVIEW else 1,
                abs(diff - target_diff),
                str(q.id),
            )
            decorated.append((sort_key, q, in_band, runtime_eligible))

        decorated.sort(key=lambda item: item[0])

        ranked: list[RankedCandidateInfo] = []
        for idx, (_, q, in_band, runtime_eligible) in enumerate(decorated, start=1):
            ranked.append(
                RankedCandidateInfo(
                    question=q,
                    difficulty_in_band=in_band,
                    runtime_eligible=runtime_eligible,
                    selection_rank=idx,
                    selection_score=round(1.0 / idx, 4),
                )
            )
        return ranked

    @staticmethod
    def calculate_acquisition_plan(
        *,
        preferred_count: int,
        approved_in_band_count: int,
        fresh_in_band_count: int | None = None,
        reason_code: QuestionSupplyReasonCode | None = None,
        existing_in_band_candidates_count: int = 0,
        total_existing_candidates_count: int = 0,
    ) -> PlannedAcquisitionCounts:
        """Compute required new candidates, strategy, and external target count."""
        if reason_code == QuestionSupplyReasonCode.STUDENT_EXPOSURE_EXHAUSTED:
            effective_in_band = (
                fresh_in_band_count if fresh_in_band_count is not None else approved_in_band_count
            )
            required_new = max(1, preferred_count - effective_in_band)
        else:
            required_new = max(0, preferred_count - approved_in_band_count)

        if existing_in_band_candidates_count >= required_new:
            strategy = QuestionAcquisitionStrategy.REVIEW_EXISTING_PIPELINE
            external_target = 0
        elif existing_in_band_candidates_count > 0:
            strategy = QuestionAcquisitionStrategy.MIXED
            external_target = max(0, required_new - existing_in_band_candidates_count)
        else:
            strategy = QuestionAcquisitionStrategy.EXTERNAL_SOURCE_REQUIRED
            external_target = max(0, required_new)

        return PlannedAcquisitionCounts(
            strategy=strategy,
            required_new_candidate_count=required_new,
            existing_candidate_count=total_existing_candidates_count,
            external_candidate_target_count=external_target,
        )


class StreamIngestValidator:
    """Incremental validator for streaming PDF ingestion checking size limits and PDF magic header across arbitrary chunk boundaries."""

    PDF_MAGIC_PREFIX = b"%PDF-"
    MAGIC_LEN = len(PDF_MAGIC_PREFIX)

    def __init__(self, max_bytes: int) -> None:
        self.max_bytes = max_bytes
        self.hasher = hashlib.sha256()
        self.total_bytes = 0
        self._magic_header = bytearray()
        self._magic_checked = False

    def process_chunk(self, chunk: bytes) -> None:
        if not chunk:
            return

        self.total_bytes += len(chunk)
        if self.total_bytes > self.max_bytes:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_FILE_TOO_LARGE",
                f"File exceeded maximum size limit ({self.max_bytes} bytes).",
            )

        if not self._magic_checked:
            needed = self.MAGIC_LEN - len(self._magic_header)
            self._magic_header.extend(chunk[:needed])
            if len(self._magic_header) == self.MAGIC_LEN:
                if not bytes(self._magic_header).startswith(self.PDF_MAGIC_PREFIX):
                    raise ApplicationError(
                        422,
                        "QUESTION_ACQUISITION_NOT_PDF",
                        "Payload does not begin with valid PDF magic bytes (%PDF-).",
                    )
                self._magic_checked = True

        self.hasher.update(chunk)

    def finalize(self) -> tuple[str, int]:
        """Finalize validation and return (sha256_hex, total_bytes)."""
        if self.total_bytes == 0:
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_NOT_PDF",
                "Uploaded file or downloaded payload is empty.",
            )
        if self.total_bytes < self.MAGIC_LEN or not bytes(self._magic_header).startswith(self.PDF_MAGIC_PREFIX):
            raise ApplicationError(
                422,
                "QUESTION_ACQUISITION_NOT_PDF",
                "Downloaded file is empty or missing valid PDF magic header.",
            )
        return self.hasher.hexdigest(), self.total_bytes

