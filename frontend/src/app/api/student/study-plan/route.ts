import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

export async function GET(request: NextRequest) {
  const session = await verifySession(
    request.cookies.get(AUTH_COOKIES.session)?.value,
    getSessionSecret()
  );
  const token = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !token) {
    return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  }
  if (session.role !== "STUDENT") {
    return errorResponse(403, "FORBIDDEN", "Chỉ học sinh mới có lộ trình học tập cá nhân.");
  }

  const backendUrl = getBackendBaseUrl();

  try {
    const upstream = await fetch(`${backendUrl}/students/me/study-plan`, {
      headers: { Authorization: `Bearer ${token}`, Accept: "application/json" },
      cache: "no-store",
    });

    if (upstream.status === 404) {
      return NextResponse.json({ plan: null, hasPlan: false }, { status: 200 });
    }

    if (!upstream.ok) {
      return errorResponse(upstream.status, "UPSTREAM_ERROR", "Không thể lấy lộ trình học tập.");
    }

    const data = await upstream.json();
    return NextResponse.json({ plan: data, hasPlan: true }, {
      status: 200,
      headers: { "Cache-Control": "private, no-store" },
    });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối máy chủ EduMS.");
  }
}

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
    return errorResponse(403, "FORBIDDEN", "Chỉ học sinh mới có thể điều chỉnh lộ trình học.");
  }

  const backendUrl = getBackendBaseUrl();
  let body: any = {};
  try {
    body = await request.json();
  } catch {
    body = {};
  }

  const action = body.action || "recalculate";

  try {
    if (action === "create_goal") {
      // 1. Create AcademicGoal
      const goalPayload = {
        target_exam: body.target_exam || "Kỳ thi Tốt nghiệp THPT & Tuyển sinh ĐH 2026",
        exam_date: body.exam_date || "2026-06-25",
        available_daily_minutes: body.available_daily_minutes || 30,
        status: "ACTIVE",
        target_university: body.target_university || null,
        target_major: body.target_major || null,
        subject_goals: body.subject_id
          ? [
              {
                subject_id: body.subject_id,
                target_score: body.target_score || 8.0,
                current_score: body.current_score || null,
                priority: 1,
              },
            ]
          : [],
      };

      const goalRes = await fetch(`${backendUrl}/students/me/goals`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify(goalPayload),
      });

      if (!goalRes.ok && goalRes.status !== 409) {
        const errJson = await goalRes.json().catch(() => ({}));
        return errorResponse(
          goalRes.status,
          errJson.code || "GOAL_CREATION_FAILED",
          errJson.message || "Không thể tạo mục tiêu học tập."
        );
      }

      // 2. Trigger recalculate study plan
      const recalcRes = await fetch(`${backendUrl}/students/me/study-plan/recalculate`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        body: JSON.stringify({ horizon_days: 7 }),
      });

      const planData = recalcRes.ok ? await recalcRes.json().catch(() => null) : null;
      return NextResponse.json(
        {
          success: true,
          message: "Đã gieo mục tiêu và sinh lộ trình 7 ngày thành công!",
          plan: planData,
        },
        { status: 200 }
      );
    }

    if (action === "explain") {
      const explainRes = await fetch(`${backendUrl}/students/me/today/explanation`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/json",
        },
      });

      if (!explainRes.ok) {
        return errorResponse(explainRes.status, "EXPLAIN_FAILED", "Không thể lấy lời giải thích.");
      }

      const explanation = await explainRes.json();
      return NextResponse.json(explanation, { status: 200 });
    }

    // Default: recalculate
    const horizon_days = body.horizon_days || 7;
    const recalcRes = await fetch(`${backendUrl}/students/me/study-plan/recalculate`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ horizon_days }),
    });

    if (!recalcRes.ok) {
      const errJson = await recalcRes.json().catch(() => ({}));
      return errorResponse(
        recalcRes.status,
        errJson.code || "RECALCULATE_FAILED",
        errJson.message || "Không thể sắp xếp lại lộ trình."
      );
    }

    const planData = await recalcRes.json();
    return NextResponse.json({ success: true, plan: planData }, { status: 200 });
  } catch {
    return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối máy chủ EduMS.");
  }
}
