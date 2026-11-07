import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { createHash } from "node:crypto";
import type { NextRequest } from "next/server";
import { AUTH_COOKIES } from "@/lib/auth/constants";
import { verifySession } from "@/lib/auth/session-codec";

/** Fixed local dataset index only; no client path, uploads, cloud inference or DB writes. */
export async function GET(request: NextRequest) {
  if (process.env.NODE_ENV === "production" || process.env.OCR_V2_EXPERIMENTAL !== "1") return new Response("Not Found", { status: 404 });
  if (!await verifySession(request.cookies.get(AUTH_COOKIES.session)?.value, process.env.AUTH_SESSION_SECRET ?? "")) return new Response("QA authentication required", { status: 401 });
  if (request.headers.get("origin") && request.headers.get("origin") !== request.nextUrl.origin) return new Response("Same origin required", { status: 403 });
  const root = path.resolve(process.cwd(), ".."), file = path.join(root, ".tmp/tri-ocr-v2-evaluation/source-index.json");
  try {
    if ((await stat(file)).size > 20_000_000) throw Error("SOURCE_INDEX_TOO_LARGE");
    const bytes = await readFile(file), index = JSON.parse(bytes.toString("utf8"));
    if (index.schemaVersion !== "ocr-eval-source-index/1" || !Array.isArray(index.records) || index.records.length > 1000) throw Error("INVALID_SOURCE_INDEX");
    const files = ["utils/ocr-evaluation-data.ts", "utils/ocr-evaluation-metrics.ts", "utils/ocr-evaluation-benchmark.ts", "utils/ocr-v2-scope-candidates.ts", "utils/ocr-model-diagnostics.ts", "utils/handwritten-ocr.ts"];
    const hashes = Object.fromEntries(await Promise.all(files.map(async name => [name, createHash("sha256").update(await readFile(path.join(root, "frontend/src/features/math-workspace", name))).digest("hex")])));
    const codeSignature = createHash("sha256").update(JSON.stringify(hashes)).digest("hex");
    const vocabBytes = await readFile(path.join(root, "frontend/public/ocr/comer/v0_1/vocab.json"));
    return Response.json({ ...index, records: index.records.filter((r: { originalSplit: string; inkCreationMethod: string }) => ["train", "valid", "test"].includes(r.originalSplit) && r.inkCreationMethod === "human"), codeSignature, codeHashes: hashes,
      sourceIndexSha256: createHash("sha256").update(bytes).digest("hex"), recognizerVocabulary: Object.keys(JSON.parse(vocabBytes.toString("utf8")).word2idx), recognizerVocabularySha256: createHash("sha256").update(vocabBytes).digest("hex"), usage: "Local noncommercial research; original license/attribution retained; no student-data mutation" }, { headers: { "Cache-Control": "no-store" } });
  } catch { return Response.json({ status: "DATASET_NOT_PREPARED", message: "Run tools/ocr-v2-lab/prepare_evaluation.py once with the existing local Python; no dataset is fabricated." }, { status: 503 }); }
}
