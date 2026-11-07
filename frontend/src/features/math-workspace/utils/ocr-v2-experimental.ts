import { generateUuid } from "./ink-math";
import type { InkStroke } from "@/lib/api/contracts";
import { segmentPageInk, type InkBounds, type PageOcrRegion } from "./page-ocr";
import { selectLassoStrokes } from "./lasso";
import { computeBounds, buildStructuredTranscriptionIR, editContentUnit, validateSolutionTranscriptionIR,
  getRootContentUnits, type ContentUnitKind, type SolutionTranscriptionIR } from "./structured-transcription-ir";

export const PAGE = { width: 794, height: 1123 } as const;
export const INFERENCE_LIMIT = 12;
export type RouteKind = "MATH" | "TEXT" | "MIXED" | "UNKNOWN";
export type LabProfile = "HYBRID" | "GEOMETRY" | "LAYOUT_M" | "LAYOUT_V3" | "V1" | "V2";
export interface RawLayoutRegion {
  id: string; label: string; score: number | null; box: number[]; polygon?: number[][];
  raw?: unknown;
}
export interface PerceptionResult {
  status: string; model: string; regions: RawLayoutRegion[]; error?: string;
  timings?: Record<string, number>; manifest?: unknown; htr?: unknown;
}
export interface ScopeProposal {
  id: string; regionIds: string[]; rawLabel: string; rawScore: number | null;
  kind: RouteKind; strokeIds: string[]; candidateStrokeIds: string[];
  coverage: Record<string, number>; flags: string[]; method: string;
}
export interface LabSource {
  pageIndex: number; sourceRevision: number; sourceKind: "LIVE_INK" | "HANDOFF_CAPTURE" | "IMPORTED_CAPTURE" | "SYNTHETIC_INK";
  datasetSplit: "DEV" | "HOLDOUT"; consent: boolean; writerId?: string; strokes: InkStroke[];
}
export interface RenderTransform { width: number; height: number; padding: number; scale: number }
export function sourceKey(source: LabSource): string { return JSON.stringify([source.pageIndex, source.sourceRevision, source.strokes]); }
export function validateLabSource(source: LabSource): InkStroke[] {
  if (!Number.isInteger(source.pageIndex) || source.pageIndex < 0 || source.pageIndex >= 30 || !Number.isInteger(source.sourceRevision) || source.sourceRevision < 0) throw new Error("INVALID_PAGE_OR_REVISION");
  if (!Array.isArray(source.strokes) || source.strokes.length > 400) throw new Error("STROKE_LIMIT_400");
  const ids = new Set<string>(); let count = 0;
  for (const s of source.strokes) {
    if (!s.id || ids.has(s.id)) throw new Error("DUPLICATE_OR_EMPTY_STROKE_ID"); ids.add(s.id);
    if (!["PEN", "HIGHLIGHTER"].includes(s.tool) || !Number.isFinite(s.width) || s.width < .25 || s.width > 24 || !Array.isArray(s.points) || !s.points.length || s.points.length > 3000) throw new Error("INVALID_STROKE");
    count += s.points.length;
    for (const p of s.points) if (![p.x, p.y, p.pressure ?? .5].every(Number.isFinite) || p.x < 0 || p.x > 1 || p.y < 0 || p.y > 1) throw new Error("INVALID_POINT_OR_OUT_OF_PAGE; source was not modified");
  }
  if (count > 15000) throw new Error("POINT_LIMIT_15000");
  return structuredClone(source.strokes.filter(s => s.tool === "PEN"));
}
export function renderTransform(padding = 16, scale = 1): RenderTransform {
  if (!Number.isFinite(padding) || padding < 0 || padding > 64 || !Number.isFinite(scale) || scale < .5 || scale > 2) throw new Error("INVALID_RENDER_OPTIONS");
  return { padding, scale, width: Math.ceil((PAGE.width + padding * 2) * scale), height: Math.ceil((PAGE.height + padding * 2) * scale) };
}
export function toPixel(p: { x: number; y: number }, t: RenderTransform) { return { x: (p.x * PAGE.width + t.padding) * t.scale, y: (p.y * PAGE.height + t.padding) * t.scale }; }
export function fromPixel(p: { x: number; y: number }, t: RenderTransform) { return { x: (p.x / t.scale - t.padding) / PAGE.width, y: (p.y / t.scale - t.padding) / PAGE.height }; }
/** Deterministic A4 polyline raster, distinct from the unchanged CoMER preprocessing. */
export function renderLabPage(source: LabSource, transform = renderTransform()) {
  const pen = validateLabSource(source), canvas = document.createElement("canvas"); canvas.width = transform.width; canvas.height = transform.height;
  const ctx = canvas.getContext("2d")!; ctx.fillStyle = "white"; ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = ctx.fillStyle = "#101010"; ctx.lineCap = ctx.lineJoin = "round";
  for (const s of pen) {
    ctx.lineWidth = s.width * transform.scale; ctx.beginPath();
    const points = s.points.map(p => toPixel(p, transform)); ctx.moveTo(points[0].x, points[0].y);
    if (points.length === 1) { ctx.arc(points[0].x, points[0].y, ctx.lineWidth / 2, 0, Math.PI * 2); ctx.fill(); }
    else { points.slice(1).forEach(p => ctx.lineTo(p.x, p.y)); ctx.stroke(); }
  }
  return { canvas, png: canvas.toDataURL("image/png"), transform, pen,
    supportIndex: pen.map(s => ({ id: s.id, bounds: computeBounds([s]), pointCount: s.points.length, width: s.width })) };
}
export function cropLabScope(page: HTMLCanvasElement, strokes: InkStroke[], t: RenderTransform): string {
  const b = computeBounds(strokes), a = toPixel({ x: b.left, y: b.top }, t), z = toPixel({ x: b.right, y: b.bottom }, t);
  const pad = 10 * t.scale, x = Math.max(0, Math.floor(a.x - pad)), y = Math.max(0, Math.floor(a.y - pad));
  const canvas = document.createElement("canvas"); canvas.width = Math.max(1, Math.min(page.width - x, Math.ceil(z.x - x + pad))); canvas.height = Math.max(1, Math.min(page.height - y, Math.ceil(z.y - y + pad)));
  canvas.getContext("2d")!.drawImage(page, x, y, canvas.width, canvas.height, 0, 0, canvas.width, canvas.height); return canvas.toDataURL("image/png");
}
export function routeLabel(label: string): RouteKind {
  if (["formula", "inline_formula", "display_formula"].includes(label)) return "MATH";
  if (["text", "paragraph_title", "doc_title", "document_title", "abstract", "reference", "footnote", "header", "footer", "aside_text"].includes(label)) return "TEXT";
  return "UNKNOWN";
}
type XY = { x: number; y: number };
function inPolygon(p: XY, poly: XY[]) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[j], b = poly[i], cross = (p.x - a.x) * (b.y - a.y) - (p.y - a.y) * (b.x - a.x);
    if (Math.abs(cross) < 1e-8 && p.x >= Math.min(a.x, b.x) - 1e-8 && p.x <= Math.max(a.x, b.x) + 1e-8 && p.y >= Math.min(a.y, b.y) - 1e-8 && p.y <= Math.max(a.y, b.y) + 1e-8) return true;
    if ((a.y > p.y) !== (b.y > p.y) && p.x < (b.x - a.x) * (p.y - a.y) / (b.y - a.y) + a.x) inside = !inside;
  } return inside;
}
function segmentCoverage(a: XY, b: XY, poly: XY[]) {
  const dx = b.x - a.x, dy = b.y - a.y, ts = [0, 1];
  for (let i = 0; i < poly.length; i++) {
    const c = poly[i], d = poly[(i + 1) % poly.length], ex = d.x - c.x, ey = d.y - c.y, den = dx * ey - dy * ex;
    if (Math.abs(den) < 1e-10) continue;
    const t = ((c.x - a.x) * ey - (c.y - a.y) * ex) / den, u = ((c.x - a.x) * dy - (c.y - a.y) * dx) / den;
    if (t > 0 && t < 1 && u >= 0 && u <= 1) ts.push(t);
  }
  ts.sort((x, y) => x - y); let covered = 0;
  for (let i = 1; i < ts.length; i++) { const mid = (ts[i - 1] + ts[i]) / 2; if (inPolygon({ x: a.x + mid * dx, y: a.y + mid * dy }, poly)) covered += ts[i] - ts[i - 1]; }
  return covered;
}
/** Arclength intersection handles segments crossing a region even when neither endpoint is inside. */
export function strokeCoverage(s: InkStroke, r: RawLayoutRegion, t: RenderTransform): number {
  const radius = s.width * t.scale / 2;
  const [l, top, right, bottom] = r.box;
  const poly = r.polygon?.length ? r.polygon.map(([x, y]) => ({ x, y })) : [
    { x: l - radius, y: top - radius }, { x: right + radius, y: top - radius }, { x: right + radius, y: bottom + radius }, { x: l - radius, y: bottom + radius }];
  const points = s.points.map(p => toPixel(p, t)); let total = 0, inside = 0;
  for (let i = 1; i < points.length; i++) { const length = Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y); total += length; inside += length * segmentCoverage(points[i - 1], points[i], poly); }
  return total > 1e-8 ? inside / total : Number(inPolygon(points[0], poly));
}
export function geometryPerception(pen: InkStroke[], profile: "V1" | "V2", t: RenderTransform, fallback = false): PerceptionResult {
  return { status: fallback ? "FALLBACK" : "GEOMETRY_BASELINE", model: profile, regions: segmentPageInk(pen, { algorithm: profile === "V1" ? "v1" : "v2" }).map((r, i) => {
    const a = toPixel({ x: r.bounds.left, y: r.bounds.top }, t), b = toPixel({ x: r.bounds.right, y: r.bounds.bottom }, t);
    return { id: `${profile}-${i + 1}`, label: fallback ? "geometry_unknown" : "legacy_assumes_math", score: null, box: [a.x, a.y, b.x, b.y], raw: { sourceStrokeIds: r.strokes.map(s => s.id) } };
  }) };
}
export function mapLayoutToScopes(source: LabSource, perception: PerceptionResult, t: RenderTransform): ScopeProposal[] {
  const pen = validateLabSource(source);
  const regions = perception.regions.filter(r => r.box.length === 4 && r.box.every(Number.isFinite) && r.box[2] >= r.box[0] && r.box[3] >= r.box[1]);
  const scopes: ScopeProposal[] = regions.slice(0, 48).map((r, i) => {
    const baselineIds = ["legacy_assumes_math", "geometry_unknown"].includes(r.label) && Array.isArray((r.raw as { sourceStrokeIds?: string[] } | undefined)?.sourceStrokeIds) ? (r.raw as { sourceStrokeIds: string[] }).sourceStrokeIds : null;
    const coverage = Object.fromEntries(pen.map(s => [s.id, baselineIds ? Number(baselineIds.includes(s.id)) : strokeCoverage(s, r, t)]));
    return { id: `scope-${i + 1}`, regionIds: [r.id], rawLabel: r.label, rawScore: r.score,
      kind: r.label === "legacy_assumes_math" ? "MATH" : routeLabel(r.label), strokeIds: [], candidateStrokeIds: pen.filter(s => coverage[s.id] > .02).map(s => s.id), coverage,
      flags: ["TYPE_AND_BOUNDARY_PROPOSAL_NOT_GROUND_TRUTH", ...(perception.status === "FALLBACK" ? ["FALLBACK"] : [])], method: baselineIds ? "EXACT_SOURCE_MEMBERSHIP_BASELINE; do not remap overlapping baseline boxes" : "POLYLINE_ARCLENGTH_INTERSECTION; rectangle expanded by half stroke width; candidate >2%; ownership maximum coverage" };
  });
  for (const s of pen) {
    const matches = scopes.filter(scope => scope.candidateStrokeIds.includes(s.id)).sort((a, b) => b.coverage[s.id] - a.coverage[s.id]);
    if (matches.length) {
      matches[0].strokeIds.push(s.id);
      if (matches[0].coverage[s.id] < .98) matches[0].flags.push(`BOUNDARY_CROSSING:${s.id}`);
      if (matches.length > 1) matches.forEach(m => m.flags.push(`OVERLAPPING_CANDIDATES:${s.id}`));
    }
  }
  const assigned = new Set(scopes.flatMap(s => s.strokeIds)), orphans = pen.filter(s => !assigned.has(s.id));
  // Keep each baseline orphan group visible; never merge all page ink as an automatic rescue.
  for (const r of segmentPageInk(orphans)) scopes.push({ id: `orphan-${r.id}`, regionIds: [], rawLabel: "unmapped_ink", rawScore: null, kind: "UNKNOWN", strokeIds: r.strokes.map(s => s.id), candidateStrokeIds: [], coverage: {}, flags: ["ORPHAN_SOURCE_INK", "MANUAL_SCOPE_REQUIRED"], method: "UNMAPPED_PEN_V2_GROUP" });
  return scopes;
}
export function scopeIntegrity(source: LabSource, scopes: ScopeProposal[]) {
  const pen = validateLabSource(source), counts = new Map<string, number>();
  scopes.flatMap(s => s.strokeIds).forEach(id => counts.set(id, (counts.get(id) ?? 0) + 1));
  return { missing: pen.filter(s => !counts.has(s.id)).map(s => s.id), duplicateOwnership: [...counts].filter(([, n]) => n > 1).map(([id]) => id), unknown: [...counts.keys()].filter(id => !pen.some(s => s.id === id)), overlappingCandidates: scopes.filter(s => s.flags.some(f => f.startsWith("OVERLAPPING_CANDIDATES"))).map(s => s.id), orphans: scopes.filter(s => s.flags.includes("ORPHAN_SOURCE_INK")).flatMap(s => s.strokeIds) };
}
/** Lab-only projection evidence in the existing reasons field; IR 1.1 is unchanged.
 * This records the input scope kind, not an independently verified content label.
 */
