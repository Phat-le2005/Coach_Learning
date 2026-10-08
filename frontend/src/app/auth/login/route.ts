import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { createBackendApiClient } from "@/lib/api/client";
import { validateLoginRequest } from "@/lib/api/contracts";
import { postLoginPath } from "@/lib/auth/rbac";
import { errorResponse, readJsonObject, upstreamErrorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { setAuthenticationCookies } from "@/lib/auth/server";

export async function POST(request: NextRequest) {
  const csrfError = verifyMutationRequest(request);
  if (csrfError) return csrfError;
  const body = await readJsonObject(request);
  if (!body || typeof body.email !== "string" || typeof body.password !== "string") {
    return errorResponse(422, "VALIDATION_ERROR", "Email và mật khẩu là bắt buộc.");
  }
  let credentials;
  try {
    credentials = validateLoginRequest({ email: body.email, password: body.password });
  } catch {
    return errorResponse(422, "VALIDATION_ERROR", "Email hoặc mật khẩu không hợp lệ.");
  }
  try {
    const api = createBackendApiClient();
    const tokens = await api.login(credentials);
    const user = await api.me(tokens.access_token);
    const response = NextResponse.json({ user, redirect_to: postLoginPath(user.role, typeof body.return_to === "string" ? body.return_to : null) }, { headers: { "Cache-Control": "no-store" } });
    await setAuthenticationCookies(response, tokens, user);
    return response;
  } catch (error) {
    return upstreamErrorResponse(error);
  }
}
