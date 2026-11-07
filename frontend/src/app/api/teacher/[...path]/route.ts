import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";
import { teacherBackendPath } from "@/features/teacher/route-path";

interface Context { params: Promise<{ path: string[] }> }
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024 + 64 * 1024;

async function forward(request: NextRequest, context: Context): Promise<NextResponse> {
  const path = teacherBackendPath((await context.params).path, request.method, request.nextUrl.search);
  if (!path) return errorResponse(404, "NOT_FOUND", "Đường dẫn giáo viên không hợp lệ.");
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const accessToken = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !accessToken) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "TEACHER") return errorResponse(403, "FORBIDDEN", "Chỉ giáo viên được truy cập dữ liệu này.");
  if (request.method !== "GET") {
    const csrfError = verifyMutationRequest(request);
    if (csrfError) return csrfError;
  }
  let body: ArrayBuffer | undefined;
  if (request.method === "POST" || request.method === "PUT") {
    const declared = Number(request.headers.get("content-length"));
    if (declared > MAX_UPLOAD_BYTES) return errorResponse(413, "REQUEST_TOO_LARGE", "Tệp vượt quá giới hạn 25 MB.");
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_UPLOAD_BYTES) return errorResponse(413, "REQUEST_TOO_LARGE", "Tệp vượt quá giới hạn 25 MB.");
  }
  try {
    const upstream = await fetch(`${getBackendBaseUrl()}${path}`, {
      method: request.method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: path.includes("/notebook/blocks/") || path.includes("/assets/") ? "image/*" : path.endsWith("/source") ? "application/pdf,image/png,image/jpeg" : "application/json",
        ...(body ? { "Content-Type": request.headers.get("content-type") ?? "application/json" } : {}),
      },
      body,
      cache: "no-store",
    });
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        "Cache-Control": "private, no-store",
        ...(upstream.headers.get("content-disposition") ? { "Content-Disposition": upstream.headers.get("content-disposition")! } : {}),
      },
    });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối dịch vụ giáo viên.");
  }
}

export async function GET(request: NextRequest, context: Context) { return forward(request, context); }
export async function POST(request: NextRequest, context: Context) { return forward(request, context); }

export async function PUT(request: NextRequest, context: Context) { return forward(request, context); }
export async function DELETE(request: NextRequest, context: Context) { return forward(request, context); }