const SCOPE_PROJECTION = "LAB_SCOPE_PROJECTION_V1:";
export interface LabScopeProjection {
  scopeId: string; originalKind: RouteKind; projectedKind: ContentUnitKind;
  pageIndex: number; sourceRevision: number; sourceStrokeIds: string[];
}
function scopeProjectionReason(source: Pick<LabSource, "pageIndex" | "sourceRevision">, scope: ScopeProposal): string {
  const evidence: LabScopeProjection = { scopeId: scope.id, originalKind: scope.kind,
    projectedKind: scope.kind === "MIXED" ? "UNKNOWN" : scope.kind,
    pageIndex: source.pageIndex, sourceRevision: source.sourceRevision, sourceStrokeIds: [...scope.strokeIds] };
  return SCOPE_PROJECTION + JSON.stringify(evidence);
}
/** Fail closed for missing/invalid/stale metadata; never infer MIXED from UNKNOWN. */
export function readLabScopeProjection(ir: SolutionTranscriptionIR, unitId: string): LabScopeProjection | null {
  const unit = ir.contentUnits.find(u => u.id === unitId);
  if (!unit || unit.role !== "ATOMIC") return null;
  const entries = unit.reasons.filter(r => r.startsWith(SCOPE_PROJECTION));
  if (entries.length !== 1) return null;
  try {
    const e = JSON.parse(entries[0].slice(SCOPE_PROJECTION.length)) as LabScopeProjection;
    if (!["MATH", "TEXT", "MIXED", "UNKNOWN"].includes(e.originalKind)
      || unit.id !== `unit-${e.scopeId}` || e.pageIndex !== ir.pageIndex
      || !Number.isInteger(e.sourceRevision) || e.sourceRevision < 0 || Math.max(1, e.sourceRevision) !== ir.sourceRevision
      || e.projectedKind !== unit.kind || e.projectedKind !== (e.originalKind === "MIXED" ? "UNKNOWN" : e.originalKind)
      || !Array.isArray(e.sourceStrokeIds) || new Set(e.sourceStrokeIds).size !== e.sourceStrokeIds.length
      || e.sourceStrokeIds.length !== unit.sourceStrokeIds.length || e.sourceStrokeIds.some(id => !unit.sourceStrokeIds.includes(id))) return null;
    return structuredClone(e);
  } catch { return null; }
}
/** Explicit Lab kind edit; update its projection evidence with the same review invalidation. */
export function editLabScopeKind(ir: SolutionTranscriptionIR, scope: ScopeProposal): SolutionTranscriptionIR {
  const id = `unit-${scope.id}`, unit = ir.contentUnits.find(u => u.id === id);
  if (!unit || unit.sourceStrokeIds.length !== scope.strokeIds.length || new Set(scope.strokeIds).size !== scope.strokeIds.length
    || scope.strokeIds.some(sid => !unit.sourceStrokeIds.includes(sid))) throw new Error("SCOPE_PROJECTION_SOURCE_MISMATCH");
  const next = editContentUnit(ir, id, { kind: scope.kind === "MIXED" ? "UNKNOWN" : scope.kind });
  return validateSolutionTranscriptionIR({ ...next, contentUnits: next.contentUnits.map(u => u.id === id
    ? { ...u, reasons: [...u.reasons.filter(r => !r.startsWith(SCOPE_PROJECTION)), scopeProjectionReason(ir, scope)] } : u) });
}
export function buildScopeIR(source: LabSource, scopes: ScopeProposal[], previous?: SolutionTranscriptionIR): SolutionTranscriptionIR {
  const pen = validateLabSource(source), integrity = scopeIntegrity(source, scopes);
  if (integrity.missing.length || integrity.duplicateOwnership.length || integrity.unknown.length) throw new Error("INVALID_ACTIVE_SCOPE_OWNERSHIP");
  const regions: PageOcrRegion[] = scopes.filter(s => s.strokeIds.length).map(s => ({ id: s.id, strokes: pen.filter(p => s.strokeIds.includes(p.id)), bounds: computeBounds(pen.filter(p => s.strokeIds.includes(p.id))) }));
  let ir = buildStructuredTranscriptionIR({ pageIndex: source.pageIndex, sourceRevision: Math.max(1, source.sourceRevision), strokes: pen, regions });
  ir.contentUnits = ir.contentUnits.map(u => {
    const s = scopes.find(s => `unit-${s.id}` === u.id)!;
    return { ...u, kind: (s.kind === "MIXED" ? "UNKNOWN" : s.kind) as ContentUnitKind,
      sourceRegionIds: [...s.regionIds], reasons: [s.method, `Raw proposal label: ${s.rawLabel}`, ...s.flags, scopeProjectionReason(source, s)] };
  });
  // Preserve reviewed data only for identical source identity, scope ink, and type.
  if (previous && previous.sourceRevision === ir.sourceRevision && JSON.stringify(previous.sourceSnapshot.strokes) === JSON.stringify(ir.sourceSnapshot.strokes)) {
    ir.contentUnits = ir.contentUnits.map(u => {
      const scope = scopes.find(s => `unit-${s.id}` === u.id)!;
      const old = previous.contentUnits.find(p => p.role === "ATOMIC" && p.id === u.id && p.kind === u.kind
        && JSON.stringify(p.sourceStrokeIds) === JSON.stringify(u.sourceStrokeIds));
      // MIXED and UNKNOWN share an IR kind, but their approvals are not interchangeable.
      const sameScopeKind = old && (readLabScopeProjection(previous, old.id)?.originalKind ?? old.kind) === scope.kind;
      return old ? { ...old, reviewStatus: sameScopeKind ? old.reviewStatus : "NEEDS_REVIEW",
        sourceRegionIds: u.sourceRegionIds, reasons: u.reasons, readingOrder: u.readingOrder } : u;
    });
    ir.approvedUnitCount = ir.contentUnits.filter(u => u.reviewStatus === "APPROVED").length;
    ir.recognizedUnitCount = ir.contentUnits.filter(u => u.rawRecognition !== null).length;
  }
  return validateSolutionTranscriptionIR(ir, pen);
}
/** Explicit user operation. Reassign whole physical strokes, archive the old review in the caller. */
export function reassignScope(scopes: ScopeProposal[], ids: string[], newId: string, kind: RouteKind): ScopeProposal[] {
  if (!ids.length || new Set(ids).size !== ids.length) throw new Error("EMPTY_OR_DUPLICATE_MANUAL_SELECTION");
  const known = new Set(scopes.flatMap(s => s.strokeIds)); if (ids.some(id => !known.has(id))) throw new Error("UNKNOWN_MANUAL_STROKE");
  return [...scopes.map(s => ({ ...s, strokeIds: s.strokeIds.filter(id => !ids.includes(id)) })), { id: newId, regionIds: [...new Set(scopes.filter(s => s.strokeIds.some(id => ids.includes(id))).flatMap(s => s.regionIds))], rawLabel: "manual_lasso", rawScore: null, kind, strokeIds: [...ids], candidateStrokeIds: [...ids], coverage: {}, flags: ["MANUAL_SCOPE_NOT_AUTOMATIC"], method: "EXPLICIT_USER_STROKE_SELECTION" }];
}
export function lassoIds(source: LabSource, polygon: { x: number; y: number; pressure: number }[]) { return selectLassoStrokes(validateLabSource(source), polygon).map(s => s.id); }
export function groupIrUnits(ir: SolutionTranscriptionIR, ids: string[], relation: "SYSTEM" | "ALTERNATIVES" | "FRACTION" | "INDEPENDENT" | "UNKNOWN"): SolutionTranscriptionIR {
  const roots = getRootContentUnits(ir.contentUnits), selected = roots.filter(u => ids.includes(u.id));
  if (selected.length < 2 || selected.length !== new Set(ids).size) throw new Error("SELECT_TWO_OR_MORE_ROOT_UNITS");
  const strokeIds = [...new Set(selected.flatMap(u => u.sourceStrokeIds))], id = `container-${generateUuid()}`;
  const container = { ...selected[0], id, role: "CONTAINER" as const, kind: "STRUCTURE" as const, structureKind: relation,
    childIds: selected.map(u => u.id), sourceStrokeIds: strokeIds, sourceRegionIds: [...new Set(selected.flatMap(u => u.sourceRegionIds))], bounds: computeBounds(ir.sourceSnapshot.strokes.filter(s => strokeIds.includes(s.id))), rawRecognition: null, approvedContent: null, recognitionStatus: "NOT_APPLICABLE" as const, reviewStatus: "NEEDS_REVIEW" as const, isManuallyCorrected: false, reasons: ["Human selected presentation relation, not a GradingStep"] };
  const units = [...ir.contentUnits.map(u => ids.includes(u.id) ? { ...u, readingOrder: ids.indexOf(u.id) } : { ...u }), container];
  const top = [...roots.filter(u => !ids.includes(u.id)), container].sort((a, b) => a.bounds.top - b.bounds.top || a.bounds.left - b.bounds.left);
  top.forEach((u, i) => { units.find(v => v.id === u.id)!.readingOrder = i; });
  return validateSolutionTranscriptionIR({ ...ir, contentUnits: units, reviewStatus: "NEEDS_REVIEW", readingOrderStatus: "AMBIGUOUS" });
}
export function csvRows(rows: Record<string, unknown>[]) {
  const keys = [...new Set(rows.flatMap(Object.keys))], q = (v: unknown) => `"${String(v ?? "").replaceAll('"', '""')}"`;
  return [keys.map(q).join(","), ...rows.map(row => keys.map(k => q(row[k])).join(","))].join("\n");
}
