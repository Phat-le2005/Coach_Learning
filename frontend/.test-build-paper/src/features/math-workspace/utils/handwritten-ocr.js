"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.toModelStrokes = toModelStrokes;
exports.recognizeHandwrittenMath = recognizeHandwrittenMath;
const types_1 = require("../types");
const ocr_math_preview_1 = require("./ocr-math-preview");
const MODEL_ROOT = "/ocr/comer/v0_1";
let modelPromise = null;
let inferenceQueue = Promise.resolve();
/** Preserve pen geometry and stroke order; never infer the formula from exercise text. */
function toModelStrokes(strokes) {
    return strokes
        .filter((stroke) => stroke.tool === "PEN" && stroke.points.length > 0)
        .map((stroke) => ({
        lineWidth: Math.max(2, Math.min(12, Math.round(stroke.width * 1.5))),
        points: stroke.points.map((point) => ({
            x: Math.min(1, Math.max(0, point.x)) * types_1.A4_WIDTH,
            y: Math.min(1, Math.max(0, point.y)) * types_1.A4_HEIGHT,
        })),
    }));
}
async function loadModel() {
    if (!modelPromise) {
        modelPromise = (async () => {
            // Load vendor ESM unchanged by Turbopack: ORT's WASM expects the
            // matching browser module. Both imports share the same module instance.
            const [ort, core] = await Promise.all([
                import(/* webpackIgnore: true */ new URL("/ocr/runtime/ort.wasm.min.mjs", location.origin).href),
                import(/* webpackIgnore: true */ new URL("/ocr/ink-on/core.js", location.origin).href),
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
                recognize: async (strokes) => {
                    if (!isStrokeMeaningful(strokes))
                        return "";
                    const result = await engine.recognize(preprocessStrokes(strokes), vocab, "expression");
                    return result.latex.trim();
                },
            };
        })().catch((error) => {
            modelPromise = null;
            throw error;
        });
    }
    return modelPromise;
}
/** Uncalibrated suggestion only; students compare with their ink before saving. */
async function recognizeHandwrittenMath(strokes) {
    const modelStrokes = toModelStrokes(strokes);
    if (modelStrokes.length === 0)
        throw new Error("OCR_NOT_RECOGNIZED");
    const model = await loadModel();
    // ONNX sessions are shared; serialize inference across requests in this page.
    const run = inferenceQueue.then(() => model.recognize(modelStrokes));
    inferenceQueue = run.then(() => undefined, () => undefined);
    const latex = await run;
    if (!(0, ocr_math_preview_1.renderOcrLatexHtml)(latex))
        throw new Error("OCR_NOT_RECOGNIZED");
    return {
        latex,
        confidence: 0,
        suggested_step_type: "EXPLANATION",
        explanation_text: null,
        detected_symbols: [],
        alternative_latex: [],
    };
}
