import { getCsrfToken, refreshBrowserSession } from "../../lib/auth/browser";
import { ApiContractError, array, boolean, integer, number, record, string } from "../../lib/api/validation";

export interface ParentProfile {
  id: string;
  user_id: string;
  created_at: string;
  updated_at: string;
}

export interface ParentStudentSummary {
  student_id: string;
  student_name: string;
  grade_level: number;
  relationship_type: string;
  school_name: string | null;
  overall_learning_trend: string;
  weekly_study_time_minutes: number;
  active_alerts_count: number;
}

export interface ParentSubjectProgress {
  subject_id: string;
  subject_name: string;
  mastery_score: number;
  completed_topics_count: number;
  total_topics_count: number;
}

export interface ParentChapterProgress {
  chapter_id: string;
  chapter_name: string;
  subject_name: string;
  mastery_score: number;
  status: string;
}

export interface ParentTopicProgress {
  topic_id: string;
  topic_name: string;
  chapter_name: string;
  mastery_score: number;
}

export interface ParentMajorWeakArea {
  problem_type_id: string;
  problem_type_name: string;
  subject_name: string;
  mastery_score: number;
  parent_friendly_message: string;
  related_concept_name: string | null;
  attempt_count: number;
}

export interface ParentStudyPlanCompletion {
  total_tasks: number;
  completed_tasks: number;
  completion_rate: number;
}

export interface ParentInterventionAlert {
  rule_code: string;
  severity: string;
  title: string;
  message: string;
  suggested_action_for_parent: string;
}

export interface ParentExamTrendItem {
  title: string;
  date: string;
  score: number;
  total_questions: number;
  assessment_type: string;
  trend_direction: string;
}

export interface ParentStudentProgress {
  student_id: string;
  student_name: string;
  grade_level: number;
  relationship_type: string;
  subject_progress: ParentSubjectProgress[];
  chapter_progress: ParentChapterProgress[];
  topic_progress: ParentTopicProgress[];
  major_weak_areas: ParentMajorWeakArea[];
  study_plan_completion: ParentStudyPlanCompletion;
  exam_trend: ParentExamTrendItem[];
  important_intervention_alerts: ParentInterventionAlert[];
  overall_learning_trend: string;
  trend_description: string;
}

export interface DailyStudyTimeItem {
  date: string;
  day_of_week: string;
  study_time_minutes: number;
  questions_attempted: number;
}

export interface ParentWeeklyData {
  student_id: string;
  student_name: string;
  week_start_date: string;
  week_end_date: string;
  total_study_time_minutes: number;
  daily_study_time: DailyStudyTimeItem[];
  tasks_completed_this_week: number;
  tasks_total_this_week: number;
  weekly_completion_rate: number;
  exam_trend: ParentExamTrendItem[];
  overall_weekly_summary: string;
}

export interface ParentWeeklyAISummary {
  student_id: string;
  student_name: string;
  week_start_date: string;
  week_end_date: string;
  progress: string;
  current_challenge: string;
  next_week: string;
  how_parent_can_help: string[];
  is_fallback: boolean;
  generated_at: string;
}

export class ParentApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string
  ) {
    super(message);
    this.name = "ParentApiError";
  }
}

export function parseParentProfile(value: unknown, path = "parent_profile"): ParentProfile {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    user_id: string(row.user_id, `${path}.user_id`),
    created_at: string(row.created_at, `${path}.created_at`),
    updated_at: string(row.updated_at, `${path}.updated_at`),
  };
}

export function parseParentStudentSummary(value: unknown, path = "student_summary"): ParentStudentSummary {
  const row = record(value, path);
  return {
    student_id: string(row.student_id, `${path}.student_id`),
    student_name: string(row.student_name, `${path}.student_name`),
    grade_level: integer(row.grade_level, `${path}.grade_level`),
    relationship_type: string(row.relationship_type, `${path}.relationship_type`),
    school_name: row.school_name === null || row.school_name === undefined ? null : string(row.school_name, `${path}.school_name`),
    overall_learning_trend: string(row.overall_learning_trend, `${path}.overall_learning_trend`),
    weekly_study_time_minutes: integer(row.weekly_study_time_minutes, `${path}.weekly_study_time_minutes`),
    active_alerts_count: integer(row.active_alerts_count, `${path}.active_alerts_count`),
  };
}

