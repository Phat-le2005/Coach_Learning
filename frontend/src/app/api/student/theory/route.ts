import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

export async function GET(request: NextRequest) {
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const token = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !token) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "STUDENT") return errorResponse(403, "FORBIDDEN", "Chỉ học sinh được xem tài liệu lớp.");
  try {
    const upstream = await fetch(`${getBackendBaseUrl()}/api/v2/student/theory`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" }, cache: "no-store",
    });
    return new NextResponse(upstream.body, { status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "private, no-store" } });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối máy chủ.");
  }
}
