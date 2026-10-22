import * as ort from "../../runtime/ort.wasm.min.mjs";
const MODEL_H = 256;
const MAX_W = 1024;
const MIN_W = 128;
const W_ALIGN = 64;
const TARGET_H = 128;
const PAD = 16;
let _rawCanvas = null;
let _targetCanvas = null;
function createCanvas(w, h, cache) {
  const fw = Math.max(1, Math.floor(w));
  const fh = Math.max(1, Math.floor(h));
  if (cache) {
    const ref = cache === "raw" ? _rawCanvas : _targetCanvas;
    if (ref && ref.width === fw && ref.height === fh) return ref;
  }
  const c = document.createElement("canvas");
  c.width = fw;
  c.height = fh;
  if (cache === "raw") _rawCanvas = c;
  else if (cache === "target") _targetCanvas = c;
  return c;
}
function resamplePoints(points, interval = 3) {
  if (points.length < 2) return points;
  const resampled = [points[0]];
  let remaining = interval;
  for (let i = 1; i < points.length; i++) {
    const prev = points[i - 1];
    const curr = points[i];
    const dx = curr.x - prev.x;
    const dy = curr.y - prev.y;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist <= remaining) {
      remaining -= dist;
      continue;
    }
    let covered = remaining;
    while (covered <= dist) {
      const t = covered / dist;
      resampled.push({
        x: prev.x + dx * t,
        y: prev.y + dy * t
      });
      covered += interval;
    }
    remaining = covered - dist;
  }
  resampled.push(points[points.length - 1]);
  return resampled;
}
function computeBBox(strokes) {
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
  for (const s of strokes) {
    for (const p of s.points) {
      if (p.x < minX) minX = p.x;
      if (p.y < minY) minY = p.y;
      if (p.x > maxX) maxX = p.x;
      if (p.y > maxY) maxY = p.y;
    }
  }
  return { minX, minY, maxX, maxY };
}
function renderStrokes(strokes) {
  const bbox = computeBBox(strokes);
  const rawW = Math.max(1, Math.ceil(bbox.maxX - bbox.minX));
  const rawH = Math.max(1, Math.ceil(bbox.maxY - bbox.minY));
  const canvas = createCanvas(rawW + PAD * 2, rawH + PAD * 2, "raw");
  const ctx = canvas.getContext("2d");
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#ffffff";
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const stroke of strokes) {
    if (stroke.points.length === 0) continue;
    const pts = resamplePoints(stroke.points);
    ctx.beginPath();
    ctx.lineWidth = Math.max(2, stroke.lineWidth);
    const first = pts[0];
    ctx.moveTo(first.x - bbox.minX + PAD, first.y - bbox.minY + PAD);
    if (pts.length === 2) {
      ctx.lineTo(pts[1].x - bbox.minX + PAD, pts[1].y - bbox.minY + PAD);
    } else if (pts.length > 2) {
      for (let i = 1; i < pts.length - 1; i++) {
        const mx = (pts[i].x + pts[i + 1].x) / 2 - bbox.minX + PAD;
        const my = (pts[i].y + pts[i + 1].y) / 2 - bbox.minY + PAD;
        ctx.quadraticCurveTo(
          pts[i].x - bbox.minX + PAD,
          pts[i].y - bbox.minY + PAD,
          mx,
          my
        );
      }
      const last = pts[pts.length - 1];
      ctx.lineTo(last.x - bbox.minX + PAD, last.y - bbox.minY + PAD);
    }
    ctx.stroke();
  }
  return canvas;
}
function scaleToFit(src) {
  const scale = Math.min(TARGET_H / src.height, MAX_W / src.width);
  const dw = Math.max(1, Math.round(src.width * scale));
  const dh = Math.max(1, Math.round(src.height * scale));
  const canvasW = Math.min(
    MAX_W,
    Math.max(MIN_W, Math.ceil((dw + PAD) / W_ALIGN) * W_ALIGN)
  );
  const target = createCanvas(canvasW, MODEL_H, "target");
  const ctx = target.getContext("2d");
  ctx.fillStyle = "#000000";
  ctx.fillRect(0, 0, canvasW, MODEL_H);
  ctx.drawImage(src, 0, 0, dw, dh);
  return { canvas: target, contentH: dh, contentW: dw, canvasW };
}
function canvasToGrayscaleTensor(canvas) {
  const ctx = canvas.getContext("2d");
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
  const { data } = imageData;
  const pixels = canvas.width * canvas.height;
  const tensor = new Float32Array(pixels);
  for (let i = 0; i < pixels; i++) {
    const offset = i * 4;
    const gray = (data[offset] * 0.299 + data[offset + 1] * 0.587 + data[offset + 2] * 0.114) / 255;
    tensor[i] = gray;
  }
  return tensor;
}
const MIN_STROKE_SIZE = 8;
const MIN_TOTAL_POINTS = 6;
const MIN_PATH_LENGTH = 15;
function isStrokeMeaningful(strokes) {
  if (strokes.length === 0) return false;
  const bbox = computeBBox(strokes);
  const w = bbox.maxX - bbox.minX;
  const h = bbox.maxY - bbox.minY;
  if (w < MIN_STROKE_SIZE && h < MIN_STROKE_SIZE) return false;
  let totalPoints = 0;
  let totalLength = 0;
  for (const s of strokes) {
    totalPoints += s.points.length;
    for (let i = 1; i < s.points.length; i++) {
      const dx = s.points[i].x - s.points[i - 1].x;
      const dy = s.points[i].y - s.points[i - 1].y;
      totalLength += Math.sqrt(dx * dx + dy * dy);
    }
  }
  return totalPoints >= MIN_TOTAL_POINTS && totalLength >= MIN_PATH_LENGTH;
}
function preprocessStrokes(strokes) {
  const rawCanvas = renderStrokes(strokes);
  const { canvas, contentH, contentW, canvasW } = scaleToFit(rawCanvas);
  const tensor = canvasToGrayscaleTensor(canvas);
  const mask = new Uint8Array(MODEL_H * canvasW);
  for (let y = 0; y < MODEL_H; y++) {
    for (let x = 0; x < canvasW; x++) {
      mask[y * canvasW + x] = y < contentH && x < contentW ? 0 : 1;
    }
  }
  return {
    tensor,
    height: MODEL_H,
    width: canvasW,
    mask,
    maskHeight: MODEL_H,
    maskWidth: canvasW
  };
}
let cachedVocab = null;
async function loadVocab(url) {
  if (cachedVocab) return cachedVocab;
  const res = await fetch(url);
  cachedVocab = await res.json();
  return cachedVocab;
}
function decodeTokenIds(ids, vocab) {
  return decodeToTokenArray(ids, vocab).join(" ");
}
function decodeToTokenArray(ids, vocab) {
  const { sos, eos, pad } = vocab.special_tokens;
  const skip = /* @__PURE__ */ new Set([sos, eos, pad]);
  const words = [];
  for (const id of ids) {
    if (skip.has(id)) continue;
    const w = vocab.idx2word[String(id)];
    if (w !== void 0) words.push(w);
  }
  return words;
}
const DB_NAME = "math-handwrite-models";
const DB_VERSION = 1;
const STORE_NAME = "onnx-models";
function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(STORE_NAME);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function getCachedModel(url) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const req = tx.objectStore(STORE_NAME).get(url);
      req.onsuccess = () => resolve(req.result ?? null);
      req.onerror = () => reject(req.error);
    });
  } catch {
    return null;
  }
}
async function cacheModel(url, data) {
  try {
    const db = await openDB();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, "readwrite");
      const req = tx.objectStore(STORE_NAME).put(data, url);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  } catch {
  }
}
async function fetchWithCache(url) {
  const cached = await getCachedModel(url);
  if (cached) return cached;
  const resp = await fetch(url);
  const buf = await resp.arrayBuffer();
  await cacheModel(url, buf);
  return buf;
}
function repairLatex(tokens) {
  let result = [...tokens];
  result = balanceBraces(result);
  result = fixFracArgs(result);
  result = fixSqrtArgs(result);
  return result;
}
function balanceBraces(tokens) {
  const result = [];
  let depth = 0;
  for (const t of tokens) {
    if (t === "{") {
      depth++;
      result.push(t);
    } else if (t === "}") {
      if (depth > 0) {
        depth--;
        result.push(t);
      }
    } else {
      result.push(t);
    }
  }
  while (depth > 0) {
    result.push("}");
    depth--;
  }
  return result;
}
function fixFracArgs(tokens) {
  const result = [];
  let i = 0;
  while (i < tokens.length) {
    if (tokens[i] === "\\frac") {
      result.push(tokens[i]);
      i++;
      let groups = 0;
      while (i < tokens.length && groups < 2) {
        if (tokens[i] === "{") {
          groups++;
          let depth = 1;
          result.push(tokens[i]);
          i++;
          while (i < tokens.length && depth > 0) {
            if (tokens[i] === "{") depth++;
            else if (tokens[i] === "}") depth--;
            result.push(tokens[i]);
            i++;
          }
        } else {
          result.push(tokens[i]);
          i++;
          groups++;
        }
      }
      while (i < tokens.length && tokens[i] === "{") {
        let depth = 1;
        i++;
        while (i < tokens.length && depth > 0) {
          if (tokens[i] === "{") depth++;
          else if (tokens[i] === "}") depth--;
          i++;
        }
      }
    } else {
      result.push(tokens[i]);
      i++;
    }
  }
  return result;
}
function fixSqrtArgs(tokens) {
  const result = [];
  let i = 0;
  while (i < tokens.length) {
    if (tokens[i] === "\\sqrt") {
      result.push(tokens[i]);
      i++;
      let groups = 0;
      while (i < tokens.length && groups < 1) {
        if (tokens[i] === "{") {
          groups++;
          let depth = 1;
          result.push(tokens[i]);
          i++;
          while (i < tokens.length && depth > 0) {
            if (tokens[i] === "{") depth++;
            else if (tokens[i] === "}") depth--;
            result.push(tokens[i]);
            i++;
          }
        } else {
          result.push(tokens[i]);
          i++;
          groups++;
        }
      }
      while (i < tokens.length && tokens[i] === "{") {
        let depth = 1;
        i++;
        while (i < tokens.length && depth > 0) {
          if (tokens[i] === "{") depth++;
          else if (tokens[i] === "}") depth--;
          i++;
        }
      }
    } else {
      result.push(tokens[i]);
      i++;
    }
  }
  return result;
}
const NEEDS_ARGS = /* @__PURE__ */ new Set([
  "\\sum",
  "\\int",
  "\\sin",
  "\\cos",
  "\\tan",
  "\\log",
  "\\lim",
  "\\sqrt",
  "\\frac"
]);
function isCompleteExpression(tokens) {
  if (tokens.length === 0) return false;
  if (tokens.length === 1 && NEEDS_ARGS.has(tokens[0])) return false;
  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i] === "\\frac") {
      const remaining = tokens.slice(i + 1);
      if (countBracedGroups(remaining) < 2) return false;
    }
    if (tokens[i] === "\\sqrt") {
      const remaining = tokens.slice(i + 1);
      if (countBracedGroups(remaining) < 1) return false;
    }
  }
  return true;
}
function countBracedGroups(tokens) {
  let groups = 0;
  let i = 0;
  while (i < tokens.length) {
    if (tokens[i] === "{") {
      groups++;
      let depth = 1;
      i++;
      while (i < tokens.length && depth > 0) {
        if (tokens[i] === "{") depth++;
        else if (tokens[i] === "}") depth--;
        i++;
      }
    } else {
      break;
    }
  }
  return groups;
}
ort.env.wasm.numThreads = navigator.hardwareConcurrency || 4;
ort.env.wasm.simd = true;
const DEFAULT_MAX_STEPS = 50;
const REPEAT_LIMIT = 3;
const NUMBER_MODE_ALLOWED = /* @__PURE__ */ new Set([
  0,
  1,
  2,
  // <pad>, <sos>, <eos>
  4,
  5,
  // ( )
  6,
  8,
  // + -
  9,
  10,
  // . /
  11,
  12,
  13,
  14,
  15,
  // 0 1 2 3 4
  16,
  17,
  18,
  19,
  20,
  // 5 6 7 8 9
  22,
  // =
  50,
  53,
  69,
  78,
  // \div \frac \pm \times
  82,
  83,
  // ^ _
  110,
  112
  // { }
]);
function yieldToMain() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}
function applyModeMask(logProbs, vocabSize, allowed) {
  if (!allowed) return;
  for (let i = 0; i < vocabSize; i++) {
    if (!allowed.has(i)) {
      logProbs[i] = -Infinity;
    }
  }
}
class InferenceEngine {
  encoderSession = null;
  decoderSession = null;
  options;
  loading = null;
  constructor(options) {
    this.options = {
      maxDecodeSteps: DEFAULT_MAX_STEPS,
      beamWidth: 3,
      executionProvider: "wasm",
      ...options
    };
  }
  async init() {
    if (this.encoderSession && this.decoderSession) return;
    if (this.loading) return this.loading;
    this.loading = this._loadSessions();
    await this.loading;
  }
  async _loadSessions() {
    const ep = this.options.executionProvider;
    const [encBuf, decBuf] = await Promise.all([
      fetchWithCache(this.options.encoderUrl),
      fetchWithCache(this.options.decoderUrl)
    ]);
    const opts = {
      executionProviders: [ep]
    };
    try {
      [this.encoderSession, this.decoderSession] = await Promise.all([
        ort.InferenceSession.create(encBuf, opts),
        ort.InferenceSession.create(decBuf, opts)
      ]);
    } catch {
      if (ep !== "wasm") {
        const fallback = {
          executionProviders: ["wasm"]
        };
        [this.encoderSession, this.decoderSession] = await Promise.all([
          ort.InferenceSession.create(encBuf, fallback),
          ort.InferenceSession.create(decBuf, fallback)
        ]);
      } else {
        throw new Error("Failed to create ONNX sessions");
      }
    }
  }
  async runDecoder(encoderFeatures, encoderMask, ids) {
    const inputIds = new ort.Tensor(
      "int64",
      BigInt64Array.from(ids.map(BigInt)),
      [1, ids.length]
    );
    const res = await this.decoderSession.run({
      encoder_features: encoderFeatures,
      encoder_mask: encoderMask,
      input_ids: inputIds
    });
    inputIds.dispose();
    return res["logits"].data;
  }
  logSoftmax(logits, offset, size) {
    const result = new Float64Array(size);
    let max = -Infinity;
    for (let i = 0; i < size; i++) {
      const v = logits[offset + i];
      if (v > max) max = v;
    }
    let sumExp = 0;
    for (let i = 0; i < size; i++) {
      sumExp += Math.exp(logits[offset + i] - max);
    }
    const logSumExp = Math.log(sumExp);
    for (let i = 0; i < size; i++) {
      result[i] = logits[offset + i] - max - logSumExp;
    }
    return result;
  }
  topK(arr, k) {
    const indices = Array.from({ length: arr.length }, (_, i) => i);
    indices.sort((a, b) => (arr[b] ?? 0) - (arr[a] ?? 0));
    return indices.slice(0, k);
  }
  async recognize(input, vocab, mode = "auto") {
    await this.init();
    const t0 = performance.now();
    const pixelValues = new ort.Tensor("float32", input.tensor, [
      1,
      1,
      input.height,
      input.width
    ]);
    const pixelMask = new ort.Tensor("bool", input.mask, [
      1,
      input.maskHeight,
      input.maskWidth
    ]);
    const encResult = await this.encoderSession.run({
      pixel_values: pixelValues,
      pixel_mask: pixelMask
    });
    pixelValues.dispose();
    pixelMask.dispose();
    const encoderFeatures = encResult["encoder_features"];
    const encoderMask = encResult["encoder_mask"];
    const t1 = performance.now();
    const { sos, eos } = vocab.special_tokens;
    const vocabSize = vocab.vocab_size;
    const beamWidth = this.options.beamWidth;
    const allowedTokens = mode === "number" ? NUMBER_MODE_ALLOWED : null;
    let resultIds;
    let resultLatex;
    if (beamWidth <= 1) {
      resultIds = await this.greedyDecode(
        encoderFeatures,
        encoderMask,
        sos,
        eos,
        vocabSize,
        allowedTokens
      );
      const tokens = decodeToTokenArray(resultIds, vocab);
      const repaired = repairLatex(tokens);
      resultLatex = repaired.join(" ");
    } else {
      const candidates = await this.beamDecode(
        encoderFeatures,
        encoderMask,
        sos,
        eos,
        vocabSize,
        beamWidth,
        allowedTokens
      );
      resultLatex = "";
      resultIds = candidates[0]?.ids ?? [];
      for (const candidate of candidates) {
        const tokens = decodeToTokenArray(candidate.ids, vocab);
        const repaired = repairLatex(tokens);
        const latex = repaired.join(" ");
        if (mode === "auto" && !isCompleteExpression(repaired)) continue;
        if (isValidMath(latex)) {
          resultLatex = latex;
          resultIds = candidate.ids;
          break;
        }
      }
      if (!resultLatex && candidates.length > 0) {
        const tokens = decodeToTokenArray(candidates[0].ids, vocab);
        const repaired = repairLatex(tokens);
        const latex = repaired.join(" ");
        resultLatex = isValidMath(latex) ? latex : "";
        resultIds = candidates[0].ids;
      }
    }
    encoderFeatures.dispose();
    encoderMask.dispose();
    const t2 = performance.now();
    return {
      latex: resultLatex,
      tokenIds: resultIds,
      encoderMs: Math.round(t1 - t0),
      decoderMs: Math.round(t2 - t1),
      totalMs: Math.round(t2 - t0)
    };
  }
  async greedyDecode(encoderFeatures, encoderMask, sos, eos, vocabSize, allowedTokens) {
    const tokenIds = [sos];
    let repeatCount = 0;
    let lastToken = -1;
    for (let step = 0; step < this.options.maxDecodeSteps; step++) {
      if (step > 0 && step % 5 === 0) await yieldToMain();
      const logits = await this.runDecoder(
        encoderFeatures,
        encoderMask,
        tokenIds
      );
      const offset = (tokenIds.length - 1) * vocabSize;
      const logProbs = this.logSoftmax(logits, offset, vocabSize);
      applyModeMask(logProbs, vocabSize, allowedTokens);
      let maxVal = -Infinity;
      let maxIdx = 0;
      for (let i = 0; i < vocabSize; i++) {
        if (logProbs[i] > maxVal) {
          maxVal = logProbs[i];
          maxIdx = i;
        }
      }
      if (maxIdx === eos) break;
      if (maxIdx === lastToken) {
        repeatCount++;
        if (repeatCount >= REPEAT_LIMIT) break;
      } else {
        repeatCount = 0;
      }
      lastToken = maxIdx;
      tokenIds.push(maxIdx);
    }
    return tokenIds.slice(1);
  }
  async beamDecode(encoderFeatures, encoderMask, sos, eos, vocabSize, beamWidth, allowedTokens) {
    let beams = [{ logProb: 0, ids: [sos], finished: false }];
    for (let step = 0; step < this.options.maxDecodeSteps; step++) {
      if (step > 0 && step % 3 === 0) await yieldToMain();
      const candidates = [];
      for (const beam of beams) {
        if (beam.finished) {
          candidates.push(beam);
          continue;
        }
        const logits = await this.runDecoder(
          encoderFeatures,
          encoderMask,
          beam.ids
        );
        const offset = (beam.ids.length - 1) * vocabSize;
        const logProbs = this.logSoftmax(logits, offset, vocabSize);
        applyModeMask(logProbs, vocabSize, allowedTokens);
        const topIndices = this.topK(logProbs, beamWidth * 2);
        for (const idx of topIndices) {
          const newLogProb = beam.logProb + (logProbs[idx] ?? 0);
          if (idx === eos) {
            candidates.push({
              logProb: newLogProb,
              ids: beam.ids,
              finished: true
            });
          } else {
            const ids = beam.ids;
            let rCount = 0;
            for (let j = ids.length - 1; j >= 1; j--) {
              if (ids[j] === idx) rCount++;
              else break;
            }
            if (rCount >= REPEAT_LIMIT) {
              candidates.push({
                logProb: newLogProb,
                ids: beam.ids,
                finished: true
              });
            } else {
              candidates.push({
                logProb: newLogProb,
                ids: [...beam.ids, idx],
                finished: false
              });
            }
          }
        }
      }
      candidates.sort(
        (a, b) => b.logProb / Math.max(b.ids.length, 1) - a.logProb / Math.max(a.ids.length, 1)
      );
      beams = candidates.slice(0, beamWidth);
      if (beams.every((b) => b.finished)) break;
    }
    const completed = beams.filter((b) => b.finished);
    const sorted = (completed.length > 0 ? completed : beams).sort(
      (a, b) => b.logProb / Math.max(b.ids.length, 1) - a.logProb / Math.max(a.ids.length, 1)
    );
    return sorted.slice(0, beamWidth).map((b) => ({
      ids: b.ids.slice(1),
      logProb: b.logProb
    }));
  }
  dispose() {
    this.encoderSession?.release();
    this.decoderSession?.release();
    this.encoderSession = null;
    this.decoderSession = null;
    this.loading = null;
  }
}
function isValidMath(latex) {
  if (!latex.trim()) return false;
  try {
    return isStructurallyValid(latex);
  } catch {
    return false;
  }
}
function isStructurallyValid(latex) {
  const tokens = latex.split(" ").filter(Boolean);
  if (tokens.length === 0) return false;
  let depth = 0;
  for (const t of tokens) {
    if (t === "{") depth++;
    else if (t === "}") depth--;
    if (depth < 0) return false;
  }
  if (depth !== 0) return false;
  for (let i = 0; i < tokens.length; i++) {
    if (tokens[i] === "\\frac") {
      const rest = tokens.slice(i + 1);
      if (countConsecutiveBracedGroups(rest) < 2) return false;
    }
    if (tokens[i] === "\\sqrt") {
      const rest = tokens.slice(i + 1);
      if (rest.length === 0) return false;
    }
  }
  return true;
}
function countConsecutiveBracedGroups(tokens) {
  let groups = 0;
  let i = 0;
  while (i < tokens.length) {
    if (tokens[i] === "{") {
      groups++;
      let d = 1;
      i++;
      while (i < tokens.length && d > 0) {
        if (tokens[i] === "{") d++;
        else if (tokens[i] === "}") d--;
        i++;
      }
    } else {
      break;
    }
  }
  return groups;
}
export {
  InferenceEngine as I,
  decodeTokenIds as a,
  isStrokeMeaningful as b,
  cacheModel as c,
  decodeToTokenArray as d,
  fetchWithCache as f,
  getCachedModel as g,
  isCompleteExpression as i,
  loadVocab as l,
  preprocessStrokes as p,
  repairLatex as r
};
//# sourceMappingURL=inference-4T2UM6yg.js.map
