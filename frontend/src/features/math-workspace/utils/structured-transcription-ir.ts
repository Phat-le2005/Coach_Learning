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

export interface BlockedProjectionUnit {
  unitId: string;
  kind: ContentUnitKind;
  sourceStrokeIds: string[];
  reason: string;
}

export interface LegacyStepProjection {
  irSchemaVersion: "1.0";
  projectedStepCount: number;
  steps: LegacyStepProjectionItem[];
  allUnitsMapped: boolean;
  isProjectionBlocked: boolean;
  blockedUnits: BlockedProjectionUnit[];
  warnings: string[];
  note: string;
}

// ============================================================================
// 2. Helper Functions & Geometry (P0.1 Fixed)
// ============================================================================

/**
 * Computes exact normalized bounding box across all points in strokes.
 * P0.1 FIX: Corrected comparison `p.x > right` (was erroneously checking `p.y > right`).
 */
export function computeBounds(strokes: readonly InkStroke[]): InkBounds {
  if (strokes.length === 0) {
    return { left: 0, top: 0, right: 0, bottom: 0 };
  }
  let left = Infinity, right = -Infinity, top = Infinity, bottom = -Infinity;
  for (const s of strokes) {
    for (const p of s.points) {
      if (p.x < left) left = p.x;
      if (p.x > right) right = p.x;
      if (p.y < top) top = p.y;
      if (p.y > bottom) bottom = p.y;
    }
  }
  return { left, right, top, bottom };
}

// ============================================================================
// 3. Construction & Assembly (P0.2 Fixed)
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
 * P0.2 FIX: Guarantees 100% pen stroke conservation: any stroke omitted by segmentation
 * or structural grouping is captured into an orphan/residual ContentUnit so zero strokes are dropped.
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

  // 4. P0.2 Conservation Safety Net:
  // Catch any active pen strokes that were NOT in any region or structural unit!
  const orphanPenStrokes = penStrokes.filter((s) => !usedStrokeIds.has(s.id));
  if (orphanPenStrokes.length > 0) {
    for (const s of orphanPenStrokes) {
      const b = computeBounds([s]);
      units.push({
        id: `orphan-${s.id}`,
        pageIndex,
        kind: "UNKNOWN",
        sourceRegionIds: [],
        sourceStrokeIds: [s.id],
        readingOrder: 0,
        rawRecognition: null,
        approvedContent: null,
        recognitionStatus: "UNRESOLVED",
        reviewStatus: "NEEDS_REVIEW",
        isManuallyCorrected: false,
        bounds: b,
        reasons: ["Orphan pen stroke omitted by segmentation"],
      });
      usedStrokeIds.add(s.id);
    }
  }

  // 5. Sort top-level content units in natural spatial reading order (top-to-bottom, left-to-right)
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
// 4. Mutation & Review Functions (P0.4 Approval Consistency)
// ============================================================================

/** Computes whether the entire IR is APPROVED based on all units and parent-child consistency */
function computeIrApprovalStatus(units: readonly ContentUnit[]): TranscriptionReviewStatus {
  if (units.length === 0) return "NEEDS_REVIEW";

  // Check parent-child consistency
  for (const u of units) {
    if (u.childIds && u.childIds.length > 0) {
      const children = units.filter((c) => u.childIds?.includes(c.id));
      const allChildrenApproved = children.every((c) => c.reviewStatus === "APPROVED");
      // If parent is marked APPROVED but any child is not APPROVED, the IR is NOT approved!
      if (u.reviewStatus === "APPROVED" && !allChildrenApproved) {
        return "NEEDS_REVIEW";
      }
    }
    if (u.reviewStatus !== "APPROVED") {
      return "NEEDS_REVIEW";
    }
  }
  return "APPROVED";
}

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
    reviewStatus: computeIrApprovalStatus(nextUnits),
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
    reviewStatus: computeIrApprovalStatus(nextUnits),
    provenance: { ...ir.provenance, updatedAt: new Date().toISOString() },
  };
}

/**
 * Human confirmation: approves a content unit's transcription.
 * P0.4 FIX: Enforces hierarchical parent-child approval consistency:
 * - A parent STRUCTURE cannot be approved unless ALL of its children are already APPROVED.
 * - When an atomic unit or child is approved, verifies non-empty content.
 */
