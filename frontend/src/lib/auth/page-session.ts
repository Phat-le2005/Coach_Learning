import "server-only";

import { redirect } from "next/navigation";

import type { Role } from "../api/contracts";
import { createBackendApiClient } from "../api/client";
import { ROLE_HOME } from "./rbac";
import { verifiedLoginRole } from "./login-session";
import { readAccessToken, readSession } from "./server";

export async function requirePageRole(role: Role, returnTo: string) {
  const session = await readSession();
  if (!session) redirect(`/login?returnTo=${encodeURIComponent(returnTo)}`);
  if (session.role !== role) redirect(`/unauthorized?required=${role}`);
  return session;
}

export async function redirectAuthenticatedUser(): Promise<void> {
  const session = await readSession();
  if (!session) return;
  const role = await verifiedLoginRole(
    session,
    await readAccessToken(),
    (accessToken) => createBackendApiClient().me(accessToken),
  );
  if (role) redirect(ROLE_HOME[role]);
}
