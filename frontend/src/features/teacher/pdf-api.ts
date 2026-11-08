import { getCsrfToken } from "../../lib/auth/browser";
import { array, boolean, integer, oneOf, record, string } from "../../lib/api/validation";
import { parseMaterial, teacherRequest } from "./api";
import { parseMaterialDifficulty, type MaterialDifficultyLevel } from "./material-difficulty";
import { parseQuestionVisuals, type QuestionVisual } from "../../lib/api/question-visuals";

export interface PdfReviewDecision {
  question_id: string;
  accepted: boolean;
  source_checked: boolean;
  content: string;
  answer: string;
  explanation: string;
  difficulty_level: MaterialDifficultyLevel | null;
}
export interface PdfReviewSubmit { title: string; decisions: PdfReviewDecision[]; }
export interface PdfImportQuestion {
  visuals?: QuestionVisual[];
  question_id: string;
  number: number;
  source_number: number | null;
  content: string;
  answer: string;
  explanation: string;
  difficulty_level: MaterialDifficultyLevel | null;
  pages: number[];
  warnings: string[];
  suggested: boolean;
  source_assets: number[];
  visual_assets: number[];
}
export interface TeacherPdfImport {
  id: string;
  classroom_id: string;
  subject_id: string;
  title: string;
  original_file_name: string;
  source_kind: "PDF" | "IMAGE";
  source_mime_type: "application/pdf" | "image/png" | "image/jpeg";
  status: "QUEUED" | "PROCESSING" | "NEEDS_REVIEW" | "FAILED" | "SUBMITTED";
  created_at: string;
  error: string | null;
  material_id: string | null;
  revision_of?: string | null;
  progress: { processed_pages?: number; selected_pages?: number; failed_regions?: number; review_regions?: number; questions?: number };
  questions: PdfImportQuestion[];
  review: PdfReviewSubmit | null;
}

function parseDecision(value: unknown, path: string): PdfReviewDecision {
  const row = record(value, path);
  return {
    question_id: string(row.question_id, `${path}.question_id`), accepted: boolean(row.accepted, `${path}.accepted`),
    source_checked: boolean(row.source_checked, `${path}.source_checked`), content: string(row.content, `${path}.content`),
    answer: string(row.answer, `${path}.answer`), explanation: string(row.explanation, `${path}.explanation`),
    difficulty_level: parseMaterialDifficulty(row.difficulty_level, `${path}.difficulty_level`),
  };
}

export function parsePdfImport(value: unknown, path = "pdfImport"): TeacherPdfImport {
  const row = record(value, path);
  const progress = record(row.progress, `${path}.progress`);
  const status = string(row.status, `${path}.status`);
  if (!["QUEUED", "PROCESSING", "NEEDS_REVIEW", "FAILED", "SUBMITTED"].includes(status)) throw new Error("Trạng thái OCR không hợp lệ.");
  const review = row.review == null ? null : record(row.review, `${path}.review`);
  return {
    id: string(row.id, `${path}.id`), classroom_id: string(row.classroom_id, `${path}.classroom_id`),
    subject_id: string(row.subject_id, `${path}.subject_id`), title: string(row.title, `${path}.title`),
    original_file_name: string(row.original_file_name, `${path}.original_file_name`), status: status as TeacherPdfImport["status"],
    source_kind: oneOf(row.source_kind ?? "PDF", `${path}.source_kind`, ["PDF", "IMAGE"] as const),
    source_mime_type: oneOf(row.source_mime_type ?? "application/pdf", `${path}.source_mime_type`, ["application/pdf", "image/png", "image/jpeg"] as const),
    created_at: string(row.created_at, `${path}.created_at`),
    error: row.error == null ? null : string(row.error, `${path}.error`),
    material_id: row.material_id == null ? null : string(row.material_id, `${path}.material_id`),
    revision_of: row.revision_of == null ? null : string(row.revision_of, `${path}.revision_of`),
    progress: Object.fromEntries(Object.entries(progress).map(([key, val]) => [key, integer(val, `${path}.progress.${key}`)])),
    review: review ? { title: string(review.title, `${path}.review.title`), decisions: array(review.decisions, `${path}.review.decisions`, parseDecision) } : null,
    questions: array(row.questions, `${path}.questions`, (value, p) => {
      const q = record(value, p);
      return {
        question_id: string(q.question_id, `${p}.question_id`), number: integer(q.number, `${p}.number`),
        source_number: q.source_number == null ? null : integer(q.source_number, `${p}.source_number`),
        content: string(q.content, `${p}.content`), answer: string(q.answer, `${p}.answer`), explanation: string(q.explanation, `${p}.explanation`),
        difficulty_level: parseMaterialDifficulty(q.difficulty_level, `${p}.difficulty_level`),
        suggested: boolean(q.suggested, `${p}.suggested`), pages: array(q.pages, `${p}.pages`, integer),
        warnings: array(q.warnings, `${p}.warnings`, string), source_assets: array(q.source_assets, `${p}.source_assets`, integer),
        visual_assets: array(q.visual_assets, `${p}.visual_assets`, integer),
        visuals: parseQuestionVisuals(q.visuals, `${p}.visuals`),
      };
    }),
  };
}

const base = "materials/pdf-imports";
const jsonMutation = async (method: string, data?: PdfReviewSubmit): Promise<RequestInit> => ({
  method, headers: { "X-CSRF-Token": await getCsrfToken(), "Content-Type": "application/json" },
  ...(data ? { body: JSON.stringify(data) } : {}),
});
export const teacherPdfApi = {
  list: (classroomId: string) => teacherRequest(`${base}?classroom_id=${encodeURIComponent(classroomId)}`, (v) => array(v, "imports", parsePdfImport)),
  get: (id: string) => teacherRequest(`${base}/${encodeURIComponent(id)}`, parsePdfImport),
  upload: async (classroomId: string, subjectId: string, title: string, file: File) => {
    const body = new FormData();
    body.set("classroom_id", classroomId); body.set("subject_id", subjectId); body.set("title", title); body.set("file", file);
    return teacherRequest(base, parsePdfImport, { method: "POST", headers: { "X-CSRF-Token": await getCsrfToken() }, body });
  },
  retry: async (id: string) => teacherRequest(`${base}/${encodeURIComponent(id)}/retry`, parsePdfImport, await jsonMutation("POST")),
  revise: async (id: string) => teacherRequest(`${base}/${encodeURIComponent(id)}/revise`, parsePdfImport, await jsonMutation("POST")),
  save: async (id: string, data: PdfReviewSubmit) => teacherRequest(`${base}/${encodeURIComponent(id)}/review`, parsePdfImport, await jsonMutation("PUT", data)),
  submit: async (id: string, data: PdfReviewSubmit) => teacherRequest(`${base}/${encodeURIComponent(id)}/submit`, parseMaterial, await jsonMutation("POST", data)),
  sourceUrl: (id: string) => `/api/teacher/${base}/${encodeURIComponent(id)}/source`,
  assetUrl: (id: string, index: number) => `/api/teacher/${base}/${encodeURIComponent(id)}/assets/${index}`,
};
