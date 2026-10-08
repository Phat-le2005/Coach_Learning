import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { createBackendApiClient } from "@/lib/api/client";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, upstreamErrorResponse } from "@/lib/auth/route-utils";

export async function GET(request: NextRequest) {
  const accessToken = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!accessToken) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  try {
    const user = await createBackendApiClient().me(accessToken);
    return NextResponse.json({ user }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    return upstreamErrorResponse(error);
  }
}
