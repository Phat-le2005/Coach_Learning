import type { InkStroke, StepKind } from "@/lib/api/contracts";
import type { PageOcrRegion, InkBounds } from "./page-ocr";
import type { StructureCandidate } from "./structural-candidate-engine";
import type { IntegralExpressionUnit } from "./expression-reconstruction";
import { classifyMathStep } from "./ocr-classifier";
import { getOcrPenStrokes } from "./ocr-ink";

// ============================================================================
// 1. Data Contracts: Structured Transcription IR v1.0
// ============================================================================

export type ContentUnitKind = "MATH" | "TEXT" | "STRUCTURE" | "UNKNOWN";
export type RecognitionStatus = "RECOGNIZED" | "UNRESOLVED" | "MANUALLY_CORRECTED";
export type UnitReviewStatus = "NEEDS_REVIEW" | "APPROVED" | "SKIPPED";
export type TranscriptionReviewStatus = "NEEDS_REVIEW" | "APPROVED" | "REJECTED";

/**
 * A logical unit of mathematical or textual solution content.
 * An expression unit can span multiple geometric regions (e.g. integral with limits, fraction).
 * 1 Region ≠ 1 ContentUnit ≠ 1 GradingStep.
 */
export interface ContentUnit {
  id: string;
  pageIndex: number;
  kind: ContentUnitKind;
  sourceRegionIds: string[];
  sourceStrokeIds: string[];
  readingOrder: number;
  rawRecognition: string | null;
  approvedContent: string | null;
  recognitionStatus: RecognitionStatus;
  reviewStatus: UnitReviewStatus;
  isManuallyCorrected: boolean;
  bounds: InkBounds;
  childIds?: string[];
  reasons: string[];
}

export interface SolutionTranscriptionIR {
  schemaVersion: "1.0";
  attemptId?: string;
  pageIndex: number;
  sourceKind: "INK";
  sourceRevision: number;
  contentUnits: ContentUnit[];
  reviewStatus: TranscriptionReviewStatus;
  rawStrokeCount: number;
  recognizedUnitCount: number;
  approvedUnitCount: number;
  provenance: {
    createdAt: string;
    updatedAt: string;
    algorithm: string;
  };
}

export interface LegacyStepProjectionItem {
  targetStepOrder: number;
  sourceUnitIds: string[];
  step_type: StepKind;
  content_latex: string | null;
  explanation_text: string | null;
  unmappedFields: string[];
  warnings: string[];
}

export interface LegacyStepProjection {
  irSchemaVersion: "1.0";
  projectedStepCount: number;
  steps: LegacyStepProjectionItem[];
  allUnitsMapped: boolean;
  unmappedUnitIds: string[];
  warnings: string[];
}

// ============================================================================
// 2. Helper Functions & Geometry
// ============================================================================

function computeBounds(strokes: readonly InkStroke[]): InkBounds {
  if (strokes.length === 0) {
    return { left: 0, top: 0, right: 0, bottom: 0 };
  }
  let left = Infinity, right = -Infinity, top = Infinity, bottom = -Infinity;
  for (const s of strokes) {
    for (const p of s.points) {
      if (p.x < left) left = p.x;
      if (p.y > right) right = p.x;
      if (p.y < top) top = p.y;
      if (p.y > bottom) bottom = p.y;
    }
  }
  return { left, right, top, bottom };
}

// ============================================================================
// 3. Construction & Assembly
// ============================================================================

export interface BuildTranscriptionIrParams {
  pageIndex: number;
  strokes: readonly InkStroke[];
  regions: readonly PageOcrRegion[];
  structuralCandidates?: readonly StructureCandidate[];
  integralUnits?: readonly IntegralExpressionUnit[];
  attemptId?: string;
  sourceRevision?: number;
}

/**
 * Builds a structured SolutionTranscriptionIR from raw ink, segmentation regions,
 * and structural/expression proposals.
 * Preserves 100% of pen strokes and chronological / spatial reading order.
 */
