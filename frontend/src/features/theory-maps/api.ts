import { getCsrfToken, refreshBrowserSession } from "../../lib/auth/browser";
import { array, boolean, integer, record, string } from "../../lib/api/validation";

export type NodeKind = "ROOT" | "SECTION" | "CONCEPT" | "FORMULA" | "EXAMPLE" | "NOTE" | "METHOD" | "QUICK_TRICK";
export interface TheoryLearningStep {
  instruction: string; latex: string | null; source_page: number | null; source_quote: string | null;
}
export interface TheoryNode {
  id: string; parent_id: string | null; kind: NodeKind; title: string; body: string;
  latex: string | null; learning_steps: TheoryLearningStep[];
  source_page: number; source_quote: string; reviewed: boolean;
  block_id?: string | null;
  bounding_box?: { top: number; bottom: number } | null;
  origin?: string | null;
}
export interface TheorySummary {
  id: string; classroom_id: string; subject_id: string; title: string; file_name: string;
  sha256: string; page_count: number; status: "DRAFT" | "PUBLISHED"; revision: number;
  source_available: boolean;
}
export interface TheoryMap extends TheorySummary {
  nodes: TheoryNode[]; ai_model: string | null; extraction_warning_pages: number[];
  source_outline: { title: string; source_page: number; kind: "CHAPTER" | "EXERCISE_TYPE" }[];
}

export function parseSummary(value: unknown, path = "map"): TheorySummary {
  const x = record(value, path);
  const status = string(x.status, `${path}.status`);
  if (status !== "DRAFT" && status !== "PUBLISHED") throw new Error("Trạng thái sơ đồ không hợp lệ.");
  return {
    id: string(x.id, `${path}.id`), classroom_id: string(x.classroom_id, `${path}.classroom_id`),
    subject_id: string(x.subject_id, `${path}.subject_id`), title: string(x.title, `${path}.title`),
    file_name: string(x.file_name, `${path}.file_name`), sha256: string(x.sha256, `${path}.sha256`),
    page_count: integer(x.page_count, `${path}.page_count`), status,
    revision: integer(x.revision, `${path}.revision`),
    source_available: boolean(x.source_available, `${path}.source_available`),
  };
}
function parseNode(value: unknown, path: string): TheoryNode {
  const x = record(value, path);
  const kind = string(x.kind, `${path}.kind`);
  if (!["ROOT", "SECTION", "CONCEPT", "FORMULA", "EXAMPLE", "NOTE", "METHOD", "QUICK_TRICK"].includes(kind)) throw new Error("Loại nút không hợp lệ.");
  return {
    id: string(x.id, `${path}.id`), parent_id: x.parent_id === null ? null : string(x.parent_id, `${path}.parent_id`),
    kind: kind as NodeKind, title: string(x.title, `${path}.title`), body: string(x.body, `${path}.body`),
    latex: x.latex == null ? null : string(x.latex, `${path}.latex`),
    learning_steps: array(x.learning_steps ?? [], `${path}.learning_steps`, (value, stepPath) => {
      const step = record(value, stepPath);
      return { instruction: string(step.instruction, `${stepPath}.instruction`),
        latex: step.latex == null ? null : string(step.latex, `${stepPath}.latex`),
        source_page: step.source_page == null ? null : integer(step.source_page, `${stepPath}.source_page`),
        source_quote: step.source_quote == null ? null : string(step.source_quote, `${stepPath}.source_quote`) };
    }),
    source_page: integer(x.source_page, `${path}.source_page`),
    source_quote: string(x.source_quote, `${path}.source_quote`), reviewed: boolean(x.reviewed, `${path}.reviewed`),
    block_id: typeof x.block_id === "string" ? x.block_id : null,
    bounding_box: x.bounding_box && typeof x.bounding_box === "object" ? (x.bounding_box as { top: number; bottom: number }) : null,
    origin: typeof x.origin === "string" ? x.origin : null,
  };
}
export function parseMap(value: unknown): TheoryMap {
  const x = record(value, "map");
  return { ...parseSummary(value), nodes: array(x.nodes, "map.nodes", parseNode),
    ai_model: x.ai_model === null ? null : string(x.ai_model, "map.ai_model"),
    extraction_warning_pages: array(x.extraction_warning_pages, "map.extraction_warning_pages", integer),
    source_outline: array(x.source_outline ?? [], "map.source_outline", (value, path) => {
      const section = record(value, path);
      const kind = string(section.kind, `${path}.kind`);
      if (kind !== "CHAPTER" && kind !== "EXERCISE_TYPE") throw new Error("Loại mục lục không hợp lệ.");
      return { title: string(section.title, `${path}.title`), source_page: integer(section.source_page, `${path}.source_page`), kind };
    }) };
}

