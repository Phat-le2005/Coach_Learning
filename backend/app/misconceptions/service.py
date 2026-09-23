from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import ApplicationError
from app.misconceptions.models import (
    MisconceptionDefinition,
    StudentMisconception,
    StudentMisconceptionStatus,
)
from app.students.models import StudentProfile

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MisconceptionPolicy:
    confirmation_threshold: float = 0.65
    minimum_occurrences: int = 2
    default_confidence_increment: float = 0.35

    def __post_init__(self) -> None:
        if not 0.0 < self.confirmation_threshold <= 1.0:
            raise ValueError("confirmation_threshold must be in (0, 1]")
        if self.minimum_occurrences < 2:
            raise ValueError("minimum_occurrences must be at least 2")
        if not 0.0 < self.default_confidence_increment <= 1.0:
            raise ValueError("default_confidence_increment must be in (0, 1]")


class MisconceptionService:
    """Apply explicit deterministic evidence to a student's misconception state."""

    def __init__(
        self,
        session: Session,
        policy: MisconceptionPolicy | None = None,
    ) -> None:
        self.session = session
        self.policy = policy or MisconceptionPolicy()

    def record_evidence(
        self,
        student_id: UUID,
        misconception_definition_id: UUID,
        *,
        confidence_increment: float | None = None,
        detected_at: datetime | None = None,
        commit: bool = True,
    ) -> StudentMisconception:
        definition = self._definition_or_404(misconception_definition_id)
        if not definition.is_active:
            raise ApplicationError(
                409,
                "MISCONCEPTION_DEFINITION_INACTIVE",
                "Evidence cannot be recorded for an inactive misconception definition.",
            )
        self._lock_student(student_id)
        row = self._state(student_id, misconception_definition_id, for_update=True)
        occurred_at = self._aware(detected_at or datetime.now(timezone.utc))
        increment = (
            self.policy.default_confidence_increment
            if confidence_increment is None
            else confidence_increment
        )
        self._validate_increment(increment)

        if row is None:
            row = StudentMisconception(
                student_id=student_id,
                misconception_definition_id=misconception_definition_id,
                confidence=0.0,
                occurrence_count=0,
                status=StudentMisconceptionStatus.SUSPECTED,
                first_detected_at=occurred_at,
                last_detected_at=occurred_at,
                resolved_at=None,
            )
            self.session.add(row)
        elif row.status == StudentMisconceptionStatus.RESOLVED:
            assert row.resolved_at is not None
            if occurred_at <= self._aware(row.resolved_at):
                raise ApplicationError(
                    409,
                    "MISCONCEPTION_EVIDENCE_STALE",
                    "Evidence detected before resolution cannot reopen a misconception.",
                )
            row.status = StudentMisconceptionStatus.SUSPECTED
            row.resolved_at = None
            row.confidence = 0.0

        row.occurrence_count += 1
        row.first_detected_at = self._earliest(row.first_detected_at, occurred_at)
        row.last_detected_at = self._latest(row.last_detected_at, occurred_at)
        self._increase(row, increment)
        self._confirm(row)
        self._finish(commit)
        logger.info(
            "Misconception evidence recorded (student_id=%s, definition_id=%s, occurrences=%d, status=%s)",
            student_id,
            misconception_definition_id,
            row.occurrence_count,
            row.status.value,
        )
        return row

    def increase_confidence(
        self,
        student_id: UUID,
        misconception_definition_id: UUID,
        amount: float,
        *,
        commit: bool = True,
    ) -> StudentMisconception:
        self._validate_increment(amount)
        row = self._state_or_404(
            student_id, misconception_definition_id, for_update=True
        )
        if row.status == StudentMisconceptionStatus.RESOLVED:
            raise ApplicationError(
                409,
                "MISCONCEPTION_ALREADY_RESOLVED",
                "Record new evidence to reopen a resolved misconception.",
            )
        self._increase(row, amount)
        self._finish(commit)
        return row

    def confirm_if_threshold(
        self,
        student_id: UUID,
        misconception_definition_id: UUID,
        *,
        commit: bool = True,
    ) -> StudentMisconception:
        row = self._state_or_404(
            student_id, misconception_definition_id, for_update=True
        )
        self._confirm(row)
        self._finish(commit)
        return row

    def resolve(
        self,
        student_id: UUID,
        misconception_definition_id: UUID,
        *,
        resolved_at: datetime | None = None,
        commit: bool = True,
    ) -> StudentMisconception:
        row = self._state_or_404(
            student_id, misconception_definition_id, for_update=True
        )
        if row.status == StudentMisconceptionStatus.RESOLVED:
            return row
        resolution_time = self._aware(resolved_at or datetime.now(timezone.utc))
        if resolution_time < self._aware(row.last_detected_at):
            raise ApplicationError(
                422,
                "INVALID_RESOLUTION_TIME",
                "Resolution time cannot be earlier than the last detection.",
            )
        row.status = StudentMisconceptionStatus.RESOLVED
        row.resolved_at = resolution_time
        self._finish(commit)
        logger.info(
            "Misconception resolved (student_id=%s, definition_id=%s)",
            student_id,
            misconception_definition_id,
        )
        return row

    def _confirm(self, row: StudentMisconception) -> None:
        if row.status == StudentMisconceptionStatus.RESOLVED:
            return
        if (
            row.occurrence_count >= self.policy.minimum_occurrences
            and row.confidence >= self.policy.confirmation_threshold
        ):
            row.status = StudentMisconceptionStatus.CONFIRMED

    @staticmethod
    def _increase(row: StudentMisconception, amount: float) -> None:
        row.confidence = round(min(1.0, row.confidence + amount), 6)

    def _definition_or_404(self, definition_id: UUID) -> MisconceptionDefinition:
        definition = self.session.get(MisconceptionDefinition, definition_id)
        if definition is None:
            raise ApplicationError(
                404,
                "MISCONCEPTION_DEFINITION_NOT_FOUND",
                "Misconception definition was not found.",
            )
        return definition

    def _lock_student(self, student_id: UUID) -> None:
        found = self.session.scalar(
            select(StudentProfile.id)
            .where(StudentProfile.id == student_id)
            .with_for_update()
        )
        if found is None:
            raise ApplicationError(404, "STUDENT_NOT_FOUND", "Student was not found.")

    def _state(
        self,
        student_id: UUID,
        definition_id: UUID,
        *,
        for_update: bool,
    ) -> StudentMisconception | None:
        statement = select(StudentMisconception).where(
            StudentMisconception.student_id == student_id,
            StudentMisconception.misconception_definition_id == definition_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def _state_or_404(
        self,
        student_id: UUID,
        definition_id: UUID,
        *,
        for_update: bool,
    ) -> StudentMisconception:
        row = self._state(student_id, definition_id, for_update=for_update)
        if row is None:
            raise ApplicationError(
                404,
                "STUDENT_MISCONCEPTION_NOT_FOUND",
                "Student misconception state was not found.",
            )
        return row

    def _finish(self, commit: bool) -> None:
        if commit:
            self.session.commit()
        else:
            self.session.flush()

    @staticmethod
    def _validate_increment(amount: float) -> None:
        if not 0.0 < amount <= 1.0:
            raise ApplicationError(
                422,
                "INVALID_CONFIDENCE_INCREMENT",
                "Confidence increment must be in (0, 1].",
            )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)

    @classmethod
    def _earliest(cls, current: datetime, candidate: datetime) -> datetime:
        return candidate if cls._aware(candidate) < cls._aware(current) else current

    @classmethod
    def _latest(cls, current: datetime, candidate: datetime) -> datetime:
        return candidate if cls._aware(candidate) > cls._aware(current) else current
