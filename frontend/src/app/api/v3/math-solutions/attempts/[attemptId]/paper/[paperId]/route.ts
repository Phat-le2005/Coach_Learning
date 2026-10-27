import type { NextRequest } from "next/server";
import { proxyPaper } from "@/lib/api/paper-proxy";

interface Context { params: Promise<{ attemptId: string; paperId: string }> }

export async function GET(request: NextRequest, context: Context) {
  const { attemptId, paperId } = await context.params;
  return proxyPaper(request, attemptId, paperId);
}
export async function POST(request: NextRequest, context: Context) {
  const { attemptId, paperId } = await context.params;
  return proxyPaper(request, attemptId, paperId, "ocr");
}
export async function DELETE(request: NextRequest, context: Context) {
  const { attemptId, paperId } = await context.params;
  return proxyPaper(request, attemptId, paperId);
}
