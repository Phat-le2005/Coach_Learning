import type { InkStroke, StepKind } from "@/lib/api/contracts";
import type { PageOcrRegion, InkBounds } from "./page-ocr";
import type { StructureCandidate, StructureKind } from "./structural-candidate-engine";
import type { IntegralExpressionUnit } from "./expression-reconstruction";
import { getOcrPenStrokes } from "./ocr-ink";

export type ContentUnitKind = "MATH" | "TEXT" | "STRUCTURE" | "UNKNOWN";
export type RecognitionStatus = "RECOGNIZED" | "UNRESOLVED" | "MANUALLY_CORRECTED" | "NOT_APPLICABLE";
export type UnitReviewStatus = "NEEDS_REVIEW" | "APPROVED" | "SKIPPED";
export type TranscriptionReviewStatus = "NEEDS_REVIEW" | "APPROVED";

/** Region != ContentUnit != GradingStep. Containers confirm relations, never fake text. */
export interface ContentUnit {
  id: string;
  pageIndex: number;
  role: "ATOMIC" | "CONTAINER";
  kind: ContentUnitKind;
  structureKind: StructureKind | null;
  sourceRegionIds: string[];
  sourceStrokeIds: string[];
  /** Order among siblings, independent of storage order and drawing chronology. */
  readingOrder: number;
  rawRecognition: string | null;
  approvedContent: string | null;
  recognitionStatus: RecognitionStatus;
  reviewStatus: UnitReviewStatus;
  isManuallyCorrected: boolean;
  bounds: InkBounds;
  childIds: string[];
  reasons: string[];
}

/** Local TypeScript contract only; no backend migration or submission adapter. */
export interface SolutionTranscriptionIR {
  schemaVersion: "1.1";
  attemptId?: string;
  pageIndex: number;
  sourceKind: "INK";
  sourceRevision: number;
  /** Physical pen ink is serialized exactly once; units only reference IDs. */
  sourceSnapshot: { strokes: InkStroke[] };
  contentUnits: ContentUnit[];
  readingOrderStatus: "PROPOSED" | "AMBIGUOUS" | "CONFIRMED";
  readingOrderWarnings: string[];
  constructionWarnings: string[];
  reviewStatus: TranscriptionReviewStatus;
  rawStrokeCount: number;
  recognizedUnitCount: number;
  approvedUnitCount: number;
  provenance: { createdAt: string; updatedAt: string; algorithm: string };
}

export type ApprovedTranscriptionIR = SolutionTranscriptionIR & { reviewStatus: "APPROVED" };

/** Local handoff guard only. This does not produce a SolutionStepDraft. */
export function requireApprovedTranscriptionIR(data: unknown, sourceStrokes?: readonly InkStroke[]): ApprovedTranscriptionIR {
  const ir = validateSolutionTranscriptionIR(data, sourceStrokes);
  if (ir.reviewStatus !== "APPROVED") throw new Error("TRANSCRIPTION_REVIEW_INCOMPLETE");
  return ir as ApprovedTranscriptionIR;
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
  irSchemaVersion: "1.1";
  mode: "PREVIEW_ONLY";
  readyToSubmit: false;
  submitPayload: null;
  projectedStepCount: 0;
  steps: [];
  /** Lossless view of every unit, including TEXT and UNKNOWN. Not API steps. */
  candidateUnits: ContentUnit[];
  allUnitsMapped: false;
  isProjectionBlocked: true;
  blockedUnits: BlockedProjectionUnit[];
  warnings: string[];
  note: string;
}

export function computeBounds(strokes: readonly InkStroke[]): InkBounds {
  let left = Infinity, right = -Infinity, top = Infinity, bottom = -Infinity;
  for (const s of strokes) for (const p of s.points) {
    left = Math.min(left, p.x); right = Math.max(right, p.x);
    top = Math.min(top, p.y); bottom = Math.max(bottom, p.y);
  }
  return left === Infinity ? { left: 0, right: 0, top: 0, bottom: 0 } : { left, right, top, bottom };
}

function spatial(a: ContentUnit, b: ContentUnit): number {
  return a.bounds.top - b.bounds.top || a.bounds.left - b.bounds.left || a.id.localeCompare(b.id);
}

