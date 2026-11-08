import type {
  StudentLearningStateRead,
  StudentLearningSubjectRead,
  StudentMasteryRead,
} from "../../lib/api/contracts";
import { ApiContractError } from "../../lib/api/validation";

import type {
  KnowledgeBiome,
  KnowledgeChapterNode,
  KnowledgeClassroomContext,
  KnowledgeConceptNode,
  KnowledgeForestSummary,
  KnowledgeForestViewModel,
  KnowledgeNodeConceptItem,
  KnowledgeProblemTypeNode,
  KnowledgeRecommendedTaskItem,
  KnowledgeScopeState,
  KnowledgeTopicNode,
} from "./types";

const fallbackBiomes: KnowledgeBiome[] = ["meadow", "river", "mountain", "forest", "sky"];

// Chapter-to-Concept keyword / code affinity for linking subject concepts to problem types
const CHAPTER_CONCEPT_AFFINITY: Record<string, string[]> = {
  DERIVATIVE_APPLICATIONS: [
    "FUNCTION_DOMAIN",
    "FIRST_DERIVATIVE",
    "DERIVATIVE",
    "DERIVATIVE_SIGN",
    "VARIATION_TABLE",
    "MONOTONICITY_CRITERION",
    "FUNCTION_GRAPH",
    "INEQUALITY_SOLVING",
  ],
  EXPONENTIAL_LOGARITHM: ["EXPONENTIAL", "LOGARITHM", "FUNCTION_DOMAIN", "EQUATION_SOLVING"],
  VECTORS_GEOMETRY: ["SPACE_VECTOR", "VECTOR_DIRECTION_3D", "DIRECTION_VECTOR"],
  GROUPED_DATA_DISPERSION: ["GROUPED_DATA_CLASS_INTERVAL", "GROUPED_DATA_CLASS_BOUNDARY"],
  INTEGRALS: ["PRIMITIVE", "INTEGRAL", "DEFINITE_INTEGRAL", "FIRST_DERIVATIVE"],
  OXYZ_CHAPTER: ["COORDINATE_GEOMETRY", "DIRECTION_VECTOR", "ANGLE_OXYZ", "SPACE_VECTOR"],
  PROBABILITY_CHAPTER: ["CONDITIONAL_PROBABILITY", "PROBABILITY_TREE", "BAYES_FORMULA"],
};

/**
 * Validates a unit interval score [0.0, 1.0] and converts it to whole integer percentage [0, 100].
 * Returns undefined if score is null, undefined, NaN, or out of valid bounds.
 */
function safePercent(score: number | null | undefined): number | undefined {
  if (score === null || score === undefined || typeof score !== "number" || Number.isNaN(score)) {
    return undefined;
  }
  if (score < 0 || score > 1) {
    return undefined;
  }
  return Math.round(score * 100);
}

function buildDiagnosticSummary(
  state: KnowledgeProblemTypeNode["state"],
  masteryScore: number | undefined,
  attemptCount: number,
  scopeState: KnowledgeScopeState,
  weakConcepts: KnowledgeNodeConceptItem[]
): string {
  if (scopeState === "FOG_OF_WAR" && attemptCount === 0) {
    return "Chủ đề này chưa nằm trong phạm vi bài giảng và bài tập PDF hiện tại của Giáo viên. Hãy hoàn thành tốt các dạng bài đang mở khóa trước.";
  }
  const weakNames = weakConcepts
    .filter((c) => c.isWeakPrerequisite)
    .slice(0, 2)
    .map((c) => c.name);

  if (state === "WEAK") {
    const rootNote =
      weakNames.length > 0
        ? ` Nguyên nhân gốc rễ cần củng cố: ${weakNames.join(", ")}.`
        : "";
    return `Độ thành thạo hiện tại đang ở mức cần khắc phục (${masteryScore ?? 0}% qua ${attemptCount} lượt làm).${rootNote} Hệ thống đã sinh lộ trình bài tập rèn luyện từng bước bên dưới.`;
  }
  if (state === "REVIEW_DUE") {
    return `Dạng bài này đã đến lịch ôn tập ngắt quãng (hiện đạt ${masteryScore ?? 0}%). Hãy làm 1 bài tập hệ thống để củng cố trí nhớ dài hạn.`;
  }
  if (state === "LEARNING" || state === "PRACTICING") {
    const rootNote =
      weakNames.length > 0
        ? ` Lưu ý củng cố thêm khái niệm: ${weakNames.join(", ")}.`
        : "";
    return `Đang tích lũy tiến độ tốt (${masteryScore ?? 0}% sau ${attemptCount} lượt giải).${rootNote} Tiếp tục luyện bài tập hệ thống để đạt ngưỡng Thành thạo (≥80%).`;
  }
  if (state === "MASTERED") {
    return `Tuyệt vời! Bạn đã làm chủ dạng bài này (${masteryScore ?? 100}% qua ${attemptCount} lượt giải chuẩn xác). Đủ điều kiện mở khóa các dạng toán vận dụng cao tiếp theo.`;
  }
  if (scopeState === "CURRENT_TEACHING") {
    return "Dạng bài trọng tâm Giáo viên đang dạy và giao đề PDF. Hãy bắt đầu giải bài để hệ thống đo lường độ thành thạo và cá nhân hóa lộ trình.";
  }
  return "Chưa có dữ liệu bài làm. Hãy bắt đầu 1 bài tập từ ngân hàng hệ thống để AI phân tích năng lực từng bước.";
}

