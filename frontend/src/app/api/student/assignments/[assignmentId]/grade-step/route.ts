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
    return errorResponse(403, "FORBIDDEN", "Chỉ học sinh mới có thể chấm bài.");
  }

  const csrfError = verifyMutationRequest(request);
  if (csrfError) return csrfError;

  let body: any;
  try {
    body = await request.json();
  } catch {
    return errorResponse(400, "BAD_REQUEST", "Dữ liệu lời giải không hợp lệ.");
  }

  const {
    source_kind,
    student_assignment_id,
    item_id,
    snapshot_id,
    step_latex,
    explanation,
  } = body;

  const backendUrl = getBackendBaseUrl();
  const headers = {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    Accept: "application/json",
  };

  try {
    // 1. Create or get SolutionAttempt for this item
    const idempotencyKey = `assignment-step:${assignmentId}:${item_id}:${Date.now()}`;
    const createPayload: Record<string, any> = {
      source_kind: source_kind === "CANONICAL" ? "CANONICAL" : "TEACHER_MATERIAL",
      context_type: "CLASSROOM_ASSIGNMENT",
      mode: "INDEPENDENT_SOLUTION",
      create_idempotency_key: idempotencyKey,
      assignment_id: assignmentId,
      student_assignment_id: student_assignment_id,
    };

    if (source_kind === "CANONICAL") {
      createPayload.question_id = snapshot_id;
      createPayload.assignment_student_question_id = item_id;
    } else {
      createPayload.assignment_material_item_id = snapshot_id;
      createPayload.student_assignment_material_item_id = item_id;
    }

    const createRes = await fetch(`${backendUrl}/math-solutions/attempts`, {
      method: "POST",
      headers,
      body: JSON.stringify(createPayload),
    });

    if (!createRes.ok) {
      const err = await createRes.json().catch(() => ({}));
      return errorResponse(createRes.status, err?.error?.code || "ATTEMPT_CREATE_FAILED", err?.error?.message || "Không thể tạo phiên làm bài.");
    }

    const attempt = await createRes.json();
    const attemptId = attempt.id;
    let rev = attempt.attempt_revision_number;

    // 2. Add step
    const addStepRes = await fetch(`${backendUrl}/math-solutions/attempts/${attemptId}/steps`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        expected_attempt_revision: rev,
        client_action_id: crypto.randomUUID(),
        draft: {
          step_type: "DERIVATIVE_CALCULATION",
          content_latex: (step_latex || "").trim() || "y'",
          explanation_text: (explanation || "").trim() || null,
        },
      }),
    });

    if (addStepRes.ok) {
      const stepData = await addStepRes.json();
      rev = stepData.attempt_revision_number;
    }

    // 3. Submit attempt
    const submitRes = await fetch(`${backendUrl}/math-solutions/attempts/${attemptId}/submit`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        expected_attempt_revision: rev,
        client_action_id: crypto.randomUUID(),
      }),
    });

    if (!submitRes.ok) {
      const err = await submitRes.json().catch(() => ({}));
      return errorResponse(submitRes.status, err?.error?.code || "SUBMIT_FAILED", err?.error?.message || "Không thể gửi bước giải.");
    }

    // 4. Request AI review
    const reviewRes = await fetch(`${backendUrl}/math-solutions/attempts/${attemptId}/ai-review`, {
      method: "POST",
      headers,
    });

    if (!reviewRes.ok) {
      const err = await reviewRes.json().catch(() => ({}));
      return errorResponse(reviewRes.status, err?.error?.code || "REVIEW_FAILED", err?.error?.message || "AI chưa thể hoàn thành chấm bước giải.");
    }

    const reviewData = await reviewRes.json();
    return NextResponse.json({
      attempt_id: attemptId,
      review: reviewData,
    }, {
      status: 200,
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch (err: any) {
    return errorResponse(503, "API_UNAVAILABLE", err.message || "Lỗi kết nối máy chủ.");
  }
}
