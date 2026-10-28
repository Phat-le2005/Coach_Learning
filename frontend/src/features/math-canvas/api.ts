import { getCsrfToken, refreshBrowserSession } from "@/lib/auth/browser";
import { createSessionRefreshingFetcher } from "@/lib/api/session-refresh";
import type { InkStroke } from "@/lib/api/contracts";
import type { GraphSettings, GraphCamera } from "./expression";

export interface CanvasExplanation { id: string; text: string; provider: string; model: string }
export interface CanvasSnapshot {
  id: string; attempt_id: string; student_id: string; student_name: string;
  expression: string; dimension: "2D" | "3D"; settings: GraphSettings; camera: GraphCamera;
  page_index: number; source_latex: string; source_strokes: InkStroke[]; source_ink_revision: number;
  note: string; explanation: CanvasExplanation | null; created_at: string;
}
const refreshingFetch = createSessionRefreshingFetcher(fetch, refreshBrowserSession);
export async function canvasRequest<T>(path: string, payload?: unknown): Promise<T> {
  const response = await refreshingFetch(`/api/v3/math-canvas/${path}`, {
    method: payload === undefined ? "GET" : "POST", credentials: "same-origin", cache: "no-store",
    headers: payload === undefined ? {} : { "Content-Type": "application/json", "X-CSRF-Token": await getCsrfToken(), "X-EduMS-BFF": "1" },
    body: payload === undefined ? undefined : JSON.stringify(payload),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error?.message ?? data?.message ?? "Không thể kết nối Math Canvas. Hãy thử lại.");
  return data as T;
}
