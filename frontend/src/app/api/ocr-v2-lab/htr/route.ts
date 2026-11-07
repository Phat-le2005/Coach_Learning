import type { NextRequest } from "next/server";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import { verifySession } from "@/lib/auth/session-codec";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { assertHtrCandidate, type HtrCandidate } from "@/features/math-workspace/utils/vietnamese-htr";

const root = path.resolve(process.cwd(), ".."), directory = path.join(root, ".tmp/tri-vietnamese-htr");
const allowed = ["HTR-1", "HTR-2", "HTR-3"];
let busy = false;
async function gate(request: NextRequest) {
  if (process.env.NODE_ENV === "production" || process.env.OCR_V2_EXPERIMENTAL !== "1") return new Response("Not Found", { status: 404 });
  if (!await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, process.env.AUTH_SESSION_SECRET ?? "")) return new Response("QA authentication required", { status: 401 });
  const origin = request.headers.get("origin");
  if (origin && origin !== request.nextUrl.origin) return new Response("Same origin required", { status: 403 });
  return null;
}
async function loadCandidate(id: string): Promise<HtrCandidate> {
  if (!allowed.includes(id)) throw Error("ONLY_THREE_CONFIRMED_CANDIDATES_ALLOWED");
  const inputs = JSON.parse(await readFile(path.join(directory, "inputs.json"), "utf8"));
  const references = JSON.parse(await readFile(path.join(directory, "references.utf8.json"), "utf8"));
  const item = inputs.find((i: { candidateId: string }) => i.candidateId === id);
  const ref = references.find((r: { id: string; candidateId: string }) => r.id === item?.referenceId && r.candidateId === id);
  if (!item || !ref || ref.text.includes("\ufffd")) throw Error("CANDIDATE_OR_UTF8_REFERENCE_MISSING");
  const file = path.join(root, ".tmp/tri-native-page-validation", id + ".png");
  if (path.resolve(root, item.pngFile) !== file) throw Error("INVALID_FIXED_CROP_PATH");
  const png = await readFile(file);
  if (createHash("sha256").update(png).digest("hex") !== item.inputImageHash) throw Error("INPUT_PNG_HASH_MISMATCH");
  const { pngFile: _privatePath, referenceId: _referenceId, ...metadata } = item;
  const result = { ...metadata, png: "data:image/png;base64," + png.toString("base64"), reference: { id: ref.id, text: ref.text, status: ref.status } };
  assertHtrCandidate(result); return result;
}
async function localRequest(route: string, signal: AbortSignal, candidateId?: string) {
  const token = (await readFile(path.join(directory, "server-key.txt"), "utf8")).trim();
  if (token.length < 32) throw Error("HTR_LOCAL_SERVICE_NOT_STARTED");
  const response = await fetch("http://127.0.0.1:8041" + route, { method: candidateId ? "POST" : "GET",
    headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    body: candidateId ? JSON.stringify({ candidateId }) : undefined, cache: "no-store", redirect: "error", signal });
  const value = await response.json();
  if (!response.ok) throw Error(value.detail ?? value.error ?? `LOCAL_HTR_HTTP_${response.status}`);
  return value;
}
export async function GET(request: NextRequest) {
  const denied = await gate(request); if (denied) return denied;
  try {
    const candidates = await Promise.all(allowed.map(loadCandidate)).catch(error => { if ((error as NodeJS.ErrnoException).code === "ENOENT") return []; throw error; });
    const health = await localRequest("/health", AbortSignal.timeout(3000)).catch(e => ({ status: "UNAVAILABLE", error: String(e) }));
    return Response.json({ candidates, health }, { headers: { "Cache-Control": "no-store" } });
  } catch (e) { return Response.json({ error: String(e) }, { status: 503 }); }
}
export async function POST(request: NextRequest) {
  const denied = await gate(request); if (denied) return denied;
  if (busy) return Response.json({ error: "HTR_BUSY" }, { status: 429 });
  const reader = request.body?.getReader(); if (!reader) return new Response("Missing candidate", { status: 400 });
  const chunks: Uint8Array[] = []; let size = 0;
  while (true) { const { value, done } = await reader.read(); if (done) break; size += value.length;
    if (size > 200) { await reader.cancel(); return new Response("Candidate request too large", { status: 413 }); } chunks.push(value); }
  let id: string;
  try { const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    if (Object.keys(body).length !== 1 || typeof body.candidateId !== "string" || !allowed.includes(body.candidateId)) throw Error();
    id = body.candidateId;
  } catch { return new Response("Only a confirmed candidate ID is allowed", { status: 400 }); }
  busy = true;
  try {
    await loadCandidate(id); // verify current local image/reference, never forward reference
    const evidence = await localRequest("/infer", AbortSignal.any([request.signal, AbortSignal.timeout(120000)]), id);
    return Response.json(evidence, { headers: { "Cache-Control": "no-store" } });
  } catch (e) { return Response.json({ status: "ERROR", error: String(e) }, { status: 503 }); }
  finally { busy = false; }
}
