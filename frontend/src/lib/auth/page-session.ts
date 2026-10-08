import "server-only";

import { redirect } from "next/navigation";

import type { Role } from "../api/contracts";
import { ROLE_HOME } from "./rbac";
import { readSession } from "./server";

export async function requirePageRole(role: Role, returnTo: string) {
  const session = await readSession();
  if (!session) redirect(`/login?returnTo=${encodeURIComponent(returnTo)}`);
  if (session.role !== role) redirect(`/unauthorized?required=${role}`);
  return session;
}

export async function redirectAuthenticatedUser(): Promise<void> {
  const session = await readSession();
  if (session) redirect(ROLE_HOME[session.role]);
}