/** IDs carry no parent/root semantics. Callers validate untrusted graphs first. */
export function getRootContentUnits(units: readonly ContentUnit[]): ContentUnit[] {
  const children = new Set(units.flatMap((u) => u.childIds));
  return units.filter((u) => !children.has(u.id)).sort((a, b) => a.readingOrder - b.readingOrder);
}

export function getOrderedReviewUnits(units: readonly ContentUnit[]): { unit: ContentUnit; depth: number; parentId: string | null }[] {
  const byId = new Map(units.map((u) => [u.id, u]));
  const rows: { unit: ContentUnit; depth: number; parentId: string | null }[] = [];
  const visit = (u: ContentUnit, depth: number, parentId: string | null) => {
    rows.push({ unit: u, depth, parentId });
    u.childIds.map((id) => byId.get(id)!).sort((a, b) => a.readingOrder - b.readingOrder)
      .forEach((ch) => visit(ch, depth + 1, u.id));
  };
  getRootContentUnits(units).forEach((u) => visit(u, 0, null));
  return rows;
}

function ambiguousOrder(units: readonly ContentUnit[]): string[] {
  const warnings: string[] = [];
  const groups = [getRootContentUnits(units), ...units.filter((u) => u.role === "CONTAINER")
    .map((u) => units.filter((ch) => u.childIds.includes(ch.id)))];
  for (const group of groups) for (let i = 0; i < group.length; i++) for (let j = i + 1; j < group.length; j++) {
    const a = group[i], b = group[j];
    if (a.bounds.right < b.bounds.left || b.bounds.right < a.bounds.left) {
      warnings.push(`AMBIGUOUS_READING_ORDER: ${a.id}, ${b.id}; verify columns/order`);
    } else if (a.bounds.bottom >= b.bounds.top && b.bounds.bottom >= a.bounds.top) {
      warnings.push(`AMBIGUOUS_READING_ORDER: overlapping siblings ${a.id}, ${b.id}`);
    }
  }
  return warnings;
}

export interface BuildTranscriptionIrParams {
  pageIndex: number;
  strokes: readonly InkStroke[];
  regions: readonly PageOcrRegion[];
  structuralCandidates?: readonly StructureCandidate[];
  integralUnits?: readonly IntegralExpressionUnit[];
  attemptId?: string;
  sourceRevision?: number;
}

