"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const account_menu_state_1 = require("../src/lib/auth/account-menu-state");
const browser_1 = require("../src/lib/auth/browser");
const login_validation_1 = require("../src/lib/auth/login-validation");
const login_session_1 = require("../src/lib/auth/login-session");
(0, node_test_1.default)("login fields report clear errors before a request is sent", () => {
    strict_1.default.deepEqual((0, login_validation_1.validateLoginFields)("", ""), {
        email: "Vui lòng nhập email.",
        password: "Vui lòng nhập mật khẩu.",
    });
    strict_1.default.deepEqual((0, login_validation_1.validateLoginFields)("not-an-email", "secret"), { email: "Email chưa đúng định dạng." });
    strict_1.default.deepEqual((0, login_validation_1.validateLoginFields)("   student@example.com   ", "secret"), {});
    strict_1.default.deepEqual((0, login_validation_1.validateLoginFields)("student@example.com", "a".repeat(129)), {
        password: "Mật khẩu không được vượt quá 128 ký tự.",
    });
    strict_1.default.equal((0, login_validation_1.hasLoginFieldErrors)((0, login_validation_1.validateLoginFields)("student@example.com", "secret")), false);
});
(0, node_test_1.default)("account menu keyboard transitions focus into the dialog and restores the trigger on Escape", () => {
    const opened = (0, account_menu_state_1.accountMenuReducer)(account_menu_state_1.initialAccountMenuState, { type: "OPEN_WITH_FOCUS" });
    strict_1.default.deepEqual(opened, { open: true, focus: "first-item" });
    const escaped = (0, account_menu_state_1.accountMenuReducer)(opened, { type: "CLOSE_AND_RESTORE" });
    strict_1.default.deepEqual(escaped, { open: false, focus: "trigger" });
    strict_1.default.deepEqual((0, account_menu_state_1.accountMenuReducer)(opened, { type: "CLOSE" }), account_menu_state_1.initialAccountMenuState);
});
(0, node_test_1.default)("logout redirects only after the BFF confirms cookie clearing", async () => {
    const events = [];
    await (0, browser_1.logoutAndRedirect)(() => events.push("redirect"), async (path) => {
        events.push(path);
        return { success: true };
    });
    strict_1.default.deepEqual(events, ["/auth/logout", "redirect"]);
});
(0, node_test_1.default)("logout rejects an invalid response and never redirects", async () => {
    let redirected = false;
    await strict_1.default.rejects((0, browser_1.logoutAndRedirect)(() => { redirected = true; }, async () => ({ success: false })), (error) => error instanceof browser_1.BrowserAuthError && error.code === "INVALID_LOGOUT_RESPONSE");
    strict_1.default.equal(redirected, false);
});
(0, node_test_1.default)("logout propagates BFF failure for retry instead of reporting success", async () => {
    const failure = new browser_1.BrowserAuthError("service unavailable", 503, "API_UNAVAILABLE");
    await strict_1.default.rejects((0, browser_1.endBrowserSession)(async () => { throw failure; }), (error) => error === failure);
});
(0, node_test_1.default)("login redirect requires a live backend session matching the signed UI cookie", async () => {
    const session = {
        v: 1, userId: "user-1", email: "student@example.com", fullName: "Student",
        role: "STUDENT", expiresAt: Date.now() + 60000,
    };
    const user = {
        id: "user-1", email: "student@example.com", full_name: "Student", role: "STUDENT",
        is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
    };
    const lookup = async () => user;
    strict_1.default.equal(await (0, login_session_1.verifiedLoginRole)(session, "access", lookup), "STUDENT");
    strict_1.default.equal(await (0, login_session_1.verifiedLoginRole)(session, null, lookup), null);
    strict_1.default.equal(await (0, login_session_1.verifiedLoginRole)(session, "revoked", async () => { throw new Error("401"); }), null);
    strict_1.default.equal(await (0, login_session_1.verifiedLoginRole)(session, "wrong-user", async () => (Object.assign(Object.assign({}, user), { id: "user-2" }))), null);
    strict_1.default.equal(await (0, login_session_1.verifiedLoginRole)(session, "wrong-role", async () => (Object.assign(Object.assign({}, user), { role: "ADMIN" }))), null);
});
