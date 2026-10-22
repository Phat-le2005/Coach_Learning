import type { InkStroke, OCRRecognizeResponse } from "@/lib/api/contracts";
import type { Stroke } from "ink-on/core";
import { A4_HEIGHT, A4_WIDTH } from "../types";
import { renderOcrLatexHtml } from "./ocr-math-preview";

const MODEL_ROOT = "/ocr/comer/v0_1";
let modelPromise: Promise<{ recognize: (strokes: Stroke[]) => Promise<string> }> | null = null;
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
          if (!isStrokeMeaningful(strokes)) return "";
          const result = await engine.recognize(preprocessStrokes(strokes), vocab, "expression");
          return result.latex.trim();
        },
      };
    })().catch((error: unknown) => {
      modelPromise = null;
      throw error;
    });
  }
  return modelPromise;
}

/** Uncalibrated suggestion only; students compare with their ink before saving. */
export async function recognizeHandwrittenMath(strokes: InkStroke[]): Promise<OCRRecognizeResponse> {
  const modelStrokes = toModelStrokes(strokes);
  if (modelStrokes.length === 0) throw new Error("OCR_NOT_RECOGNIZED");
  const model = await loadModel();
  // ONNX sessions are shared; serialize inference across requests in this page.
  const run = inferenceQueue.then(() => model.recognize(modelStrokes));
  inferenceQueue = run.then(() => undefined, () => undefined);
  const latex = await run;
  if (!renderOcrLatexHtml(latex)) throw new Error("OCR_NOT_RECOGNIZED");
  return {
    latex,
    confidence: 0,
    suggested_step_type: "EXPLANATION",
    explanation_text: null,
    detected_symbols: [],
    alternative_latex: [],
  };
}