export function buildStructuredTranscriptionIR(params: BuildTranscriptionIrParams): SolutionTranscriptionIR {
  const { pageIndex, regions, structuralCandidates = [], integralUnits = [] } = params;
  const pen = structuredClone(getOcrPenStrokes([...params.strokes]));
  const byId = new Map(pen.map((s) => [s.id, s]));
  if (byId.size !== pen.length) throw new Error("DUPLICATE_SOURCE_STROKE");
  const units: ContentUnit[] = [], warnings: string[] = [];
  const unitIds = new Set<string>();
  const used = new Set<string>();
  const create = (id: string, ids: string[], kind: ContentUnitKind, reasons: string[], structureKind: StructureKind | null = null): ContentUnit => {
    if (unitIds.has(id)) throw new Error("DUPLICATE_UNIT_ID");
    unitIds.add(id);
    if (new Set(ids).size !== ids.length) throw new Error("DUPLICATE_STROKE_REFERENCE");
    if (ids.some((sid) => !byId.has(sid))) throw new Error("UNKNOWN_SOURCE_STROKE");
    const container = kind === "STRUCTURE";
    const u: ContentUnit = {
      id, pageIndex, role: container ? "CONTAINER" : "ATOMIC", kind, structureKind,
      sourceStrokeIds: [...ids], sourceRegionIds: [...new Set(regions.filter((r) => r.strokes.some((s) => ids.includes(s.id))).map((r) => r.id))],
      readingOrder: 0, rawRecognition: null, approvedContent: null,
      recognitionStatus: container ? "NOT_APPLICABLE" : "UNRESOLVED", reviewStatus: "NEEDS_REVIEW",
      isManuallyCorrected: false, bounds: computeBounds(ids.map((sid) => byId.get(sid)!)), childIds: [], reasons: [...reasons],
    };
    units.push(u);
    return u;
  };
  for (const proposal of integralUnits) {
    if (proposal.sourceStrokeIds.some((id) => used.has(id))) { warnings.push(`Overlapping integral proposal omitted: ${proposal.id}`); continue; }
    create(proposal.id, proposal.sourceStrokeIds, "MATH", proposal.reasons);
    proposal.sourceStrokeIds.forEach((id) => used.add(id));
  }
  const addCandidate = (c: StructureCandidate, child: boolean, ancestry: Set<StructureCandidate>): ContentUnit => {
    if (ancestry.has(c) || ancestry.size >= 64) throw new Error("CYCLIC_OR_TOO_DEEP_CANDIDATE");
    const path = new Set(ancestry).add(c);
    const kind = c.children.length || c.kind === "SYSTEM" || c.kind === "ALTERNATIVES" ? "STRUCTURE" : c.kind === "UNKNOWN" ? "UNKNOWN" : "MATH";
    const u = create(child ? `sub-${c.id}` : c.id, c.sourceStrokeIds, kind, c.reasons, kind === "STRUCTURE" ? c.kind : null);
    u.childIds = c.children.map((ch) => addCandidate(ch, true, path).id);
    return u;
  };
  for (const c of structuralCandidates) {
    if (c.sourceStrokeIds.some((id) => used.has(id))) { warnings.push(`Overlapping structure proposal omitted: ${c.id}`); continue; }
    addCandidate(c, false, new Set());
    c.sourceStrokeIds.forEach((id) => used.add(id));
  }
  for (const r of regions) {
    for (const s of r.strokes) {
      if (!byId.has(s.id) || JSON.stringify(s) !== JSON.stringify(byId.get(s.id))) throw new Error("REGION_SOURCE_MISMATCH");
    }
    const ids = r.strokes.map((s) => s.id).filter((id) => !used.has(id));
    if (ids.length) create(`unit-${r.id}`, ids, "MATH", ["Baseline segmentation region"]);
    ids.forEach((id) => used.add(id));
  }
  for (const s of pen.filter((s) => !used.has(s.id))) create(`orphan-${s.id}`, [s.id], "UNKNOWN", ["Orphan pen stroke omitted by segmentation"]);
  const assign = (group: ContentUnit[]) => group.sort(spatial).forEach((u, i) => { u.readingOrder = i; });
  assign(getRootContentUnits(units));
  units.forEach((u) => assign(units.filter((ch) => u.childIds.includes(ch.id))));
  const orderWarnings = ambiguousOrder(units);
  const now = new Date().toISOString();
  return validateSolutionTranscriptionIR({
    schemaVersion: "1.1", attemptId: params.attemptId, pageIndex, sourceKind: "INK", sourceRevision: params.sourceRevision ?? 1,
    sourceSnapshot: { strokes: pen }, contentUnits: units, readingOrderStatus: orderWarnings.length ? "AMBIGUOUS" : "PROPOSED",
    readingOrderWarnings: orderWarnings, constructionWarnings: warnings, reviewStatus: "NEEDS_REVIEW",
    rawStrokeCount: pen.length, recognizedUnitCount: 0, approvedUnitCount: 0,
    provenance: { createdAt: now, updatedAt: now, algorithm: "MathCanvas-OCR-V2-StructuredTranscription" },
  });
}

function approvalStatus(ir: SolutionTranscriptionIR): TranscriptionReviewStatus {
  return ir.contentUnits.length > 0 && ir.readingOrderStatus === "CONFIRMED" &&
    ir.contentUnits.every((u) => u.reviewStatus === "APPROVED") ? "APPROVED" : "NEEDS_REVIEW";
}

function finish(ir: SolutionTranscriptionIR, units: ContentUnit[], orderStatus = ir.readingOrderStatus): SolutionTranscriptionIR {
  const next = { ...ir, contentUnits: units, readingOrderStatus: orderStatus,
    approvedUnitCount: units.filter((u) => u.reviewStatus === "APPROVED").length,
    recognizedUnitCount: units.filter((u) => u.rawRecognition !== null).length,
    provenance: { ...ir.provenance, updatedAt: new Date().toISOString() } };
  next.reviewStatus = approvalStatus(next);
  return validateSolutionTranscriptionIR(next);
}