function parseExamTrendItem(value: unknown, path = "exam_trend_item"): ParentExamTrendItem {
  const row = record(value, path);
  return {
    title: string(row.title, `${path}.title`),
    date: string(row.date, `${path}.date`),
    score: number(row.score, `${path}.score`),
    total_questions: integer(row.total_questions, `${path}.total_questions`),
    assessment_type: string(row.assessment_type, `${path}.assessment_type`),
    trend_direction: string(row.trend_direction ?? "STABLE", `${path}.trend_direction`),
  };
}

export function parseParentStudentProgress(value: unknown, path = "student_progress"): ParentStudentProgress {
  const row = record(value, path);
  const comp = record(row.study_plan_completion, `${path}.study_plan_completion`);
  return {
    student_id: string(row.student_id, `${path}.student_id`),
    student_name: string(row.student_name, `${path}.student_name`),
    grade_level: integer(row.grade_level, `${path}.grade_level`),
    relationship_type: string(row.relationship_type, `${path}.relationship_type`),
    subject_progress: array(row.subject_progress ?? [], `${path}.subject_progress`, (item, p) => {
      const s = record(item, p);
      return {
        subject_id: string(s.subject_id, `${p}.subject_id`),
        subject_name: string(s.subject_name, `${p}.subject_name`),
        mastery_score: number(s.mastery_score, `${p}.mastery_score`),
        completed_topics_count: integer(s.completed_topics_count, `${p}.completed_topics_count`),
        total_topics_count: integer(s.total_topics_count, `${p}.total_topics_count`),
      };
    }),
    chapter_progress: array(row.chapter_progress ?? [], `${path}.chapter_progress`, (item, p) => {
      const c = record(item, p);
      return {
        chapter_id: string(c.chapter_id, `${p}.chapter_id`),
        chapter_name: string(c.chapter_name, `${p}.chapter_name`),
        subject_name: string(c.subject_name, `${p}.subject_name`),
        mastery_score: number(c.mastery_score, `${p}.mastery_score`),
        status: string(c.status, `${p}.status`),
      };
    }),
    topic_progress: array(row.topic_progress ?? [], `${path}.topic_progress`, (item, p) => {
      const t = record(item, p);
      return {
        topic_id: string(t.topic_id, `${p}.topic_id`),
        topic_name: string(t.topic_name, `${p}.topic_name`),
        chapter_name: string(t.chapter_name, `${p}.chapter_name`),
        mastery_score: number(t.mastery_score, `${p}.mastery_score`),
      };
    }),
    major_weak_areas: array(row.major_weak_areas ?? [], `${path}.major_weak_areas`, (item, p) => {
      const w = record(item, p);
      return {
        problem_type_id: string(w.problem_type_id, `${p}.problem_type_id`),
        problem_type_name: string(w.problem_type_name, `${p}.problem_type_name`),
        subject_name: string(w.subject_name, `${p}.subject_name`),
        mastery_score: number(w.mastery_score, `${p}.mastery_score`),
        parent_friendly_message: string(w.parent_friendly_message, `${p}.parent_friendly_message`),
        related_concept_name:
          w.related_concept_name === null || w.related_concept_name === undefined
            ? null
            : string(w.related_concept_name, `${p}.related_concept_name`),
        attempt_count: integer(w.attempt_count, `${p}.attempt_count`),
      };
    }),
    study_plan_completion: {
      total_tasks: integer(comp.total_tasks, `${path}.study_plan_completion.total_tasks`),
      completed_tasks: integer(comp.completed_tasks, `${path}.study_plan_completion.completed_tasks`),
      completion_rate: number(comp.completion_rate, `${path}.study_plan_completion.completion_rate`),
    },
    exam_trend: array(row.exam_trend ?? [], `${path}.exam_trend`, parseExamTrendItem),
    important_intervention_alerts: array(
      row.important_intervention_alerts ?? [],
      `${path}.important_intervention_alerts`,
      (item, p) => {
        const a = record(item, p);
        return {
          rule_code: string(a.rule_code, `${p}.rule_code`),
          severity: string(a.severity, `${p}.severity`),
          title: string(a.title, `${p}.title`),
          message: string(a.message, `${p}.message`),
          suggested_action_for_parent: string(a.suggested_action_for_parent, `${p}.suggested_action_for_parent`),
        };
      }
    ),
    overall_learning_trend: string(row.overall_learning_trend, `${path}.overall_learning_trend`),
    trend_description: string(row.trend_description, `${path}.trend_description`),
  };
}

