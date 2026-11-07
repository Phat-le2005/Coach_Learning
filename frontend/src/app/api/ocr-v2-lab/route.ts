import type { NextRequest } from "next/server";
import { verifySession } from "@/lib/auth/session-codec";
import { AUTH_COOKIES } from "@/lib/auth/constants";

async function gate(request: NextRequest) {
  if (process.env.NODE_ENV === "production" || process.env.OCR_V2_EXPERIMENTAL !== "1") return new Response("Not Found", { status: 404 });
  const session = await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, process.env.AUTH_SESSION_SECRET ?? "");
  if (!session) return new Response("QA authentication required", { status: 401 });
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) return new Response("Same origin required", { status: 403 });
  return null;
}
async function forward(request: NextRequest, method: "GET" | "POST") {
  const denied = await gate(request); if (denied) return denied;
  const base = process.env.OCR_V2_SIDECAR_URL ?? "http://127.0.0.1:8014";
  const url = new URL(base);
  if (url.hostname !== "127.0.0.1" || url.protocol !== "http:" || url.pathname !== "/" || url.username || url.password) return Response.json({ error: "INVALID_LOCAL_SIDECAR_URL" }, { status: 503 });
  const token = process.env.OCR_V2_SIDECAR_TOKEN;
  if (!token) return Response.json({ error: "SIDECAR_NOT_CONFIGURED" }, { status: 503 });
  let body: string | undefined;
  if (method === "POST") {
    const reader = request.body?.getReader(); if (!reader) return new Response("Missing body", { status: 400 });
    const chunks: Uint8Array[] = []; let total = 0;
    while (true) { const { value, done } = await reader.read(); if (done) break; total += value.byteLength; if (total > 4_000_000) { await reader.cancel(); return new Response("Request too large", { status: 413 }); } chunks.push(value); }
    const data = new Uint8Array(total); let at = 0; for (const chunk of chunks) { data.set(chunk, at); at += chunk.length; }
    body = new TextDecoder().decode(data);
    try { const value = JSON.parse(body); if (!["LAYOUT_M", "LAYOUT_V3"].includes(value.model) || typeof value.png !== "string" || !value.png.startsWith("data:image/png;base64,")) throw new Error(); body = JSON.stringify({ model: value.model, png: value.png }); }
    catch { return new Response("Invalid image request", { status: 400 }); }
  }
  try {
    const response = await fetch(new URL(method === "GET" ? "/health" : "/infer", base), { method, body, headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" }, signal: AbortSignal.timeout(85000), cache: "no-store", redirect: "error" });
    return new Response(await response.text(), { status: response.status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
  } catch { return Response.json({ status: "SIDECAR_UNAVAILABLE", error: "Local detector unavailable or timed out; use explicit geometry/manual fallback" }, { status: 503 }); }
}
export async function GET(request: NextRequest) { return forward(request, "GET"); }
export async function POST(request: NextRequest) { return forward(request, "POST"); }
