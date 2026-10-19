const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** Restrict the browser BFF to the exact Math Workspace operations it needs. */
export function mathWorkspaceProxyPath(parts: readonly string[], method: string): string | null {
  if (!UUID.test(parts[0] ?? "")) return null;
  const tail = parts.slice(1).join("/");
  const allowed =
    (method === "GET" && ["", "problem", "ink"].includes(tail)) ||
    (method === "GET" && /^ink\/pages\/(?:[0-9]|[12][0-9])$/.test(tail)) ||
    (method === "PUT" && /^ink\/pages\/(?:[0-9]|[12][0-9])$/.test(tail)) ||
    (method === "POST" && ["ocr/recognize", "steps"].includes(tail));
  return allowed ? `/api/v2/math-solutions/attempts/${parts.join("/")}` : null;
}
