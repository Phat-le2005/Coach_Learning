import type { InkStroke } from "@/lib/api/contracts";
import type { OcrEvalCaptureV1 } from "./ocr-eval-capture";
import { segmentPageInk_v2, segmentPageInk_v1, type PageOcrRegion, type InkBounds } from "./page-ocr";
import { getOcrPenStrokes } from "./ocr-ink";

// ============================================================================
// 1. Types: Capture Validation, Replay Report & Ground Truth
// ============================================================================

export interface ReplayMembershipDiff {
  regionIndex: number;
  capturedRegionId: string;
  replayedRegionId?: string;
  capturedStrokeIds: string[];
  replayedStrokeIds: string[];
  addedInReplay: string[];
  removedInReplay: string[];
}

export interface ReplaySegmentationDiff {
  matchingRegionCount: boolean;
  capturedRegionCount: number;
  replayedRegionCount: number;
  strokeCoverageIntact: boolean;
  missingStrokes: string[];
  duplicateStrokes: string[];
  membershipDifferences: ReplayMembershipDiff[];
  readingOrderChanged: boolean;
  capturedReadingOrder: string[];
  replayedReadingOrder: string[];
}

export interface ReplayReport {
  sampleId?: string;
  algorithm: "v1" | "v2";
  replayedRegions: PageOcrRegion[];
  diff: ReplaySegmentationDiff;
  identicalToCapture: boolean;
}

export interface GroundTruthGroup {
  groupId: string;
  strokeIds: string[];
  kind?: "EQUATION" | "SYSTEM" | "ALTERNATIVES" | "FRACTION" | "EXPLANATION" | "OTHER";
}

export interface OcrGroundTruthV1 {
  schemaVersion: 1;
  sampleId: string;
  sourceCaptureId?: string;
  expectedGroups: GroundTruthGroup[];
  expectedReadingOrder?: string[];
  structureKind?: "SYSTEM" | "ALTERNATIVES" | "FRACTION" | "INDEPENDENT" | "MIXED";
  annotationNotes?: string;
}

export interface SegmentationMetrics {
  totalExpectedStrokes: number;
  totalPredictedStrokes: number;
  strokeCoverage: number;
  missingStrokeIds: string[];
  duplicateStrokeIds: string[];
  totalExpectedGroups: number;
  totalPredictedRegions: number;
  exactGroupMatches: number;
  falseSplitCount: number;
  falseMergeCount: number;
  groupPrecision: number;
  groupRecall: number;
  groupF1: number;
  /** Null when the predictions offer no comparable ordered pair. */
  readingOrderCorrectness: number | null;
  readingOrderComparablePairs: number;
}

// ============================================================================
// 2. Safe Capture Reader & Validator
// ============================================================================

const SENSITIVE_KEY_PATTERN = /(?:password|token|secret|authorization|bearer|jwt|attempt_?id)/i;

function isObject(val: unknown): val is Record<string, unknown> {
  return typeof val === "object" && val !== null && !Array.isArray(val);
}

function isValidBounds(b: unknown): b is InkBounds {
  if (!isObject(b)) return false;
  const { left, top, right, bottom } = b;
  return (
    typeof left === "number" &&
    typeof top === "number" &&
    typeof right === "number" &&
    typeof bottom === "number" &&
    Number.isFinite(left) &&
    Number.isFinite(top) &&
    Number.isFinite(right) &&
    Number.isFinite(bottom) &&
    left <= right &&
    top <= bottom
  );
}

/**
 * Validates untrusted JSON as a well-formed OcrEvalCaptureV1.
 * Fails closed on malformed structures, non-finite coords, or sensitive credentials.
 */
