import { NextRequest, NextResponse } from "next/server";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";
import { lanConnectionInfo } from "@/lib/network/lan";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  if (!session || session.role !== "STUDENT") return new NextResponse(null, { status: 401 });
  return NextResponse.json(lanConnectionInfo(), { headers: { "Cache-Control": "no-store" } });
}