function target(ir: SolutionTranscriptionIR, id: string): ContentUnit {
  validateSolutionTranscriptionIR(ir);
  const u = ir.contentUnits.find((u) => u.id === id);
  if (!u) throw new Error(`TRANSCRIPTION_UNIT_NOT_FOUND: ${id}`);
  return u;
}

/** Invalidate every dependent ancestor, including nested containers. */
function invalidate(units: ContentUnit[], id: string): ContentUnit[] {
  const invalid = new Set([id]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const u of units) if (!invalid.has(u.id) && u.childIds.some((ch) => invalid.has(ch))) { invalid.add(u.id); changed = true; }
  }
  return units.map((u) => invalid.has(u.id) ? { ...u, reviewStatus: "NEEDS_REVIEW" } : u);
}

export function applyOcrToContentUnit(ir: SolutionTranscriptionIR, id: string, raw: string): SolutionTranscriptionIR {
  const u = target(ir, id);
  if (u.role !== "ATOMIC" || u.kind !== "MATH") throw new Error("COMER_REQUIRES_ATOMIC_MATH");
  if (!raw.trim()) throw new Error("EMPTY_OCR_RESULT");
  let units = ir.contentUnits.map((v) => v.id === id ? { ...v, rawRecognition: raw,
    recognitionStatus: u.isManuallyCorrected ? "MANUALLY_CORRECTED" as const : "RECOGNIZED" as const } : v);
  // Reruns are new evidence when manual content is frozen; otherwise re-review.
  if (!u.isManuallyCorrected && u.rawRecognition !== raw) {
    units = invalidate(units.map((v) => v.id === id ? { ...v, approvedContent: null } : v), id);
  }
  return finish(ir, units);
}

export function editContentUnit(ir: SolutionTranscriptionIR, id: string, changes: { content?: string; kind?: ContentUnitKind }): SolutionTranscriptionIR {
  const u = target(ir, id);
  if (u.role !== "ATOMIC" || changes.kind === "STRUCTURE") throw new Error("CONTAINER_RELATION_REQUIRES_STRUCTURE_REVIEW");
  const content = changes.content ?? u.approvedContent ?? u.rawRecognition ?? "";
  return finish(ir, invalidate(ir.contentUnits.map((v) => v.id === id ? { ...v,
    kind: changes.kind ?? v.kind, approvedContent: content, isManuallyCorrected: true,
    recognitionStatus: "MANUALLY_CORRECTED" as const } : v), id));
}

export function approveContentUnit(ir: SolutionTranscriptionIR, id: string): SolutionTranscriptionIR {
  const u = target(ir, id);
  if (u.role === "CONTAINER") {
    if (u.structureKind === "UNKNOWN" || ir.contentUnits.some((ch) => u.childIds.includes(ch.id) && ch.reviewStatus !== "APPROVED")) {
      throw new Error("TRANSCRIPTION_PARENT_CHILDREN_UNAPPROVED: review children and relation first");
    }
  } else if (!(u.approvedContent ?? u.rawRecognition)?.trim() || u.recognitionStatus === "UNRESOLVED") {
    throw new Error("TRANSCRIPTION_UNIT_EMPTY_CONTENT");
  }
  return finish(ir, ir.contentUnits.map((v) => v.id === id ? { ...v, reviewStatus: "APPROVED",
    approvedContent: u.role === "CONTAINER" ? null : (u.approvedContent ?? u.rawRecognition)!.trim() } : v));
}

/** Explicit relation correction, not mathematical inference. UNKNOWN cannot be confirmed. */
export function editContainerRelation(ir: SolutionTranscriptionIR, id: string, relation: StructureKind): SolutionTranscriptionIR {
  const u = target(ir, id);
  if (u.role !== "CONTAINER") throw new Error("NOT_A_CONTAINER");
  return finish(ir, invalidate(ir.contentUnits.map((v) => v.id === id ? { ...v, structureKind: relation } : v), id));
}

