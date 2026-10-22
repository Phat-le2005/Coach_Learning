import type { Role, UserRead } from "../api/contracts";
import type { SessionPayload } from "./session-codec";

/** A signed UI cookie alone cannot prove that the backend auth session is live. */
export async function verifiedLoginRole(
  session: SessionPayload | null,
  accessToken: string | null,
  readCurrentUser: (accessToken: string) => Promise<UserRead>,
): Promise<Role | null> {
  if (!session || !accessToken) return null;
  try {
    const user = await readCurrentUser(accessToken);
    return user.id === session.userId && user.role === session.role ? user.role : null;
  } catch {
    return null;
  }
}
