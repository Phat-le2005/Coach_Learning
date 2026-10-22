import { createSingleFlight, refreshSessionWithCurrentCheck } from "../api/session-refresh";

interface ErrorEnvelope { error?: { code?: string; message?: string; details?: unknown } }

export class BrowserAuthError extends Error {
  constructor(message: string, public readonly status: number, public readonly code: string, public readonly details?: unknown) {
    super(message);
    this.name = "BrowserAuthError";
  }
}

async function parseResponse(response: Response): Promise<Record<string, unknown>> {
  const body = await response.json().catch(() => null) as ErrorEnvelope | Record<string, unknown> | null;
  if (!response.ok) {
    const envelope = body as ErrorEnvelope | null;
    throw new BrowserAuthError(envelope?.error?.message ?? "Yêu cầu xác thực thất bại.", response.status, envelope?.error?.code ?? "HTTP_ERROR", envelope?.error?.details);
  }
  if (typeof body !== "object" || body === null) throw new BrowserAuthError("Phản hồi xác thực không hợp lệ.", 503, "INVALID_RESPONSE");
  return body as Record<string, unknown>;
}

export async function getCsrfToken(): Promise<string> {
  const response = await fetch("/auth/csrf", { method: "GET", credentials: "same-origin", cache: "no-store" });
  const body = await parseResponse(response);
  if (typeof body.csrf_token !== "string" || !body.csrf_token) throw new BrowserAuthError("Không thể tạo CSRF token.", 503, "INVALID_CSRF_RESPONSE");
  return body.csrf_token;
}

export async function authenticatedMutation(path: "/auth/login" | "/auth/refresh" | "/auth/logout", body?: Record<string, unknown>): Promise<Record<string, unknown>> {
  const csrfToken = await getCsrfToken();
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
    body: JSON.stringify(body ?? {}),
  });
  return parseResponse(response);
}

/** One refresh rotation per browser profile, including tabs that become visible together. */
export const refreshBrowserSession = createSingleFlight(async (): Promise<void> => {
  const withLock = typeof navigator !== "undefined" && navigator.locks
    ? async (task: () => Promise<void>): Promise<void> => {
      await navigator.locks.request("edums-auth-refresh", async () => { await task(); });
    }
    : undefined;
  await refreshSessionWithCurrentCheck(
    async () => (await fetch("/auth/me", { credentials: "same-origin", cache: "no-store" })).ok,
    async () => { await authenticatedMutation("/auth/refresh"); },
    withLock,
  );
});

type AuthMutation = typeof authenticatedMutation;

export async function endBrowserSession(mutate: AuthMutation = authenticatedMutation): Promise<void> {
  const body = await mutate("/auth/logout");
  if (body.success !== true) {
    throw new BrowserAuthError("Phản hồi đăng xuất không hợp lệ.", 503, "INVALID_LOGOUT_RESPONSE");
  }
}

export async function logoutAndRedirect(redirect: () => void, mutate: AuthMutation = authenticatedMutation): Promise<void> {
  await endBrowserSession(mutate);
  redirect();
}
