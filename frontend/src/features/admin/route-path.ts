const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const SAFE_QUERY = /^\?[a-zA-Z0-9_=&.%:-]{1,300}$/;

function isSafeSearch(search: string): boolean {
  if (!search) return true;
  if (!SAFE_QUERY.test(search)) return false;
  if (search.includes("..") || search.includes("//") || search.includes("\\")) return false;
  return true;
}

/**
 * Explicit allowlist of Admin-authorized backend endpoints mapped from `/api/admin/...`.
 * Prevents arbitrary SSRF or path traversal.
 */
export function adminBackendPath(parts: string[], method: string, search: string): string | null {
  if (parts.some((part) => !part || part === "." || part === ".." || part.includes("/"))) return null;
  if (!isSafeSearch(search)) return null;

  const [first, second, third] = parts;

  // 1. AI Observability & Usage Logs (/admin/ai/usage, /admin/ai/usage/summary)
  if (first === "ai" && method === "GET") {
    if (parts.length === 2 && second === "usage") return `/admin/ai/usage${search}`;
    if (parts.length === 3 && second === "usage" && third === "summary") return `/admin/ai/usage/summary${search}`;
  }

  // 2. Subjects & Curriculum Hierarchy (/admin/subjects, /admin/curricula, /admin/chapters, /admin/topics, /admin/problem-types, /admin/learning-outcomes)
  if (first === "subjects") {
    if (parts.length === 1 && (method === "GET" || method === "POST")) return `/admin/subjects${search}`;
    if (parts.length === 3 && UUID.test(second ?? "") && !search) {
      if (third === "chapters" && method === "GET") return `/admin/subjects/${second}/chapters`;
      if (third === "learning-outcomes" && method === "GET") return `/admin/subjects/${second}/learning-outcomes`;
      if (third === "curriculum-tree" && method === "GET") return `/admin/subjects/${second}/curriculum-tree`;
    }
  }

  if (first === "curricula" && parts.length === 1 && !search) {
    if (method === "GET" || method === "POST") return "/admin/curricula";
  }

  if (first === "curriculum-versions" && parts.length === 1) {
    if (method === "GET" || (method === "POST" && !search)) return `/admin/curriculum-versions${search}`;
  }

  if (first === "chapters") {
    if (parts.length === 1 && method === "POST" && !search) return "/admin/chapters";
    if (parts.length === 3 && UUID.test(second ?? "") && third === "topics" && method === "GET" && !search) {
      return `/admin/chapters/${second}/topics`;
    }
  }

  if (first === "topics") {
    if (parts.length === 1 && method === "POST" && !search) return "/admin/topics";
    if (parts.length === 3 && UUID.test(second ?? "") && third === "problem-types" && method === "GET" && !search) {
      return `/admin/topics/${second}/problem-types`;
    }
  }

  if (first === "problem-types") {
    if (parts.length === 1 && method === "POST" && !search) return "/admin/problem-types";
    if (parts.length === 2 && UUID.test(second ?? "") && method === "GET" && !search) {
      return `/admin/problem-types/${second}`;
    }
  }

  if (first === "learning-outcomes" && parts.length === 1 && method === "POST" && !search) {
    return "/admin/learning-outcomes";
  }

  // 3. Concepts & Knowledge Graph (/admin/concepts, /admin/concept-relations)
  if (first === "concepts") {
    if (parts.length === 1 && method === "POST" && !search) return "/admin/concepts";
    if (parts.length === 2 && UUID.test(second ?? "") && method === "PATCH" && !search) {
      return `/admin/concepts/${second}`;
    }
  }

  if (first === "concept-relations") {
    if (parts.length === 1 && method === "POST" && !search) return "/admin/concept-relations";
    if (parts.length === 2 && UUID.test(second ?? "") && method === "DELETE" && !search) {
      return `/admin/concept-relations/${second}`;
    }
  }

  // 4. Question Bank & Approval (/questions, /questions/{id}/approve)
  if (first === "questions") {
    if (parts.length === 1 && method === "GET") return `/questions${search}`;
    if (parts.length === 2 && UUID.test(second ?? "") && !search) {
      if (method === "GET" || method === "PATCH") return `/questions/${second}`;
    }
    if (parts.length === 3 && UUID.test(second ?? "") && third === "approve" && method === "POST" && !search) {
      return `/questions/${second}/approve`;
    }
  }

  // 5. Question Supply Gaps (/question-supply/gaps, /question-supply/assess)
  if (first === "question-supply") {
    if (parts.length === 2 && second === "gaps" && method === "GET") {
      return `/question-supply/gaps${search}`;
    }
    if (parts.length === 2 && second === "assess" && method === "POST" && !search) {
      return "/question-supply/assess";
    }
    if (parts.length === 3 && second === "gaps" && third === "reassess-open" && method === "POST" && !search) {
      return "/question-supply/gaps/reassess-open";
    }
    if (parts.length === 3 && second === "gaps" && UUID.test(third ?? "") && method === "GET" && !search) {
      return `/question-supply/gaps/${third}`;
    }
    if (
      parts.length === 4 &&
      second === "gaps" &&
      UUID.test(third ?? "") &&
      (parts[3] === "reassess" || parts[3] === "acquisition") &&
      method === "POST" &&
      !search
    ) {
      return `/question-supply/gaps/${third}/${parts[3]}`;
    }
  }

  // 6. Question Acquisition (/question-acquisition/requests)
  if (first === "question-acquisition") {
    if (parts.length === 2 && second === "requests" && method === "GET") {
      return `/question-acquisition/requests${search}`;
    }
    if (parts.length === 3 && second === "requests" && UUID.test(third ?? "") && method === "GET" && !search) {
      return `/question-acquisition/requests/${third}`;
    }
    if (
      parts.length === 4 &&
      second === "requests" &&
      UUID.test(third ?? "") &&
      parts[3] === "cancel" &&
      method === "POST" &&
      !search
    ) {
      return `/question-acquisition/requests/${third}/cancel`;
    }
  }

  // 7. Question Validation Batches (/question-validation/batches, /question-validation/candidates/{id}/promote)
  if (first === "question-validation") {
    if (parts.length === 2 && second === "batches" && method === "GET") {
      return `/question-validation/batches${search}`;
    }
    if (parts.length === 3 && second === "batches" && UUID.test(third ?? "") && method === "GET" && !search) {
      return `/question-validation/batches/${third}`;
    }
    if (
      parts.length === 4 &&
      second === "candidates" &&
      UUID.test(third ?? "") &&
      ["validate", "promote", "reject"].includes(parts[3] ?? "") &&
      method === "POST" &&
      !search
    ) {
      return `/question-validation/candidates/${third}/${parts[3]}`;
    }
  }

  // 8. Admission Catalog & Import History (/admission/universities, /admission/majors, /admission/import/history)
  if (first === "admission") {
    if (parts.length === 2 && second === "universities") {
      if (method === "GET") return `/admission/universities${search}`;
      if (method === "POST" && !search) return "/admission/universities";
    }
    if (parts.length === 2 && second === "majors" && method === "POST" && !search) {
      return "/admission/majors";
    }
    if (parts.length === 2 && second === "rules" && method === "POST" && !search) {
      return "/admission/rules";
    }
    if (parts.length === 4 && second === "universities" && UUID.test(third ?? "") && parts[3] === "majors" && method === "GET") {
      return `/admission/universities/${third}/majors${search}`;
    }
    if (parts.length === 4 && second === "majors" && UUID.test(third ?? "") && parts[3] === "rules" && method === "GET") {
      return `/admission/majors/${third}/rules${search}`;
    }
    if (parts.length === 3 && second === "import" && third === "history" && method === "GET") {
      return `/admission/import/history${search}`;
    }
  }

  return null;
}
