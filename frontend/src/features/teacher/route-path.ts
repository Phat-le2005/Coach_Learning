const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PAGE_QUERY = /^\?offset=\d+&limit=\d+$/;

/** Only explicit teacher-owned backend routes are exposed. */
export function teacherBackendPath(parts: string[], method: string, search: string): string | null {
  if (parts.some((part) => !part || part === "." || part === ".." || part.includes("/"))) return null;
  const [first, id, action] = parts;
  if (first === "subjects" && parts.length === 1 && method === "GET" && !search) return "/api/v2/teacher/subjects";
  if (first === "classes") {
    if (parts.length === 1 && method === "GET" && (!search || PAGE_QUERY.test(search))) return `/teacher/classes${search}`;
    if (parts.length === 1 && method === "POST" && !search) return "/teacher/classes";
    if (UUID.test(id ?? "") && parts.length === 3) {
      if (action === "analytics" && method === "GET" && !search) return `/teacher/classes/${id}/analytics`;
      if (["students", "assignments"].includes(action ?? "") && method === "GET" && (!search || PAGE_QUERY.test(search))) return `/teacher/classes/${id}/${action}${search}`;
      if (action === "assignments" && method === "POST" && !search) return `/teacher/classes/${id}/assignments`;
    }
  }
  if (first === "materials") {
    if (id === "pdf-imports") {
      if (parts.length === 2 && method === "POST" && !search) return "/teacher-materials/pdf-imports";
      if (parts.length === 2 && method === "GET" && /^\?classroom_id=[0-9a-f-]{36}$/i.test(search) && UUID.test(search.slice(14))) return `/teacher-materials/pdf-imports${search}`;
      if (UUID.test(action ?? "") && !search) {
        const base = `/teacher-materials/pdf-imports/${action}`;
        if (parts.length === 3 && method === "GET") return base;
        if (parts.length === 4 && parts[3] === "source" && method === "GET") return `${base}/source`;
        if (parts.length === 4 && parts[3] === "review" && method === "PUT") return `${base}/review`;
        if (parts.length === 4 && ["retry", "submit", "revise"].includes(parts[3]) && method === "POST") return `${base}/${parts[3]}`;
        if (parts.length === 5 && parts[3] === "assets" && /^\d{1,6}$/.test(parts[4]) && method === "GET") return `${base}/assets/${parts[4]}`;
      }
      return null;
    }
    if (parts.length === 1 && method === "GET" && search.startsWith("?classroom_id=") && UUID.test(search.slice(14))) return `/teacher-materials${search}`;
    if (parts.length === 2 && id === "upload" && method === "POST" && !search) return "/teacher-materials/upload";
    if (parts.length === 2 && UUID.test(id ?? "") && method === "DELETE" && !search) return `/teacher-materials/${id}`;
    if (UUID.test(id ?? "") && parts.length === 3 && !search) {
      if (action === "items" && method === "GET") return `/teacher-materials/${id}/items`;
      if (action === "document" && method === "GET") return `/teacher-materials/${id}/document`;
      if (action === "prepare-assignment" && method === "POST") return `/teacher-materials/${id}/prepare-assignment`;
    }
    if (UUID.test(id ?? "") && parts.length === 4 && action === "assets" && /^\d{1,6}$/.test(parts[3]) && method === "GET" && !search) return `/teacher-materials/${id}/assets/${parts[3]}`;
  }
  if (first === "theory") {
    if (parts.length === 1 && method === "GET" && /^\?classroom_id=[0-9a-f-]{36}$/i.test(search) && UUID.test(search.slice(14))) return `/api/v2/teacher/theory${search}`;
    if (parts.length === 2 && id === "upload" && method === "POST" && !search) return "/api/v2/teacher/theory/upload";
    if (UUID.test(id ?? "") && !search) {
      if (parts.length === 2 && (method === "GET" || method === "DELETE")) return `/api/v2/teacher/theory/${id}`;
      if (parts.length === 3 && action === "notebook" && method === "GET") return "/api/v2/teacher/theory/" + id + "/notebook";
      if (parts.length === 6 && action === "notebook" && parts[3] === "blocks" && method === "GET" &&
          /^[1-9]\d{0,2}$/.test(parts[4]) && /^\d{1,2}$/.test(parts[5])) {
        return "/api/v2/teacher/theory/" + id + "/notebook/blocks/" + parts[4] + "/" + parts[5];
      }
      if (parts.length === 3 && action === "source" && method === "GET") return `/api/v2/teacher/theory/${id}/source`;
      if (parts.length === 3 && action === "map" && method === "PUT") return `/api/v2/teacher/theory/${id}/map`;
      if (parts.length === 3 && ["generate", "regenerate", "prefill", "publish", "share-source", "unshare-source"].includes(action ?? "") && method === "POST") return `/api/v2/teacher/theory/${id}/${action}`;
    }
  }  if (first === "assignments" && UUID.test(id ?? "")) {
    if (parts.length === 8 && parts[2] === "students" && UUID.test(parts[3])
        && parts[4] === "material-items" && UUID.test(parts[5]) && parts[6] === "assets"
        && /^\d{1,6}$/.test(parts[7]) && method === "GET" && !search) {
      return `/teacher/assignments/${id}/students/${parts[3]}/material-items/${parts[5]}/assets/${parts[7]}`;
    }
    if (action === "submissions" && parts.length === 3 && method === "GET" && !search) {
      return `/teacher/assignments/${id}/submissions`;
    }
    if (action === "publish" && parts.length === 3 && method === "POST" && !search) {
      return `/teacher/assignments/${id}/publish`;
    }
    if (action === "close" && parts.length === 3 && method === "POST" && !search) {
      return `/teacher/assignments/${id}/close`;
    }
    if (parts.length === 4 && parts[2] === "students" && UUID.test(parts[3]) && method === "GET" && !search) {
      return `/teacher/assignments/${id}/students/${parts[3]}`;
    }
    if (parts.length === 5 && parts[2] === "students" && UUID.test(parts[3]) && parts[4] === "finalize" && method === "POST" && !search) {
      return `/teacher/assignments/${id}/students/${parts[3]}/finalize`;
    }
    if (
      parts.length === 7 &&
      parts[2] === "students" &&
      UUID.test(parts[3]) &&
      (parts[4] === "material-items" || parts[4] === "questions") &&
      UUID.test(parts[5]) &&
      parts[6] === "grade" &&
      method === "POST" &&
      !search
    ) {
      return `/teacher/assignments/${id}/students/${parts[3]}/${parts[4]}/${parts[5]}/grade`;
    }
  }
  if (first === "grading") {
    if (parts.length === 2 && id === "queue" && method === "GET") {
      return `/api/v2/teacher/grading/queue${search}`;
    }
    if (parts.length === 2 && id === "batch-approve" && method === "POST" && !search) {
      return "/api/v2/teacher/grading/batch-approve";
    }
    if (parts.length === 3 && id === "attempts" && UUID.test(action ?? "") && method === "GET" && !search) {
      return `/api/v2/teacher/grading/attempts/${action}`;
    }
    if (parts.length === 3 && UUID.test(id ?? "") && !search) {
      if (action === "override" && method === "POST") return `/api/v2/teacher/grading/${id}/override`;
      if (action === "retry-sync" && method === "POST") return `/api/v2/teacher/grading/${id}/retry-sync`;
    }
  }
  return null;
}
