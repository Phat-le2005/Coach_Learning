const UUID = "[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}";
export function mathCanvasProxyPath(parts: string[], method: string, role: string): string | null {
  const path = parts.join("/");
  if (role === "TEACHER" && method === "GET" && path === "teacher/snapshots") return "/api/v3/math-canvas/teacher/snapshots";
  if (role !== "STUDENT") return null;
  if (new RegExp(`^attempts/${UUID}/snapshots$`, "i").test(path) && ["GET", "POST"].includes(method)) return `/api/v3/math-canvas/${path}`;
  if (new RegExp(`^attempts/${UUID}/explain$`, "i").test(path) && method === "POST") return `/api/v3/math-canvas/${path}`;
  return null;
}