export function approveContentUnit(
  ir: SolutionTranscriptionIR,
  unitId: string,
): SolutionTranscriptionIR {
  const targetUnit = ir.contentUnits.find((u) => u.id === unitId);
  if (!targetUnit) {
    throw new Error(`TRANSCRIPTION_UNIT_NOT_FOUND: Unit '${unitId}' does not exist`);
  }

  // P0.4 Check: if parent has children, verify that ALL children are already approved!
  if (targetUnit.childIds && targetUnit.childIds.length > 0) {
    const children = ir.contentUnits.filter((c) => targetUnit.childIds?.includes(c.id));
    const unapprovedChild = children.find((c) => c.reviewStatus !== "APPROVED");
    if (unapprovedChild) {
      throw new Error(
        `TRANSCRIPTION_PARENT_CHILDREN_UNAPPROVED: Cannot approve parent '${unitId}' because child '${unapprovedChild.id}' is not yet approved`,
      );
    }
  } else {
    // Atomic unit / child unit must have non-empty content
    const content = targetUnit.approvedContent ?? targetUnit.rawRecognition;
    if (!content || !content.trim()) {
      throw new Error(`TRANSCRIPTION_UNIT_EMPTY_CONTENT: Cannot approve unit '${unitId}' without content`);
    }
  }

  const nextUnits = ir.contentUnits.map((u) => {
    if (u.id !== unitId) return u;
    const content = u.approvedContent ?? u.rawRecognition ?? "";
    return {
      ...u,
      approvedContent: content.trim() || null,
      reviewStatus: "APPROVED" as const,
    };
  });

  const approvedCount = nextUnits.filter((u) => u.reviewStatus === "APPROVED").length;
  return {
    ...ir,
    contentUnits: nextUnits,
    approvedUnitCount: approvedCount,
    reviewStatus: computeIrApprovalStatus(nextUnits),
    provenance: { ...ir.provenance, updatedAt: new Date().toISOString() },
  };
}

// ============================================================================
// 5. Evaluator Handoff Projection (P0.3 Fixed: Preview-Only & Blocked Safety)
// ============================================================================

/**
 * Explicitly projects an approved SolutionTranscriptionIR into the legacy SolutionStepDraft
 * API format accepted by Phát's Mathematical Evaluator (Module G).
 *
 * P0.3 FIXES:
 * 1. PREVIEW-ONLY: Does NOT dictate that 1 ContentUnit = 1 GradingStep.
 * 2. NO PLACEHOLDERS: Never generates fake text like "(UNKNOWN content unit)".
 * 3. BLOCKED SAFETY: Unapproved, UNRESOLVED, or unmappable units are NOT emitted as valid steps.
 *    Instead, they are recorded in `blockedUnits` with reasons, and `isProjectionBlocked = true`.
 */