function buildRecommendedTasksForNode(
  pt: {
    id: string;
    code: string;
    name: string;
    state: KnowledgeProblemTypeNode["state"];
    masteryScore?: number;
    scopeState: KnowledgeScopeState;
  },
  weakConcepts: KnowledgeNodeConceptItem[],
  learningState?: StudentLearningStateRead | null
): KnowledgeRecommendedTaskItem[] {
  const tasks: KnowledgeRecommendedTaskItem[] = [];

  // 1. Check if today_plan already has explicit tasks for this problem type
  const planTasks = learningState?.today_plan?.tasks ?? [];
  for (const t of planTasks) {
    if (t.problem_type_id === pt.id) {
      tasks.push({
        id: t.id,
        taskType: t.task_type,
        reasonCode: t.reason_code,
        title: `Nhiệm vụ lộ trình: ${pt.name}`,
        subtitle:
          t.reason_code === "CURRENT_TEACHING_PLAN"
            ? "Bám sát tiến độ bài giảng & đề PDF của Giáo viên"
            : "Bài tập hệ thống tự động chọn theo năng lực",
        estimatedMinutes: t.estimated_duration_minutes || 20,
        problemTypeId: pt.id,
      });
    }
  }

  // 2. If there are weak prerequisite concepts, add a Root Repair step first
  const urgentWeakConcepts = weakConcepts.filter((c) => c.isWeakPrerequisite).slice(0, 2);
  for (const wc of urgentWeakConcepts) {
    tasks.push({
      id: `repair-concept-${pt.id}-${wc.id}`,
      taskType: "REPAIR",
      reasonCode: "PREREQUISITE_REPAIR",
      title: `Củng cố rễ kiến thức: ${wc.name}`,
      subtitle: `Khắc phục lỗi sai bước nền tảng (${wc.masteryScore ?? 0}% thành thạo)`,
      estimatedMinutes: 15,
      problemTypeId: pt.id,
      conceptId: wc.id,
    });
  }

  // 3. Always provide the canonical system exercise step tailored to current mastery state
  if (tasks.length === 0 || !tasks.some((t) => t.taskType === "PRACTICE" || t.taskType === "LEARN")) {
    if (pt.state === "WEAK") {
      tasks.push({
        id: `sys-repair-${pt.id}`,
        taskType: "REPAIR",
        reasonCode: "WEAK_PROBLEM_TYPE",
        title: `Bài tập khắc phục lỗi sai: ${pt.name}`,
        subtitle: "Bài tập hệ thống mức Cơ bản – Thông hiểu, chấm chữa từng bước",
        estimatedMinutes: 20,
        problemTypeId: pt.id,
      });
    } else if (pt.state === "MASTERED") {
      tasks.push({
        id: `sys-advance-${pt.id}`,
        taskType: "PRACTICE",
        reasonCode: "DIFFICULTY_PROGRESSION",
        title: `Thử thách nâng cao: ${pt.name}`,
        subtitle: "Bài tập vận dụng từ ngân hàng câu hỏi chuẩn của hệ thống",
        estimatedMinutes: 20,
        problemTypeId: pt.id,
      });
    } else {
      tasks.push({
        id: `sys-practice-${pt.id}`,
        taskType: "PRACTICE",
        reasonCode:
          pt.scopeState === "CURRENT_TEACHING"
            ? "CURRENT_TEACHING_PLAN"
            : "DIAGNOSTIC_FOLLOWUP",
        title: `Luyện giải từng bước: ${pt.name}`,
        subtitle: "Bài tập chuẩn từ ngân hàng hệ thống (AI đối chiếu từng bước giải)",
        estimatedMinutes: 20,
        problemTypeId: pt.id,
      });
    }
  }

  return tasks.slice(0, 3);
}

