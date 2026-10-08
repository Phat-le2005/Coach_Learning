import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { verifyMutationRequest } from "@/lib/auth/route-utils";
import { clearAuthenticationCookies } from "@/lib/auth/server";

export async function POST(request: NextRequest) {
  const csrfError = verifyMutationRequest(request);
  if (csrfError) return csrfError;
  const response = NextResponse.json({ success: true }, { headers: { "Cache-Control": "no-store" } });
  clearAuthenticationCookies(response);
  return response;
}
