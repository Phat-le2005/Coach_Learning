import type { InkStroke } from "@/lib/api/contracts";
import type { Stroke, PreprocessResult } from "ink-on/core";
import { toModelStrokes } from "./handwritten-ocr";
import { renderOcrLatexHtml } from "./ocr-math-preview";
import { sha256Hex } from "./ocr-digest";

export const DIAGNOSTIC_CONFIG = {
  model: "CoMER/v0_1/INT8", beamWidth: 3, executionProvider: "wasm", mode: "expression",
  maxDecodeSteps: 50,
  scoreNormalization: "logProb / max(returnedTokenIds.length + 1, 1); denominator includes SOS; terminal score may include EOS/repeat token omitted from ids",
} as const;
export const PREPROCESS_VARIANTS = [
  { id: "default", widthMultiplier: 1 },
  { id: "width-075", widthMultiplier: 0.75 },
  { id: "width-125", widthMultiplier: 1.25 },
] as const;
export type PreprocessVariant = typeof PREPROCESS_VARIANTS[number]["id"];
export async function sha256(bytes: ArrayBuffer | Uint8Array): Promise<string> {
  const input = bytes instanceof Uint8Array ? Uint8Array.from(bytes) : new Uint8Array(bytes);
  return sha256Hex(input);
}
type Beam = { ids: number[]; logProb: number };
type EngineResult = { latex: string; tokenIds: number[]; encoderMs: number; decoderMs: number; totalMs: number };
export type ObservableEngine = {
  beamDecode: (...args: unknown[]) => Promise<Beam[]>;
  recognize: (...args: unknown[]) => Promise<EngineResult>;
};

/** Instance-local observation. No replacement decoding, vendor edits, or candidate re-ranking. */
export async function observeRecognition(engine: ObservableEngine, input: unknown, vocab: unknown) {
  const original = engine.beamDecode;
  let beams: Beam[] | null = null;
  engine.beamDecode = async function (...args: unknown[]) {
    const result = await original.apply(this, args);
    beams = structuredClone(result);
    return result;
  };
  try { return { result: await engine.recognize(input, vocab, "expression"), beams: beams as Beam[] | null }; }
  finally { engine.beamDecode = original; }
}

function tensorPreview(input: PreprocessResult): string {
  const canvas = document.createElement("canvas"); canvas.width = input.width; canvas.height = input.height;
  const ctx = canvas.getContext("2d")!; const pixels = ctx.createImageData(input.width, input.height);
  input.tensor.forEach((v: number, i: number) => { const c = Math.round(v * 255); pixels.data.set([c, c, c, 255], i * 4); });
  ctx.putImageData(pixels, 0, 0); return canvas.toDataURL("image/png");
}

let runtimePromise: Promise<Awaited<ReturnType<typeof loadRuntime>>> | null = null;
let queue: Promise<unknown> = Promise.resolve();
async function loadRuntime() {
  const ort = await import(/* webpackIgnore: true */ new URL("/ocr/runtime/ort.wasm.min.mjs", location.origin).href) as typeof import("onnxruntime-web");
  const core = await import(/* webpackIgnore: true */ new URL("/ocr/ink-on/core.js", location.origin).href) as typeof import("ink-on/core");
  ort.env.wasm.wasmPaths = "/ocr/runtime/";
  const modelRoot = "/ocr/comer/v0_1";
  const [enc, dec, vocabBytes, runtimeBytes] = await Promise.all([
    core.fetchWithCache(`${modelRoot}/encoder_int8.onnx`), core.fetchWithCache(`${modelRoot}/decoder_int8.onnx`),
    fetch(`${modelRoot}/vocab.json`).then((r) => r.arrayBuffer()),
    fetch("/ocr/ink-on/chunks/inference-4T2UM6yg.js").then((r) => r.arrayBuffer()),
  ]);
  const vocab = await core.loadVocab(`${modelRoot}/vocab.json`);
  if (JSON.stringify(vocab) !== JSON.stringify(JSON.parse(new TextDecoder().decode(vocabBytes)))) throw new Error("VOCAB_CACHE_MISMATCH");
  const engine = new core.InferenceEngine({ encoderUrl: `${modelRoot}/encoder_int8.onnx`, decoderUrl: `${modelRoot}/decoder_int8.onnx`,
    beamWidth: DIAGNOSTIC_CONFIG.beamWidth, maxDecodeSteps: DIAGNOSTIC_CONFIG.maxDecodeSteps, executionProvider: "wasm" });
  await engine.init();
  return { core, vocab, engine, modelHashes: { encoder: await sha256(enc), decoder: await sha256(dec), vocab: await sha256(vocabBytes), runtime: await sha256(runtimeBytes) } };
}