export function setSiblingReadingOrder(ir: SolutionTranscriptionIR, parentId: string | null, orderedIds: string[]): SolutionTranscriptionIR {
  validateSolutionTranscriptionIR(ir);
  const siblings = parentId === null ? getRootContentUnits(ir.contentUnits) : target(ir, parentId).childIds.map((id) => target(ir, id));
  if (orderedIds.length !== siblings.length || new Set(orderedIds).size !== orderedIds.length || siblings.some((u) => !orderedIds.includes(u.id))) throw new Error("INVALID_ORDER_PERMUTATION");
  let units = ir.contentUnits.map((u) => orderedIds.includes(u.id) ? { ...u, readingOrder: orderedIds.indexOf(u.id) } : u);
  if (parentId !== null) units = invalidate(units, parentId);
  const status = ambiguousOrder(units).length ? "AMBIGUOUS" : "PROPOSED";
  return finish(ir, units, status);
}

export function confirmTranscriptionReadingOrder(ir: SolutionTranscriptionIR): SolutionTranscriptionIR {
  validateSolutionTranscriptionIR(ir);
  return finish(ir, ir.contentUnits, "CONFIRMED");
}

/** No agreed Module G boundary mapping exists. Never emit a partial submission-shaped list. */
export function projectTranscriptionToLegacySteps(ir: SolutionTranscriptionIR): LegacyStepProjection {
  validateSolutionTranscriptionIR(ir);
  return {
    irSchemaVersion: ir.schemaVersion, mode: "PREVIEW_ONLY", readyToSubmit: false, submitPayload: null,
    projectedStepCount: 0, steps: [], candidateUnits: structuredClone(getOrderedReviewUnits(ir.contentUnits).map((r) => r.unit)),
    allUnitsMapped: false, isProjectionBlocked: true,
    blockedUnits: ir.contentUnits.map((u) => ({ unitId: u.id, kind: u.kind, sourceStrokeIds: [...u.sourceStrokeIds],
      reason: u.reviewStatus !== "APPROVED" ? "TRANSCRIPTION_NOT_APPROVED" : u.kind === "UNKNOWN" ? "UNKNOWN_REQUIRES_EXPLICIT_MAPPING" : "GRADING_BOUNDARIES_NOT_DEFINED" })),
    warnings: ["BLOCKED: Module G must explicitly define GradingStep boundaries and StepKind.",
      "Legacy SolutionStepDraft cannot preserve hierarchy, UNKNOWN, source snapshot, reading order uncertainty or review provenance.",
      ...(ir.reviewStatus !== "APPROVED" ? ["Transcription/order review is incomplete."] : [])],
    note: "Preview only. No evaluator payload, automatic StepKind, or ContentUnit-to-GradingStep mapping. Contract proposal awaiting Phát review.",
  };
}

function fail(code: string): never { throw new Error(code); }
function strings(value: unknown, code: string, unique = false): asserts value is string[] {
  if (!Array.isArray(value) || value.some((s) => typeof s !== "string" || !s.trim())) fail(code);
  if (unique && new Set(value).size !== value.length) fail(code);
}

