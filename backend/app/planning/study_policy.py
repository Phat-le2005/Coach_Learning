from dataclasses import dataclass, field
from datetime import date, timedelta
from uuid import UUID

from app.planning.study_models import (
    StudyTaskReasonCode,
    StudyTaskStatus,
    StudyTaskType,
)


@dataclass(frozen=True, slots=True)
class PlanningContext:
    student_id: UUID
    as_of: date
    available_daily_minutes: int = 60
    exam_date: date | None = None
    target_subjects: list[UUID] = field(default_factory=list)
    active_teaching_plan_problem_type_ids: list[UUID] = field(default_factory=list)
    prerequisite_gap_concept_ids: list[UUID] = field(default_factory=list)
    weak_problem_type_ids: list[UUID] = field(default_factory=list)
    weak_concept_ids: list[UUID] = field(default_factory=list)
    due_review_problem_type_ids: list[UUID] = field(default_factory=list)
    due_review_concept_ids: list[UUID] = field(default_factory=list)
    diagnostic_followup_problem_type_ids: list[UUID] = field(default_factory=list)
    diagnostic_followup_concept_ids: list[UUID] = field(default_factory=list)


@dataclass(slots=True)
class CandidateTask:
    task_type: StudyTaskType
    reason_code: str
    problem_type_id: UUID | None = None
    concept_id: UUID | None = None
    subject_id: UUID | None = None
    estimated_duration_minutes: int = 20
    priority_score: float = 1.0


