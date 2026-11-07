import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";
import { launchClassroomCanvasAttempt } from "@/lib/classroom-assignments/launch";

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
    return errorResponse(403, "FORBIDDEN", "Chỉ học sinh mới có bài tập được giao.");
  }

  let index: number | undefined;
  try {
    const body = await request.json();
    if (typeof body.index === "number") {
      index = body.index;
    }
  } catch {
    // If body empty, default to undefined (auto next)
  }

  const result = await launchClassroomCanvasAttempt(token, assignmentId, index);
  if (!result) {
    return errorResponse(
      500,
      "CANVAS_LAUNCH_FAILED",
      "Không thể mở trang Canvas cho câu hỏi này. Vui lòng thử lại."
    );
  }

  return NextResponse.json(result, {
    status: 200,
    headers: { "Cache-Control": "private, no-store" },
  });
}