export interface NotebookBlock {
  id: string; page: number; ordinal: number;
  kind: "METHOD" | "STEP" | "THEORY" | "NOTE" | "EXAMPLE" | "CONTINUATION" | "TOPIC" | "SECTION" | "FORMULA" | "CONCEPT" | "CHAPTER" | string;
  title: string;
  top?: number;
  bottom?: number;
}
export interface NotebookSection {
  id: string; title: string; chapter_number: number | null; chapter_title: string;
  blocks: NotebookBlock[];
}
export interface TheoryNotebook {
  sections: NotebookSection[]; total_blocks: number; page_count: number;
}
export function parseNotebook(value: unknown): TheoryNotebook {
  const x = record(value, "notebook");
  const knownKinds = new Set(["METHOD", "STEP", "THEORY", "NOTE", "EXAMPLE", "CONTINUATION", "TOPIC", "SECTION", "FORMULA", "CONCEPT", "CHAPTER"]);
  const sections = array(x.sections, "notebook.sections", (item, path) => {
    const section = record(item, path);
    const blocks = array(section.blocks, path + ".blocks", (part, partPath) => {
      const block = record(part, partPath);
      const rawKind = string(block.kind, partPath + ".kind");
      const kind = knownKinds.has(rawKind.toUpperCase()) ? rawKind.toUpperCase() : "THEORY";
      return { id: string(block.id, partPath + ".id"),
        page: integer(block.page, partPath + ".page"),
        ordinal: integer(block.ordinal, partPath + ".ordinal"),
        kind: kind as NotebookBlock["kind"],
        title: string(block.title, partPath + ".title") };
    });
    return { id: string(section.id, path + ".id"), title: string(section.title, path + ".title"),
      chapter_number: section.chapter_number === null ? null : integer(section.chapter_number, path + ".chapter_number"),
      chapter_title: string(section.chapter_title, path + ".chapter_title"), blocks };
  });
  const total_blocks = integer(x.total_blocks, "notebook.total_blocks");
  const page_count = integer(x.page_count, "notebook.page_count");
  if (sections.length === 0 || sections.some((section) => section.blocks.length === 0) || page_count < 1 ||
      sections.reduce((sum, section) => sum + section.blocks.length, 0) !== total_blocks ||
      sections.some((section) => section.blocks.some((block) => block.page < 1 || block.page > page_count || block.ordinal < 0))) {
    throw new Error("Sổ học không đúng cấu trúc.");
  }
  return { sections, total_blocks, page_count };
}
async function request<T>(url: string, parse: (value: unknown) => T, init: RequestInit = {}): Promise<T> {
  const send = () => fetch(url, { ...init, cache: "no-store", credentials: "same-origin" });
  let response: Response;
  try {
    response = await send();
    if (response.status === 401) { await refreshBrowserSession(); response = await send(); }
  } catch {
    throw new Error("Không thể kết nối máy chủ hoặc phiên đăng nhập đã hết hạn.");
  }
  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body && typeof body === "object" && "error" in body ? (body as { error?: { message?: string } }).error : null;
    throw new Error(error?.message || `Yêu cầu thất bại (${response.status}).`);
  }
  return parse(body);
}
const teacher = "/api/teacher/theory";
export const theoryApi = {
  teacherList: (classroomId: string) => request(`${teacher}?classroom_id=${encodeURIComponent(classroomId)}`,
    (v) => array(v, "maps", parseSummary)),
  teacherGet: (id: string) => request(`${teacher}/${encodeURIComponent(id)}`, parseMap),
  studentList: () => request("/api/student/theory", (v) => array(v, "maps", parseSummary)),
  teacherNotebook: (id: string) => request(teacher + "/" + encodeURIComponent(id) + "/notebook", parseNotebook),
  studentNotebook: (id: string) => request("/api/student/theory/" + encodeURIComponent(id) + "/notebook", parseNotebook),  studentGet: (id: string) => request(`/api/student/theory/${encodeURIComponent(id)}`, parseMap),
  upload: async (classroomId: string, subjectId: string, title: string, file: File) => {
    const body = new FormData();
    body.set("classroom_id", classroomId); body.set("subject_id", subjectId);
    body.set("title", title); body.set("file", file);
    return request(`${teacher}/upload`, parseMap,
      { method: "POST", headers: { "X-CSRF-Token": await getCsrfToken() }, body });
  },
  generate: async (id: string) => request(`${teacher}/${id}/generate`, parseMap,
    { method: "POST", headers: { "X-CSRF-Token": await getCsrfToken() } }),
  regenerate: async (map: TheoryMap) => request(`${teacher}/${map.id}/regenerate`, parseMap,
    { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify({ expected_revision: map.revision }) }),
  prefill: async (map: TheoryMap) => request(`${teacher}/${map.id}/prefill`, parseMap,
    { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify({ expected_revision: map.revision }) }),
  save: async (map: TheoryMap, nodes: TheoryNode[]) => request(`${teacher}/${map.id}/map`, parseMap,
    { method: "PUT", headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify({ expected_revision: map.revision, nodes }) }),
  publish: async (map: TheoryMap) => request(`${teacher}/${map.id}/publish`, parseMap,
    { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify({ expected_revision: map.revision }) }),
  unpublish: async (map: TheoryMap) => request(`${teacher}/${map.id}/unpublish`, parseMap,
    { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify({ expected_revision: map.revision }) }),
  setSourceVisibility: async (map: TheoryMap, visible: boolean) => request(
    `${teacher}/${map.id}/${visible ? "share-source" : "unshare-source"}`, parseMap,
    { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken() },
      body: JSON.stringify({ expected_revision: map.revision }) }),
  delete: async (id: string) => request(
    `${teacher}/${encodeURIComponent(id)}`, () => undefined,
    { method: "DELETE", headers: { "X-CSRF-Token": await getCsrfToken() } }),
};
