"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.refreshBrowserSession = exports.BrowserAuthError = void 0;
exports.getCsrfToken = getCsrfToken;
exports.authenticatedMutation = authenticatedMutation;
exports.endBrowserSession = endBrowserSession;
exports.logoutAndRedirect = logoutAndRedirect;
const session_refresh_1 = require("../api/session-refresh");
class BrowserAuthError extends Error {
    constructor(message, status, code, details) {
        super(message);
        this.status = status;
        this.code = code;
        this.details = details;
        this.name = "BrowserAuthError";
    }
}
exports.BrowserAuthError = BrowserAuthError;
async function parseResponse(response) {
    var _a, _b, _c, _d, _e;
    const body = await response.json().catch(() => null);
    if (!response.ok) {
        const envelope = body;
        throw new BrowserAuthError((_b = (_a = envelope === null || envelope === void 0 ? void 0 : envelope.error) === null || _a === void 0 ? void 0 : _a.message) !== null && _b !== void 0 ? _b : "Yêu cầu xác thực thất bại.", response.status, (_d = (_c = envelope === null || envelope === void 0 ? void 0 : envelope.error) === null || _c === void 0 ? void 0 : _c.code) !== null && _d !== void 0 ? _d : "HTTP_ERROR", (_e = envelope === null || envelope === void 0 ? void 0 : envelope.error) === null || _e === void 0 ? void 0 : _e.details);
    }
    if (typeof body !== "object" || body === null)
        throw new BrowserAuthError("Phản hồi xác thực không hợp lệ.", 503, "INVALID_RESPONSE");
    return body;
}
async function getCsrfToken() {
    const response = await fetch("/auth/csrf", { method: "GET", credentials: "same-origin", cache: "no-store" });
    const body = await parseResponse(response);
    if (typeof body.csrf_token !== "string" || !body.csrf_token)
        throw new BrowserAuthError("Không thể tạo CSRF token.", 503, "INVALID_CSRF_RESPONSE");
    return body.csrf_token;
}
async function authenticatedMutation(path, body) {
    const csrfToken = await getCsrfToken();
    const response = await fetch(path, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken },
        body: JSON.stringify(body !== null && body !== void 0 ? body : {}),
    });
    return parseResponse(response);
}
/** One refresh rotation per browser profile, including tabs that become visible together. */
exports.refreshBrowserSession = (0, session_refresh_1.createSingleFlight)(async () => {
    const withLock = typeof navigator !== "undefined" && navigator.locks
        ? async (task) => {
            await navigator.locks.request("edums-auth-refresh", async () => { await task(); });
        }
        : undefined;
    await (0, session_refresh_1.refreshSessionWithCurrentCheck)(async () => (await fetch("/auth/me", { credentials: "same-origin", cache: "no-store" })).ok, async () => { await authenticatedMutation("/auth/refresh"); }, withLock);
});
async function endBrowserSession(mutate = authenticatedMutation) {
    const body = await mutate("/auth/logout");
    if (body.success !== true) {
        throw new BrowserAuthError("Phản hồi đăng xuất không hợp lệ.", 503, "INVALID_LOGOUT_RESPONSE");
    }
}
async function logoutAndRedirect(redirect, mutate = authenticatedMutation) {
    await endBrowserSession(mutate);
    redirect();
}
