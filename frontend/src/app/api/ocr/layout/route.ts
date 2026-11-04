import type { NextRequest } from "next/server";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { verifySession } from "@/lib/auth/session-codec";

/** Server-configured loopback model service only. Never a client-controlled URL or filesystem path. */
async function configuration(request: NextRequest) {
  if (!await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, process.env.AUTH_SESSION_SECRET ?? "")) return { error: new Response("Authentication required", { status: 401 }) };
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) return { error: new Response("Same origin required", { status: 403 }) };
  const address = process.env.OCR_LAYOUT_SERVICE_URL, token = process.env.OCR_LAYOUT_SERVICE_TOKEN;
  if (!address || !token) return { error: Response.json({ status: "NOT_CONFIGURED", regions: [] }) };
  const url = new URL(address);
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "[::1]"].includes(url.hostname) || url.username || url.password || url.search || url.hash) return { error: Response.json({ status: "INVALID_SERVICE_CONFIGURATION", regions: [] }, { status: 503 }) };
  return { address: url.origin, token };
}
export async function GET(request: NextRequest) {
  try { const cfg = await configuration(request); if (cfg.error) return cfg.error;
    const r = await fetch(`${cfg.address}/health`, { headers: { Authorization: `Bearer ${cfg.token}` }, signal: AbortSignal.timeout(2500), cache: "no-store" });
    if (!r.ok) throw Error(`HTTP_${r.status}`);
    const data = await r.json(); return Response.json({ status: data.status, models: data.models, htr: data.htr });
  } catch { return Response.json({ status: "UNAVAILABLE", regions: [] }, { status: 503 }); }
}
export async function POST(request: NextRequest) {
  try { const cfg = await configuration(request); if (cfg.error) return cfg.error;
    if (Number(request.headers.get("content-length") ?? 0) > 4_000_000) return new Response("Image too large", { status: 413 });
    const reader = request.body?.getReader(); if (!reader) return new Response("Image required", { status: 400 });
    const chunks: Uint8Array[] = []; let size = 0;
    while (true) { const { value, done } = await reader.read(); if (done) break; size += value.length; if (size > 4_000_000) { await reader.cancel(); return new Response("Image too large", { status: 413 }); } chunks.push(value); }
    const input = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (Object.keys(input).some(k => k !== "png") || typeof input.png !== "string" || !input.png.startsWith("data:image/png;base64,")) return new Response("PNG required", { status: 400 });
    const r = await fetch(`${cfg.address}/infer`, { method: "POST", headers: { Authorization: `Bearer ${cfg.token}`, "Content-Type": "application/json" }, body: JSON.stringify({ model: "LAYOUT_M", png: input.png }), signal: AbortSignal.timeout(12000), cache: "no-store" });
    if (!r.ok) throw Error(`HTTP_${r.status}`);
    const data = await r.json(); return Response.json({ status: data.status, regions: data.regions ?? [], error: data.error, model: "LAYOUT_M" });
  } catch { return Response.json({ status: "UNAVAILABLE", regions: [] }, { status: 503 }); }
}
