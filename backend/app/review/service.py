from datetime import datetime, timedelta, timezone
import logging
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.concepts.models import Concept
from app.core.exceptions import ApplicationError
from app.curriculum.models import Chapter, ProblemType, Topic
from app.review.models import ReviewResult, ReviewSchedule
from app.review.policy import ReviewPolicy
from app.review.schemas import ReviewDueItemRead, ReviewScheduleRead
from app.students.models import StudentProfile

logger = logging.getLogger(__name__)


class ReviewScheduleService:
    def __init__(self, session: Session, policy: ReviewPolicy | None = None) -> None:
        self.session = session
        self.policy = policy or ReviewPolicy()

    def ensure_problem_type_schedule(
        self,
        student_id: UUID,
        problem_type_id: UUID,
        *,
        as_of: datetime | None = None,
        initial_interval_days: float | None = None,
    ) -> ReviewSchedule:
        existing = self.session.scalar(
            select(ReviewSchedule).where(
                ReviewSchedule.student_id == student_id,
                ReviewSchedule.problem_type_id == problem_type_id,
            )
        )
        if existing is not None:
            return existing

        pt = self.session.get(ProblemType, problem_type_id)
        if pt is None:
            raise ApplicationError(404, "PROBLEM_TYPE_NOT_FOUND", "Problem type was not found.")

        ref_time = as_of or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        interval = initial_interval_days or self.policy.thresholds.initial_interval_days
        schedule = ReviewSchedule(
            student_id=student_id,
            problem_type_id=problem_type_id,
            concept_id=None,
            next_review_at=ref_time + timedelta(days=interval),
            review_interval_days=interval,
            review_count=0,
            last_review_result=None,
        )
        self.session.add(schedule)
        self.session.flush()
        logger.info(
            "Review schedule created for problem_type (student_id=%s, pt_id=%s, next_at=%s)",
            student_id,
            problem_type_id,
            schedule.next_review_at,
        )
        return schedule

    def ensure_concept_schedule(
        self,
        student_id: UUID,
        concept_id: UUID,
        *,
        as_of: datetime | None = None,
        initial_interval_days: float | None = None,
    ) -> ReviewSchedule:
        existing = self.session.scalar(
            select(ReviewSchedule).where(
                ReviewSchedule.student_id == student_id,
                ReviewSchedule.concept_id == concept_id,
            )
        )
        if existing is not None:
            return existing

        concept = self.session.get(Concept, concept_id)
        if concept is None:
            raise ApplicationError(404, "CONCEPT_NOT_FOUND", "Concept was not found.")

        ref_time = as_of or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        interval = initial_interval_days or self.policy.thresholds.initial_interval_days
        schedule = ReviewSchedule(
            student_id=student_id,
            problem_type_id=None,
            concept_id=concept_id,
            next_review_at=ref_time + timedelta(days=interval),
            review_interval_days=interval,
            review_count=0,
            last_review_result=None,
        )
        self.session.add(schedule)
        self.session.flush()
        logger.info(
            "Review schedule created for concept (student_id=%s, concept_id=%s, next_at=%s)",
            student_id,
            concept_id,
            schedule.next_review_at,
        )
        return schedule

    def record_performance(
        self,
        student_id: UUID,
        *,
        target_problem_type_id: UUID | None = None,
        target_concept_id: UUID | None = None,
        score: float | None = None,
        is_correct: bool | None = None,
        as_of: datetime | None = None,
    ) -> ReviewSchedule:
        if (target_problem_type_id is None) == (target_concept_id is None):
            raise ApplicationError(
                422,
                "INVALID_TARGET",
                "Exactly one of target_problem_type_id or target_concept_id must be provided.",
            )

        ref_time = as_of or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        schedule: ReviewSchedule | None = None
        if target_problem_type_id is not None:
            schedule = self.session.scalar(
                select(ReviewSchedule).where(
                    ReviewSchedule.student_id == student_id,
                    ReviewSchedule.problem_type_id == target_problem_type_id,
                )
            )
            if schedule is None:
                schedule = self.ensure_problem_type_schedule(
                    student_id, target_problem_type_id, as_of=ref_time
                )
        else:
            schedule = self.session.scalar(
                select(ReviewSchedule).where(
                    ReviewSchedule.student_id == student_id,
                    ReviewSchedule.concept_id == target_concept_id,
                )
            )
            if schedule is None:
                schedule = self.ensure_concept_schedule(
                    student_id, target_concept_id, as_of=ref_time  # type: ignore[arg-type]
                )

        eval_result = self.policy.evaluate_performance(score, is_correct)
        next_interval = self.policy.calculate_next_interval(
            schedule.review_interval_days, eval_result
        )

        schedule.review_interval_days = next_interval
        schedule.review_count += 1
        schedule.last_review_result = eval_result.value
        schedule.next_review_at = ref_time + timedelta(days=next_interval)
        schedule.updated_at = datetime.now(timezone.utc)

        self.session.flush()
        logger.info(
            "Review performance recorded (schedule_id=%s, result=%s, next_interval=%.2f, next_at=%s)",
            schedule.id,
            eval_result.value,
            next_interval,
            schedule.next_review_at,
        )
        return schedule

    def get_due_schedules(
        self,
        student_id: UUID,
        *,
        subject_id: UUID | None = None,
        as_of: datetime | None = None,
    ) -> list[ReviewSchedule]:
        ref_time = as_of or datetime.now(timezone.utc)
        if ref_time.tzinfo is None:
            ref_time = ref_time.replace(tzinfo=timezone.utc)

        stmt = select(ReviewSchedule).where(
            ReviewSchedule.student_id == student_id,
            ReviewSchedule.next_review_at <= ref_time,
        )

        if subject_id is not None:
            stmt = stmt.where(
                or_(
                    ReviewSchedule.problem_type_id.in_(
                        select(ProblemType.id)
                        .join(Topic, Topic.id == ProblemType.topic_id)
                        .join(Chapter, Chapter.id == Topic.chapter_id)
                        .where(Chapter.subject_id == subject_id)
                    ),
                    ReviewSchedule.concept_id.in_(
                        select(Concept.id).where(Concept.subject_id == subject_id)
                    ),
                )
            )

        stmt = stmt.order_by(ReviewSchedule.next_review_at.asc(), ReviewSchedule.id)
        return list(self.session.scalars(stmt))

    def get_due_target_ids(
        self,
        student_id: UUID,
        subject_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> tuple[set[UUID], set[UUID]]:
        due = self.get_due_schedules(student_id, subject_id=subject_id, as_of=as_of)
        due_pts = {s.problem_type_id for s in due if s.problem_type_id is not None}
        due_concepts = {s.concept_id for s in due if s.concept_id is not None}
        return due_pts, due_concepts