export async function diagnoseMathScope(strokes: readonly InkStroke[], variant: PreprocessVariant = "default") {
  if (process.env.NODE_ENV === "production") throw new Error("QA_DIAGNOSTICS_DISABLED_IN_PRODUCTION");
  const run = async () => {
    const t0 = performance.now();
    runtimePromise ??= loadRuntime().catch((err) => { runtimePromise = null; throw err; });
    const rt = await runtimePromise;
    const settings = PREPROCESS_VARIANTS.find((v) => v.id === variant);
    if (!settings) throw new Error("UNKNOWN_PREPROCESS_VARIANT");
    const source = structuredClone([...strokes]);
    const modelStrokes: Stroke[] = toModelStrokes(source).map((s) => ({ ...s, lineWidth: s.lineWidth * settings.widthMultiplier }));
    if (!rt.core.isStrokeMeaningful(modelStrokes)) return { status: "ABSTAIN_NOT_MEANINGFUL" as const, sourceStrokeIds: source.map((s) => s.id),
      variant, config: DIAGNOSTIC_CONFIG, modelHashes: rt.modelHashes, confidence: "NOT_AVAILABLE" as const };
    const startPreprocess = performance.now();
    const input = rt.core.preprocessStrokes(modelStrokes);
    const preprocessMs = performance.now() - startPreprocess;
    const tensorSha256 = await sha256(new Uint8Array(input.tensor.buffer));
    const maskSha256 = await sha256(input.mask);
    const previewPng = tensorPreview(input);
    const observed = await observeRecognition(rt.engine as unknown as ObservableEngine, input, rt.vocab);
    const candidates = observed.beams?.map((beam, index) => {
      const rawTokens = rt.core.decodeToTokenArray(beam.ids, rt.vocab);
      const rawLatex = rawTokens.join(" ");
      const repaired = rt.core.repairLatex(rawTokens);
      const postprocessedLatex = repaired.join(" ");
      return { rank: index + 1, tokenIds: [...beam.ids], rawTokens, rawLatex, postprocessedLatex,
        logProb: Number.isFinite(beam.logProb) ? beam.logProb : "NOT_AVAILABLE",
        normalizedLogProb: Number.isFinite(beam.logProb) ? beam.logProb / Math.max(beam.ids.length + 1, 1) : "NOT_AVAILABLE",
        rawKatexValid: Boolean(renderOcrLatexHtml(rawLatex)), postprocessedKatexValid: Boolean(renderOcrLatexHtml(postprocessedLatex)),
        postprocessingChangedTokens: JSON.stringify(rawTokens) !== JSON.stringify(repaired),
        runtimeStructuralValidity: "NOT_AVAILABLE", stopReason: "NOT_AVAILABLE" };
    }) ?? "NOT_AVAILABLE";
    const rawTokens = rt.core.decodeToTokenArray(observed.result.tokenIds, rt.vocab);
    return {
      status: "COMPLETED" as const, sourceStrokeIds: source.map((s) => s.id), config: DIAGNOSTIC_CONFIG, modelHashes: rt.modelHashes,
      preprocessing: { variant, widthMultiplier: settings.widthMultiplier, effectiveLineWidths: modelStrokes.map((s) => Math.max(2, s.lineWidth)),
        pipeline: "unchanged vendor preprocessStrokes", padding: 16, targetContentHeight: 128, canvasHeight: input.height, canvasWidth: input.width,
        tensorSha256, maskSha256, previewPng, paddingScaleControls: "NOT_AVAILABLE; fixed vendor constants" },
      selectedTokenIds: observed.result.tokenIds, rawTokens, rawLatex: rawTokens.join(" "),
      postprocessedLatex: rt.core.repairLatex(rawTokens).join(" "), selectedLatex: observed.result.latex,
      selectedCandidateRanks: Array.isArray(candidates) && observed.result.latex ? candidates.filter((b) => JSON.stringify(b.tokenIds) === JSON.stringify(observed.result.tokenIds)).map((b) => b.rank) : [],
      frontendAcceptedLatex: renderOcrLatexHtml(observed.result.latex.trim()) ? observed.result.latex.trim() : null,
      candidates, confidence: "NOT_AVAILABLE" as const,
      timings: { encoderMs: observed.result.encoderMs, decoderMs: observed.result.decoderMs, runtimeTotalMs: observed.result.totalMs,
        preprocessMs, actionTotalMs: performance.now() - t0 },
      stopReason: "NOT_AVAILABLE", attention: "NOT_AVAILABLE", rawLogitTensors: "NOT_AVAILABLE; intentionally not retained",
      tokenStreamLimitations: "vendor returned ids exclude SOS, EOS and discarded repeat terminators; pre-repair sequence is available, complete decoder event history is not",
    };
  };
  const pending = queue.then(run); queue = pending.catch(() => undefined); return pending;
}
export type MathScopeDiagnostic = Awaited<ReturnType<typeof diagnoseMathScope>>;

/** Cache identity from actual vendor preprocessing, never from a GT label or scope ID. */
export async function fingerprintMathScope(strokes: readonly InkStroke[]) {
  if (process.env.NODE_ENV === "production") throw new Error("QA_DIAGNOSTICS_DISABLED_IN_PRODUCTION");
  runtimePromise ??= loadRuntime().catch(err => { runtimePromise = null; throw err; });
  const rt = await runtimePromise, modelStrokes = toModelStrokes([...strokes]);
  if (!rt.core.isStrokeMeaningful(modelStrokes)) return { status: "ABSTAIN_NOT_MEANINGFUL" as const };
  const input = rt.core.preprocessStrokes(modelStrokes);
  return { status: "READY" as const, modelHashes: rt.modelHashes, config: DIAGNOSTIC_CONFIG,
    tensorSha256: await sha256(new Uint8Array(input.tensor.buffer)), maskSha256: await sha256(input.mask) };
}
