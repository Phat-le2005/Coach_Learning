import { getCsrfToken, refreshBrowserSession } from "../../lib/auth/browser";
import { ApiContractError, array, boolean, integer, number, record, string } from "../../lib/api/validation";

export interface TeacherClassroom { id: string; name: string; academic_year: string; grade_level: number; }
export interface TeacherSubject { id: string; code: string; name: string; grade_level: number | null; }
export interface TeacherStudent { student_id: string; full_name: string; email: string; status: string; is_synthetic: boolean; }
export interface TeacherMaterial { id: string; title: string; original_file_name: string; mime_type: string; file_size_bytes: number; status: string; subject_id: string; created_at: string; items_count?: number; }
export interface TeacherAssignment { id: string; title: string; status: string; question_count: number; due_at: string | null; subject_id: string; }
export interface TeacherRosterStudent { student_id: string; student_name: string; status: string; score: number | null; submitted_at: string | null; }
export interface TeacherRoster { assignment_id: string; title: string; total_students: number; submitted_count: number; graded_count: number; roster: TeacherRosterStudent[]; }
export interface TeacherAnalytics {
  student_count: number;
  subject_progress: { subject_id: string; subject_name: string; average_mastery: number; coverage_percentage: number }[];
  chapter_progress: { chapter_id: string; chapter_name: string; average_mastery: number; total_student_count: number }[];
  weak_problem_types: { id: string; name: string; average_score: number; student_count: number }[];
  students_needing_attention: { student_id: string; student_name: string; summary_reason: string }[];
  assignment_completion: { assignment_count: number; submitted_count: number; graded_count: number; completion_rate: number };
  evidence_summary: { scored_events: number; needs_teacher_review_count: number };
}

export class TeacherApiError extends Error {
  constructor(message: string, public readonly status: number, public readonly code: string) { super(message); this.name = "TeacherApiError"; }
}

export function parseClassroom(value: unknown, path = "classroom"): TeacherClassroom {
  const row = record(value, path);
  return { id: string(row.id, `${path}.id`), name: string(row.name, `${path}.name`), academic_year: string(row.academic_year, `${path}.academic_year`), grade_level: integer(row.grade_level, `${path}.grade_level`) };
}
export function parseSubject(value: unknown, path = "subject"): TeacherSubject {
  const row = record(value, path);
  return { id: string(row.id, `${path}.id`), code: string(row.code, `${path}.code`), name: string(row.name, `${path}.name`), grade_level: row.grade_level === null ? null : integer(row.grade_level, `${path}.grade_level`) };
}
export function parseStudent(value: unknown, path = "student"): TeacherStudent {
  const row = record(value, path);
  return { student_id: string(row.student_id, `${path}.student_id`), full_name: string(row.full_name, `${path}.full_name`), email: string(row.email, `${path}.email`), status: string(row.status, `${path}.status`), is_synthetic: boolean(row.is_synthetic, `${path}.is_synthetic`) };
}
export function parseMaterial(value: unknown, path = "material"): TeacherMaterial {
  const row = record(value, path);
  return { id: string(row.id, `${path}.id`), title: string(row.title, `${path}.title`), original_file_name: string(row.original_file_name, `${path}.original_file_name`), mime_type: string(row.mime_type, `${path}.mime_type`), file_size_bytes: integer(row.file_size_bytes, `${path}.file_size_bytes`), status: string(row.status, `${path}.status`), subject_id: string(row.subject_id, `${path}.subject_id`), created_at: string(row.created_at, `${path}.created_at`) };
}
export function parseAssignment(value: unknown, path = "assignment"): TeacherAssignment {
  const row = record(value, path);
  return { id: string(row.id, `${path}.id`), title: string(row.title, `${path}.title`), status: string(row.status, `${path}.status`), question_count: integer(row.question_count, `${path}.question_count`), due_at: row.due_at === null ? null : string(row.due_at, `${path}.due_at`), subject_id: string(row.subject_id, `${path}.subject_id`) };
}
export function parseRoster(value: unknown, path = "roster"): TeacherRoster {
  const row = record(value, path);
  return {
    assignment_id: string(row.assignment_id, `${path}.assignment_id`), title: string(row.title, `${path}.title`),
    total_students: integer(row.total_students, `${path}.total_students`), submitted_count: integer(row.submitted_count, `${path}.submitted_count`), graded_count: integer(row.graded_count, `${path}.graded_count`),
    roster: array(row.roster, `${path}.roster`, (item, itemPath) => {
      const student = record(item, itemPath);
      return { student_id: string(student.student_id, `${itemPath}.student_id`), student_name: string(student.student_name, `${itemPath}.student_name`), status: string(student.status, `${itemPath}.status`), score: student.score === null ? null : number(student.score, `${itemPath}.score`), submitted_at: student.submitted_at === null ? null : string(student.submitted_at, `${itemPath}.submitted_at`) };
    }),
  };
}
export function parseAnalytics(value: unknown, path = "analytics"): TeacherAnalytics {
  const row = record(value, path);
  return {
    student_count: integer(row.student_count, `${path}.student_count`),
    subject_progress: array(row.subject_progress, `${path}.subject_progress`, (v,p) => { const x=record(v,p); return { subject_id:string(x.subject_id,`${p}.subject_id`), subject_name:string(x.subject_name,`${p}.subject_name`), average_mastery:number(x.average_mastery,`${p}.average_mastery`), coverage_percentage:number(x.coverage_percentage,`${p}.coverage_percentage`) }; }),
    chapter_progress: array(row.chapter_progress, `${path}.chapter_progress`, (v,p) => { const x=record(v,p); return { chapter_id:string(x.chapter_id,`${p}.chapter_id`), chapter_name:string(x.chapter_name,`${p}.chapter_name`), average_mastery:number(x.average_mastery,`${p}.average_mastery`), total_student_count:integer(x.total_student_count,`${p}.total_student_count`) }; }),
    weak_problem_types: array(row.weak_problem_types, `${path}.weak_problem_types`, (v,p) => { const x=record(v,p); return { id:string(x.id,`${p}.id`), name:string(x.name,`${p}.name`), average_score:number(x.average_score,`${p}.average_score`), student_count:integer(x.student_count,`${p}.student_count`) }; }),
    students_needing_attention: array(row.students_needing_attention, `${path}.students_needing_attention`, (v,p) => { const x=record(v,p); return { student_id:string(x.student_id,`${p}.student_id`), student_name:string(x.student_name,`${p}.student_name`), summary_reason:string(x.summary_reason,`${p}.summary_reason`) }; }),
    assignment_completion: (() => { const x=record(row.assignment_completion,`${path}.assignment_completion`); return { assignment_count:integer(x.assignment_count,`${path}.assignment_completion.assignment_count`), submitted_count:integer(x.submitted_count,`${path}.assignment_completion.submitted_count`), graded_count:integer(x.graded_count,`${path}.assignment_completion.graded_count`), completion_rate:number(x.completion_rate,`${path}.assignment_completion.completion_rate`) }; })(),
    evidence_summary: (() => { const x=record(row.evidence_summary,`${path}.evidence_summary`); return { scored_events:integer(x.scored_events,`${path}.evidence_summary.scored_events`), needs_teacher_review_count:integer(x.needs_teacher_review_count,`${path}.evidence_summary.needs_teacher_review_count`) }; })(),
  };
}