export function validateOcrEvalCapture(data: unknown): OcrEvalCaptureV1 {
  if (!isObject(data)) {
    throw new Error("OCR_CAPTURE_INVALID_ROOT: Expected a JSON object");
  }

  // Security & privacy check: scan keys for credentials or attempt tracking leakage
  const ownKeys = Object.getOwnPropertyNames(data);
  for (const key of ownKeys) {
    if (key === "__proto__" || key === "constructor" || key === "prototype") {
      throw new Error("OCR_CAPTURE_INSECURE_PAYLOAD: Prototype pollution key detected");
    }
    if (SENSITIVE_KEY_PATTERN.test(key)) {
      throw new Error(`OCR_CAPTURE_PRIVACY_VIOLATION: Capture must not contain credential or attempt key '${key}'`);
    }
  }

  if (data.schemaVersion !== 1) {
    throw new Error(`OCR_CAPTURE_UNSUPPORTED_VERSION: Expected schemaVersion 1, got ${String(data.schemaVersion)}`);
  }

  if (data.sourceKind !== "MATHCANVAS_INK") {
    throw new Error(`OCR_CAPTURE_INVALID_SOURCE: Expected sourceKind 'MATHCANVAS_INK', got '${String(data.sourceKind)}'`);
  }

  if (typeof data.pageIndex !== "number" || !Number.isInteger(data.pageIndex) || data.pageIndex < 0) {
    throw new Error("OCR_CAPTURE_INVALID_PAGE: pageIndex must be a non-negative integer");
  }

  if (!Array.isArray(data.strokes)) {
    throw new Error("OCR_CAPTURE_INVALID_STROKES: strokes must be an array");
  }

  const validatedStrokes: InkStroke[] = [];
  const seenStrokeIds = new Set<string>();

  for (let i = 0; i < data.strokes.length; i++) {
    const s = data.strokes[i];
    if (!isObject(s)) {
      throw new Error(`OCR_CAPTURE_MALFORMED_STROKE: Stroke at index ${i} is not an object`);
    }

    if (typeof s.id !== "string" || !s.id.trim()) {
      throw new Error(`OCR_CAPTURE_MALFORMED_STROKE: Stroke at index ${i} has empty or non-string id`);
    }
    if (seenStrokeIds.has(s.id)) {
      throw new Error(`OCR_CAPTURE_DUPLICATE_STROKE_ID: Stroke id '${s.id}' duplicated in strokes array`);
    }
    seenStrokeIds.add(s.id);

    if (s.tool !== "PEN" && s.tool !== "HIGHLIGHTER") {
      throw new Error(`OCR_CAPTURE_MALFORMED_STROKE: Stroke '${s.id}' has invalid tool '${String(s.tool)}'`);
    }

    if (typeof s.color !== "string" || !s.color) {
      throw new Error(`OCR_CAPTURE_MALFORMED_STROKE: Stroke '${s.id}' missing color`);
    }

    if (typeof s.width !== "number" || !Number.isFinite(s.width) || s.width <= 0) {
      throw new Error(`OCR_CAPTURE_MALFORMED_STROKE: Stroke '${s.id}' has non-positive or non-finite width`);
    }

    if (!Array.isArray(s.points)) {
      throw new Error(`OCR_CAPTURE_MALFORMED_STROKE: Stroke '${s.id}' points is not an array`);
    }

    const validatedPoints: InkStroke["points"] = [];
    for (let j = 0; j < s.points.length; j++) {
      const p = s.points[j];
      if (!isObject(p)) {
        throw new Error(`OCR_CAPTURE_MALFORMED_POINT: Point ${j} in stroke '${s.id}' is not an object`);
      }
      if (typeof p.x !== "number" || !Number.isFinite(p.x) || p.x < -0.2 || p.x > 1.2) {
        throw new Error(`OCR_CAPTURE_OUT_OF_BOUNDS: Point ${j} x in stroke '${s.id}' is out of bounds: ${String(p.x)}`);
      }
      if (typeof p.y !== "number" || !Number.isFinite(p.y) || p.y < -0.2 || p.y > 1.2) {
        throw new Error(`OCR_CAPTURE_OUT_OF_BOUNDS: Point ${j} y in stroke '${s.id}' is out of bounds: ${String(p.y)}`);
      }
      const pressure = typeof p.pressure === "number" && Number.isFinite(p.pressure) ? p.pressure : 0.5;
      validatedPoints.push({ x: p.x, y: p.y, pressure });
    }

    validatedStrokes.push({
      id: s.id,
      tool: s.tool,
      color: s.color,
      width: s.width,
      points: validatedPoints,
    });
  }

  // Validate segmentation
  if (!isObject(data.segmentation)) {
    throw new Error("OCR_CAPTURE_INVALID_SEGMENTATION: segmentation must be an object");
  }
  if (data.segmentation.algorithm !== "v2") {
    throw new Error(`OCR_CAPTURE_UNSUPPORTED_ALGORITHM: Expected algorithm 'v2', got '${String(data.segmentation.algorithm)}'`);
  }
  if (!Array.isArray(data.segmentation.regions)) {
    throw new Error("OCR_CAPTURE_INVALID_SEGMENTATION: regions must be an array");
  }

  const validatedRegions: OcrEvalCaptureV1["segmentation"]["regions"] = [];
  for (let i = 0; i < data.segmentation.regions.length; i++) {
    const r = data.segmentation.regions[i];
    if (!isObject(r)) {
      throw new Error(`OCR_CAPTURE_MALFORMED_REGION: Region at index ${i} is not an object`);
    }
    if (typeof r.id !== "string" || !r.id.trim()) {
      throw new Error(`OCR_CAPTURE_MALFORMED_REGION: Region at index ${i} has invalid id`);
    }
    if (!Array.isArray(r.strokeIds) || !r.strokeIds.every((id) => typeof id === "string")) {
      throw new Error(`OCR_CAPTURE_MALFORMED_REGION: Region '${r.id}' strokeIds must be array of strings`);
    }
    if (!isValidBounds(r.bounds)) {
      throw new Error(`OCR_CAPTURE_MALFORMED_REGION: Region '${r.id}' bounds are invalid`);
    }
    validatedRegions.push({
      id: r.id,
      strokeIds: [...r.strokeIds],
      bounds: { ...r.bounds },
    });
  }

  // Validate diagnostics
  if (!isObject(data.diagnostics)) {
    throw new Error("OCR_CAPTURE_INVALID_DIAGNOSTICS: diagnostics must be an object");
  }
  const { missingPenStrokeIds, repeatedPenStrokeIds, unknownRegionStrokeIds } = data.diagnostics;
  if (!Array.isArray(missingPenStrokeIds) || !missingPenStrokeIds.every((id) => typeof id === "string")) {
    throw new Error("OCR_CAPTURE_INVALID_DIAGNOSTICS: missingPenStrokeIds must be an array of strings");
  }
  if (!Array.isArray(repeatedPenStrokeIds) || !repeatedPenStrokeIds.every((id) => typeof id === "string")) {
    throw new Error("OCR_CAPTURE_INVALID_DIAGNOSTICS: repeatedPenStrokeIds must be an array of strings");
  }
  if (!Array.isArray(unknownRegionStrokeIds) || !unknownRegionStrokeIds.every((id) => typeof id === "string")) {
    throw new Error("OCR_CAPTURE_INVALID_DIAGNOSTICS: unknownRegionStrokeIds must be an array of strings");
  }

  return {
    schemaVersion: 1,
    sourceKind: "MATHCANVAS_INK",
    pageIndex: data.pageIndex,
    strokes: validatedStrokes,
    segmentation: {
      algorithm: "v2",
      regions: validatedRegions,
    },
    diagnostics: {
      missingPenStrokeIds: [...missingPenStrokeIds],
      repeatedPenStrokeIds: [...repeatedPenStrokeIds],
      unknownRegionStrokeIds: [...unknownRegionStrokeIds],
    },
  };
}

