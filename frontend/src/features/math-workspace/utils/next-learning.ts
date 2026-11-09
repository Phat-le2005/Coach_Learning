export interface LearningTarget {
  id: string; kind: "CONCEPT" | "PROBLEM_TYPE"; name: string; reason: string;
  mastery_score: number | null; mastery_state: string | null; evidence_count: number;
  next_review_at: string | null;
}
export interface NextLearning {
  attempt_id: string; decision_id: string | null;
  status: "WAITING_REVIEW" | "WAITING_SUBMISSION" | "REINFORCE" | "CONTINUE";
  score: number | null; evidence_recorded: boolean; headline: string; explanation: string;
  criterion_gaps: { title: string; achieved: number; maximum: number; step_index: number | null }[];
  target: LearningTarget | null;
  question: { id: string; content: string; difficulty: number } | null;
  supply_message: string | null;
}
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const unit = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
const text = (value: unknown): value is string => typeof value === "string" && value.trim().length > 0;
const nullable = (value: unknown) => value === null || typeof value === "string";
const identifier = (value: unknown) => typeof value === "string" && UUID.test(value);
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);

export function parseNextLearning(value: unknown, attemptId: string): NextLearning {
  if (!record(value) || value.attempt_id !== attemptId ||
      !["WAITING_REVIEW", "WAITING_SUBMISSION", "REINFORCE", "CONTINUE"].includes(String(value.status)) ||
      !(value.decision_id === null || identifier(value.decision_id)) ||
      !(value.score === null || unit(value.score)) || typeof value.evidence_recorded !== "boolean" ||
      !text(value.headline) || !text(value.explanation) || !nullable(value.supply_message) ||
      !Array.isArray(value.criterion_gaps) || !value.criterion_gaps.every(gap => record(gap) && text(gap.title) &&
        unit(gap.achieved) && unit(gap.maximum) && gap.maximum > 0 && gap.achieved < gap.maximum &&
        (gap.step_index === null || Number.isInteger(gap.step_index) && Number(gap.step_index) > 0))) throw new Error("Đề xuất chưa có dữ liệu hợp lệ.");
  const t = value.target, q = value.question;
  if (t !== null && (!record(t) || !identifier(t.id) || !["CONCEPT", "PROBLEM_TYPE"].includes(String(t.kind)) ||
      !text(t.name) || !text(t.reason) || !(t.mastery_score === null || unit(t.mastery_score)) || !nullable(t.mastery_state) ||
      !Number.isInteger(t.evidence_count) || Number(t.evidence_count) < 0 ||
      !(t.next_review_at === null || typeof t.next_review_at === "string" && Number.isFinite(Date.parse(t.next_review_at))))) throw new Error("Mục tiêu học chưa hợp lệ.");
  if (q !== null && (!record(q) || !identifier(q.id) || !text(q.content) || !unit(q.difficulty) || !t || !value.decision_id)) throw new Error("Bài luyện chưa hợp lệ.");
  if (String(value.status).startsWith("WAITING") && (q !== null || value.score !== null || value.evidence_recorded)) throw new Error("Bài chưa chấm không thể có điểm chính thức.");
  return value as unknown as NextLearning;
}

export function learningLinks(data: NextLearning) {
  return { theory: data.target ? `/student/theory?topic=${encodeURIComponent(data.target.name)}` : "/student/theory",
    knowledge: "/student/knowledge", plan: `/student?after_attempt=${encodeURIComponent(data.attempt_id)}#learning-pulse` };
}

export function afterAttempt(search: string): string | null {
  const value = new URLSearchParams(search).get('after_attempt');
  return value && UUID.test(value) ? value : null;
}

export function reviewDate(value: string) {
  return new Intl.DateTimeFormat("vi-VN", { day: "2-digit", month: "2-digit", timeZone: "Asia/Ho_Chi_Minh" }).format(new Date(value));
}
