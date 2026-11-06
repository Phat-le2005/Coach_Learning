import { getCsrfToken, refreshBrowserSession } from "@/lib/auth/browser";

export async function deviceRequest<T>(path: string, body?: unknown): Promise<T> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const response = await fetch(path, { method: body === undefined ? "GET" : "POST", cache: "no-store", credentials: "same-origin",
      headers: {"Content-Type": "application/json", "X-EduMS-BFF": "1", ...(body === undefined ? {} : {"X-CSRF-Token": await getCsrfToken()})},
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(20000),
    });
    if (response.status === 401 && attempt === 0 && !path.startsWith("/api/ink-device/")) { await refreshBrowserSession(); continue; }
    const result = await response.json();
    if (!response.ok) throw Object.assign(new Error(result.error?.message ?? "Chưa thể kết nối. Hãy thử lại."), {status: response.status});
    return result as T;
  }
  throw new Error("Phiên kết nối đã hết hạn.");
}
export interface DevicePairing {
  id: string; status: "WAITING" | "PENDING" | "ACTIVE" | "REVOKED" | "EXPIRED";
  device_name: string; confirmation: string; expires_in: number; page_index: number; attempt_id: string;
  code?: string; page_count?: number;
  origin?: string;
}
