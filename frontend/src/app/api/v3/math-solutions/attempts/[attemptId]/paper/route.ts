import type { NextRequest } from "next/server";
import { proxyPaper } from "@/lib/api/paper-proxy";

interface Context { params: Promise<{ attemptId: string }> }

export async function GET(request: NextRequest, context: Context) {
  return proxyPaper(request, (await context.params).attemptId);
}
export async function POST(request: NextRequest, context: Context) {
  return proxyPaper(request, (await context.params).attemptId);
}