async function request<T>(path: string, parse: (value: unknown) => T, init: RequestInit = {}): Promise<T> {
  async function send(): Promise<Response> {
    try { return await fetch(`/api/teacher/${path}`, { ...init, credentials: "same-origin", cache: "no-store" }); }
    catch { throw new TeacherApiError("Không thể kết nối đến máy chủ. Hãy kiểm tra backend.", 503, "NETWORK_ERROR"); }
  }
  let response = await send();
  if (response.status === 401) {
    try { await refreshBrowserSession(); response = await send(); }
    catch { throw new TeacherApiError("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.", 401, "SESSION_EXPIRED"); }
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope = body && typeof body === "object" && "error" in body ? (body as { error?: { code?: string; message?: string } }).error : undefined;
    throw new TeacherApiError(envelope?.message ?? `Yêu cầu thất bại (${response.status}).`, response.status, envelope?.code ?? "HTTP_ERROR");
  }
  try { return parse(body); }
  catch (error) {
    if (error instanceof ApiContractError) throw new TeacherApiError("Dữ liệu backend không đúng hợp đồng API.", 503, "CONTRACT_ERROR");
    throw error;
  }
}
const list = <T,>(value: unknown, parse: (value: unknown, path?: string) => T): T[] => array(value, "items", parse);
async function pages<T>(path: string, parse: (value: unknown, path?: string) => T): Promise<T[]> {
  const all: T[] = [];
  for (let offset = 0; ; offset += 200) {
    const batch = await request(`${path}?offset=${offset}&limit=200`, (v) => list(v, parse));
    all.push(...batch);
    if (batch.length < 200) return all;
  }
}
export const teacherApi = {
  subjects: () => request("subjects", (v) => list(v, parseSubject)),
  classes: () => pages("classes", parseClassroom),
  students: (id: string) => pages(`classes/${encodeURIComponent(id)}/students`, parseStudent),
  assignments: (id: string) => pages(`classes/${encodeURIComponent(id)}/assignments`, parseAssignment),
  materials: (id: string) => request(`materials?classroom_id=${encodeURIComponent(id)}`, (v) => list(v, parseMaterial)),
  analytics: (id: string) => request(`classes/${encodeURIComponent(id)}/analytics`, parseAnalytics),
  roster: (id: string) => request(`assignments/${encodeURIComponent(id)}/submissions`, parseRoster),
  createClass: async (name: string, academicYear: string, gradeLevel: number) => request("classes", parseClassroom, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() }, body: JSON.stringify({ name, academic_year: academicYear, grade_level: gradeLevel }) }),
  uploadMaterial: async (classroomId: string, subjectId: string, title: string, file: File) => {
    const body = new FormData(); body.set("classroom_id", classroomId); body.set("subject_id", subjectId); body.set("title", title); body.set("file", file);
    return request("materials/upload", parseMaterial, { method: "POST", headers: { "X-CSRF-Token": await getCsrfToken() }, body });
  },
};
