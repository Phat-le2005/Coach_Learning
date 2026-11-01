import type { NextRequest } from "next/server";
import { studentNotebookProxy } from "@/features/theory-maps/notebook-proxy";

export async function GET(request: NextRequest, context: { params: Promise<{ id: string }> }) {
  return studentNotebookProxy(request, (await context.params).id);
}