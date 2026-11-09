import { NextResponse, type NextRequest } from "next/server";

import { setCsrfCookie } from "@/lib/auth/server";
import { getOrCreateCsrfToken } from "@/lib/auth/security";
import { AUTH_COOKIES } from "@/lib/auth/constants";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const token = getOrCreateCsrfToken(request.cookies.get(AUTH_COOKIES.csrf)?.value);
  const response = NextResponse.json({ csrf_token: token }, { headers: { "Cache-Control": "no-store" } });
  setCsrfCookie(response, token);
  return response;
}
