import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

export const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_BODY = 10 * 1024 * 1024 + 64 * 1024;

export async function proxyPaper(request: NextRequest, attemptId: string, paperId?: string, operation?: "ocr"): Promise<NextResponse> {
  if (!UUID.test(attemptId) || (paperId && !UUID.test(paperId)) || request.nextUrl.search) {
    return errorResponse(404, "NOT_FOUND", "Tệp bài làm không hợp lệ.");
  }
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const accessToken = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !accessToken) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "STUDENT") return errorResponse(403, "FORBIDDEN", "Chỉ học sinh được xem bài làm của mình.");
  if (request.method !== "GET") {
    const csrfError = verifyMutationRequest(request);
    if (csrfError) return csrfError;
  }
  let body: ArrayBuffer | undefined;
  if (request.method === "POST") {
    const size = Number(request.headers.get("content-length"));
    if (size > MAX_BODY) return errorResponse(413, "PAPER_TOO_LARGE", "Tệp bài làm vượt quá 10 MB.");
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_BODY) return errorResponse(413, "PAPER_TOO_LARGE", "Tệp bài làm vượt quá 10 MB.");
  }
  const suffix = paperId ? `/paper/${paperId}${operation ? "/ocr" : ""}` : "/paper";
  try {
    const upstream = await fetch(
      `${getBackendBaseUrl()}/api/v3/math-solutions/attempts/${attemptId}${suffix}`,
      { method: request.method, headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: request.method === "GET" && paperId && !operation ? "image/png, image/jpeg, application/pdf" : "application/json",
        ...(body ? { "Content-Type": request.headers.get("content-type") ?? "application/octet-stream" } : {}),
      }, body, cache: "no-store" },
    );
    const contentType = upstream.headers.get("content-type") ?? "application/json";
    return new NextResponse(upstream.status === 204 ? null : upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        ...(paperId && !operation && upstream.ok ? { "Content-Disposition": "inline", "Content-Security-Policy": "sandbox" } : {}),
      },
    });
  } catch {
    return errorResponse(503, "PAPER_SERVICE_UNAVAILABLE", "Không thể kết nối nơi lưu bài viết giấy.");
  }
}
