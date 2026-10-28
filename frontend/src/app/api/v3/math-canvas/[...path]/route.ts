import { NextResponse, type NextRequest } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { mathCanvasProxyPath } from "@/lib/api/math-canvas-path";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

async function forward(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const token = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !token) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  const path = mathCanvasProxyPath((await context.params).path, request.method, session.role);
  if (!path) return errorResponse(404, "NOT_FOUND", "Không tìm thấy trang Math Canvas.");
  const params = request.nextUrl.searchParams;
  if ([...params.keys()].some((key) => key !== "offset") || params.getAll("offset").length > 1
    || (params.has("offset") && (session.role !== "TEACHER" || !/^\d{1,5}$/.test(params.get("offset")!)))) {
    return errorResponse(400, "INVALID_QUERY", "Bộ lọc không hợp lệ.");
  }
  if (request.method !== "GET") {
    const error = verifyMutationRequest(request);
    if (error) return error;
  }
  const body = request.method === "POST" ? await request.text() : undefined;
  if (body && new TextEncoder().encode(body).length > 20000) return errorResponse(413, "BODY_TOO_LARGE", "Nội dung quá dài.");
  try {
    const upstream = await fetch(`${getBackendBaseUrl()}${path}${request.nextUrl.search}`, {
      method: request.method, cache: "no-store",
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json", "Content-Type": "application/json" }, body,
    });
    return new NextResponse(await upstream.text(), { status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch { return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối Math Canvas."); }
}
export const GET = forward;
export const POST = forward;
