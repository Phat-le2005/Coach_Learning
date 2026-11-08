import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { createBackendApiClient } from "@/lib/api/client";
import { validateRegisterRequest } from "@/lib/api/contracts";
import { postLoginPath } from "@/lib/auth/rbac";
import { errorResponse, readJsonObject, upstreamErrorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { setAuthenticationCookies } from "@/lib/auth/server";

export async function POST(request: NextRequest) {
  const csrfError = verifyMutationRequest(request);
  if (csrfError) return csrfError;

  const body = await readJsonObject(request);
  if (
    !body ||
    typeof body.full_name !== "string" ||
    typeof body.email !== "string" ||
    typeof body.password !== "string"
  ) {
    return errorResponse(422, "VALIDATION_ERROR", "Họ và tên, email và mật khẩu là bắt buộc.");
  }

  let payload;
  try {
    payload = validateRegisterRequest({
      full_name: body.full_name,
      email: body.email,
      password: body.password,
      role: "STUDENT",
    });
  } catch (err) {
    return errorResponse(
      422,
      "VALIDATION_ERROR",
      err instanceof Error ? err.message : "Thông tin đăng ký không hợp lệ."
    );
  }

  try {
    const api = createBackendApiClient();
    await api.register(payload);
    const tokens = await api.login({ email: payload.email, password: payload.password });
    const user = await api.me(tokens.access_token);
    const response = NextResponse.json(
      {
        user,
        redirect_to: postLoginPath(
          user.role,
          typeof body.return_to === "string" ? body.return_to : null
        ),
      },
      { status: 201, headers: { "Cache-Control": "no-store" } }
    );
    await setAuthenticationCookies(response, tokens, user);
    return response;
  } catch (error) {
    return upstreamErrorResponse(error);
  }
}
