import { NextRequest, NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { inkWebSocketUrl } from "@/lib/api/ink-websocket";
import { errorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";

const COOKIE = "edums_ink_device";
async function forward(request: NextRequest, context: { params: Promise<{path: string[]}> }) {
  const tail = (await context.params).path.join("/");
  const allowed = (request.method === "GET" && (tail === "session" || /^ink\/pages\/(?:[0-9]|[12][0-9])$/.test(tail)))
    || (request.method === "POST" && (["claim", "disconnect", "ink/live-ticket"].includes(tail) || /^ink\/pages\/(?:[0-9]|[12][0-9])\/operations$/.test(tail)));
  if (!allowed || request.nextUrl.search) return errorResponse(404, "NOT_FOUND", "Đường dẫn không hợp lệ.");
  if (request.method !== "GET") { const error = verifyMutationRequest(request); if (error) return error; }
  const device = request.cookies.get(COOKIE)?.value;
  if (tail !== "claim" && !device) return errorResponse(401, "DEVICE_REQUIRED", "Quét mã trên máy tính để bắt đầu viết.");
  try {
    let body: string | undefined;
    if (request.method !== "GET") {
      const chunks: Uint8Array[] = []; let bytes = 0;
      const reader = request.body?.getReader();
      if (reader) while (true) {
        const part = await reader.read(); if (part.done) break;
        bytes += part.value.byteLength;
        if (bytes > (tail === "claim" ? 2048 : 768 * 1024)) { await reader.cancel(); return errorResponse(413, "INK_REQUEST_TOO_LARGE", "Nét viết vượt giới hạn lưu trữ."); }
        chunks.push(part.value);
      }
      body = Buffer.concat(chunks).toString("utf8");
      if (["claim", "ink/live-ticket"].includes(tail)) {
        const value = JSON.parse(body);
        body = JSON.stringify({ ...value, origin: request.headers.get("origin") });
      }
    }
    const upstream = await fetch(`${getBackendBaseUrl()}/api/v2/math-ink-device/${tail}`, {
      method: request.method, cache: "no-store", signal: AbortSignal.timeout(20000), body,
      headers: { "Content-Type": "application/json", ...(device ? {"X-Ink-Device": device} : {}),
        ...(request.headers.get("origin") ? {Origin: request.headers.get("origin")!} : {}) },
    });
    const result = await upstream.json();
    const token = result.device_token; delete result.device_token;
    if (upstream.ok && tail === "ink/live-ticket") {
      result.websocket_url = inkWebSocketUrl(`/api/v2/math-solutions/attempts/${result.attempt_id}/ink/live`, request.headers.get("origin")!);
    }
    const response = NextResponse.json(result, { status: upstream.status, headers: {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"} });
    if (upstream.ok && tail === "claim" && typeof token === "string") response.cookies.set(COOKIE, token, {
      httpOnly: true, secure: process.env.NODE_ENV === "production" || process.env.SESSION_COOKIE_SECURE === "true",
      sameSite: "strict", path: "/api/ink-device", maxAge: 7200,
    });
    if (upstream.ok && tail === "disconnect") response.cookies.set(COOKIE, "", {path: "/api/ink-device", maxAge: 0});
    return response;
  } catch {
    return errorResponse(503, "DEVICE_UNAVAILABLE", "Chưa kết nối được với máy tính. Kiểm tra mạng rồi thử lại.");
  }
}
export const GET = forward;
export const POST = forward;
