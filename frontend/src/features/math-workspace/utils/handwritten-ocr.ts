import type { InkStroke, OCRRecognizeResponse } from "@/lib/api/contracts";
import type { Stroke } from "ink-on/core";
import { A4_HEIGHT, A4_WIDTH } from "../types";
import { renderOcrLatexHtml } from "./ocr-math-preview";

const MODEL_ROOT = "/ocr/comer/v0_1";
export interface HandwrittenMathEvidence { rawLatex: string; latex: string; tokenIds: number[]; durationMs: number; encoderMs: number; decoderMs: number }
let modelPromise: Promise<{ recognize: (strokes: Stroke[]) => Promise<HandwrittenMathEvidence> }> | null = null;
let inferenceQueue: Promise<void> = Promise.resolve();

/** Preserve pen geometry and stroke order; never infer the formula from exercise text. */
export function toModelStrokes(strokes: InkStroke[]): Stroke[] {
  return strokes
    .filter((stroke) => stroke.tool === "PEN" && stroke.points.length > 0)
    .map((stroke) => ({
      lineWidth: Math.max(2, Math.min(12, Math.round(stroke.width * 1.5))),
      points: stroke.points.map((point) => ({
        x: Math.min(1, Math.max(0, point.x)) * A4_WIDTH,
        y: Math.min(1, Math.max(0, point.y)) * A4_HEIGHT,
      })),
    }));
}

async function loadModel() {
  if (!modelPromise) {
    modelPromise = (async () => {
      // Load vendor ESM unchanged by Turbopack: ORT's WASM expects the
      // matching browser module. Both imports share the same module instance.
      const [ort, core] = await Promise.all([
        import(/* webpackIgnore: true */ new URL("/ocr/runtime/ort.wasm.min.mjs", location.origin).href) as Promise<typeof import("onnxruntime-web")>,
        import(/* webpackIgnore: true */ new URL("/ocr/ink-on/core.js", location.origin).href) as Promise<typeof import("ink-on/core")>,
      ]);
      const { InferenceEngine, loadVocab, preprocessStrokes, isStrokeMeaningful } = core;
      ort.env.wasm.wasmPaths = "/ocr/runtime/";
      const vocab = await loadVocab(`${MODEL_ROOT}/vocab.json`);
      const engine = new InferenceEngine({
        encoderUrl: `${MODEL_ROOT}/encoder_int8.onnx`,
        decoderUrl: `${MODEL_ROOT}/decoder_int8.onnx`,
        beamWidth: 3,
        executionProvider: "wasm",
      });
      await engine.init();
      return {
        recognize: async (strokes: Stroke[]) => {
          if (!isStrokeMeaningful(strokes)) throw new Error("OCR_NOT_RECOGNIZED");
          const result = await engine.recognize(preprocessStrokes(strokes), vocab, "expression");
          return { rawLatex: core.decodeToTokenArray(result.tokenIds, vocab).join(" "), latex: result.latex.trim(), tokenIds: [...result.tokenIds], durationMs: result.totalMs, encoderMs: result.encoderMs, decoderMs: result.decoderMs };
        },
      };
    })().catch((error: unknown) => {
      modelPromise = null;
      throw error;
    });
  }
  return modelPromise;
}

/** Shared sessions and vendor preprocessing remain identical for Math View and page OCR. */
export async function recognizeHandwrittenMathEvidence(strokes: InkStroke[]): Promise<HandwrittenMathEvidence> {
  const modelStrokes = toModelStrokes(strokes);
  if (!modelStrokes.length) throw new Error("OCR_NOT_RECOGNIZED");
  const model = await loadModel();
  const run = inferenceQueue.then(() => model.recognize(modelStrokes));
  inferenceQueue = run.then(() => undefined, () => undefined);
  return run;
}

/** Legacy response contract retained for Math View and single-region tools. */
export async function recognizeHandwrittenMath(strokes: InkStroke[]): Promise<OCRRecognizeResponse> {
  const { latex } = await recognizeHandwrittenMathEvidence(strokes);
  if (!renderOcrLatexHtml(latex)) throw new Error("OCR_NOT_RECOGNIZED");
  return { latex, confidence: 0, suggested_step_type: "EXPLANATION", explanation_text: null, detected_symbols: [], alternative_latex: [] };
}
