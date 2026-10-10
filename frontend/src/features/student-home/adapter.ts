import type {
  StudentCurrentActionRead,
  StudentLearningStateRead,
  StudentLearningSubjectRead,
  StudentMasteryRead,
} from "../../lib/api/contracts";
import { ApiContractError } from "../../lib/api/validation";

import { resolveStudentAction } from "./action-resolver";
import type {
  KnowledgeBiome,
  KnowledgeRegionState,
  KnowledgeRegionViewModel,
  StudentHomeActionType,
  StudentHomeViewModel,
} from "./types";

export interface StudentHomeAdapter<TStudentLearningState> {
  toViewModel(
    source: TStudentLearningState,
    fullName: string,
    email?: string,
    masteryData?: StudentMasteryRead | null
  ): StudentHomeViewModel;
}

export interface StudentHomeAdapterOptions {
  availableSubjects?: readonly StudentLearningSubjectRead[];
  selectedSubjectId?: string;
  discoveryOnlySubjectIds?: readonly string[];
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
  email?: string,
  masteryData?: StudentMasteryRead | null,
  options: StudentHomeAdapterOptions = {}
): StudentHomeViewModel {
  if (!actionTypes.includes(source.current_action.action_type as StudentHomeActionType)) {
    throw new ApiContractError("Unknown StudentCurrentActionType", "response.current_action.action_type");
  }

  const effectiveSubjects = options.availableSubjects ?? source.available_subjects;
  const availableSubjects = effectiveSubjects.map((subject) => ({
    id: subject.id,
    code: subject.code,
    name: subject.name,
  }));

  const requestedSubject = options.selectedSubjectId
    ? effectiveSubjects.find(
        (subject) =>
          subject.id === options.selectedSubjectId ||
          subject.code.toLowerCase() === options.selectedSubjectId?.toLowerCase()
      )
    : undefined;
  const focus =
    requestedSubject ??
    effectiveSubjects.find((subject) => subject.id === source.focus_subject_id) ??
    effectiveSubjects[0];
  const subject = focus
    ? { id: focus.id, name: focus.name, code: focus.code }
    : { id: "", name: "Chưa có môn học", code: "" };

  const subjectHasActivity = source.available_subjects.some(
    (availableSubject) => availableSubject.id === subject.id
  );
  const isFocusedLearningState =
    subjectHasActivity && source.focus_subject_id === subject.id;
  const isDiscoveryOnly = (options.discoveryOnlySubjectIds ?? []).includes(subject.id);
  const classContextCount = isFocusedLearningState ? source.class_contexts.length : 0;
  const learningMode = !subject.id
    ? "UNAVAILABLE"
    : isDiscoveryOnly
      ? "SELF_STUDY_ONBOARDING"
      : classContextCount > 0
        ? "CLASSROOM"
        : "SELF_STUDY";

  const idleAction: StudentCurrentActionRead = {
    action_type: "IDLE",
    subject_id: subject.id || null,
    resource_id: null,
    practice_session_id: null,
    assignment_id: null,
    verification_id: null,
    adaptive_repair_session_id: null,
    study_task_id: null,
    target_type: null,
    problem_type_id: null,
    concept_id: null,
    target_name: null,
    target_code: null,
    reason_code: null,
    repair_cycle_index: null,
    phase: null,
  };
  const currentAction = isFocusedLearningState ? source.current_action : idleAction;
  const resolvedAction = resolveStudentAction(currentAction);

  const activeMasterySubject = masteryData?.subjects.find(
    (masterySubject) => masterySubject.subject_id === subject.id
  );

  const rawMastery = isFocusedLearningState
    ? source.mastery_summary.average_problem_type_mastery ??
      source.mastery_summary.average_concept_mastery
    : activeMasterySubject?.attempt_count
      ? activeMasterySubject.mastery_score
      : null;
  const masteryScore = safeMasteryPercent(rawMastery);
  const hasEvidence = isFocusedLearningState
    ? source.mastery_summary.problem_type_started_count > 0 ||
      source.mastery_summary.concept_started_count > 0
    : (activeMasterySubject?.attempt_count ?? 0) > 0;

  const selectedProblemTypes =
    activeMasterySubject?.chapters.flatMap((chapter) =>
      chapter.topics.flatMap((topic) => topic.problem_types)
    ) ?? [];
  const selectedConcepts = activeMasterySubject?.concepts ?? [];
  const problemTypeStartedCount = isFocusedLearningState
    ? source.mastery_summary.problem_type_started_count
    : selectedProblemTypes.filter((item) => item.attempt_count > 0).length;
  const conceptStartedCount = isFocusedLearningState
    ? source.mastery_summary.concept_started_count
    : selectedConcepts.filter((item) => item.attempt_count > 0).length;
  const masteredProblemTypeCount = isFocusedLearningState
    ? source.mastery_summary.mastered_problem_type_count
    : selectedProblemTypes.filter((item) => item.state === "MASTERED").length;
  const weakProblemTypeCount = isFocusedLearningState
    ? source.mastery_summary.weak_problem_type_count
    : selectedProblemTypes.filter((item) => item.state === "WEAK").length;

  const overdueCount = isFocusedLearningState ? source.assignments.overdue_count : 0;
  const inProgressCount = isFocusedLearningState ? source.assignments.in_progress_count : 0;
  const pendingCount = isFocusedLearningState ? source.assignments.pending_count : 0;
  const activeCount = overdueCount + inProgressCount + pendingCount;

  const todayPlan = isFocusedLearningState && source.today_plan
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
    learningContext: {
      mode: learningMode,
      classContextCount,
      subjectHasActivity,
    },
    currentAction: {
      type: currentAction.action_type as StudentHomeActionType,
      targetName: currentAction.target_name ?? undefined,
      targetCode: currentAction.target_code ?? undefined,
      reasonCode: currentAction.reason_code ?? undefined,
      resourceId: currentAction.resource_id ?? undefined,
      resourceType: currentAction.target_type ?? undefined,
      phase: currentAction.phase ?? undefined,
      repairCycleIndex: currentAction.repair_cycle_index ?? undefined,
    },
    resolvedAction,
    mastery: {
      score: masteryScore,
      rawScore: rawMastery === null ? undefined : rawMastery,
      label: masteryScore === undefined ? "Chưa đủ dữ liệu" : "Độ vững hiện tại",
      hasEvidence,
      problemTypeStartedCount,
      conceptStartedCount,
      masteredProblemTypeCount,
      weakProblemTypeCount,
    },
    review: {
      dueCount: isFocusedLearningState ? source.review.due_now_count : 0,
      upcomingCount: isFocusedLearningState ? source.review.upcoming_count : 0,
      dueTargets: (isFocusedLearningState ? source.review.due_targets : []).map((target) => ({
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
      upcoming: (isFocusedLearningState ? source.assignments.upcoming : []).map((item) => ({
        assignmentId: item.assignment_id,
        title: item.title,
        status: item.status,
        dueAt: item.due_at,
        isOverdue: item.is_overdue,
      })),
    },
    todayPlan,
    momentum: {},
    knowledgeRegions: (() => {
      if (!masteryData?.subjects) return [];
      if (masteryData.student_id && source.student_id && masteryData.student_id !== source.student_id) return [];
      const activeMasterySubject = masteryData.subjects.find(
        (s) => s.subject_id === subject.id
      );
      if (!activeMasterySubject?.chapters) return [];
      const fallbackBiomes: readonly KnowledgeBiome[] = ["meadow", "river", "mountain", "forest", "sky"];
      const accents: readonly ("mint" | "aqua" | "sky" | "violet" | "amber")[] = [
        "mint",
        "aqua",
        "sky",
        "violet",
        "amber",
      ];
      return activeMasterySubject.chapters.map((chapter, index) => {
        let state: KnowledgeRegionState = "not_started";
        if (chapter.state === "MASTERED") state = "mastered";
        else if (chapter.state === "WEAK") state = "weak";
        else if (chapter.state === "REVIEW_DUE") state = "review";
        else if (chapter.state === "LEARNING" || chapter.state === "PRACTICING") state = "developing";
        else if (chapter.attempt_count === 0 || chapter.state === "NOT_STARTED") state = "not_started";

        return {
          id: chapter.chapter_id,
          label: chapter.name,
          progress: chapter.attempt_count > 0 ? safeMasteryPercent(chapter.mastery_score) : undefined,
          state,
          accent: accents[index % accents.length],
          biome: fallbackBiomes[index % fallbackBiomes.length],
        };
      });
    })(),
    priorities: (isFocusedLearningState ? source.priority_targets : []).map((priority) => ({
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
