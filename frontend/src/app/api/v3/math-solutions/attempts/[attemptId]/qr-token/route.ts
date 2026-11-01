import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { createBackendApiClient } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse } from "@/lib/auth/route-utils";
import { getSessionSecret, setAuthenticationCookies } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";
import { signQRUploadToken } from "@/lib/auth/qr-upload-token";

export const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

interface Context {
  params: Promise<{ attemptId: string }> | { attemptId: string };
}

async function handleGenerateToken(
  request: NextRequest,
  rawAttemptId: string,
): Promise<NextResponse> {
  const attemptId = (rawAttemptId ?? "").trim();
  if (!attemptId || !UUID_REGEX.test(attemptId)) {
    return errorResponse(404, "NOT_FOUND", "Mã bài làm không hợp lệ.");
  }

  try {
    const sessionCookie = request.cookies.get(AUTH_COOKIES.session)?.value;
    let accessToken = request.cookies.get(AUTH_COOKIES.access)?.value;
    const refreshToken = request.cookies.get(AUTH_COOKIES.refresh)?.value;
    let session = await verifySession(sessionCookie, getSessionSecret());

    let refreshedResponse: NextResponse | null = null;

    // Auto-refresh access token if expired but refresh token exists
    if ((!session || !accessToken) && refreshToken) {
      try {
        const api = createBackendApiClient();
        const tokens = await api.refresh(refreshToken);
        const user = await api.me(tokens.access_token);
        accessToken = tokens.access_token;
        refreshedResponse = NextResponse.json({});
        await setAuthenticationCookies(refreshedResponse, tokens, user);
        session = await verifySession(
          refreshedResponse.cookies.get(AUTH_COOKIES.session)?.value,
          getSessionSecret(),
        );
      } catch {
        // Refresh failed
      }
    }

    // Fallback for header Authorization if provided
    const authHeader = request.headers.get("authorization");
    if (!accessToken && authHeader?.startsWith("Bearer ")) {
      accessToken = authHeader.slice(7).trim();
    }

    if (!session || !accessToken) {
      return errorResponse(
        401,
        "SESSION_EXPIRED",
        "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
      );
    }

    if (session.role !== "STUDENT") {
      return errorResponse(
        403,
        "FORBIDDEN",
        "Chỉ học sinh mới có thể tạo mã chụp ảnh bài làm.",
      );
    }

    const { token, expiresAt } = await signQRUploadToken({
      attemptId,
      studentId: session.userId,
      accessToken,
      expiresInMinutes: 20,
    });

    const response = NextResponse.json({
      token,
      expiresAt,
      uploadPath: `/student/attempts/${attemptId}/mobile-upload?token=${token}`,
    });

    // If we refreshed cookies, copy them over
    if (refreshedResponse) {
      for (const cookie of refreshedResponse.cookies.getAll()) {
        response.cookies.set(cookie.name, cookie.value, cookie);
      }
    }

    return response;
  } catch (error) {
    console.error("[qr-token] Failed to generate upload token:", error);
    return errorResponse(
      500,
      "TOKEN_GENERATION_FAILED",
      "Không thể tạo mã xác thực chụp ảnh bài làm lúc này. Vui lòng thử lại.",
    );
  }
}

export async function GET(
  request: NextRequest,
  context: Context,
): Promise<NextResponse> {
  try {
    const params = await Promise.resolve(context?.params);
    return await handleGenerateToken(request, params?.attemptId);
  } catch (error) {
    console.error("[qr-token] GET error:", error);
    return errorResponse(500, "SERVER_ERROR", "Lỗi xử lý yêu cầu mã QR.");
  }
}

export async function POST(
  request: NextRequest,
  context: Context,
): Promise<NextResponse> {
  try {
    const params = await Promise.resolve(context?.params);
    return await handleGenerateToken(request, params?.attemptId);
  } catch (error) {
    console.error("[qr-token] POST error:", error);
    return errorResponse(500, "SERVER_ERROR", "Lỗi xử lý yêu cầu mã QR.");
  }
}
