import assert from "node:assert/strict";
import test from "node:test";

import {
  signQRUploadToken,
  verifyQRUploadToken,
} from "../src/lib/auth/qr-upload-token.js";

const TEST_SECRET = "super_secret_test_key_with_more_than_32_characters_long_123456";

test("sign and verify QR upload token with valid payload", async () => {
  const attemptId = "c0000000-0000-0000-0000-000000000001";
  const studentId = "student-123";
  const accessToken = "mock.jwt.token";

  const { token, expiresAt } = await signQRUploadToken(
    { attemptId, studentId, accessToken, expiresInMinutes: 15 },
    TEST_SECRET,
  );

  assert.ok(token);
  assert.ok(expiresAt > Date.now());

  const verified = await verifyQRUploadToken(token, TEST_SECRET);
  assert.ok(verified);
  assert.equal(verified.attemptId, attemptId);
  assert.equal(verified.studentId, studentId);
  assert.equal(verified.accessToken, accessToken);
  assert.equal(verified.type, "qr_upload");
});

test("verify QR upload token fails if tampered", async () => {
  const attemptId = "c0000000-0000-0000-0000-000000000001";
  const { token } = await signQRUploadToken(
    { attemptId, studentId: "s1", accessToken: "t1" },
    TEST_SECRET,
  );

  const tampered = token.slice(0, -5) + "abcde";
  const verified = await verifyQRUploadToken(tampered, TEST_SECRET);
  assert.equal(verified, null);
});

test("verify QR upload token fails if expired", async () => {
  const attemptId = "c0000000-0000-0000-0000-000000000001";
  const { token, expiresAt } = await signQRUploadToken(
    { attemptId, studentId: "s1", accessToken: "t1", expiresInMinutes: 1 },
    TEST_SECRET,
  );

  // Future check where now > expiresAt
  const futureNow = expiresAt + 5000;
  const verified = await verifyQRUploadToken(token, TEST_SECRET, futureNow);
  assert.equal(verified, null);
});

test("verify QR upload token rejects invalid string format", async () => {
  assert.equal(await verifyQRUploadToken("", TEST_SECRET), null);
  assert.equal(await verifyQRUploadToken("invalid-token", TEST_SECRET), null);
  assert.equal(await verifyQRUploadToken("part1.part2.part3.part4", TEST_SECRET), null);
});
