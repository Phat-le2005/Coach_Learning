import { type NextRequest, NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

interface Context { params: Promise<{ attemptId: string }> }
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function proxyNextLearning(request: NextRequest, context: Context, explain = false) {
  const { attemptId } = await context.params;
  if (!UUID.test(attemptId) || request.nextUrl.search) return errorResponse(404, "NOT_FOUND", "Bài làm không hợp lệ.");
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const token = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !token) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "STUDENT") return errorResponse(403, "FORBIDDEN", "Chỉ học sinh được xem đề xuất của mình.");
  let body: string | undefined;
  if (request.method === "POST") {
    const csrfError = verifyMutationRequest(request);
    if (csrfError) return csrfError;
    if (!explain) try {
      const data = await request.json();
      if (!UUID.test(data.decision_id) || !UUID.test(data.question_id)) throw new Error();
      body = JSON.stringify({ decision_id: data.decision_id, question_id: data.question_id });
    } catch {
      return errorResponse(422, "INVALID_SUGGESTION", "Đề xuất bài luyện không hợp lệ.");
    }
  }
  try {
    const upstream = await fetch(`${getBackendBaseUrl()}/api/v3/math-solutions/attempts/${attemptId}/next-learning${explain ? "/explain" : ""}`, {
      method: request.method, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body, cache: "no-store", signal: AbortSignal.timeout(15_000),
    });
    return new NextResponse(await upstream.text(), { status: upstream.status,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch {
    return errorResponse(503, "LEARNING_UNAVAILABLE", "Chưa tải được bước học tiếp theo. Kết quả chấm vẫn được giữ.");
  }
}
