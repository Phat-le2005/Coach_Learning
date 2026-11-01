import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { getBackendBaseUrl } from "@/lib/api/client";
import { errorResponse } from "@/lib/auth/route-utils";
import { verifyQRUploadToken } from "@/lib/auth/qr-upload-token";

export const UUID_REGEX =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_BODY = 10 * 1024 * 1024 + 64 * 1024;

interface Context {
  params: Promise<{ attemptId: string }>;
}

export async function POST(request: NextRequest, context: Context) {
  const { attemptId } = await context.params;
  if (!UUID_REGEX.test(attemptId)) {
    return errorResponse(404, "NOT_FOUND", "Bài làm không hợp lệ.");
  }

  const tokenFromHeader = request.headers.get("x-qr-upload-token");
  const tokenFromQuery = request.nextUrl.searchParams.get("token");
  const rawToken = tokenFromHeader || tokenFromQuery || undefined;

  const tokenPayload = await verifyQRUploadToken(rawToken);
  if (!tokenPayload || tokenPayload.attemptId !== attemptId) {
    return errorResponse(
      401,
      "INVALID_QR_TOKEN",
      "Mã quét QR đã hết hạn hoặc không hợp lệ. Vui lòng quét lại mã mới trên máy tính.",
    );
  }

  const size = Number(request.headers.get("content-length"));
  if (size > MAX_BODY) {
    return errorResponse(
      413,
      "PAPER_TOO_LARGE",
      "Ảnh chụp bài làm vượt quá giới hạn 10 MB.",
    );
  }

  let body: ArrayBuffer;
  try {
    body = await request.arrayBuffer();
    if (body.byteLength > MAX_BODY) {
      return errorResponse(
        413,
        "PAPER_TOO_LARGE",
        "Ảnh chụp bài làm vượt quá giới hạn 10 MB.",
      );
    }
  } catch {
    return errorResponse(
      400,
      "UPLOAD_BODY_ERROR",
      "Không thể đọc dữ liệu ảnh chụp gửi lên.",
    );
  }

  const contentType =
    request.headers.get("content-type") ?? "multipart/form-data";

  try {
    const upstream = await fetch(
      `${getBackendBaseUrl()}/api/v3/math-solutions/attempts/${attemptId}/paper`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${tokenPayload.accessToken}`,
          Accept: "application/json",
          "Content-Type": contentType,
        },
        body,
        cache: "no-store",
      },
    );

    const data = await upstream.json().catch(() => null);
    if (!upstream.ok) {
      return NextResponse.json(
        data ?? {
          code: "UPSTREAM_UPLOAD_FAILED",
          message: "Lưu ảnh lên máy chủ không thành công.",
        },
        { status: upstream.status },
      );
    }

    return NextResponse.json(data, { status: upstream.status });
  } catch {
    return errorResponse(
      503,
      "PAPER_SERVICE_UNAVAILABLE",
      "Không thể kết nối đến máy chủ lưu trữ bài làm.",
    );
  }
}
