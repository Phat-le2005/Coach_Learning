from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.learning.feedback_schemas import LearningFeedbackDecisionRead
from app.planning.study_schemas import StudyDayRead
from app.recommendations.schemas import PriorityReasonCode, PriorityTargetType


class StudentCurrentActionType(StrEnum):
    CONTINUE_REPAIR = "CONTINUE_REPAIR"
    CONTINUE_VERIFICATION = "CONTINUE_VERIFICATION"
    CONTINUE_ASSIGNMENT = "CONTINUE_ASSIGNMENT"
    COMPLETE_OVERDUE_ASSIGNMENT = "COMPLETE_OVERDUE_ASSIGNMENT"
    CONTINUE_PRACTICE = "CONTINUE_PRACTICE"
    REVIEW_DUE = "REVIEW_DUE"
    TODAY_TASK = "TODAY_TASK"
    LEARNING_PRIORITY = "LEARNING_PRIORITY"
    IDLE = "IDLE"


class StudentLearningSubjectRead(BaseModel):
    id: UUID
    code: str
    name: str


class StudentCurrentActionRead(BaseModel):
    action_type: StudentCurrentActionType

    subject_id: UUID | None = None

    resource_id: UUID | None = None
    practice_session_id: UUID | None = None
    assignment_id: UUID | None = None
    verification_id: UUID | None = None
    adaptive_repair_session_id: UUID | None = None
    study_task_id: UUID | None = None

    target_type: str | None = None
    problem_type_id: UUID | None = None
    concept_id: UUID | None = None

    target_name: str | None = None
    target_code: str | None = None

    reason_code: str | None = None
    repair_cycle_index: int | None = None
    phase: str | None = None


class StudentWeakTargetRead(BaseModel):
    problem_type_id: UUID | None = None
    concept_id: UUID | None = None
    target_name: str
    target_code: str
    code: str | None = None
    name: str | None = None
    mastery_score: float
    confidence: float
    last_practiced_at: datetime | None = None


class StudentMasterySummaryRead(BaseModel):
    problem_type_started_count: int = 0
    concept_started_count: int = 0

    mastered_problem_type_count: int = 0
    weak_problem_type_count: int = 0

    mastered_concept_count: int = 0
    weak_concept_count: int = 0

    average_problem_type_mastery: float | None = None
    average_concept_mastery: float | None = None

    weak_problem_types: list[StudentWeakTargetRead] = []
    weak_concepts: list[StudentWeakTargetRead] = []


class StudentPriorityTargetRead(BaseModel):
    target_type: PriorityTargetType | str
    problem_type_id: UUID | None = None
    concept_id: UUID | None = None
    target_name: str
    target_code: str
    reason_code: PriorityReasonCode | str
    priority_score: float
    mastery_score: float
    confidence: float
    desired_difficulty: float


class StudentActiveLearningRead(BaseModel):
    practice_session_id: UUID | None = None
    practice_session_type: str | None = None
    verification_id: UUID | None = None
    adaptive_repair_session_id: UUID | None = None
    assignment_id: UUID | None = None


class StudentVerifiedRootCauseRead(BaseModel):
    diagnosis_id: UUID
    verification_id: UUID
    verification_target_id: UUID

    target_type: str
    concept_id: UUID | None = None
    problem_type_id: UUID | None = None
    misconception_definition_id: UUID | None = None

    target_name: str | None = None
    target_code: str | None = None

    diagnosis_type: str
    diagnosis_confidence: float
    verified_at: datetime | None = None


class StudentRepairStateRead(BaseModel):
    adaptive_repair_session_id: UUID
    practice_session_id: UUID
    subject_id: UUID
    verification_target_id: UUID
    diagnosis_id: UUID
    status: str
    phase: str
    target_type: str
    target_concept_id: UUID | None = None
    target_problem_type_id: UUID | None = None
    misconception_definition_id: UUID | None = None
    target_name: str | None = None
    target_code: str | None = None
    repair_cycle_index: int
    current_difficulty: float
    target_exit_difficulty: float
    attempted_count: int
    correct_count: int
    max_questions: int


class StudentReviewTargetRead(BaseModel):
    schedule_id: UUID
    target_type: str
    problem_type_id: UUID | None = None
    concept_id: UUID | None = None
    target_name: str
    target_code: str
    next_review_at: datetime
    review_interval_days: float
    review_count: int
    last_review_result: str | None = None


class StudentReviewStateRead(BaseModel):
    due_now_count: int = 0
    upcoming_count: int = 0
    due_targets: list[StudentReviewTargetRead] = []


class StudentAssignmentStateItemRead(BaseModel):
    assignment_id: UUID
    student_assignment_id: UUID
    classroom_id: UUID
    subject_id: UUID
    title: str
    status: str
    start_at: datetime
    due_at: datetime | None = None
    score: float | None = None
    is_overdue: bool


class StudentAssignmentStateRead(BaseModel):
    overdue_count: int = 0
    in_progress_count: int = 0
    pending_count: int = 0
    upcoming: list[StudentAssignmentStateItemRead] = []


class StudentClassContextRead(BaseModel):
    classroom_id: UUID
    classroom_name: str
    teaching_plan_id: UUID | None = None


# Alias for today plan snapshot to match prompt Section 8 naming
StudentTodayPlanSnapshotRead = StudyDayRead
StudentLatestFeedbackRead = LearningFeedbackDecisionRead


class StudentLearningStateRead(BaseModel):
    student_id: UUID
    as_of: datetime

    available_subjects: list[StudentLearningSubjectRead]
    focus_subject_id: UUID | None

    current_action: StudentCurrentActionRead

    mastery_summary: StudentMasterySummaryRead
    priority_targets: list[StudentPriorityTargetRead]

    active_learning: StudentActiveLearningRead

    verified_root_causes: list[StudentVerifiedRootCauseRead]
    repair: StudentRepairStateRead | None

    review: StudentReviewStateRead
    assignments: StudentAssignmentStateRead

    today_plan: StudentTodayPlanSnapshotRead | None = None
    latest_feedback: StudentLatestFeedbackRead | None = None
    class_contexts: list[StudentClassContextRead] = []
