import { redirect } from "next/navigation";

import { ROLE_HOME } from "@/lib/auth/rbac";
import { readSession } from "@/lib/auth/server";

export default async function HomePage() {
  const session = await readSession();
  if (session) {
    redirect(ROLE_HOME[session.role]);
  }
  redirect("/login");
}
