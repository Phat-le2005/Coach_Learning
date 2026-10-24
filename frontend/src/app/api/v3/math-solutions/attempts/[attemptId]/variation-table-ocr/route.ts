import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

interface Context { params: Promise<{ attemptId: string }> }
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function POST(request: NextRequest, context: Context): Promise<NextResponse> {
  const { attemptId } = await context.params;
  if (!UUID.test(attemptId) || request.nextUrl.search) return errorResponse(404, "NOT_FOUND", "Bài làm không hợp lệ.");
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const accessToken = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !accessToken) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "STUDENT") return errorResponse(403, "FORBIDDEN", "Chỉ học sinh được nhận dạng bài của mình.");
  const csrfError = verifyMutationRequest(request);
  if (csrfError) return csrfError;
  try {
    const raw = await request.text();
    if (raw.length > 2_800_100) return errorResponse(422, "INVALID_INK_IMAGE", "Ảnh nét viết quá lớn.");
    const upstream = await fetch(`${getBackendBaseUrl()}/api/v3/math-solutions/attempts/${attemptId}/variation-table-ocr`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}`, Accept: "application/json", "Content-Type": "application/json" },
      body: raw,
      cache: "no-store",
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối dịch vụ nhận dạng bảng.");
  }
}