export function toKnowledgeForestViewModel(
  mastery: StudentMasteryRead | null | undefined,
  availableSubjects: StudentLearningSubjectRead[] = [],
  selectedSubjectId?: string,
  studentId?: string,
  discoveryOnlySubjectIds: readonly string[] = [],
  learningState?: StudentLearningStateRead | null
): KnowledgeForestViewModel {
  // P0 Data Isolation invariant: Mastery student_id must match learning state student_id
  if (mastery && studentId && mastery.student_id !== studentId) {
    throw new ApiContractError(
      `Hồ sơ học sinh không đồng nhất: Mastery student_id (${mastery.student_id}) không khớp Learning State (${studentId}).`
    );
  }

  // Safe fallback when availableSubjects is empty
  if (!availableSubjects || availableSubjects.length === 0) {
    return {
      subject: { id: "", code: "", name: "Chưa có môn học" },
      availableSubjects: [],
      accessMode: "UNAVAILABLE",
      summary: createEmptySummary(),
      chapters: [],
      concepts: [],
      hasCurriculum: false,
      hasEvidence: false,
    };
  }

  // Filter mastery subjects strictly to the student's available scope
  const availableIds = new Set(availableSubjects.map((s) => s.id));
  const scopedMasterySubjects = (mastery?.subjects ?? []).filter((subj) =>
    availableIds.has(subj.subject_id)
  );

  // Determine active subject from student's available scope
  const requestedAvailableSubject = selectedSubjectId
    ? availableSubjects.find(
        (s) => s.id === selectedSubjectId || s.code.toLowerCase() === selectedSubjectId.toLowerCase()
      )
    : undefined;

  const activeSubjectInfo = requestedAvailableSubject ?? availableSubjects[0];

  // Find corresponding mastery data for this active subject by exact subject_id
  const activeMasterySubject = scopedMasterySubjects.find(
    (subj) => subj.subject_id === activeSubjectInfo.id
  );

  if (!activeMasterySubject) {
    return {
      subject: {
        id: activeSubjectInfo.id,
        code: activeSubjectInfo.code,
        name: activeSubjectInfo.name,
      },
      availableSubjects,
      accessMode: discoveryOnlySubjectIds.includes(activeSubjectInfo.id)
        ? "SELF_STUDY_DISCOVERY"
        : "LEARNING_ACTIVITY",
      summary: createEmptySummary(),
      chapters: [],
      concepts: [],
      hasCurriculum: false,
      hasEvidence: false,
    };
  }

  // Map concepts (subject-level knowledge nodes) first so we can link them to problem types
  const concepts: KnowledgeConceptNode[] = activeMasterySubject.concepts.map((concept) => {
    const hasEvidence = concept.attempt_count > 0;
    return {
      id: concept.concept_id,
      code: concept.code,
      name: concept.name,
      subjectId: concept.subject_id,
      masteryScore: hasEvidence ? safePercent(concept.mastery_score) : undefined,
      rawMasteryScore: concept.mastery_score,
      confidence: hasEvidence ? safePercent(concept.confidence) : undefined,
      attemptCount: concept.attempt_count,
      correctCount: concept.correct_count,
      state: concept.state,
      lastPracticedAt: concept.last_practiced_at,
    };
  });

  const conceptByCode = new Map<string, KnowledgeConceptNode>();
  concepts.forEach((c) => conceptByCode.set(c.code, c));

  // Extract Teacher Classroom & TeachingPlan Scope from learningState
  const teachingPlanPtIds = new Set<string>();
  const assignedPtIds = new Set<string>();
  const currentFocusPtIds = new Set<string>();
  let classroomName = "";
  let hasActiveTeachingPlan = false;

  if (learningState?.class_contexts && learningState.class_contexts.length > 0) {
    for (const rawCtx of learningState.class_contexts) {
      const cname = typeof rawCtx.classroom_name === "string" ? rawCtx.classroom_name : "";
      if (cname && !classroomName) classroomName = cname;
      if (rawCtx.teaching_plan_id) {
        hasActiveTeachingPlan = true;
      }
      if (Array.isArray(rawCtx.teaching_plan_problem_type_ids)) {
        rawCtx.teaching_plan_problem_type_ids.forEach((id, idx) => {
          if (typeof id === "string") {
            teachingPlanPtIds.add(id);
            // First 4 items in the teacher's active plan are highlighted as immediate current focus
            if (idx < 4) currentFocusPtIds.add(id);
          }
        });
      }
      if (Array.isArray(rawCtx.assigned_problem_type_ids)) {
        rawCtx.assigned_problem_type_ids.forEach((id) => {
          if (typeof id === "string") {
            assignedPtIds.add(id);
            currentFocusPtIds.add(id);
          }
        });
      }
    }
  }

  // Also check priority_targets and today_plan for current teaching focus
  const priorityReasonByPtId = new Map<string, string>();
  if (learningState?.priority_targets) {
    for (const ptTarget of learningState.priority_targets) {
      if (ptTarget.problem_type_id) {
        priorityReasonByPtId.set(ptTarget.problem_type_id, ptTarget.reason_code);
        if (
          ptTarget.reason_code === "CURRENT_LESSON" ||
          ptTarget.reason_code === "CURRENT_TEACHING_PLAN"
        ) {
          currentFocusPtIds.add(ptTarget.problem_type_id);
          teachingPlanPtIds.add(ptTarget.problem_type_id);
        }
      }
    }
  }
  if (learningState?.today_plan?.tasks) {
    for (const task of learningState.today_plan.tasks) {
      if (task.problem_type_id) {
        currentFocusPtIds.add(task.problem_type_id);
      }
    }
  }

  const enforceTeacherScope =
    hasActiveTeachingPlan && (teachingPlanPtIds.size > 0 || assignedPtIds.size > 0);

  // Map chapters, topics, problem types
  let totalMastered = 0;
  let totalPracticing = 0;
  let totalLearning = 0;
  let totalWeak = 0;
  let totalReviewDue = 0;
  let totalNotStarted = 0;
  let totalProblemTypes = 0;

  let currentTeachingCount = 0;
  let unlockedCount = 0;
  let fogCount = 0;

  const chapters: KnowledgeChapterNode[] = activeMasterySubject.chapters.map(
    (chapter, chapterIndex) => {
      const biome = fallbackBiomes[chapterIndex % fallbackBiomes.length];

      // Check if any problem type in this chapter is in the teacher's plan or already practiced
      const chapterHasActivePlanNode = chapter.topics.some((t) =>
        t.problem_types.some(
          (pt) =>
            teachingPlanPtIds.has(pt.problem_type_id) ||
            assignedPtIds.has(pt.problem_type_id) ||
            pt.attempt_count > 0
        )
      );

      const affinityCodes = CHAPTER_CONCEPT_AFFINITY[chapter.code] ?? [];
      const chapterConcepts: KnowledgeNodeConceptItem[] = affinityCodes
        .map((code) => conceptByCode.get(code))
        .filter((c): c is KnowledgeConceptNode => Boolean(c))
        .map((c) => ({
          id: c.id,
          code: c.code,
          name: c.name,
          masteryScore: c.masteryScore,
          confidence: c.confidence,
          attemptCount: c.attemptCount,
          state: c.state,
          isWeakPrerequisite:
            c.state === "WEAK" || (c.attemptCount > 0 && (c.masteryScore ?? 0) < 55),
        }));

      let chCurrentTeaching = 0;
      let chUnlocked = 0;

      const topics: KnowledgeTopicNode[] = chapter.topics.map((topic) => {
        const topicHasActiveNode = topic.problem_types.some(
          (pt) =>
            teachingPlanPtIds.has(pt.problem_type_id) ||
            assignedPtIds.has(pt.problem_type_id) ||
            pt.attempt_count > 0
        );

        const problemTypes: KnowledgeProblemTypeNode[] = topic.problem_types.map((pt) => {
          totalProblemTypes += 1;

          switch (pt.state) {
            case "MASTERED":
              totalMastered += 1;
              break;
            case "PRACTICING":
              totalPracticing += 1;
              break;
            case "LEARNING":
              totalLearning += 1;
              break;
            case "WEAK":
              totalWeak += 1;
              break;
            case "REVIEW_DUE":
              totalReviewDue += 1;
              break;
            case "NOT_STARTED":
            default:
              totalNotStarted += 1;
              break;
          }

          const hasEvidence = pt.attempt_count > 0;
          const relatedConcepts = pt.concept_ids === undefined ? chapterConcepts : pt.concept_ids
            .map((id) => concepts.find((c) => c.id === id))
            .filter((c): c is KnowledgeConceptNode => Boolean(c))
            .map((c) => ({ id: c.id, code: c.code, name: c.name, masteryScore: c.masteryScore,
              confidence: c.confidence, attemptCount: c.attemptCount, state: c.state,
              isWeakPrerequisite: c.state === "WEAK" }));
          const masteryScore = hasEvidence ? safePercent(pt.mastery_score) : undefined;
          const confidence = hasEvidence ? safePercent(pt.confidence) : undefined;

          // Determine scopeState accurately
          let scopeState: KnowledgeScopeState = "UNLOCKED";
          let teacherScopeLabel = "Đã mở khóa luyện tập";

          if (currentFocusPtIds.has(pt.problem_type_id)) {
            scopeState = "CURRENT_TEACHING";
            teacherScopeLabel = classroomName
              ? `Đang học & giao bài (${classroomName})`
              : "Trọng tâm đang học";
            currentTeachingCount += 1;
            chCurrentTeaching += 1;
          } else if (
            !enforceTeacherScope ||
            teachingPlanPtIds.has(pt.problem_type_id) ||
            assignedPtIds.has(pt.problem_type_id) ||
            hasEvidence ||
            topicHasActiveNode
          ) {
            scopeState = "UNLOCKED";
            teacherScopeLabel = classroomName
              ? `Trong phạm vi đã mở (${classroomName})`
              : "Đã mở khóa";
            unlockedCount += 1;
            chUnlocked += 1;
          } else {
            scopeState = "FOG_OF_WAR";
            teacherScopeLabel = "Sương mù tri thức — Giáo viên chưa dạy tới";
            fogCount += 1;
          }

          const diagnosticSummary = pt.available_question_count === 0
            ? "Dạng bài đã có trên cây tri thức; bộ câu hỏi luyện tập đang được bổ sung."
            : buildDiagnosticSummary(
            pt.state,
            masteryScore,
            pt.attempt_count,
            scopeState,
            relatedConcepts
          );

          const recommendedTasks = pt.available_question_count === 0 ? [] : buildRecommendedTasksForNode(
            {
              id: pt.problem_type_id,
              code: pt.code,
              name: pt.name,
              state: pt.state,
              masteryScore,
              scopeState,
            },
            relatedConcepts,
            learningState
          );

          return {
            id: pt.problem_type_id,
            code: pt.code,
            name: pt.name,
            availableQuestionCount: pt.available_question_count,
            topicId: topic.topic_id,
            topicName: topic.name,
            chapterId: chapter.chapter_id,
            chapterName: chapter.name,
            masteryScore,
            rawMasteryScore: pt.mastery_score,
            confidence,
            attemptCount: pt.attempt_count,
            correctCount: pt.correct_count,
            state: pt.state,
            lastPracticedAt: pt.last_practiced_at,
            isReviewDue: pt.state === "REVIEW_DUE",
            scopeState,
            teacherScopeLabel,
            priorityReasonCode: priorityReasonByPtId.get(pt.problem_type_id),
            diagnosticSummary,
            relatedConcepts,
            recommendedTasks,
          };
        });

        const topicScopeState: KnowledgeScopeState = problemTypes.some(
          (p) => p.scopeState === "CURRENT_TEACHING"
        )
          ? "CURRENT_TEACHING"
          : problemTypes.some((p) => p.scopeState === "UNLOCKED")
            ? "UNLOCKED"
            : "FOG_OF_WAR";

        const hasTopicEvidence = topic.attempt_count > 0;
        return {
          id: topic.topic_id,
          code: topic.code,
          name: topic.name,
          chapterId: chapter.chapter_id,
          problemTypeCount: topic.problem_type_count,
          startedProblemTypeCount: topic.started_problem_type_count,
          masteryScore: hasTopicEvidence ? safePercent(topic.mastery_score) : undefined,
          rawMasteryScore: topic.mastery_score,
          state: topic.state,
          attemptCount: topic.attempt_count,
          problemTypes,
          scopeState: topicScopeState,
        };
      });

      const chapterScopeState: KnowledgeScopeState =
        chCurrentTeaching > 0
          ? "CURRENT_TEACHING"
          : chUnlocked > 0 || chapterHasActivePlanNode || !enforceTeacherScope
            ? "UNLOCKED"
            : "FOG_OF_WAR";

      const hasChapterEvidence = chapter.attempt_count > 0;
      return {
        id: chapter.chapter_id,
        code: chapter.code,
        name: chapter.name,
        biome,
        problemTypeCount: chapter.problem_type_count,
        startedProblemTypeCount: chapter.started_problem_type_count,
        masteryScore: hasChapterEvidence ? safePercent(chapter.mastery_score) : undefined,
        rawMasteryScore: chapter.mastery_score,
        state: chapter.state,
        attemptCount: chapter.attempt_count,
        topics,
        scopeState: chapterScopeState,
        currentTeachingCount: chCurrentTeaching,
        unlockedCount: chUnlocked + chCurrentTeaching,
      };
    }
  );

  const hasSubjectEvidence = activeMasterySubject.attempt_count > 0;
  const summary: KnowledgeForestSummary = {
    problemTypeCount: totalProblemTypes || activeMasterySubject.problem_type_count,
    startedProblemTypeCount: activeMasterySubject.started_problem_type_count,
    masteryScore: hasSubjectEvidence ? safePercent(activeMasterySubject.mastery_score) : undefined,
    rawMasteryScore: activeMasterySubject.mastery_score,
    confidence: hasSubjectEvidence ? safePercent(activeMasterySubject.confidence) : undefined,
    attemptCount: activeMasterySubject.attempt_count,
    state: activeMasterySubject.state,
    masteredCount: totalMastered,
    practicingCount: totalPracticing,
    learningCount: totalLearning,
    weakCount: totalWeak,
    reviewDueCount: totalReviewDue,
    notStartedCount: totalNotStarted,
  };

  const classroomContext: KnowledgeClassroomContext | undefined =
    classroomName || hasActiveTeachingPlan
      ? {
          classroomName: classroomName || "Lớp học của Giáo viên",
          hasActiveTeachingPlan,
          hasActiveTeacherScope: hasActiveTeachingPlan,
          currentTeachingCount,
          unlockedCount: unlockedCount + currentTeachingCount,
          fogCount,
          fogOfWarCount: fogCount,
        }
      : undefined;

  return {
    subject: {
      id: activeSubjectInfo.id,
      code: activeSubjectInfo.code,
      name: activeSubjectInfo.name,
    },
    availableSubjects,
    accessMode: discoveryOnlySubjectIds.includes(activeSubjectInfo.id)
      ? "SELF_STUDY_DISCOVERY"
      : "LEARNING_ACTIVITY",
    summary,
    chapters,
    concepts,
    hasCurriculum: chapters.length > 0 || concepts.length > 0,
    hasEvidence: hasSubjectEvidence,
    classroomContext,
  };
}

function createEmptySummary(): KnowledgeForestSummary {
  return {
    problemTypeCount: 0,
    startedProblemTypeCount: 0,
    rawMasteryScore: 0,
    attemptCount: 0,
    state: "NOT_STARTED",
    masteredCount: 0,
    weakCount: 0,
    learningCount: 0,
    practicingCount: 0,
    reviewDueCount: 0,
    notStartedCount: 0,
  };
}
