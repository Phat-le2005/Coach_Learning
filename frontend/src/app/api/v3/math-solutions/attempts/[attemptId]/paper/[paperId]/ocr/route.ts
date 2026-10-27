import type { NextRequest } from "next/server";
import { proxyPaper } from "@/lib/api/paper-proxy";

interface Context { params: Promise<{ attemptId: string; paperId: string }> }

export async function POST(request: NextRequest, context: Context) {
  const { attemptId, paperId } = await context.params;
  return proxyPaper(request, attemptId, paperId, "ocr");
}
