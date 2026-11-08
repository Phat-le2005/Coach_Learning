import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { studentQuestionImagePath } from "@/lib/api/question-image-path";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

interface Context { params: Promise<{ assignmentId: string; itemId: string; index: string }> }

// A normal img request carries cookies, without the header used by the legacy v2 BFF.
export async function GET(request: NextRequest, context: Context): Promise<NextResponse> {
  const { assignmentId, itemId, index } = await context.params;
  const path = studentQuestionImagePath(assignmentId, itemId, index);
  if (!path || request.nextUrl.search) return errorResponse(404, "NOT_FOUND", "Ảnh bài tập không hợp lệ.");
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const token = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !token) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "STUDENT") return errorResponse(403, "FORBIDDEN", "Chỉ học sinh được xem ảnh bài tập của mình.");
  try {
    const upstream = await fetch(`${getBackendBaseUrl()}${path}`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "image/png,image/jpeg" }, cache: "no-store",
    });
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "application/octet-stream",
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff" },
    });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể tải ảnh bài tập lúc này.");
  }
}
