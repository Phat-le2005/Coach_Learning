from datetime import date, datetime, timedelta, timezone
import logging
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import ApplicationError
from app.students.goal_models import AcademicGoal, AcademicGoalStatus, SubjectGoal
from app.students.goal_schemas import AcademicGoalCreate, AcademicGoalPatch, SubjectGoalCreate
from app.students.models import StudentProfile
from app.subjects.models import Subject

logger = logging.getLogger(__name__)

DEFAULT_SCORE_SCALE: tuple[float, float] = (0.0, 10.0)

EXAM_SCORE_SCALES: dict[str, tuple[float, float]] = {
    "TN_THPT": (0.0, 10.0),
    "THPT_QG": (0.0, 10.0),
    "DGNL_VNU_HN": (0.0, 150.0),
    "DGNL_VNU_HCM": (0.0, 1200.0),
    "DGTD_HUST": (0.0, 100.0),
}


def get_score_scale_for_exam(exam: str) -> tuple[float, float]:
    return EXAM_SCORE_SCALES.get(exam.strip().upper(), DEFAULT_SCORE_SCALE)


class AcademicGoalService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_goals(
        self, student_id: UUID, status: AcademicGoalStatus | None = None
    ) -> list[AcademicGoal]:
        stmt = (
            self._goal_statement()
            .where(AcademicGoal.student_id == student_id)
            .order_by(AcademicGoal.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(AcademicGoal.status == status)
        return list(self.session.scalars(stmt))

    def get_goal(self, student_id: UUID, goal_id: UUID) -> AcademicGoal:
        goal = self.session.scalar(
            self._goal_statement().where(
                AcademicGoal.id == goal_id,
                AcademicGoal.student_id == student_id,
            )
        )
        if goal is None:
            raise ApplicationError(404, "GOAL_NOT_FOUND", "Academic goal was not found.")
        return goal

    def create_goal(self, student_id: UUID, data: AcademicGoalCreate) -> AcademicGoal:
        self._require_student(student_id)
        self._validate_exam_date(data.exam_date)

        if data.status == AcademicGoalStatus.ACTIVE:
            self._assert_active_goal_limit(student_id)

        self._validate_subject_goals(data.target_exam, data.subject_goals)

        goal = AcademicGoal(
            student_id=student_id,
            target_exam=data.target_exam,
            exam_date=data.exam_date,
            available_daily_minutes=data.available_daily_minutes,
            status=data.status,
            target_university=data.target_university,
            target_major=data.target_major,
            subject_goals=[
                SubjectGoal(
                    subject_id=item.subject_id,
                    current_score=item.current_score,
                    target_score=item.target_score,
                    priority=item.priority,
                )
                for item in data.subject_goals
            ],
        )
        self.session.add(goal)
        self.session.commit()
        logger.info("Academic goal created (goal_id=%s, student_id=%s)", goal.id, student_id)
        return self.get_goal(student_id, goal.id)

    def patch_goal(
        self, student_id: UUID, goal_id: UUID, data: AcademicGoalPatch
    ) -> AcademicGoal:
        goal = self.get_goal(student_id, goal_id)

        if data.status == AcademicGoalStatus.ACTIVE and goal.status != AcademicGoalStatus.ACTIVE:
            self._assert_active_goal_limit(student_id, current_goal_id=goal_id)

        if data.exam_date is not None:
            self._validate_exam_date(data.exam_date)

        effective_exam = data.target_exam if data.target_exam is not None else goal.target_exam

        if data.subject_goals is not None:
            self._validate_subject_goals(effective_exam, data.subject_goals)
            goal.subject_goals.clear()
            self.session.flush()
            for item in data.subject_goals:
                goal.subject_goals.append(
                    SubjectGoal(
                        academic_goal_id=goal.id,
                        subject_id=item.subject_id,
                        current_score=item.current_score,
                        target_score=item.target_score,
                        priority=item.priority,
                    )
                )
        elif data.target_exam is not None and data.target_exam != goal.target_exam:
            # Revalidate existing subject goals with new exam scale
            existing_as_create = [
                SubjectGoalCreate(
                    subject_id=sg.subject_id,
                    current_score=sg.current_score,
                    target_score=sg.target_score,
                    priority=sg.priority,
                )
                for sg in goal.subject_goals
            ]
            self._validate_subject_goals(effective_exam, existing_as_create)

        for field_name in (
            "target_exam",
            "exam_date",
            "available_daily_minutes",
            "status",
            "target_university",
            "target_major",
        ):
            if field_name in data.model_fields_set:
                setattr(goal, field_name, getattr(data, field_name))

        goal.updated_at = datetime.now(timezone.utc)
        self.session.commit()
        logger.info("Academic goal updated (goal_id=%s, student_id=%s)", goal.id, student_id)
        return self.get_goal(student_id, goal.id)

    def _require_student(self, student_id: UUID) -> StudentProfile:
        student = self.session.get(StudentProfile, student_id)
        if student is None:
            raise ApplicationError(404, "PROFILE_NOT_FOUND", "Student profile was not found.")
        return student

    def _validate_exam_date(self, exam_date: date) -> None:
        today = date.today()
        if exam_date < today:
            raise ApplicationError(
                422, "INVALID_EXAM_DATE", "Exam date must be today or in the future."
            )
        if exam_date > today + timedelta(days=365 * 5):
            raise ApplicationError(
                422,
                "INVALID_EXAM_DATE",
                "Exam date cannot be more than 5 years in the future.",
            )

    def _validate_subject_goals(
        self, target_exam: str, items: list[SubjectGoalCreate]
    ) -> None:
        seen_subject_ids: set[UUID] = set()
        for item in items:
            if item.subject_id in seen_subject_ids:
                raise ApplicationError(
                    422,
                    "DUPLICATE_SUBJECT_GOAL",
                    f"Subject {item.subject_id} is duplicated in subject goals.",
                )
            seen_subject_ids.add(item.subject_id)

        if items:
            subject_ids = [item.subject_id for item in items]
            existing = set(
                self.session.scalars(select(Subject.id).where(Subject.id.in_(subject_ids)))
            )
            missing = set(subject_ids) - existing
            if missing:
                missing_str = ", ".join(sorted(str(m) for m in missing))
                raise ApplicationError(
                    422, "SUBJECT_NOT_FOUND", f"One or more subjects were not found: {missing_str}."
                )

        min_score, max_score = get_score_scale_for_exam(target_exam)
        for item in items:
            if not (min_score <= item.target_score <= max_score):
                raise ApplicationError(
                    422,
                    "SCORE_OUT_OF_RANGE",
                    f"Target score {item.target_score} is out of range [{min_score}, {max_score}] for exam '{target_exam}'.",
                )
            if item.current_score is not None:
                if not (min_score <= item.current_score <= max_score):
                    raise ApplicationError(
                        422,
                        "SCORE_OUT_OF_RANGE",
                        f"Current score {item.current_score} is out of range [{min_score}, {max_score}] for exam '{target_exam}'.",
                    )
                if item.target_score < item.current_score:
                    raise ApplicationError(
                        422,
                        "INVALID_TARGET_SCORE",
                        f"Target score ({item.target_score}) must be greater than or equal to current score ({item.current_score}).",
                    )

    def _assert_active_goal_limit(
        self, student_id: UUID, current_goal_id: UUID | None = None
    ) -> None:
        query = select(func.count(AcademicGoal.id)).where(
            AcademicGoal.student_id == student_id,
            AcademicGoal.status == AcademicGoalStatus.ACTIVE,
        )
        if current_goal_id is not None:
            query = query.where(AcademicGoal.id != current_goal_id)

        active_count = self.session.scalar(query) or 0
        if active_count >= 1:
            raise ApplicationError(
                409,
                "ACTIVE_GOAL_LIMIT_EXCEEDED",
                "Student already has an active academic goal. Complete or archive the active goal first.",
            )

    @staticmethod
    def _goal_statement() -> Select[tuple[AcademicGoal]]:
        return select(AcademicGoal).options(selectinload(AcademicGoal.subject_goals))
