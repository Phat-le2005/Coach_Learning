import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { ApiContractError } from "../api/validation";
import { ApiNetworkError, ApiResponseError } from "../api/client";
import { AUTH_COOKIES } from "./constants";
import { constantTimeEqual, isTrustedFrontendMutation } from "./security";
import { lanEnabled, runtimeFrontendOrigins } from "../network/lan";

export function errorResponse(status: number, code: string, message: string, details?: unknown): NextResponse {
  return NextResponse.json({ error: { code, message, ...(details === undefined ? {} : { details }) } }, { status, headers: { "Cache-Control": "no-store" } });
}

export function upstreamErrorResponse(error: unknown): NextResponse {
  if (error instanceof ApiResponseError) return errorResponse(error.status, error.code, error.message, error.details);
  if (error instanceof ApiNetworkError) return errorResponse(503, "API_UNAVAILABLE", error.message);
  if (error instanceof ApiContractError) return errorResponse(503, "UPSTREAM_CONTRACT_ERROR", "Phản hồi từ EduMS API không đúng contract.");
  return errorResponse(503, "AUTH_SERVICE_UNAVAILABLE", "Dịch vụ xác thực hiện chưa sẵn sàng.");
}

export function verifyMutationRequest(request: NextRequest): NextResponse | null {
  // Next's internal request URL can use localhost when bound to 0.0.0.0.
  // Permit the explicitly configured public frontend origin, never an arbitrary Host.
  const origin = request.headers.get("origin");
  const site = request.headers.get("sec-fetch-site");
  const publicOrigin = process.env.NEXT_PUBLIC_APP_URL?.trim();
  const trusted = lanEnabled()
    ? runtimeFrontendOrigins().some(allowed => isTrustedFrontendMutation(origin, allowed, site))
    : isTrustedFrontendMutation(origin, request.nextUrl.origin, site, publicOrigin, process.env.NODE_ENV === "development");
  if (!trusted) {
    return errorResponse(403, "CSRF_ORIGIN_REJECTED", "Nguồn yêu cầu không hợp lệ.");
  }
  const cookieToken = request.cookies.get(AUTH_COOKIES.csrf)?.value;
  const headerToken = request.headers.get("x-csrf-token");
  if (!constantTimeEqual(cookieToken, headerToken)) return errorResponse(403, "CSRF_TOKEN_INVALID", "CSRF token không hợp lệ.");
  return null;
}

export async function readJsonObject(request: NextRequest): Promise<Record<string, unknown> | null> {
  try {
    const value: unknown = await request.json();
    return typeof value === "object" && value !== null && !Array.isArray(value) ? value as Record<string, unknown> : null;
  } catch {
    return null;
  }
}