export function projectTranscriptionToLegacySteps(
  ir: SolutionTranscriptionIR,
): LegacyStepProjection {
  const steps: LegacyStepProjectionItem[] = [];
  const warnings: string[] = [];
  const unmappedUnitIds: string[] = [];
  const blockedUnits: BlockedProjectionUnit[] = [];

  // Consider only top-level content units (descendants are represented in their parent)
  const topUnits = ir.contentUnits
    .filter((u) => !u.id.startsWith("sub-"))
    .sort((a, b) => a.readingOrder - b.readingOrder);

  let targetOrder = 1;

  for (const unit of topUnits) {
    // P0.3 Check 1: Unit must be APPROVED by human review
    if (unit.reviewStatus !== "APPROVED") {
      blockedUnits.push({
        unitId: unit.id,
        kind: unit.kind,
        sourceStrokeIds: [...unit.sourceStrokeIds],
        reason: `Unit '${unit.id}' is not APPROVED (current status: ${unit.reviewStatus})`,
      });
      warnings.push(`Unit '${unit.id}' skipped from legacy steps: not APPROVED`);
      continue;
    }

    // P0.3 Check 2: Unit must not be UNRESOLVED
    if (unit.recognitionStatus === "UNRESOLVED") {
      blockedUnits.push({
        unitId: unit.id,
        kind: unit.kind,
        sourceStrokeIds: [...unit.sourceStrokeIds],
        reason: `Unit '${unit.id}' has UNRESOLVED recognition status`,
      });
      warnings.push(`Unit '${unit.id}' skipped from legacy steps: UNRESOLVED`);
      continue;
    }

    // P0.3 Check 3: Unit of kind UNKNOWN cannot be represented by legacy StepKind without guessing
    if (unit.kind === "UNKNOWN") {
      unmappedUnitIds.push(unit.id);
      blockedUnits.push({
        unitId: unit.id,
        kind: unit.kind,
        sourceStrokeIds: [...unit.sourceStrokeIds],
        reason: `Unit '${unit.id}' has kind UNKNOWN; cannot be projected without guessing StepKind`,
      });
      warnings.push(`Unit '${unit.id}' of kind UNKNOWN blocked from projection (requires human rubric mapping)`);
      continue;
    }

    const content = (unit.approvedContent ?? unit.rawRecognition ?? "").trim();
    if (!content) {
      blockedUnits.push({
        unitId: unit.id,
        kind: unit.kind,
        sourceStrokeIds: [...unit.sourceStrokeIds],
        reason: `Unit '${unit.id}' has empty content`,
      });
      warnings.push(`Unit '${unit.id}' skipped from legacy steps: empty content`);
      continue;
    }

    let projectedKind: StepKind = "CUSTOM";
    let contentLatex: string | null = null;
    let explanationText: string | null = null;
    const unmappedFields: string[] = [];
    const itemWarnings: string[] = [];

    if (unit.kind === "TEXT") {
      projectedKind = "EXPLANATION";
      explanationText = content;
      unmappedFields.push("kind=TEXT (mapped to StepKind EXPLANATION)");
    } else if (unit.kind === "MATH" || unit.kind === "STRUCTURE") {
      contentLatex = content;
      const classification = classifyMathStep({ contentLatex: content, explanationText: "" });
      if (classification.status === "DETERMINED") {
        projectedKind = classification.predictedType;
      } else {
        projectedKind = "CUSTOM";
        itemWarnings.push("StepKind unverified by heuristic; defaulted to StepKind.CUSTOM");
      }
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

  const isProjectionBlocked = blockedUnits.length > 0;

  return {
    irSchemaVersion: ir.schemaVersion,
    projectedStepCount: steps.length,
    steps,
    allUnitsMapped: unmappedUnitIds.length === 0,
    isProjectionBlocked,
    blockedUnits,
    warnings,
    note: "Preview-only projection. Does not dictate that 1 ContentUnit = 1 GradingStep. Evaluator rubric boundaries require explicit agreement with Module G (Phát).",
  };
}

// ============================================================================
// 6. Comprehensive Validation (P0.5 Fixed)
// ============================================================================

/**
 * Validates untrusted data as a strictly well-formed SolutionTranscriptionIR v1.0.
 * P0.5 FIX: Checks:
 * 1. Root object, schemaVersion '1.0', sourceKind 'INK'.
 * 2. Unique unit IDs across all units.
 * 3. Finite bounds within canvas bounds [-0.5, 1.5] with left <= right and top <= bottom.
 * 4. Non-empty string sourceStrokeIds.
 * 5. Reading order non-negative integer.
 * 6. Parent-child consistency: referenced childIds exist in contentUnits, child strokes are subset of parent strokes.
 * 7. Approval consistency: if unit is APPROVED, approvedContent must be non-empty string.
 * 8. If ir.reviewStatus is APPROVED, every unit must be APPROVED and parent-child consistent.
 */
export function validateSolutionTranscriptionIR(data: unknown): SolutionTranscriptionIR {
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    throw new Error("INVALID_IR_ROOT: Root must be a non-null JSON object");
  }

  const ir = data as Record<string, unknown>;
  if (ir.schemaVersion !== "1.0") {
    throw new Error(`UNSUPPORTED_IR_VERSION: Expected '1.0', got '${String(ir.schemaVersion)}'`);
  }

  if (ir.sourceKind !== "INK") {
    throw new Error(`UNSUPPORTED_IR_SOURCE_KIND: Expected 'INK', got '${String(ir.sourceKind)}'`);
  }

  if (!Array.isArray(ir.contentUnits)) {
    throw new Error("INVALID_IR_CONTENT_UNITS: contentUnits must be an array");
  }

  const seenUnitIds = new Set<string>();
  const unitsById = new Map<string, ContentUnit>();

  for (let i = 0; i < ir.contentUnits.length; i++) {
    const u = ir.contentUnits[i] as ContentUnit;
    if (typeof u !== "object" || u === null) {
      throw new Error(`INVALID_UNIT: Unit at index ${i} is not an object`);
    }

    if (typeof u.id !== "string" || !u.id.trim()) {
      throw new Error(`INVALID_UNIT_ID: Unit at index ${i} has empty or non-string id`);
    }

    if (seenUnitIds.has(u.id)) {
      throw new Error(`DUPLICATE_UNIT_ID: Unit id '${u.id}' is duplicated`);
    }
    seenUnitIds.add(u.id);
    unitsById.set(u.id, u);

    // Validate bounds
    const b = u.bounds;
    if (!b || typeof b.left !== "number" || typeof b.right !== "number" || typeof b.top !== "number" || typeof b.bottom !== "number") {
      throw new Error(`INVALID_UNIT_BOUNDS: Unit '${u.id}' has invalid bounds structure`);
    }
    if (!Number.isFinite(b.left) || !Number.isFinite(b.right) || !Number.isFinite(b.top) || !Number.isFinite(b.bottom)) {
      throw new Error(`NON_FINITE_UNIT_BOUNDS: Unit '${u.id}' bounds contain NaN or Infinity`);
    }
    if (b.left > b.right || b.top > b.bottom) {
      throw new Error(`MALFORMED_UNIT_BOUNDS: Unit '${u.id}' bounds inverted (left > right or top > bottom)`);
    }

    // Validate strokes
    if (!Array.isArray(u.sourceStrokeIds) || u.sourceStrokeIds.length === 0) {
      throw new Error(`EMPTY_UNIT_STROKES: Unit '${u.id}' has no sourceStrokeIds`);
    }
    for (const sid of u.sourceStrokeIds) {
      if (typeof sid !== "string" || !sid.trim()) {
        throw new Error(`INVALID_STROKE_ID: Unit '${u.id}' has invalid stroke id '${String(sid)}'`);
      }
    }

    // Validate reading order
    if (typeof u.readingOrder !== "number" || !Number.isInteger(u.readingOrder) || u.readingOrder < 0) {
      throw new Error(`INVALID_READING_ORDER: Unit '${u.id}' readingOrder must be non-negative integer`);
    }

    // Validate approval consistency
    if (u.reviewStatus === "APPROVED") {
      if (!u.approvedContent || typeof u.approvedContent !== "string" || !u.approvedContent.trim()) {
        throw new Error(`APPROVED_UNIT_EMPTY_CONTENT: Unit '${u.id}' is APPROVED but has empty approvedContent`);
      }
    }
  }

  // Check parent-child integrity
  for (const [, u] of unitsById) {
    if (u.childIds && u.childIds.length > 0) {
      const parentStrokeSet = new Set(u.sourceStrokeIds);
      for (const chId of u.childIds) {
        const ch = unitsById.get(chId);
        if (!ch) {
          throw new Error(`MISSING_CHILD_UNIT: Parent '${u.id}' references non-existent child '${chId}'`);
        }
        for (const csId of ch.sourceStrokeIds) {
          if (!parentStrokeSet.has(csId)) {
            throw new Error(`CHILD_STROKE_NOT_IN_PARENT: Child '${chId}' stroke '${csId}' not in parent '${u.id}'`);
          }
        }
      }
    }
  }

  // Check overall IR approval consistency
  if (ir.reviewStatus === "APPROVED") {
    for (const [, u] of unitsById) {
      if (u.reviewStatus !== "APPROVED") {
        throw new Error(`INCONSISTENT_IR_APPROVAL: IR is APPROVED but unit '${u.id}' is ${u.reviewStatus}`);
      }
    }
  }

  return data as SolutionTranscriptionIR;
}