export function parseParentWeeklyData(value: unknown, path = "weekly_data"): ParentWeeklyData {
  const row = record(value, path);
  return {
    student_id: string(row.student_id, `${path}.student_id`),
    student_name: string(row.student_name, `${path}.student_name`),
    week_start_date: string(row.week_start_date, `${path}.week_start_date`),
    week_end_date: string(row.week_end_date, `${path}.week_end_date`),
    total_study_time_minutes: integer(row.total_study_time_minutes, `${path}.total_study_time_minutes`),
    daily_study_time: array(row.daily_study_time ?? [], `${path}.daily_study_time`, (item, p) => {
      const d = record(item, p);
      return {
        date: string(d.date, `${p}.date`),
        day_of_week: string(d.day_of_week, `${p}.day_of_week`),
        study_time_minutes: integer(d.study_time_minutes, `${p}.study_time_minutes`),
        questions_attempted: integer(d.questions_attempted, `${p}.questions_attempted`),
      };
    }),
    tasks_completed_this_week: integer(row.tasks_completed_this_week, `${path}.tasks_completed_this_week`),
    tasks_total_this_week: integer(row.tasks_total_this_week, `${path}.tasks_total_this_week`),
    weekly_completion_rate: number(row.weekly_completion_rate, `${path}.weekly_completion_rate`),
    exam_trend: array(row.exam_trend ?? [], `${path}.exam_trend`, parseExamTrendItem),
    overall_weekly_summary: string(row.overall_weekly_summary, `${path}.overall_weekly_summary`),
  };
}

export function parseParentWeeklyAISummary(value: unknown, path = "ai_summary"): ParentWeeklyAISummary {
  const row = record(value, path);
  return {
    student_id: string(row.student_id, `${path}.student_id`),
    student_name: string(row.student_name, `${path}.student_name`),
    week_start_date: string(row.week_start_date, `${path}.week_start_date`),
    week_end_date: string(row.week_end_date, `${path}.week_end_date`),
    progress: string(row.progress, `${path}.progress`),
    current_challenge: string(row.current_challenge, `${path}.current_challenge`),
    next_week: string(row.next_week, `${path}.next_week`),
    how_parent_can_help: array(row.how_parent_can_help ?? [], `${path}.how_parent_can_help`, (item, p) => string(item, p)),
    is_fallback: boolean(row.is_fallback, `${path}.is_fallback`),
    generated_at: string(row.generated_at, `${path}.generated_at`),
  };
}

async function request<T>(path: string, parse: (value: unknown) => T, init: RequestInit = {}): Promise<T> {
  async function send(): Promise<Response> {
    try {
      return await fetch(`/api/parent/${path}`, {
        ...init,
        credentials: "same-origin",
        cache: "no-store",
      });
    } catch {
      throw new ParentApiError("Không thể kết nối đến máy chủ. Hãy kiểm tra backend.", 503, "NETWORK_ERROR");
    }
  }
  let response = await send();
  if (response.status === 401) {
    try {
      await refreshBrowserSession();
      response = await send();
    } catch {
      throw new ParentApiError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", 401, "SESSION_EXPIRED");
    }
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope =
      body && typeof body === "object" && "error" in body
        ? (body as { error?: { code?: string; message?: string } }).error
        : undefined;
    throw new ParentApiError(
      envelope?.message ?? `Yêu cầu thất bại (${response.status}).`,
      response.status,
      envelope?.code ?? "HTTP_ERROR"
    );
  }
  try {
    return parse(body);
  } catch (error) {
    if (error instanceof ApiContractError) {
      throw new ParentApiError("Dữ liệu backend không đúng hợp đồng API.", 503, "CONTRACT_ERROR");
    }
    throw error;
  }
}

export const parentApi = {
  me: () => request("me", parseParentProfile),
  students: () => request("students", (v) => array(v, "students", parseParentStudentSummary)),
  studentProgress: (studentId: string) =>
    request(`students/${encodeURIComponent(studentId)}/progress`, parseParentStudentProgress),
  studentWeeklyData: (studentId: string, targetDate?: string) => {
    const query = targetDate ? `?target_date=${encodeURIComponent(targetDate)}` : "";
    return request(`students/${encodeURIComponent(studentId)}/weekly-data${query}`, parseParentWeeklyData);
  },
  generateAiSummary: async (studentId: string, targetDate?: string) => {
    const query = targetDate ? `?target_date=${encodeURIComponent(targetDate)}` : "";
    return request(`students/${encodeURIComponent(studentId)}/ai-summary${query}`, parseParentWeeklyAISummary, {
      method: "POST",
      headers: { "X-CSRF-Token": await getCsrfToken() },
    });
  },
};
