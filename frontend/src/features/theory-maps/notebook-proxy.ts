import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PAGE = /^[1-9]\d{0,2}$/;
const ORDINAL = /^\d{1,2}$/;

export async function studentNotebookProxy(request: NextRequest, id: string, page?: string, ordinal?: string): Promise<NextResponse> {
  if (!UUID.test(id) || (page !== undefined && (!PAGE.test(page) || !ORDINAL.test(ordinal ?? "")))) {
    return errorResponse(404, "NOT_FOUND", "Không tìm thấy phần sổ học.");
  }
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const token = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !token) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "STUDENT") return errorResponse(403, "FORBIDDEN", "Chỉ học sinh trong lớp được xem tài liệu.");
  const image = page !== undefined;
  const suffix = image ? "/blocks/" + page + "/" + ordinal : "";
  try {
    const upstream = await fetch(getBackendBaseUrl() + "/api/v2/student/theory/" + id + "/notebook" + suffix, {
      headers: { Authorization: "Bearer " + token, Accept: image ? "image/png" : "application/json" },
      cache: "no-store",
    });
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.ok && image ? "image/png" : "application/json",
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
      },
    });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể tải sổ học từ máy chủ.");
  }
}