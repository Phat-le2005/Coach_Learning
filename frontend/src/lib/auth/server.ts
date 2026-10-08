import "server-only";

import { cookies } from "next/headers";
import type { NextResponse } from "next/server";

import type { TokenPair, UserRead } from "../api/contracts";
import { AUTH_COOKIES, SESSION_VERSION } from "./constants";
import { authCookiePolicy } from "./cookie-policy";
import { signSession, verifySession, type SessionPayload } from "./session-codec";

export function getSessionSecret(): string {
  const secret = process.env.AUTH_SESSION_SECRET;
  if (!secret || secret.length < 32) throw new Error("AUTH_SESSION_SECRET must contain at least 32 characters.");
  return secret;
}

function policy() {
  return authCookiePolicy({
    nodeEnv: process.env.NODE_ENV,
    secureOverride: process.env.SESSION_COOKIE_SECURE,
    refreshMaxAge: process.env.AUTH_REFRESH_COOKIE_MAX_AGE_SECONDS,
  });
}

export async function setAuthenticationCookies(response: NextResponse, tokens: TokenPair, user: UserRead): Promise<void> {
  const currentPolicy = policy();
  const expiresAt = Date.now() + currentPolicy.refreshMaxAge * 1000;
  const session: SessionPayload = {
    v: SESSION_VERSION,
    userId: user.id,
    email: user.email,
    fullName: user.full_name,
    role: user.role,
    expiresAt,
  };
  response.cookies.set(AUTH_COOKIES.access, tokens.access_token, { ...currentPolicy.base, maxAge: tokens.expires_in });
  response.cookies.set(AUTH_COOKIES.refresh, tokens.refresh_token, { ...currentPolicy.base, maxAge: currentPolicy.refreshMaxAge });
  response.cookies.set(AUTH_COOKIES.session, await signSession(session, getSessionSecret()), { ...currentPolicy.base, maxAge: currentPolicy.refreshMaxAge });
}

export function setCsrfCookie(response: NextResponse, token: string): void {
  const currentPolicy = policy();
  response.cookies.set(AUTH_COOKIES.csrf, token, { ...currentPolicy.csrf, maxAge: currentPolicy.refreshMaxAge });
}

export function clearAuthenticationCookies(response: NextResponse): void {
  const currentPolicy = policy();
  for (const name of [AUTH_COOKIES.access, AUTH_COOKIES.refresh, AUTH_COOKIES.session]) response.cookies.set(name, "", { ...currentPolicy.base, maxAge: 0 });
  response.cookies.set(AUTH_COOKIES.csrf, "", { ...currentPolicy.csrf, maxAge: 0 });
}

export async function readSession(): Promise<SessionPayload | null> {
  const store = await cookies();
  return verifySession(store.get(AUTH_COOKIES.session)?.value, getSessionSecret());
}

export async function readAccessToken(): Promise<string | null> {
  return (await cookies()).get(AUTH_COOKIES.access)?.value ?? null;
}