export function buildStructuredTranscriptionIR(
  params: BuildTranscriptionIrParams,
): SolutionTranscriptionIR {
  const {
    pageIndex,
    strokes,
    regions,
    structuralCandidates = [],
    integralUnits = [],
    attemptId,
    sourceRevision = 1,
  } = params;

  const penStrokes = getOcrPenStrokes([...strokes]);
  const penById = new Map(penStrokes.map((s) => [s.id, s]));
  const usedStrokeIds = new Set<string>();
  const units: ContentUnit[] = [];

  // 1. Process Integral Expression Units first (spans limits + body)
  for (const intUnit of integralUnits) {
    const unitStrokes = intUnit.sourceStrokeIds.flatMap((id) => {
      const s = penById.get(id);
      return s ? [s] : [];
    });
    const overlappingRegionIds = regions
      .filter((r) => r.strokes.some((s) => intUnit.sourceStrokeIds.includes(s.id)))
      .map((r) => r.id);

    units.push({
      id: intUnit.id,
      pageIndex,
      kind: "MATH",
      sourceRegionIds: overlappingRegionIds,
      sourceStrokeIds: [...intUnit.sourceStrokeIds],
      readingOrder: 0,
      rawRecognition: null,
      approvedContent: null,
      recognitionStatus: "UNRESOLVED",
      reviewStatus: "NEEDS_REVIEW",
      isManuallyCorrected: false,
      bounds: { ...intUnit.bounds },
      reasons: [...intUnit.reasons],
    });

    for (const sid of intUnit.sourceStrokeIds) {
      usedStrokeIds.add(sid);
    }
  }

  // 2. Process Hierarchical Structural Candidates (SYSTEM, ALTERNATIVES, FRACTION)
  for (const cand of structuralCandidates) {
    if (cand.sourceStrokeIds.some((id) => usedStrokeIds.has(id))) {
      continue;
    }
    const overlappingRegionIds = regions
      .filter((r) => r.strokes.some((s) => cand.sourceStrokeIds.includes(s.id)))
      .map((r) => r.id);

    const childIds: string[] = [];
    if (cand.children && cand.children.length > 0) {
      for (const ch of cand.children) {
        const chUnitId = `sub-${ch.id}`;
        childIds.push(chUnitId);
        units.push({
          id: chUnitId,
          pageIndex,
          kind: "MATH",
          sourceRegionIds: overlappingRegionIds,
          sourceStrokeIds: [...ch.sourceStrokeIds],
          readingOrder: 0,
          rawRecognition: null,
          approvedContent: null,
          recognitionStatus: "UNRESOLVED",
          reviewStatus: "NEEDS_REVIEW",
          isManuallyCorrected: false,
          bounds: { ...ch.bounds },
          reasons: [...ch.reasons],
        });
      }
    }

    units.push({
      id: cand.id,
      pageIndex,
      kind: cand.kind === "FRACTION" ? "MATH" : "STRUCTURE",
      sourceRegionIds: overlappingRegionIds,
      sourceStrokeIds: [...cand.sourceStrokeIds],
      readingOrder: 0,
      rawRecognition: null,
      approvedContent: null,
      recognitionStatus: "UNRESOLVED",
      reviewStatus: "NEEDS_REVIEW",
      isManuallyCorrected: false,
      bounds: { ...cand.bounds },
      childIds: childIds.length > 0 ? childIds : undefined,
      reasons: [...cand.reasons],
    });

    for (const sid of cand.sourceStrokeIds) {
      usedStrokeIds.add(sid);
    }
  }

  // 3. Process Remaining Regions as Individual Content Units
  for (const reg of regions) {
    const unassignedStrokes = reg.strokes.filter((s) => !usedStrokeIds.has(s.id));
    if (unassignedStrokes.length === 0) continue;

    const unitBounds = computeBounds(unassignedStrokes);
    units.push({
      id: `unit-${reg.id}`,
      pageIndex,
      kind: "MATH",
      sourceRegionIds: [reg.id],
      sourceStrokeIds: unassignedStrokes.map((s) => s.id),
      readingOrder: 0,
      rawRecognition: null,
      approvedContent: null,
      recognitionStatus: "UNRESOLVED",
      reviewStatus: "NEEDS_REVIEW",
      isManuallyCorrected: false,
      bounds: unitBounds,
      reasons: ["Baseline segmentation region"],
    });

    for (const s of unassignedStrokes) {
      usedStrokeIds.add(s.id);
    }
  }

  // 4. Sort top-level content units in natural spatial reading order (top-to-bottom, left-to-right)
  const topLevel = units.filter((u) => !u.id.startsWith("sub-"));
  topLevel.sort((a, b) => a.bounds.top - b.bounds.top || a.bounds.left - b.bounds.left);
  topLevel.forEach((u, idx) => {
    u.readingOrder = idx;
  });

  const now = new Date().toISOString();
  return {
    schemaVersion: "1.0",
    attemptId,
    pageIndex,
    sourceKind: "INK",
    sourceRevision,
    contentUnits: units,
    reviewStatus: "NEEDS_REVIEW",
    rawStrokeCount: penStrokes.length,
    recognizedUnitCount: 0,
    approvedUnitCount: 0,
    provenance: {
      createdAt: now,
      updatedAt: now,
      algorithm: "MathCanvas-OCR-V2-StructuredTranscription",
    },
  };
}

