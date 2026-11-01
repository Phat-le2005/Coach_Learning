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
    if (UUID.test(id ?? "") && parts.length === 3 && method === "GET") {
      if (action === "analytics" && !search) return `/teacher/classes/${id}/analytics`;
      if (["students", "assignments"].includes(action ?? "") && (!search || PAGE_QUERY.test(search))) return `/teacher/classes/${id}/${action}${search}`;
    }
  }
  if (first === "materials") {
    if (parts.length === 1 && method === "GET" && search.startsWith("?classroom_id=") && UUID.test(search.slice(14))) return `/teacher-materials${search}`;
    if (parts.length === 2 && id === "upload" && method === "POST" && !search) return "/teacher-materials/upload";
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
  }  if (first === "assignments" && UUID.test(id ?? "") && action === "submissions" && parts.length === 3 && method === "GET" && !search) {
    return `/teacher/assignments/${id}/submissions`;
  }
  return null;
}
