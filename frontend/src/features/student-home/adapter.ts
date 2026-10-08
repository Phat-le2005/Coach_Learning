import type { StudentLearningStateRead } from "../../lib/api/contracts";
import { ApiContractError } from "../../lib/api/validation";

import { resolveStudentAction } from "./action-resolver";
import type { StudentHomeActionType, StudentHomeViewModel } from "./types";

export interface StudentHomeAdapter<TStudentLearningState> {
  toViewModel(source: TStudentLearningState, fullName: string, email?: string): StudentHomeViewModel;
}

const actionTypes: readonly StudentHomeActionType[] = [
  "CONTINUE_REPAIR",
  "CONTINUE_VERIFICATION",
  "CONTINUE_ASSIGNMENT",
  "COMPLETE_OVERDUE_ASSIGNMENT",
  "CONTINUE_PRACTICE",
  "REVIEW_DUE",
  "TODAY_TASK",
  "LEARNING_PRIORITY",
  "IDLE",
] as const;

/**
 * Safely converts a fractional mastery score in [0.0, 1.0] to an integer percentage in [0, 100].
 * Rejects null, undefined, NaN, and values outside the [0.0, 1.0] unit interval without clamping.
 */
export function safeMasteryPercent(value: number | null | undefined): number | undefined {
  if (value === null || value === undefined || typeof value !== "number" || Number.isNaN(value)) {
    return undefined;
  }
  if (value < 0 || value > 1) {
    return undefined;
  }
  return Math.round(value * 100);
}

export function toStudentHomeViewModel(
  source: StudentLearningStateRead,
  fullName: string,
  email?: string
): StudentHomeViewModel {
  if (!actionTypes.includes(source.current_action.action_type as StudentHomeActionType)) {
    throw new ApiContractError("Unknown StudentCurrentActionType", "response.current_action.action_type");
  }

  const resolvedAction = resolveStudentAction(source.current_action);

  const availableSubjects = source.available_subjects.map((subject) => ({
    id: subject.id,
    code: subject.code,
    name: subject.name,
  }));

  const focus = source.available_subjects.find((subject) => subject.id === source.focus_subject_id) ?? source.available_subjects[0];
  const subject = focus
    ? { id: focus.id, name: focus.name, code: focus.code }
    : { id: "", name: "Chưa có môn học", code: "" };

  const rawMastery = source.mastery_summary.average_problem_type_mastery ?? source.mastery_summary.average_concept_mastery;
  const masteryScore = safeMasteryPercent(rawMastery);
  const hasEvidence = source.mastery_summary.problem_type_started_count > 0 || source.mastery_summary.concept_started_count > 0;

  const overdueCount = source.assignments.overdue_count;
  const inProgressCount = source.assignments.in_progress_count;
  const pendingCount = source.assignments.pending_count;
  const activeCount = overdueCount + inProgressCount + pendingCount;

  const todayPlan = source.today_plan
    ? {
        date: source.today_plan.date,
        totalCount: source.today_plan.total_count,
        completedCount: source.today_plan.completed_count,
        totalEstimatedMinutes: source.today_plan.total_estimated_minutes,
        availableMinutes: source.today_plan.available_daily_minutes,
        notice: source.today_plan.notice,
      }
    : null;

  return {
    student: {
      displayName: fullName,
      email,
    },
    subject,
    availableSubjects,
    currentAction: {
      type: source.current_action.action_type as StudentHomeActionType,
      targetName: source.current_action.target_name ?? undefined,
      targetCode: source.current_action.target_code ?? undefined,
      reasonCode: source.current_action.reason_code ?? undefined,
      resourceId: source.current_action.resource_id ?? undefined,
      resourceType: source.current_action.target_type ?? undefined,
      phase: source.current_action.phase ?? undefined,
      repairCycleIndex: source.current_action.repair_cycle_index ?? undefined,
    },
    resolvedAction,
    mastery: {
      score: masteryScore,
      rawScore: rawMastery === null ? undefined : rawMastery,
      label: masteryScore === undefined ? "Chưa đủ dữ liệu" : "Độ vững hiện tại",
      hasEvidence,
      problemTypeStartedCount: source.mastery_summary.problem_type_started_count,
      conceptStartedCount: source.mastery_summary.concept_started_count,
      masteredProblemTypeCount: source.mastery_summary.mastered_problem_type_count,
      weakProblemTypeCount: source.mastery_summary.weak_problem_type_count,
    },
    review: {
      dueCount: source.review.due_now_count,
      upcomingCount: source.review.upcoming_count,
      dueTargets: source.review.due_targets.map((target) => ({
        scheduleId: target.schedule_id,
        targetType: target.target_type,
        targetName: target.target_name,
        targetCode: target.target_code,
        nextReviewAt: target.next_review_at,
      })),
    },
    assignments: {
      activeCount,
      overdueCount,
      inProgressCount,
      pendingCount,
      upcoming: source.assignments.upcoming.map((item) => ({
        assignmentId: item.assignment_id,
        title: item.title,
        status: item.status,
        dueAt: item.due_at,
        isOverdue: item.is_overdue,
      })),
    },
    todayPlan,
    momentum: {},
    knowledgeRegions: [],
    priorities: source.priority_targets.map((priority) => ({
      id: priority.problem_type_id ?? priority.concept_id ?? `${priority.target_type}:${priority.target_code}`,
      targetType: priority.target_type,
      targetName: priority.target_name,
      targetCode: priority.target_code,
      reasonCode: priority.reason_code,
      mastery: safeMasteryPercent(priority.mastery_score),
      rawMastery: priority.mastery_score,
      confidence: priority.confidence,
      desiredDifficulty: priority.desired_difficulty,
      priorityScore: priority.priority_score,
    })),
  };
}

export const studentHomeAdapter: StudentHomeAdapter<StudentLearningStateRead> = {
  toViewModel: (source, fullName, email) => toStudentHomeViewModel(source, fullName, email),
};
export const STUDENT_HOME_API_ADAPTER_STATUS = "CONNECTED" as const;
