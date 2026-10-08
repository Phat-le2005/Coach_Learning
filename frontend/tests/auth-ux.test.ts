import assert from "node:assert/strict";
import test from "node:test";

import { accountMenuReducer, initialAccountMenuState } from "../src/lib/auth/account-menu-state";
import { BrowserAuthError, endBrowserSession, logoutAndRedirect } from "../src/lib/auth/browser";
import { hasLoginFieldErrors, validateLoginFields } from "../src/lib/auth/login-validation";

test("login fields report clear errors before a request is sent", () => {
  assert.deepEqual(validateLoginFields("", ""), {
    email: "Vui lòng nhập email.",
    password: "Vui lòng nhập mật khẩu.",
  });
  assert.deepEqual(validateLoginFields("not-an-email", "secret"), { email: "Email chưa đúng định dạng." });
  assert.equal(hasLoginFieldErrors(validateLoginFields("student@example.com", "secret")), false);
});

test("account menu keyboard transitions focus into the dialog and restores the trigger on Escape", () => {
  const opened = accountMenuReducer(initialAccountMenuState, { type: "OPEN_WITH_FOCUS" });
  assert.deepEqual(opened, { open: true, focus: "first-item" });
  const escaped = accountMenuReducer(opened, { type: "CLOSE_AND_RESTORE" });
  assert.deepEqual(escaped, { open: false, focus: "trigger" });
  assert.deepEqual(accountMenuReducer(opened, { type: "CLOSE" }), initialAccountMenuState);
});

test("logout redirects only after the BFF confirms cookie clearing", async () => {
  const events: string[] = [];
  await logoutAndRedirect(
    () => events.push("redirect"),
    async (path) => {
      events.push(path);
      return { success: true };
    },
  );
  assert.deepEqual(events, ["/auth/logout", "redirect"]);
});

test("logout rejects an invalid response and never redirects", async () => {
  let redirected = false;
  await assert.rejects(
    logoutAndRedirect(
      () => { redirected = true; },
      async () => ({ success: false }),
    ),
    (error: unknown) => error instanceof BrowserAuthError && error.code === "INVALID_LOGOUT_RESPONSE",
  );
  assert.equal(redirected, false);
});

test("logout propagates BFF failure for retry instead of reporting success", async () => {
  const failure = new BrowserAuthError("service unavailable", 503, "API_UNAVAILABLE");
  await assert.rejects(endBrowserSession(async () => { throw failure; }), (error: unknown) => error === failure);
});
