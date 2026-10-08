import { NextResponse } from "next/server";

import { setCsrfCookie } from "@/lib/auth/server";
import { generateCsrfToken } from "@/lib/auth/security";

export const dynamic = "force-dynamic";

export async function GET() {
  const token = generateCsrfToken();
  const response = NextResponse.json({ csrf_token: token }, { headers: { "Cache-Control": "no-store" } });
  setCsrfCookie(response, token);
  return response;
}