// ============================================================================
// 4. Mutation & Review Functions (Faithful & Non-destructive)
// ============================================================================

/**
 * Applies OCR engine output to a content unit.
 * CRITICAL INVARIANT: Re-running recognition NEVER overwrites student's manual corrections!
 */
export function applyOcrToContentUnit(
  ir: SolutionTranscriptionIR,
  unitId: string,
  rawLatex: string,
): SolutionTranscriptionIR {
  const nextUnits: ContentUnit[] = ir.contentUnits.map((u) => {
    if (u.id !== unitId) return u;
    // Protection: student manual correction is preserved
    const approvedContent = u.isManuallyCorrected ? u.approvedContent : u.approvedContent;
    const recognitionStatus: RecognitionStatus = u.isManuallyCorrected ? "MANUALLY_CORRECTED" : "RECOGNIZED";

    return {
      ...u,
      rawRecognition: rawLatex,
      approvedContent,
      recognitionStatus,
    };
  });

  const recognizedCount = nextUnits.filter((u) => u.rawRecognition !== null).length;
  return {
    ...ir,
    contentUnits: nextUnits,
    recognizedUnitCount: recognizedCount,
    provenance: { ...ir.provenance, updatedAt: new Date().toISOString() },
  };
}

/**
 * Records student manual edits to transcribed content.
 * Invalidates previous approval status while preserving kind and provenance.
 */
export function editContentUnit(
  ir: SolutionTranscriptionIR,
  unitId: string,
  changes: { content?: string; kind?: ContentUnitKind },
): SolutionTranscriptionIR {
  const nextUnits = ir.contentUnits.map((u) => {
    if (u.id !== unitId) return u;
    const newContent = changes.content !== undefined ? changes.content : (u.approvedContent ?? u.rawRecognition ?? "");
    const newKind = changes.kind ?? u.kind;

    return {
      ...u,
      kind: newKind,
      approvedContent: newContent,
      isManuallyCorrected: true,
      recognitionStatus: "MANUALLY_CORRECTED" as const,
      reviewStatus: "NEEDS_REVIEW" as const, // Invalidate approval on edit!
    };
  });

  const approvedCount = nextUnits.filter((u) => u.reviewStatus === "APPROVED").length;
  return {
    ...ir,
    contentUnits: nextUnits,
    approvedUnitCount: approvedCount,
    reviewStatus: approvedCount === nextUnits.length ? "APPROVED" : "NEEDS_REVIEW",
    provenance: { ...ir.provenance, updatedAt: new Date().toISOString() },
  };
}

/**
 * Human confirmation: approves a content unit's transcription.
 */
export function approveContentUnit(
  ir: SolutionTranscriptionIR,
  unitId: string,
): SolutionTranscriptionIR {
  const nextUnits = ir.contentUnits.map((u) => {
    if (u.id !== unitId) return u;
    const content = u.approvedContent ?? u.rawRecognition;
    if (!content || !content.trim()) {
      throw new Error("TRANSCRIPTION_UNIT_EMPTY_CONTENT: Cannot approve unit without content");
    }
    return {
      ...u,
      approvedContent: content.trim(),
      reviewStatus: "APPROVED" as const,
    };
  });

  const approvedCount = nextUnits.filter((u) => u.reviewStatus === "APPROVED").length;
  return {
    ...ir,
    contentUnits: nextUnits,
    approvedUnitCount: approvedCount,
    reviewStatus: approvedCount === nextUnits.length ? "APPROVED" : "NEEDS_REVIEW",
    provenance: { ...ir.provenance, updatedAt: new Date().toISOString() },
  };
}

