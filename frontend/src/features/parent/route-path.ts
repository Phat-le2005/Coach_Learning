const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const TARGET_DATE_QUERY = /^\?target_date=\d{4}-\d{2}-\d{2}$/;

/**
 * Only explicit parent-owned backend routes are exposed.
 * Prevents path traversal or cross-role proxy access.
 */
export function parentBackendPath(parts: string[], method: string, search: string): string | null {
  if (parts.some((part) => !part || part === "." || part === ".." || part.includes("/"))) return null;
  const [first, id, action] = parts;

  if (first === "me" && parts.length === 1 && !search) {
    if (method === "GET" || method === "PATCH") return "/parents/me";
  }

  if (first === "students") {
    if (parts.length === 1 && method === "GET" && !search) {
      return "/parent/students";
    }
    if (parts.length === 3 && UUID.test(id ?? "")) {
      if (action === "progress" && method === "GET" && !search) {
        return `/parent/students/${id}/progress`;
      }
      if (action === "weekly-data" && method === "GET" && (!search || TARGET_DATE_QUERY.test(search))) {
        return `/parent/students/${id}/weekly-data${search}`;
      }
      if (action === "ai-summary" && method === "POST" && (!search || TARGET_DATE_QUERY.test(search))) {
        return `/parent/students/${id}/ai-summary${search}`;
      }
    }
  }

  return null;
}
