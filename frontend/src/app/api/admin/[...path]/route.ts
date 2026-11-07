import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";
import { adminBackendPath } from "@/features/admin/route-path";

interface Context {
  params: Promise<{ path: string[] }>;
}

const MAX_BODY_BYTES = 5 * 1024 * 1024;

async function forward(request: NextRequest, context: Context): Promise<NextResponse> {
  const path = adminBackendPath((await context.params).path, request.method, request.nextUrl.search);
  if (!path) return errorResponse(404, "NOT_FOUND", "Đường dẫn quản trị không hợp lệ.");

  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const accessToken = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !accessToken) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "ADMIN") return errorResponse(403, "FORBIDDEN", "Chỉ quản trị viên được truy cập dữ liệu này.");

  if (request.method !== "GET") {
    const csrfError = verifyMutationRequest(request);
    if (csrfError) return csrfError;
  }

  let body: ArrayBuffer | undefined;
  if (request.method === "POST" || request.method === "PUT" || request.method === "PATCH") {
    const declared = Number(request.headers.get("content-length"));
    if (declared > MAX_BODY_BYTES) return errorResponse(413, "REQUEST_TOO_LARGE", "Dữ liệu vượt quá giới hạn 5 MB.");
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_BODY_BYTES) return errorResponse(413, "REQUEST_TOO_LARGE", "Dữ liệu vượt quá giới hạn 5 MB.");
  }

  try {
    const upstream = await fetch(`${getBackendBaseUrl()}${path}`, {
      method: request.method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: "application/json",
        ...(body && body.byteLength > 0 ? { "Content-Type": request.headers.get("content-type") ?? "application/json" } : {}),
      },
      body: body && body.byteLength > 0 ? body : undefined,
      cache: "no-store",
    });
    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: {
        "Content-Type": upstream.headers.get("content-type") ?? "application/json",
        "Cache-Control": "private, no-store",
      },
    });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối dịch vụ quản trị.");
  }
}

export async function GET(request: NextRequest, context: Context) {
  return forward(request, context);
}

export async function POST(request: NextRequest, context: Context) {
  return forward(request, context);
}

export async function PATCH(request: NextRequest, context: Context) {
  return forward(request, context);
}

export async function DELETE(request: NextRequest, context: Context) {
  return forward(request, context);
}