/** Validate JSON, graph, coverage, sibling ownership, approval and derived counters together. */
export function validateSolutionTranscriptionIR(data: unknown, sourceStrokes?: readonly InkStroke[]): SolutionTranscriptionIR {
  if (!data || typeof data !== "object" || Array.isArray(data)) fail("INVALID_IR_ROOT");
  const ir = data as SolutionTranscriptionIR;
  if (ir.schemaVersion !== "1.1") fail("UNSUPPORTED_IR_VERSION");
  if (ir.sourceKind !== "INK") fail("UNSUPPORTED_IR_SOURCE_KIND");
  if (!Number.isInteger(ir.pageIndex) || ir.pageIndex < 0 || !Number.isInteger(ir.sourceRevision) || ir.sourceRevision < 1) fail("INVALID_SOURCE_IDENTITY");
  if (ir.attemptId !== undefined && (typeof ir.attemptId !== "string" || !ir.attemptId.trim())) fail("INVALID_ATTEMPT_ID");
  if (!ir.provenance || typeof ir.provenance.createdAt !== "string" || typeof ir.provenance.updatedAt !== "string" ||
    typeof ir.provenance.algorithm !== "string" || !ir.provenance.algorithm.trim() ||
    !Number.isFinite(Date.parse(ir.provenance.createdAt)) || !Number.isFinite(Date.parse(ir.provenance.updatedAt))) fail("INVALID_PROVENANCE");
  strings(ir.readingOrderWarnings, "INVALID_ORDER_WARNINGS"); strings(ir.constructionWarnings, "INVALID_CONSTRUCTION_WARNINGS");
  if (!["PROPOSED", "AMBIGUOUS", "CONFIRMED"].includes(ir.readingOrderStatus)) fail("INVALID_ORDER_STATUS");
  if (!Array.isArray(ir.contentUnits) || !Array.isArray(ir.sourceSnapshot?.strokes)) fail("INVALID_IR_CONTENT_UNITS_OR_SNAPSHOT");
  const source = new Map<string, InkStroke>();
  for (const s of ir.sourceSnapshot.strokes) {
    if (!s || typeof s.id !== "string" || !s.id.trim() || s.tool !== "PEN" || !Array.isArray(s.points) || !s.points.length ||
      !Number.isFinite(s.width) || s.width < 0.25 || s.width > 24 || typeof s.color !== "string" || !/^#[0-9a-f]{6}$/i.test(s.color) ||
      s.points.some((p) => !p || !Number.isFinite(p.x) || !Number.isFinite(p.y) || !Number.isFinite(p.pressure) ||
        p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1 || p.pressure < 0 || p.pressure > 1)) fail("INVALID_SOURCE_STROKE");
    if (source.has(s.id)) fail("DUPLICATE_SOURCE_STROKE");
    source.set(s.id, s);
  }
  if (sourceStrokes && JSON.stringify(getOcrPenStrokes([...sourceStrokes])) !== JSON.stringify(ir.sourceSnapshot.strokes)) fail("SOURCE_SNAPSHOT_MISMATCH");
  const byId = new Map<string, ContentUnit>();
  for (const u of ir.contentUnits) {
    if (!u || typeof u !== "object" || typeof u.id !== "string" || !u.id.trim()) fail("INVALID_UNIT_ID");
    if (byId.has(u.id)) fail("DUPLICATE_UNIT_ID"); byId.set(u.id, u);
    if (u.pageIndex !== ir.pageIndex) fail("UNIT_PAGE_MISMATCH");
    if (!["MATH", "TEXT", "STRUCTURE", "UNKNOWN"].includes(u.kind) || !["ATOMIC", "CONTAINER"].includes(u.role) ||
      !["RECOGNIZED", "UNRESOLVED", "MANUALLY_CORRECTED", "NOT_APPLICABLE"].includes(u.recognitionStatus) ||
      !["NEEDS_REVIEW", "APPROVED", "SKIPPED"].includes(u.reviewStatus) || typeof u.isManuallyCorrected !== "boolean") fail("INVALID_UNIT_STATE");
    for (const content of [u.rawRecognition, u.approvedContent]) if (content !== null && typeof content !== "string") fail("INVALID_UNIT_CONTENT");
    strings(u.sourceStrokeIds, "DUPLICATE_OR_INVALID_STROKE_REFERENCE", true);
    if (!u.sourceStrokeIds.length) fail("EMPTY_UNIT_STROKES");
    if (u.sourceStrokeIds.some((id) => !source.has(id))) fail("UNKNOWN_SOURCE_STROKE");
    strings(u.sourceRegionIds, "INVALID_REGION_REFERENCE", true); strings(u.reasons, "INVALID_REASONS");
    strings(u.childIds, "DUPLICATE_OR_INVALID_CHILD_REFERENCE", true);
    if (!Number.isInteger(u.readingOrder) || u.readingOrder < 0) fail("INVALID_READING_ORDER");
    const b = u.bounds;
    if (!b || [b.left, b.right, b.top, b.bottom].some((v) => !Number.isFinite(v))) fail("INVALID_UNIT_BOUNDS");
    if (b.left > b.right || b.top > b.bottom) fail("MALFORMED_UNIT_BOUNDS");
    const exact = computeBounds(u.sourceStrokeIds.map((id) => source.get(id)!));
    if (Object.keys(exact).some((key) => Math.abs(exact[key as keyof InkBounds] - b[key as keyof InkBounds]) > 1e-9)) fail("SOURCE_BOUNDS_MISMATCH");
  }
  const parent = new Map<string, string>();
  for (const u of ir.contentUnits) for (const id of u.childIds) {
    const ch = byId.get(id);
    if (!ch) fail("MISSING_CHILD_UNIT");
    if (parent.has(id)) fail("MULTIPLE_CHILD_PARENTS"); parent.set(id, u.id);
    if (ch.sourceStrokeIds.some((sid) => !u.sourceStrokeIds.includes(sid))) fail("CHILD_STROKE_NOT_IN_PARENT");
  }
  for (const u of ir.contentUnits) {
    const path = new Set<string>(); let id: string | undefined = u.id;
    while (id !== undefined) { if (path.has(id)) fail("CYCLIC_CHILD_REFERENCE"); path.add(id); if (path.size > 64) fail("STRUCTURE_DEPTH_EXCEEDED"); id = parent.get(id); }
    if (u.role === "CONTAINER") {
      if (u.kind !== "STRUCTURE" || !u.childIds.length || !["SYSTEM", "ALTERNATIVES", "FRACTION", "INDEPENDENT", "UNKNOWN"].includes(u.structureKind ?? "") ||
        u.approvedContent !== null || u.rawRecognition !== null || u.recognitionStatus !== "NOT_APPLICABLE" || u.isManuallyCorrected) fail("INVALID_CONTAINER_CONTRACT");
      if (u.reviewStatus === "APPROVED" && (u.structureKind === "UNKNOWN" || u.childIds.some((id) => byId.get(id)!.reviewStatus !== "APPROVED"))) fail("APPROVED_PARENT_UNRESOLVED_CHILD_OR_RELATION");
    } else {
      if (u.kind === "STRUCTURE" || u.childIds.length || u.structureKind !== null || u.recognitionStatus === "NOT_APPLICABLE") fail("INVALID_ATOMIC_CONTRACT");
      if (u.isManuallyCorrected !== (u.recognitionStatus === "MANUALLY_CORRECTED")) fail("INCONSISTENT_MANUAL_CORRECTION");
      if (u.recognitionStatus === "RECOGNIZED" && !u.rawRecognition?.trim()) fail("RECOGNIZED_WITHOUT_RAW_CONTENT");
      if (u.reviewStatus === "APPROVED" && (!u.approvedContent?.trim() || u.recognitionStatus === "UNRESOLVED")) fail("APPROVED_UNIT_EMPTY_CONTENT_OR_UNRESOLVED");
    }
  }
  const groups = [getRootContentUnits(ir.contentUnits), ...ir.contentUnits.filter((u) => u.role === "CONTAINER").map((u) => u.childIds.map((id) => byId.get(id)!))];
  for (const siblings of groups) {
    const owners = new Set<string>(), orders = new Set<number>();
    for (const u of siblings) {
      if (orders.has(u.readingOrder)) fail("DUPLICATE_SIBLING_READING_ORDER"); orders.add(u.readingOrder);
      for (const sid of u.sourceStrokeIds) { if (owners.has(sid)) fail("DUPLICATE_SIBLING_STROKE_OWNERSHIP"); owners.add(sid); }
    }
    if (siblings.some((u) => u.readingOrder >= siblings.length)) fail("NONCONTIGUOUS_READING_ORDER");
  }
  const covered = new Set(getRootContentUnits(ir.contentUnits).flatMap((u) => u.sourceStrokeIds));
  if (covered.size !== source.size || [...source.keys()].some((id) => !covered.has(id))) fail("MISSING_SOURCE_STROKE_COVERAGE");
  if (ir.readingOrderStatus !== "CONFIRMED" && ambiguousOrder(ir.contentUnits).length && ir.readingOrderStatus !== "AMBIGUOUS") fail("UNDECLARED_READING_ORDER_AMBIGUITY");
  if (ir.rawStrokeCount !== source.size || ir.approvedUnitCount !== ir.contentUnits.filter((u) => u.reviewStatus === "APPROVED").length ||
    ir.recognizedUnitCount !== ir.contentUnits.filter((u) => u.rawRecognition !== null).length) fail("INCONSISTENT_IR_COUNTERS");
  if (ir.reviewStatus !== approvalStatus(ir)) fail("INCONSISTENT_IR_APPROVAL");
  return ir;
}
