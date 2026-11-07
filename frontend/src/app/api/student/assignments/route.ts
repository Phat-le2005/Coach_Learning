import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

export async function GET(request: NextRequest) {
  const session = await verifySession(
    request.cookies.get(AUTH_COOKIES.session)?.value,
    getSessionSecret()
  );
  const token = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !token) {
    return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  }
  if (session.role !== "STUDENT") {
    return errorResponse(403, "FORBIDDEN", "Chỉ học sinh mới có bài tập được giao.");
  }

  const backendUrl = getBackendBaseUrl();
  try {
    const upstream = await fetch(`${backendUrl}/students/me/assignments?limit=100`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
    });

    if (!upstream.ok) {
      return errorResponse(upstream.status, "UPSTREAM_ERROR", "Không thể lấy danh sách bài tập.");
    }

    const data = await upstream.json();
    return NextResponse.json(data, {
      status: 200,
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối máy chủ EduMS.");
  }
}
