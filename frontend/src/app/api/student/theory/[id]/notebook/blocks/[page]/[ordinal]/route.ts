import type { NextRequest } from "next/server";
import { studentNotebookProxy } from "@/features/theory-maps/notebook-proxy";

export async function GET(request: NextRequest, context: { params: Promise<{ id: string; page: string; ordinal: string }> }) {
  const { id, page, ordinal } = await context.params;
  return studentNotebookProxy(request, id, page, ordinal);
}