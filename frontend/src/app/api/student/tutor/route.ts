import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getBackendBaseUrl } from "@/lib/api/client";
import { parseStudentTutorReply, parseStudentTutorRequest } from "@/lib/api/student-tutor";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, readJsonObject, verifyMutationRequest } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

export async function POST(request: NextRequest): Promise<NextResponse> {
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const accessToken = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !accessToken) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "STUDENT") return errorResponse(403, "FORBIDDEN", "Gia sư AI dành cho tài khoản học sinh.");
  const csrfError = verifyMutationRequest(request);
  if (csrfError) return csrfError;

  const body = parseStudentTutorRequest(await readJsonObject(request));
  if (!body) return errorResponse(422, "INVALID_QUESTION", "Em hãy nhập câu hỏi từ 1 đến 2.000 ký tự.");

  try {
    const upstream = await fetch(`${getBackendBaseUrl()}/ai/tutor`, {
      method: "POST",
      headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
      cache: "no-store",
      signal: AbortSignal.timeout(105_000),
    });
    const data = await upstream.json().catch(() => null);
    if (!upstream.ok) {
      return errorResponse(
        upstream.status,
        typeof data?.error?.code === "string" ? data.error.code : "TUTOR_UNAVAILABLE",
        upstream.status === 401 ? "Phiên đăng nhập đã hết hạn. Em hãy đăng nhập lại."
          : upstream.status === 429 ? "Em đã gửi nhiều câu hỏi. Hãy đợi một chút rồi thử lại."
            : "Gia sư AI chưa thể phản hồi. Em hãy thử lại sau.",
      );
    }
    const reply = parseStudentTutorReply(data);
    if (!reply) return errorResponse(503, "INVALID_TUTOR_REPLY", "Gia sư chưa trả lời được câu hỏi này. Em hãy thử lại.");
    return NextResponse.json({ reply }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return errorResponse(
      503,
      "TUTOR_UNAVAILABLE",
      error instanceof Error && error.name === "TimeoutError"
        ? "Gia sư đang phản hồi lâu hơn bình thường. Em hãy thử lại."
        : "Chưa kết nối được với Gia sư AI. Em hãy thử lại sau.",
    );
  }
}
