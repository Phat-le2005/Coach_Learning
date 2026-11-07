import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

import { getBackendBaseUrl } from "@/lib/api/client";
import { inkWebSocketUrl } from "@/lib/api/ink-websocket";
import { pairingOrigin } from "@/lib/network/lan";
import { mathWorkspaceProxyPath } from "@/lib/api/math-workspace-path";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { errorResponse, verifyMutationRequest } from "@/lib/auth/route-utils";
import { getSessionSecret } from "@/lib/auth/server";
import { verifySession } from "@/lib/auth/session-codec";

interface Context { params: Promise<{ path: string[] }> }

async function forward(request: NextRequest, context: Context): Promise<NextResponse> {
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, getSessionSecret());
  const accessToken = request.cookies.get(AUTH_COOKIES.access)?.value;
  if (!session || !accessToken) return errorResponse(401, "SESSION_EXPIRED", "Phiên đăng nhập đã hết hạn.");
  if (session.role !== "STUDENT") return errorResponse(403, "FORBIDDEN", "Bạn không có quyền truy cập bài làm học sinh.");

  const path = mathWorkspaceProxyPath((await context.params).path, request.method);
  if (!path || request.nextUrl.search) return errorResponse(404, "NOT_FOUND", "Đường dẫn bài làm không hợp lệ.");
  if (request.method !== "GET") {
    const csrfError = verifyMutationRequest(request);
    if (csrfError) return csrfError;
  }

  try {
    const inkRequest = path.endsWith("/ink") || path.includes("/ink/");
    // Bound streaming bodies too; Content-Length alone is not a limit.
    let body: string | undefined;
    if (request.method !== "GET" && inkRequest) {
      const reader = request.body?.getReader();
      const chunks: Uint8Array[] = [];
      let size = 0;
      if (reader) {
        while (true) {
          const part = await reader.read();
          if (part.done) break;
          size += part.value.byteLength;
          if (size > 768 * 1024) {
            await reader.cancel();
            return errorResponse(413, "INK_REQUEST_TOO_LARGE", "Yêu cầu quá lớn.");
          }
          chunks.push(part.value);
        }
      }
      body = Buffer.concat(chunks).toString("utf8");
      if (path.endsWith("/ink/live-ticket") || path.endsWith("/ink/pairings")) {
        const value = JSON.parse(body);
        // CSRF validation above already checked this Origin. Preserve the actual
        // browser origin (Next may normalize 127.0.0.1 to localhost internally).
        const origin = path.endsWith("/ink/pairings")
          ? pairingOrigin(request.headers.get("origin"))
          : request.headers.get("origin");
        body = JSON.stringify({ page_index: value.page_index, origin });
      }
    }
    if (request.method !== "GET" && !inkRequest) body = await request.text();
    const upstream = await fetch(`${getBackendBaseUrl()}${path}`, {
      method: request.method,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        Accept: "application/json",
        ...(request.method === "GET" ? {} : { "Content-Type": "application/json" }),
      },
      body,
      cache: "no-store",
      signal: inkRequest ? AbortSignal.timeout(20000) : undefined,
    });
    if (upstream.ok && path.endsWith("/ink/live-ticket")) {
      const result = await upstream.json();
      return NextResponse.json({ ...result, websocket_url: inkWebSocketUrl(path.replace(/\/live-ticket$/, "/live"), request.headers.get("origin")!) }, { headers: { "Cache-Control": "no-store" } });
    }
    return new NextResponse(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("Content-Type") ?? "application/json", "Cache-Control": "no-store" },
    });
  } catch (error) {
    if (error instanceof Error && error.message === "LAN_ADDRESS_UNAVAILABLE") return errorResponse(503, "LAN_ADDRESS_UNAVAILABLE", "Chưa tìm thấy địa chỉ mạng nội bộ. Kết nối Wi-Fi hoặc cáp mạng rồi thử lại.");
    if (error instanceof Error && error.message === "LIVE_WSS_REQUIRED") return errorResponse(503, "LIVE_WSS_REQUIRED", "Cần cấu hình địa chỉ wss:// cho HTTPS/production.");
    if (error instanceof Error && error.message === "LIVE_CONFIG_INVALID") return errorResponse(503, "LIVE_CONFIG_INVALID", "Cấu hình địa chỉ WebSocket không hợp lệ.");
    return errorResponse(503, "API_UNAVAILABLE", "Không thể kết nối đến dịch vụ bài làm.");
  }
}

export async function GET(request: NextRequest, context: Context) { return forward(request, context); }
export async function PUT(request: NextRequest, context: Context) { return forward(request, context); }
export async function POST(request: NextRequest, context: Context) { return forward(request, context); }

export async function PATCH(request: NextRequest, context: Context) { return forward(request, context); }
