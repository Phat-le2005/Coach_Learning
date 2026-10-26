"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const cookie_policy_1 = require("../src/lib/auth/cookie-policy");
const security_1 = require("../src/lib/auth/security");
const session_codec_1 = require("../src/lib/auth/session-codec");
const secret = "a-secure-test-secret-that-is-over-32-characters";
const payload = { v: 1, userId: "user-1", email: "student@example.com", fullName: "Nguyễn Minh", role: "STUDENT", expiresAt: Date.now() + 60000 };
(0, node_test_1.default)("session token verifies and rejects tampering", async () => {
    const token = await (0, session_codec_1.signSession)(payload, secret);
    strict_1.default.deepEqual(await (0, session_codec_1.verifySession)(token, secret), payload);
    const tampered = token.endsWith("x") ? `${token.slice(0, -1)}y` : `${token.slice(0, -1)}x`;
    strict_1.default.equal(await (0, session_codec_1.verifySession)(tampered, secret), null);
});
(0, node_test_1.default)("expired signed session is rejected", async () => {
    const token = await (0, session_codec_1.signSession)(Object.assign(Object.assign({}, payload), { expiresAt: 1 }), secret);
    strict_1.default.equal(await (0, session_codec_1.verifySession)(token, secret, 2), null);
});
(0, node_test_1.default)("production cookie policy is secure and tokens are HttpOnly", () => {
    const policy = (0, cookie_policy_1.authCookiePolicy)({ nodeEnv: "production" });
    strict_1.default.equal(policy.base.httpOnly, true);
    strict_1.default.equal(policy.base.secure, true);
    strict_1.default.equal(policy.base.sameSite, "lax");
    strict_1.default.equal(policy.csrf.httpOnly, false);
    strict_1.default.equal(policy.csrf.sameSite, "strict");
    strict_1.default.equal((0, cookie_policy_1.authCookiePolicy)({ nodeEnv: "production", secureOverride: "false" }).base.secure, true);
});
(0, node_test_1.default)("CSRF tokens are random and use constant-time comparison", () => {
    const first = (0, security_1.generateCsrfToken)();
    const second = (0, security_1.generateCsrfToken)();
    strict_1.default.equal(first.length, 64);
    strict_1.default.notEqual(first, second);
    strict_1.default.equal((0, security_1.constantTimeEqual)(first, first), true);
    strict_1.default.equal((0, security_1.constantTimeEqual)(first, second), false);
});
(0, node_test_1.default)("mutation origin rejects cross-site requests", () => {
    strict_1.default.equal((0, security_1.isTrustedMutationOrigin)("https://app.example.com", "https://app.example.com", "same-origin"), true);
    strict_1.default.equal((0, security_1.isTrustedMutationOrigin)("https://evil.example", "https://app.example.com", "cross-site"), false);
    strict_1.default.equal((0, security_1.isTrustedMutationOrigin)(null, "https://app.example.com", null), false);
});
