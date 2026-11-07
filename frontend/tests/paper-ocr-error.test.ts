import assert from "node:assert/strict";
import test from "node:test";
import { ApiNetworkError, ApiResponseError, createApiClient } from "../src/lib/api/client.js";
import { ApiContractError } from "../src/lib/api/validation.js";
import { paperOcrErrorMessage } from "../src/features/math-workspace/utils/paper-ocr-error.js";

const privateDetails = "Paper recognition failed; private API key and provider details";

for (const [code, fragment] of [
  ["PAPER_OCR_UNAVAILABLE", "tạm thời gián đoạn"],
  ["PAPER_OCR_NOT_CONFIGURED", "cấu hình máy chủ"],
  ["PAPER_OCR_RATE_LIMITED", "hết lượt"],
  ["PAPER_OCR_TIMEOUT", "quá nhiều thời gian"],
  ["PAPER_OCR_INVALID", "chưa hợp lệ"],
  ["PAPER_OCR_REQUEST_REJECTED", "chưa xử lý được"],
] as const) {
  test(`paper OCR ${code} displays a safe actionable message`, async () => {
    const api = createApiClient({ baseUrl: "http://api.example.test", fetcher: async () => Response.json({
      error: { code, message: privateDetails },
    }, { status: 503 }) });
    await assert.rejects(api.recognizeMathPaper("session-token", "attempt", "paper"), (cause: unknown) => {
      const message = paperOcrErrorMessage(cause);
      assert.ok(message.includes(fragment));
      assert.ok(!message.includes(privateDetails));
      assert.ok(!message.includes("API key"));
      return true;
    });
  });
}

test("expired login remains separate from provider access problems", () => {
  const message = paperOcrErrorMessage(new ApiResponseError(privateDetails, 401, "INVALID_TOKEN", "unauthorized"));
  assert.ok(message.includes("đăng nhập"));
  assert.ok(!message.includes("cấu hình"));
});

test("network and response contract failures have distinct recovery messages", () => {
  assert.ok(paperOcrErrorMessage(new ApiNetworkError(privateDetails)).includes("Mất kết nối"));
  assert.ok(paperOcrErrorMessage(new ApiContractError(privateDetails)).includes("chưa hợp lệ"));
  assert.ok(!paperOcrErrorMessage(new Error(privateDetails)).includes(privateDetails));
});