/**
 * Reconstructs clean, deeply-copied InkStroke input ready for segmentation.
 */
export function reconstructSegmentationInput(capture: OcrEvalCaptureV1): InkStroke[] {
  return capture.strokes.map((s) => ({
    ...s,
    points: s.points.map((p) => ({ ...p })),
  }));
}

// ============================================================================
// 3. Baseline Replay Runner
// ============================================================================

/**
 * Replays segmentation on captured ink and computes divergence from the captured state.
 * Never treats captured segmentation as ground truth.
 */
export function replaySegmentationCapture(
  capture: OcrEvalCaptureV1,
  options: { algorithm?: "v1" | "v2"; sampleId?: string } = {},
): ReplayReport {
  const algorithm = options.algorithm ?? "v2";
  const inputStrokes = reconstructSegmentationInput(capture);
  const replayedRegions =
    algorithm === "v1" ? segmentPageInk_v1(inputStrokes) : segmentPageInk_v2(inputStrokes);

  const penStrokes = getOcrPenStrokes(inputStrokes);
  const allPenIds = new Set(penStrokes.map((s) => s.id));

  // 1. Check stroke coverage and duplicates in replay
  const replayedStrokeCounts = new Map<string, number>();
  for (const reg of replayedRegions) {
    for (const stroke of reg.strokes) {
      replayedStrokeCounts.set(stroke.id, (replayedStrokeCounts.get(stroke.id) ?? 0) + 1);
    }
  }

  const missingStrokes = [...allPenIds].filter((id) => !replayedStrokeCounts.has(id));
  const duplicateStrokes = [...replayedStrokeCounts.entries()]
    .filter(([, count]) => count > 1)
    .map(([id]) => id);

  // 2. Reading order comparison
  const capturedReadingOrder = capture.segmentation.regions.map((r) => r.id);
  const replayedReadingOrder = replayedRegions.map((r) => r.id);
  const readingOrderChanged =
    capturedReadingOrder.length !== replayedReadingOrder.length ||
    capturedReadingOrder.some((id, idx) => id !== replayedReadingOrder[idx]);

  // 3. Membership diffs by region alignment
  const membershipDifferences: ReplayMembershipDiff[] = [];
  const maxLen = Math.max(capture.segmentation.regions.length, replayedRegions.length);

  for (let i = 0; i < maxLen; i++) {
    const cap = capture.segmentation.regions[i];
    const rep = replayedRegions[i];
    const capStrokeIds = cap ? cap.strokeIds : [];
    const repStrokeIds = rep ? rep.strokes.map((s) => s.id) : [];

    const capSet = new Set(capStrokeIds);
    const repSet = new Set(repStrokeIds);

    const addedInReplay = repStrokeIds.filter((id) => !capSet.has(id));
    const removedInReplay = capStrokeIds.filter((id) => !repSet.has(id));

    if (addedInReplay.length > 0 || removedInReplay.length > 0 || !cap || !rep) {
      membershipDifferences.push({
        regionIndex: i,
        capturedRegionId: cap?.id ?? `missing-${i}`,
        replayedRegionId: rep?.id,
        capturedStrokeIds: capStrokeIds,
        replayedStrokeIds: repStrokeIds,
        addedInReplay,
        removedInReplay,
      });
    }
  }

  const matchingRegionCount = capture.segmentation.regions.length === replayedRegions.length;
  const strokeCoverageIntact = missingStrokes.length === 0 && duplicateStrokes.length === 0;
  const identicalToCapture =
    matchingRegionCount &&
    strokeCoverageIntact &&
    membershipDifferences.length === 0 &&
    !readingOrderChanged;

  return {
    sampleId: options.sampleId,
    algorithm,
    replayedRegions,
    diff: {
      matchingRegionCount,
      capturedRegionCount: capture.segmentation.regions.length,
      replayedRegionCount: replayedRegions.length,
      strokeCoverageIntact,
      missingStrokes,
      duplicateStrokes,
      membershipDifferences,
      readingOrderChanged,
      capturedReadingOrder,
      replayedReadingOrder,
    },
    identicalToCapture,
  };
}

