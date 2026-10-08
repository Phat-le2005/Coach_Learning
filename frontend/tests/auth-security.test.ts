import assert from "node:assert/strict";
import test from "node:test";

import { authCookiePolicy } from "../src/lib/auth/cookie-policy";
import { constantTimeEqual, generateCsrfToken, isTrustedMutationOrigin } from "../src/lib/auth/security";
import { signSession, verifySession, type SessionPayload } from "../src/lib/auth/session-codec";

const secret = "a-secure-test-secret-that-is-over-32-characters";
const payload: SessionPayload = { v: 1, userId: "user-1", email: "student@example.com", fullName: "Nguyễn Minh", role: "STUDENT", expiresAt: Date.now() + 60_000 };

test("session token verifies and rejects tampering", async () => {
  const token = await signSession(payload, secret);
  assert.deepEqual(await verifySession(token, secret), payload);
  const tampered = token.endsWith("x") ? `${token.slice(0, -1)}y` : `${token.slice(0, -1)}x`;
  assert.equal(await verifySession(tampered, secret), null);
});

test("expired signed session is rejected", async () => {
  const token = await signSession({ ...payload, expiresAt: 1 }, secret);
  assert.equal(await verifySession(token, secret, 2), null);
});

test("production cookie policy is secure and tokens are HttpOnly", () => {
  const policy = authCookiePolicy({ nodeEnv: "production" });
  assert.equal(policy.base.httpOnly, true);
  assert.equal(policy.base.secure, true);
  assert.equal(policy.base.sameSite, "lax");
  assert.equal(policy.csrf.httpOnly, false);
  assert.equal(policy.csrf.sameSite, "strict");
  assert.equal(authCookiePolicy({ nodeEnv: "production", secureOverride: "false" }).base.secure, true);
});

test("CSRF tokens are random and use constant-time comparison", () => {
  const first = generateCsrfToken();
  const second = generateCsrfToken();
  assert.equal(first.length, 64);
  assert.notEqual(first, second);
  assert.equal(constantTimeEqual(first, first), true);
  assert.equal(constantTimeEqual(first, second), false);
});

test("mutation origin rejects cross-site requests", () => {
  assert.equal(isTrustedMutationOrigin("https://app.example.com", "https://app.example.com", "same-origin"), true);
  assert.equal(isTrustedMutationOrigin("https://evil.example", "https://app.example.com", "cross-site"), false);
  assert.equal(isTrustedMutationOrigin(null, "https://app.example.com", null), false);
});
