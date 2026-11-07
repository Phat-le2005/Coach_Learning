import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { AUTH_COOKIES } from "@/lib/auth/constants";
import { canAccessPath, requiredRoleForPath, ROLE_HOME } from "@/lib/auth/rbac";
import { verifySession } from "@/lib/auth/session-codec";

export async function proxy(request: NextRequest) {
  const secret = process.env.AUTH_SESSION_SECRET ?? "";
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, secret);
  const pathname = request.nextUrl.pathname;
  const research = /^\/(?:ocr-v2-lab|api\/ocr-v2-lab|ocr-diagnostics)(?:\/|$)/.test(pathname);
  if (research && (process.env.NODE_ENV === "production" || process.env.OCR_V2_EXPERIMENTAL !== "1")) return new NextResponse("Not Found", { status: 404 });
  if (research && !session) { const url = new URL("/login", request.url); url.searchParams.set("returnTo", pathname); return NextResponse.redirect(url); }
  if (pathname.includes("/mobile-upload")) return NextResponse.next();

  if (pathname === "/") {
    if (session) return NextResponse.redirect(new URL(ROLE_HOME[session.role], request.url));
    return NextResponse.redirect(new URL("/login", request.url));
  }

  if ((pathname === "/account" || pathname.startsWith("/account/")) && !session) {
    const url = new URL("/login", request.url);
    url.searchParams.set("returnTo", "/account");
    return NextResponse.redirect(url);
  }

  const requiredRole = requiredRoleForPath(pathname);
  if (!requiredRole) return NextResponse.next();
  if (!session) {
    const url = new URL("/login", request.url);
    url.searchParams.set("returnTo", `${pathname}${request.nextUrl.search}`);
    return NextResponse.redirect(url);
  }
  if (!canAccessPath(session.role, pathname)) {
    const url = new URL("/unauthorized", request.url);
    url.searchParams.set("required", requiredRole);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/ocr-v2-lab/:path*", "/api/ocr-v2-lab/:path*", "/ocr-diagnostics/:path*", "/", "/login", "/account/:path*", "/student/:path*", "/teacher/:path*", "/parent/:path*", "/admin/:path*"],
};
