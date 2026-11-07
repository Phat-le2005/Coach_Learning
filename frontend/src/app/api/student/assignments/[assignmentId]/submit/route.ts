import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

interface Context {
  params: Promise<{ assignmentId: string }>;
}

export async function POST(request: NextRequest, context: Context) {
  const { assignmentId } = await context.params;
  const session = await verifySession(
    request.cookies.get(AUTH_COOKIES.session)?.value,
    getSessionSecret()
  );
  const token = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !token) {
    return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  }
  if (session.role !== "STUDENT") {
    return errorResponse(403, "FORBIDDEN", "Chỉ học sinh mới có thể nộp bài tập.");
  }

  const csrfError = verifyMutationRequest(request);
  if (csrfError) return csrfError;

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse(400, "BAD_REQUEST", "Dữ liệu nộp bài không hợp lệ.");
  }

  const backendUrl = getBackendBaseUrl();
  try {
    const upstream = await fetch(
      `${backendUrl}/students/me/assignments/${encodeURIComponent(assignmentId)}/submit`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(body),
        cache: "no-store",
      }
    );

    const data = await upstream.json().catch(() => ({}));
    if (!upstream.ok) {
      const msg = (data as any)?.error?.message || (data as any)?.detail || "Không thể nộp bài tập.";
      return errorResponse(upstream.status, (data as any)?.error?.code || "SUBMIT_FAILED", msg);
    }

    return NextResponse.json(data, {
      status: 200,
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối máy chủ EduMS.");
  }
}
