import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { createBackendApiClient } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, upstreamErrorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { clearAuthenticationCookies, setAuthenticationCookies } from "@/lib/auth/server";

export async function POST(request: NextRequest) {
  const csrfError = verifyMutationRequest(request);
  if (csrfError) return csrfError;
  const refreshToken = request.cookies.get(AUTH_COOKIES.refresh)?.value;
  if (!refreshToken) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  try {
    const api = createBackendApiClient();
    const tokens = await api.refresh(refreshToken);
    const user = await api.me(tokens.access_token);
    const response = NextResponse.json({ user }, { headers: { "Cache-Control": "no-store" } });
    await setAuthenticationCookies(response, tokens, user);
    return response;
  } catch (error) {
    const response = upstreamErrorResponse(error);
    if (response.status === 401 || response.status === 403) clearAuthenticationCookies(response);
    return response;
  }
}
