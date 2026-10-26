"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.verifiedLoginRole = verifiedLoginRole;
/** A signed UI cookie alone cannot prove that the backend auth session is live. */
async function verifiedLoginRole(session, accessToken, readCurrentUser) {
    if (!session || !accessToken)
        return null;
    try {
        const user = await readCurrentUser(accessToken);
        return user.id === session.userId && user.role === session.role ? user.role : null;
    }
    catch (_a) {
        return null;
    }
}