class StudyPlanningPolicy:
    DEFAULT_DURATION_MAP: dict[StudyTaskType, int] = {
        StudyTaskType.LEARN: 25,
        StudyTaskType.PRACTICE: 20,
        StudyTaskType.REPAIR: 20,
        StudyTaskType.REVIEW: 15,
        StudyTaskType.QUICK_CHECK: 10,
        StudyTaskType.MINI_TEST: 30,
        StudyTaskType.EXAM: 60,
    }

    def generate_candidate_tasks(self, ctx: PlanningContext) -> list[CandidateTask]:
        candidates: list[CandidateTask] = []
        days_to_exam: int | None = None
        if ctx.exam_date:
            days_to_exam = (ctx.exam_date - ctx.as_of).days

        # 1. Exam approaching adjustments
        is_exam_imminent = days_to_exam is not None and days_to_exam <= 14
        is_exam_near = days_to_exam is not None and 14 < days_to_exam <= 45

        # If exam is imminent (<= 14 days), heavily prioritize full exam simulations and mini tests
        if is_exam_imminent:
            primary_subject = ctx.target_subjects[0] if ctx.target_subjects else None
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.EXAM,
                    reason_code=StudyTaskReasonCode.EXAM_PREPARATION,
                    subject_id=primary_subject,
                    estimated_duration_minutes=min(ctx.available_daily_minutes, 60),
                    priority_score=150.0,
                )
            )
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.MINI_TEST,
                    reason_code=StudyTaskReasonCode.EXAM_PREPARATION,
                    subject_id=primary_subject,
                    estimated_duration_minutes=30,
                    priority_score=140.0,
                )
            )
        elif is_exam_near:
            primary_subject = ctx.target_subjects[0] if ctx.target_subjects else None
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.MINI_TEST,
                    reason_code=StudyTaskReasonCode.EXAM_PREPARATION,
                    subject_id=primary_subject,
                    estimated_duration_minutes=30,
                    priority_score=110.0,
                )
            )

        # 2. Active Teaching Plan: Current lesson priority
        for pt_id in ctx.active_teaching_plan_problem_type_ids:
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.LEARN,
                    reason_code=StudyTaskReasonCode.CURRENT_TEACHING_PLAN,
                    problem_type_id=pt_id,
                    estimated_duration_minutes=self.DEFAULT_DURATION_MAP[StudyTaskType.LEARN],
                    priority_score=120.0 if not is_exam_imminent else 95.0,
                )
            )
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.PRACTICE,
                    reason_code=StudyTaskReasonCode.CURRENT_TEACHING_PLAN,
                    problem_type_id=pt_id,
                    estimated_duration_minutes=self.DEFAULT_DURATION_MAP[StudyTaskType.PRACTICE],
                    priority_score=115.0 if not is_exam_imminent else 90.0,
                )
            )

        # 3. Severe prerequisite gap: Repair before building further
        for c_id in ctx.prerequisite_gap_concept_ids:
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.REPAIR,
                    reason_code=StudyTaskReasonCode.PREREQUISITE_REPAIR,
                    concept_id=c_id,
                    estimated_duration_minutes=self.DEFAULT_DURATION_MAP[StudyTaskType.REPAIR],
                    priority_score=110.0 if not is_exam_imminent else 85.0,
                )
            )

        # 4. Weak ProblemType: Specific gap practice
        for pt_id in ctx.weak_problem_type_ids:
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.REPAIR,
                    reason_code=StudyTaskReasonCode.WEAK_PROBLEM_TYPE,
                    problem_type_id=pt_id,
                    estimated_duration_minutes=self.DEFAULT_DURATION_MAP[StudyTaskType.REPAIR],
                    priority_score=95.0 if not is_exam_imminent else 105.0,
                )
            )

        # 5. Diagnostic followup
        for pt_id in ctx.diagnostic_followup_problem_type_ids:
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.PRACTICE,
                    reason_code=StudyTaskReasonCode.DIAGNOSTIC_FOLLOWUP,
                    problem_type_id=pt_id,
                    estimated_duration_minutes=self.DEFAULT_DURATION_MAP[StudyTaskType.PRACTICE],
                    priority_score=90.0,
                )
            )
        for c_id in ctx.diagnostic_followup_concept_ids:
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.REPAIR,
                    reason_code=StudyTaskReasonCode.DIAGNOSTIC_FOLLOWUP,
                    concept_id=c_id,
                    estimated_duration_minutes=self.DEFAULT_DURATION_MAP[StudyTaskType.REPAIR],
                    priority_score=88.0,
                )
            )

        # 6. Spaced Review Due
        for pt_id in ctx.due_review_problem_type_ids:
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.REVIEW,
                    reason_code=StudyTaskReasonCode.REVIEW_DUE,
                    problem_type_id=pt_id,
                    estimated_duration_minutes=self.DEFAULT_DURATION_MAP[StudyTaskType.REVIEW],
                    priority_score=85.0,
                )
            )
        for c_id in ctx.due_review_concept_ids:
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.REVIEW,
                    reason_code=StudyTaskReasonCode.REVIEW_DUE,
                    concept_id=c_id,
                    estimated_duration_minutes=self.DEFAULT_DURATION_MAP[StudyTaskType.REVIEW],
                    priority_score=80.0,
                )
            )

        # 7. Goal / General practice fallback if list is sparse
        if not candidates:
            primary_subject = ctx.target_subjects[0] if ctx.target_subjects else None
            candidates.append(
                CandidateTask(
                    task_type=StudyTaskType.PRACTICE,
                    reason_code=StudyTaskReasonCode.GENERAL_PRACTICE,
                    subject_id=primary_subject,
                    estimated_duration_minutes=self.DEFAULT_DURATION_MAP[StudyTaskType.PRACTICE],
                    priority_score=50.0,
                )
            )

        # Sort candidates descending by priority score
        candidates.sort(key=lambda c: -c.priority_score)
        return candidates

    def schedule_horizon(
        self,
        ctx: PlanningContext,
        candidates: list[CandidateTask],
        *,
        horizon_days: int = 7,
    ) -> dict[date, list[CandidateTask]]:
        """
        Distribute candidate tasks across the horizon days respecting available_daily_minutes.
        Ensures NO giant backlog: each day only receives tasks up to available_daily_minutes.
        """
        schedule: dict[date, list[CandidateTask]] = {}
        daily_budget = max(ctx.available_daily_minutes, 15)

        # Track which candidate index we are on
        candidate_idx = 0
        total_candidates = len(candidates)

        for day_offset in range(horizon_days):
            current_date = ctx.as_of + timedelta(days=day_offset)
            schedule[current_date] = []
            minutes_remaining = daily_budget

            # Keep adding tasks to current_date until daily budget is satisfied
            attempts = 0
            while minutes_remaining >= 10 and attempts < total_candidates:
                candidate = candidates[candidate_idx % total_candidates]
                candidate_idx += 1
                attempts += 1

                # Check if this exact target is already scheduled for this day
                already_scheduled = any(
                    existing.task_type == candidate.task_type
                    and existing.problem_type_id == candidate.problem_type_id
                    and existing.concept_id == candidate.concept_id
                    and existing.reason_code == candidate.reason_code
                    for existing in schedule[current_date]
                )
                if already_scheduled and len(schedule[current_date]) > 0:
                    continue

                duration = min(candidate.estimated_duration_minutes, minutes_remaining)
                if duration < 10 and len(schedule[current_date]) > 0:
                    # Budget practically exhausted for this day
                    break

                task_to_add = CandidateTask(
                    task_type=candidate.task_type,
                    reason_code=candidate.reason_code,
                    problem_type_id=candidate.problem_type_id,
                    concept_id=candidate.concept_id,
                    subject_id=candidate.subject_id,
                    estimated_duration_minutes=candidate.estimated_duration_minutes,
                    priority_score=candidate.priority_score,
                )
                schedule[current_date].append(task_to_add)
                minutes_remaining -= candidate.estimated_duration_minutes

                # Allow a small 5-minute overrun tolerance to fit standard modules
                if minutes_remaining <= 5:
                    break

        return schedule
