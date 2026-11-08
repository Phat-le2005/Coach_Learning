import type { StudentHomeViewModel, StudyTaskItemViewModel } from "./types";
/** Mutations remain behind the existing launch/review flows. */
export function getHomeRoutes(data: StudentHomeViewModel) {
  const subject = data.subject.id ? `subject_id=${encodeURIComponent(data.subject.id)}` : "";
  const knowledge = `/student/knowledge${subject ? `?${subject}` : ""}`;
  const practice = `/student/practice${subject ? `?${subject}` : ""}`;
  const action = data.resolvedAction;
  const continuation = ["CONTINUE_REPAIR", "CONTINUE_VERIFICATION", "CONTINUE_ASSIGNMENT", "COMPLETE_OVERDUE_ASSIGNMENT", "CONTINUE_PRACTICE"].includes(action.type);
  return { knowledge, practice, attempts: "/student/attempts",
    recommended: action.type !== "IDLE" && action.hasAvailableRoute && action.route ? action.route : null,
    resume: continuation && action.hasAvailableRoute && action.route ? action.route : null };
}

export function homeTaskTypeLabel(type: string) {
  switch (type) {
    case "REPAIR": case "REMEDIAL_PRACTICE": return "Củng cố";
    case "REVIEW": case "SPACED_REVIEW": return "Ôn tập";
    case "LEARN": case "CONCEPT_ACQUISITION": return "Học kiến thức";
    case "MINI_TEST": return "Kiểm tra ngắn";
    case "EXAM": return "Luyện đề";
    default: return "Luyện tập";
  }
}

export function homeDate(value?: string | null) {
  if (!value) return null;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return null;
  const parts = new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit", month: "2-digit", timeZone: "Asia/Ho_Chi_Minh",
  }).formatToParts(date);
  // Node/Chrome may use different locale separators; keep SSR and hydration identical.
  return `${parts.find(part => part.type === "day")!.value}/${parts.find(part => part.type === "month")!.value}`;
}
export function homeTaskHref(task: StudyTaskItemViewModel, subjectId: string) {
  const params = new URLSearchParams();
  if (subjectId) params.set("subject_id", subjectId);
  if (task.problemTypeId) params.set("problem_type_id", task.problemTypeId);
  else if (task.conceptId) params.set("concept_id", task.conceptId);
  return `/student/practice${params.size ? `?${params}` : ""}`;
}
