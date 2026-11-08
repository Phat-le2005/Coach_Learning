import { getCsrfToken, refreshBrowserSession } from "../../lib/auth/browser";
import { ApiContractError, array, boolean, integer, number, record, string } from "../../lib/api/validation";
import { parseMaterialDifficulty, type MaterialDifficultyLevel } from "./material-difficulty";

export interface TeacherClassroom { id: string; name: string; academic_year: string; grade_level: number; }
export interface TeacherSubject { id: string; code: string; name: string; grade_level: number | null; }
export interface TeacherStudent { student_id: string; full_name: string; email: string; status: string; is_synthetic: boolean; }
export interface TeacherMaterial { id: string; title: string; original_file_name: string; mime_type: string; file_size_bytes: number; status: string; subject_id: string; created_at: string; items_count?: number; pdf_import_id?: string | null; }
export interface TeacherAssignment { id: string; title: string; status: string; question_count: number; due_at: string | null; subject_id: string; delivery_mode?: string; }
export interface TeacherRosterStudent { student_id: string; student_name: string; status: string; score: number | null; provisional_score?: number | null; submitted_at: string | null; }
export interface TeacherRoster { assignment_id: string; title: string; total_students: number; submitted_count: number; graded_count: number; roster: TeacherRosterStudent[]; }
export interface TeacherMaterialItemOption { id: string; label: string; content: string; order_index: number; }
export interface TeacherMaterialItem { id: string; order_index: number; content: string; question_type: string | null; correct_answer: string | null; explanation: string | null; difficulty: number | null; difficulty_level?: MaterialDifficultyLevel | null; extraction_status: string; evaluation_mode: string; options: TeacherMaterialItemOption[]; visual_assets?: number[]; }
export interface TeacherSubmissionStepDetail { step_id: string; step_index: number; step_type: string; content_latex: string | null; explanation_text: string | null; math_validity: string | null; confidence: number | null; error_detected: boolean | null; error_description: string | null; }
export interface TeacherSubmissionPaperAttachment { id: string; file_name: string; content_type: string; storage_key: string; }
export interface TeacherSubmissionItem { id: string; source_kind: string; order_index: number; content: string | null; question_type: string | null; options: { id: string; label: string; content: string; order_index: number }[]; correct_answer: string | null; explanation: string | null; student_answer: string | null; is_correct: boolean | null; score: number | null; provisional_score?: number | null; evaluation_status: string | null; teacher_feedback: string | null; graded_at: string | null; graded_by: string | null; attempt_id: string | null; attempt_status: string | null; steps: TeacherSubmissionStepDetail[]; paper_attachments: TeacherSubmissionPaperAttachment[]; }
export interface TeacherStudentSubmissionDetail { assignment_id: string; assignment_title: string; delivery_mode: string; classroom_id: string; student_id: string; student_name: string; status: string; score: number | null; provisional_score?: number | null; submitted_at: string | null; items: TeacherSubmissionItem[]; }
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
  return { id: string(row.id, `${path}.id`), title: string(row.title, `${path}.title`), original_file_name: string(row.original_file_name, `${path}.original_file_name`), mime_type: string(row.mime_type, `${path}.mime_type`), file_size_bytes: integer(row.file_size_bytes, `${path}.file_size_bytes`), status: string(row.status, `${path}.status`), subject_id: string(row.subject_id, `${path}.subject_id`), created_at: string(row.created_at, `${path}.created_at`), pdf_import_id: row.pdf_import_id == null ? null : string(row.pdf_import_id, `${path}.pdf_import_id`) };
}
export function parseAssignment(value: unknown, path = "assignment"): TeacherAssignment {
  const row = record(value, path);
  return {
    id: string(row.id, `${path}.id`),
    title: string(row.title, `${path}.title`),
    status: string(row.status, `${path}.status`),
    question_count: integer(row.question_count, `${path}.question_count`),
    due_at: row.due_at === null ? null : string(row.due_at, `${path}.due_at`),
    subject_id: string(row.subject_id, `${path}.subject_id`),
    delivery_mode: row.delivery_mode ? string(row.delivery_mode, `${path}.delivery_mode`) : undefined,
  };
}
export function parseRoster(value: unknown, path = "roster"): TeacherRoster {
  const row = record(value, path);
  return {
    assignment_id: string(row.assignment_id, `${path}.assignment_id`), title: string(row.title, `${path}.title`),
    total_students: integer(row.total_students, `${path}.total_students`), submitted_count: integer(row.submitted_count, `${path}.submitted_count`), graded_count: integer(row.graded_count, `${path}.graded_count`),
    roster: array(row.roster, `${path}.roster`, (item, itemPath) => {
      const student = record(item, itemPath);
      return {
        student_id: string(student.student_id, `${itemPath}.student_id`),
        student_name: string(student.student_name, `${itemPath}.student_name`),
        status: string(student.status, `${itemPath}.status`),
        score: student.score === null || student.score === undefined ? null : number(student.score, `${itemPath}.score`),
        provisional_score: student.provisional_score === null || student.provisional_score === undefined ? null : number(student.provisional_score, `${itemPath}.provisional_score`),
        submitted_at: student.submitted_at === null ? null : string(student.submitted_at, `${itemPath}.submitted_at`),
      };
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
export { request as teacherRequest };
const list = <T,>(value: unknown, parse: (value: unknown, path?: string) => T): T[] => array(value, "items", parse);
async function pages<T>(path: string, parse: (value: unknown, path?: string) => T): Promise<T[]> {
  const all: T[] = [];
  for (let offset = 0; ; offset += 200) {
    const batch = await request(`${path}?offset=${offset}&limit=200`, (v) => list(v, parse));
    all.push(...batch);
    if (batch.length < 200) return all;
  }
}
export function parseMaterialItem(value: unknown, path = "item"): TeacherMaterialItem {
  const row = record(value, path);
  const metadata = row.raw_metadata == null ? {} : record(row.raw_metadata, `${path}.raw_metadata`);
  return {
    id: string(row.id, `${path}.id`),
    order_index: integer(row.order_index, `${path}.order_index`),
    content: string(row.content, `${path}.content`),
    visual_assets: array(metadata.visual_assets ?? [], `${path}.visual_assets`, integer),
    question_type: row.question_type === null || row.question_type === undefined ? null : string(row.question_type, `${path}.question_type`),
    correct_answer: row.correct_answer === null || row.correct_answer === undefined ? null : string(row.correct_answer, `${path}.correct_answer`),
    explanation: row.explanation === null || row.explanation === undefined ? null : string(row.explanation, `${path}.explanation`),
    difficulty: row.difficulty === null || row.difficulty === undefined ? null : number(row.difficulty, `${path}.difficulty`),
    difficulty_level: parseMaterialDifficulty(metadata.difficulty_level, `${path}.difficulty_level`),
    extraction_status: string(row.extraction_status, `${path}.extraction_status`),
    evaluation_mode: string(row.evaluation_mode, `${path}.evaluation_mode`),
    options: array(row.options ?? [], `${path}.options`, (opt, optP) => {
      const o = record(opt, optP);
      return {
        id: string(o.id, `${optP}.id`),
        label: string(o.label, `${optP}.label`),
        content: string(o.content, `${optP}.content`),
        order_index: integer(o.order_index, `${optP}.order_index`),
      };
    }),
  };
}

export function parseStudentSubmission(value: unknown, path = "submission"): TeacherStudentSubmissionDetail {
  const row = record(value, path);
  return {
    assignment_id: string(row.assignment_id, `${path}.assignment_id`),
    assignment_title: string(row.assignment_title, `${path}.assignment_title`),
    delivery_mode: string(row.delivery_mode ?? "PRACTICE", `${path}.delivery_mode`),
    classroom_id: string(row.classroom_id, `${path}.classroom_id`),
    student_id: string(row.student_id, `${path}.student_id`),
    student_name: string(row.student_name, `${path}.student_name`),
    status: string(row.status, `${path}.status`),
    score: row.score === null || row.score === undefined ? null : number(row.score, `${path}.score`),
    provisional_score: row.provisional_score === null || row.provisional_score === undefined ? null : number(row.provisional_score, `${path}.provisional_score`),
    submitted_at: row.submitted_at === null || row.submitted_at === undefined ? null : string(row.submitted_at, `${path}.submitted_at`),
    items: array(row.items ?? [], `${path}.items`, (item, itemP) => {
      const i = record(item, itemP);
      return {
        id: string(i.id, `${itemP}.id`),
        source_kind: string(i.source_kind, `${itemP}.source_kind`),
        order_index: integer(i.order_index, `${itemP}.order_index`),
        content: i.content === null || i.content === undefined ? null : string(i.content, `${itemP}.content`),
        question_type: i.question_type === null || i.question_type === undefined ? null : string(i.question_type, `${itemP}.question_type`),
        options: array(i.options ?? [], `${itemP}.options`, (o, oP) => {
          const opt = record(o, oP);
          return {
            id: string(opt.id, `${oP}.id`),
            label: string(opt.label, `${oP}.label`),
            content: string(opt.content, `${oP}.content`),
            order_index: integer(opt.order_index, `${oP}.order_index`),
          };
        }),
        correct_answer: i.correct_answer === null || i.correct_answer === undefined ? null : string(i.correct_answer, `${itemP}.correct_answer`),
        explanation: i.explanation === null || i.explanation === undefined ? null : string(i.explanation, `${itemP}.explanation`),
        student_answer: i.student_answer === null || i.student_answer === undefined ? null : string(i.student_answer, `${itemP}.student_answer`),
        is_correct: i.is_correct === null || i.is_correct === undefined ? null : boolean(i.is_correct, `${itemP}.is_correct`),
        score: i.score === null || i.score === undefined ? null : number(i.score, `${itemP}.score`),
        provisional_score: i.provisional_score === null || i.provisional_score === undefined ? null : number(i.provisional_score, `${itemP}.provisional_score`),
        evaluation_status: i.evaluation_status === null || i.evaluation_status === undefined ? null : string(i.evaluation_status, `${itemP}.evaluation_status`),
        teacher_feedback: i.teacher_feedback === null || i.teacher_feedback === undefined ? null : string(i.teacher_feedback, `${itemP}.teacher_feedback`),
        graded_at: i.graded_at === null || i.graded_at === undefined ? null : string(i.graded_at, `${itemP}.graded_at`),
        graded_by: i.graded_by === null || i.graded_by === undefined ? null : string(i.graded_by, `${itemP}.graded_by`),
        attempt_id: i.attempt_id === null || i.attempt_id === undefined ? null : string(i.attempt_id, `${itemP}.attempt_id`),
        attempt_status: i.attempt_status === null || i.attempt_status === undefined ? null : string(i.attempt_status, `${itemP}.attempt_status`),
        steps: array(i.steps ?? [], `${itemP}.steps`, (st, stP) => {
          const s = record(st, stP);
          return {
            step_id: string(s.step_id, `${stP}.step_id`),
            step_index: integer(s.step_index, `${stP}.step_index`),
            step_type: string(s.step_type, `${stP}.step_type`),
            content_latex: s.content_latex === null || s.content_latex === undefined ? null : string(s.content_latex, `${stP}.content_latex`),
            explanation_text: s.explanation_text === null || s.explanation_text === undefined ? null : string(s.explanation_text, `${stP}.explanation_text`),
            math_validity: s.math_validity === null || s.math_validity === undefined ? null : string(s.math_validity, `${stP}.math_validity`),
            confidence: s.confidence === null || s.confidence === undefined ? null : number(s.confidence, `${stP}.confidence`),
            error_detected: s.error_detected === null || s.error_detected === undefined ? null : boolean(s.error_detected, `${stP}.error_detected`),
            error_description: s.error_description === null || s.error_description === undefined ? null : string(s.error_description, `${stP}.error_description`),
          };
        }),
        paper_attachments: array(i.paper_attachments ?? [], `${itemP}.paper_attachments`, (p, pP) => {
          const pa = record(p, pP);
          return {
            id: string(pa.id, `${pP}.id`),
            file_name: string(pa.file_name, `${pP}.file_name`),
            content_type: string(pa.content_type, `${pP}.content_type`),
            storage_key: string(pa.storage_key, `${pP}.storage_key`),
          };
        }),
      };
    }),
  };
}

export const teacherApi = {
  deleteMaterial: async (materialId: string) => request(`materials/${encodeURIComponent(materialId)}`, () => undefined, {
    method: "DELETE", headers: { "X-CSRF-Token": await getCsrfToken() },
  }),
  subjects: () => request("subjects", (v) => list(v, parseSubject)),
  classes: () => pages("classes", parseClassroom),
  students: (id: string) => pages(`classes/${encodeURIComponent(id)}/students`, parseStudent),
  assignments: (id: string) => pages(`classes/${encodeURIComponent(id)}/assignments`, parseAssignment),
  materials: (id: string) => request(`materials?classroom_id=${encodeURIComponent(id)}`, (v) => list(v, parseMaterial)),
  materialItems: (materialId: string) => request(`materials/${encodeURIComponent(materialId)}/items`, (v) => array(v, "items", parseMaterialItem)),
  prepareMaterialForAssignment: async (materialId: string) =>
    request(`materials/${encodeURIComponent(materialId)}/prepare-assignment`, parseMaterial, {
      method: "POST",
      headers: { "X-CSRF-Token": await getCsrfToken() },
    }),
  createAssignmentFromMaterial: async (
    classroomId: string,
    data: {
      title: string;
      subjectId: string;
      deliveryMode: "PRACTICE" | "EXAM";
      dueAt?: string | null;
      teacherMaterialItemIds: string[];
    }
  ) => {
    return request(
      `classes/${encodeURIComponent(classroomId)}/assignments`,
      parseAssignment,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
        body: JSON.stringify({
          classroom_id: classroomId,
          subject_id: data.subjectId,
          title: data.title,
          assignment_type: "SAME_SET",
          delivery_mode: data.deliveryMode,
          question_count: data.teacherMaterialItemIds.length,
          teacher_material_item_ids: data.teacherMaterialItemIds,
          due_at: data.dueAt || null,
        }),
      }
    );
  },
  publishAssignment: async (assignmentId: string) =>
    request(`assignments/${encodeURIComponent(assignmentId)}/publish`, parseAssignment, {
      method: "POST",
      headers: { "X-CSRF-Token": await getCsrfToken() },
    }),
  analytics: (id: string) => request(`classes/${encodeURIComponent(id)}/analytics`, parseAnalytics),
  roster: (id: string) => request(`assignments/${encodeURIComponent(id)}/submissions`, parseRoster),
  submissionDetail: (assignmentId: string, studentId: string) =>
    request(`assignments/${encodeURIComponent(assignmentId)}/students/${encodeURIComponent(studentId)}`, parseStudentSubmission),
  gradeMaterialItem: async (
    assignmentId: string,
    studentId: string,
    materialItemId: string,
    score: number,
    isCorrect: boolean,
    feedback?: string
  ) => {
    return request(
      `assignments/${encodeURIComponent(assignmentId)}/students/${encodeURIComponent(studentId)}/material-items/${encodeURIComponent(materialItemId)}/grade`,
      (v) => v,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
        body: JSON.stringify({ score, is_correct: isCorrect, feedback, allow_override: true }),
      }
    );
  },
  gradeCanonicalItem: async (
    assignmentId: string,
    studentId: string,
    questionItemId: string,
    score: number,
    isCorrect: boolean,
    feedback?: string
  ) => {
    return request(
      `assignments/${encodeURIComponent(assignmentId)}/students/${encodeURIComponent(studentId)}/questions/${encodeURIComponent(questionItemId)}/grade`,
      (v) => v,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
        body: JSON.stringify({ score, is_correct: isCorrect, feedback, allow_override: true }),
      }
    );
  },
  finalizeSubmission: async (assignmentId: string, studentId: string) => {
    return request(
      `assignments/${encodeURIComponent(assignmentId)}/students/${encodeURIComponent(studentId)}/finalize`,
      (v) => v,
      {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      }
    );
  },
  createClass: async (name: string, academicYear: string, gradeLevel: number) => request("classes", parseClassroom, { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() }, body: JSON.stringify({ name, academic_year: academicYear, grade_level: gradeLevel }) }),
  uploadMaterial: async (classroomId: string, subjectId: string, title: string, file: File) => {
    const body = new FormData(); body.set("classroom_id", classroomId); body.set("subject_id", subjectId); body.set("title", title); body.set("file", file);
    return request("materials/upload", parseMaterial, { method: "POST", headers: { "X-CSRF-Token": await getCsrfToken() }, body });
  },
};
