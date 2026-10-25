import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getBackendBaseUrl } from "@/lib/api/client";
import { mathWorkspaceProxyPath } from "@/lib/api/math-workspace-path";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

interface Context { params: Promise<{ path: string[] }> }

async function forward(request: NextRequest, context: Context): Promise<NextResponse> {
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const accessToken = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !accessToken) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "STUDENT") return errorResponse(403, "FORBIDDEN", "Bạn không có quyền truy cập bài làm học sinh.");

  const path = mathWorkspaceProxyPath((await context.params).path, request.method);
  if (!path || request.nextUrl.search) return errorResponse(404, "NOT_FOUND", "Đường dẫn bài làm không hợp lệ.");
  if (request.method !== "GET") {
    const csrfError = verifyMutationRequest(request);
    if (csrfError) return csrfError;
  }

  try {
    const upstream = await fetch(`${getBackendBaseUrl()}${path}`, {
      method: request.method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: "application/json",
        ...(request.method === "GET" ? {} : { "Content-Type": "application/json" }),
      },
      body: request.method === "GET" ? undefined : await request.text(),
      cache: "no-store",
    });
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json", "Cache-Control": "no-store" },
    });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối đến dịch vụ bài làm.");
  }
}

export async function GET(request: NextRequest, context: Context) { return forward(request, context); }
export async function PUT(request: NextRequest, context: Context) { return forward(request, context); }
export async function POST(request: NextRequest, context: Context) { return forward(request, context); }

export async function PATCH(request: NextRequest, context: Context) { return forward(request, context); }