// ============================================================================
// 5. Evaluator Handoff Projection (Legacy Adapter)
// ============================================================================

/**
 * Explicitly projects an approved SolutionTranscriptionIR into the legacy SolutionStepDraft
 * API format accepted by Phát's Mathematical Evaluator (Module G).
 * Does NOT swallow UNKNOWN/TEXT units; flags unmapped metadata transparently.
 */
export function projectTranscriptionToLegacySteps(
  ir: SolutionTranscriptionIR,
): LegacyStepProjection {
  const steps: LegacyStepProjectionItem[] = [];
  const warnings: string[] = [];
  const unmappedUnitIds: string[] = [];

  // Consider only top-level content units (descendants are represented in their parent)
  const topUnits = ir.contentUnits
    .filter((u) => !u.id.startsWith("sub-"))
    .sort((a, b) => a.readingOrder - b.readingOrder);

  let targetOrder = 1;

  for (const unit of topUnits) {
    const content = (unit.approvedContent ?? unit.rawRecognition ?? "").trim();
    const itemWarnings: string[] = [];
    const unmappedFields: string[] = [];

    if (unit.reviewStatus !== "APPROVED") {
      itemWarnings.push("Unit was not approved by human review before projection");
      warnings.push(`Unit '${unit.id}' projected without APPROVED status`);
    }

    if (unit.recognitionStatus === "UNRESOLVED") {
      itemWarnings.push("Unit recognition status is UNRESOLVED");
      warnings.push(`Unit '${unit.id}' has UNRESOLVED recognition status`);
    }

    let projectedKind: StepKind = "CUSTOM";
    let contentLatex: string | null = null;
    let explanationText: string | null = null;

    if (unit.kind === "TEXT") {
      projectedKind = "EXPLANATION";
      explanationText = content;
      unmappedFields.push("kind=TEXT (projected to StepKind EXPLANATION)");
    } else if (unit.kind === "MATH" || unit.kind === "STRUCTURE") {
      contentLatex = content;
      // Classify step using deterministic classifier
      const classification = classifyMathStep({ contentLatex: content, explanationText: "" });
      if (classification.status === "DETERMINED") {
        projectedKind = classification.predictedType;
      } else {
        projectedKind = "CUSTOM";
        itemWarnings.push("Mathematical classification unverified; defaulted to StepKind CUSTOM");
      }
    } else {
      // UNKNOWN
      unmappedUnitIds.push(unit.id);
      projectedKind = "EXPLANATION";
      explanationText = content || "(UNKNOWN content unit)";
      itemWarnings.push("Unit kind is UNKNOWN; projected to EXPLANATION to prevent silent drop");
      warnings.push(`Unit '${unit.id}' of kind UNKNOWN preserved as fallback EXPLANATION`);
    }

    steps.push({
      targetStepOrder: targetOrder++,
      sourceUnitIds: [unit.id, ...(unit.childIds ?? [])],
      step_type: projectedKind,
      content_latex: contentLatex,
      explanation_text: explanationText,
      unmappedFields,
      warnings: itemWarnings,
    });
  }

  return {
    irSchemaVersion: ir.schemaVersion,
    projectedStepCount: steps.length,
    steps,
    allUnitsMapped: unmappedUnitIds.length === 0,
    unmappedUnitIds,
    warnings,
  };
}

// ============================================================================
// 6. Validation
// ============================================================================

export function validateSolutionTranscriptionIR(data: unknown): SolutionTranscriptionIR {
  if (typeof data !== "object" || data === null) {
    throw new Error("INVALID_IR_ROOT: Root must be an object");
  }
  const ir = data as Record<string, unknown>;
  if (ir.schemaVersion !== "1.0") {
    throw new Error(`UNSUPPORTED_IR_VERSION: Expected '1.0', got '${String(ir.schemaVersion)}'`);
  }
  if (!Array.isArray(ir.contentUnits)) {
    throw new Error("INVALID_IR_CONTENT_UNITS: contentUnits must be an array");
  }
  return data as SolutionTranscriptionIR;
}
