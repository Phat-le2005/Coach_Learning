import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!UUID.test(id)) return errorResponse(404, "NOT_FOUND", "Không tìm thấy tài liệu.");
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const token = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !token) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "STUDENT") return errorResponse(403, "FORBIDDEN", "Chỉ học sinh trong lớp được xem tài liệu.");
  try {
    const upstream = await fetch(`${getBackendBaseUrl()}/api/v2/student/theory/${id}/source`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/pdf" }, cache: "no-store",
    });
    return new NextResponse(upstream.body, { status: upstream.status, headers: {
      "Content-Type": upstream.ok ? "application/pdf" : "application/json",
      "Content-Disposition": upstream.ok ? "inline" : "attachment",
      "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff",
    } });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể tải PDF từ máy chủ.");
  }
}
