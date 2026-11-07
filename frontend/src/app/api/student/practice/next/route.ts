import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";
import { createBackendApiClient } from "@/lib/api/client";
import { getWorkspaceSubjects } from "@/features/math-workspace/entry-service";

export async function POST(request: NextRequest) {
  const session = await verifySession(
    request.cookies.get(AUTH_COOKIES.session)?.value,
    getSessionSecret()
  );
  const token = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !token) {
    return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  }
  if (session.role !== "STUDENT") {
    return errorResponse(403, "FORBIDDEN", "Chỉ học sinh mới có bài tập luyện tập.");
  }

  let subjectId: string | undefined;
  let practiceSessionId: string | undefined;

  try {
    const body = await request.json();
    subjectId = typeof body.subjectId === "string" && body.subjectId.trim() ? body.subjectId.trim() : undefined;
    practiceSessionId = typeof body.practiceSessionId === "string" && body.practiceSessionId.trim() ? body.practiceSessionId.trim() : undefined;
  } catch {
    // Empty body is acceptable
  }

  const client = createBackendApiClient();

  try {
    // 1. If we have an existing practice session, try fetching the next problem from it
    if (practiceSessionId) {
      try {
        const nextProb = await client.getMathPracticeNextProblem(token, practiceSessionId);
        const nextAttempt = await client.createMathAttempt(token, practiceSessionId, nextProb.id);
        return NextResponse.json({ attemptId: nextAttempt.id }, { status: 200 });
      } catch {
        // Fallback to creating a new practice session below if existing session is finished
      }
    }

    // 2. Resolve subject to start a new practice session
    const subjects = await getWorkspaceSubjects(token);
    const subject = (subjectId ? subjects.find((s) => s.id === subjectId) : undefined) ?? subjects[0];
    if (!subject) {
      return errorResponse(404, "NO_SUBJECT", "Chưa có môn học khả dụng.");
    }

    const newSession = await client.createPracticeSession(token, subject.id);
    const prob = await client.getMathPracticeNextProblem(token, newSession.id);
    const attempt = await client.createMathAttempt(token, newSession.id, prob.id);

    return NextResponse.json({ attemptId: attempt.id }, { status: 200 });
  } catch (err: unknown) {
    return errorResponse(
      500,
      "PRACTICE_CREATION_FAILED",
      err instanceof Error ? err.message : "Chưa thể tạo bài luyện tập tiếp theo."
    );
  }
}