// ============================================================================
// 4. Ground Truth Metrics Evaluation
// ============================================================================

/**
 * Evaluates predicted regions against an annotated ground truth.
 * Accurately measures:
 * - Stroke coverage
 * - Exact group matches
 * - False splits (ground truth group split into >= 2 regions)
 * - False merges (region includes strokes from >= 2 ground truth groups)
 * - Reading order correctness (pairwise concordance)
 */
export function evaluateSegmentationAgainstGroundTruth(
  regions: readonly PageOcrRegion[],
  groundTruth: OcrGroundTruthV1,
): SegmentationMetrics {
  const expectedGroups = groundTruth.expectedGroups;
  const allExpectedStrokes = new Set(expectedGroups.flatMap((g) => g.strokeIds));
  const totalExpectedStrokes = allExpectedStrokes.size;

  const predictedStrokeToRegion = new Map<string, number>();
  const duplicateStrokeIds: string[] = [];
  let totalPredictedStrokes = 0;

  for (let rIdx = 0; rIdx < regions.length; rIdx++) {
    for (const stroke of regions[rIdx].strokes) {
      totalPredictedStrokes++;
      if (predictedStrokeToRegion.has(stroke.id)) {
        duplicateStrokeIds.push(stroke.id);
      } else {
        predictedStrokeToRegion.set(stroke.id, rIdx);
      }
    }
  }

  const missingStrokeIds = [...allExpectedStrokes].filter((id) => !predictedStrokeToRegion.has(id));
  const coveredExpectedStrokes = [...allExpectedStrokes].filter((id) => predictedStrokeToRegion.has(id)).length;
  const strokeCoverage = totalExpectedStrokes > 0 ? coveredExpectedStrokes / totalExpectedStrokes : 1;

  // 1. Group membership: Exact matches, False splits, False merges
  let exactGroupMatches = 0;
  let falseSplitCount = 0;

  const strokeToExpectedGroup = new Map<string, string>();
  for (const g of expectedGroups) {
    for (const sid of g.strokeIds) {
      strokeToExpectedGroup.set(sid, g.groupId);
    }

    const assignedRegionIndices = new Set<number>();
    for (const sid of g.strokeIds) {
      const rIdx = predictedStrokeToRegion.get(sid);
      if (rIdx !== undefined) assignedRegionIndices.add(rIdx);
    }

    if (assignedRegionIndices.size > 1) {
      falseSplitCount++;
    }

    // Check exact match
    if (assignedRegionIndices.size === 1) {
      const rIdx = [...assignedRegionIndices][0];
      const regionStrokes = regions[rIdx].strokes.map((s) => s.id);
      if (
        regionStrokes.length === g.strokeIds.length &&
        g.strokeIds.every((id) => regionStrokes.includes(id))
      ) {
        exactGroupMatches++;
      }
    }
  }

  // False merges: A predicted region containing strokes from >= 2 different expected groups
  let falseMergeCount = 0;
  for (const reg of regions) {
    const representedGroups = new Set<string>();
    for (const s of reg.strokes) {
      const gId = strokeToExpectedGroup.get(s.id);
      if (gId) representedGroups.add(gId);
    }
    if (representedGroups.size > 1) {
      falseMergeCount++;
    }
  }

  const totalExpectedGroups = expectedGroups.length;
  const totalPredictedRegions = regions.length;

  const groupPrecision = totalPredictedRegions > 0 ? exactGroupMatches / totalPredictedRegions : 0;
  const groupRecall = totalExpectedGroups > 0 ? exactGroupMatches / totalExpectedGroups : 0;
  const groupF1 =
    groupPrecision + groupRecall > 0
      ? (2 * groupPrecision * groupRecall) / (groupPrecision + groupRecall)
      : 0;

  // 2. Reading order correctness (Pairwise concordance)
  let readingOrderCorrectness: number | null = null;
  let readingOrderComparablePairs = 0;
  if (groundTruth.expectedReadingOrder && groundTruth.expectedReadingOrder.length > 1) {
    const orderMap = new Map<string, number>();
    groundTruth.expectedReadingOrder.forEach((gId, idx) => orderMap.set(gId, idx));

    // Determine representative group for each predicted region
    const predictedGroupSequence: string[] = [];
    for (const reg of regions) {
      const counts = new Map<string, number>();
      for (const s of reg.strokes) {
        const gId = strokeToExpectedGroup.get(s.id);
        if (gId && orderMap.has(gId)) {
          counts.set(gId, (counts.get(gId) ?? 0) + 1);
        }
      }
      let topGroup: string | null = null;
      let maxCount = 0;
      for (const [gid, cnt] of counts) {
        if (cnt > maxCount) {
          topGroup = gid;
          maxCount = cnt;
        }
      }
      if (topGroup) predictedGroupSequence.push(topGroup);
    }

    if (predictedGroupSequence.length > 1) {
      let concordant = 0;
      let totalPairs = 0;
      for (let i = 0; i < predictedGroupSequence.length; i++) {
        for (let j = i + 1; j < predictedGroupSequence.length; j++) {
          const expectedI = orderMap.get(predictedGroupSequence[i])!;
          const expectedJ = orderMap.get(predictedGroupSequence[j])!;
          // Repeated references to the same GT group do not provide an
          // independent ordered pair.
          if (predictedGroupSequence[i] === predictedGroupSequence[j]) continue;
          totalPairs++;
          if (expectedI < expectedJ) concordant++;
        }
      }
      readingOrderComparablePairs = totalPairs;
      if (totalPairs > 0) readingOrderCorrectness = concordant / totalPairs;
    }
  }

  return {
    totalExpectedStrokes,
    totalPredictedStrokes,
    strokeCoverage,
    missingStrokeIds,
    duplicateStrokeIds,
    totalExpectedGroups,
    totalPredictedRegions,
    exactGroupMatches,
    falseSplitCount,
    falseMergeCount,
    groupPrecision,
    groupRecall,
    groupF1,
    readingOrderCorrectness,
    readingOrderComparablePairs,
  };
}
