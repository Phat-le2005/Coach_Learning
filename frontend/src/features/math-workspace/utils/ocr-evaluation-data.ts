import type { InkStroke } from "@/lib/api/contracts";
import { validateLabSource, type LabSource } from "./ocr-v2-experimental";
import { sha256Hex } from "./ocr-digest";

export type Kind = "MATH" | "TEXT" | "UNKNOWN" | "STRUCTURE";
export type LabelOrigin = "DATASET_METADATA" | "GENERATOR" | "HUMAN" | "MACHINE_PROPOSAL" | "UNVERIFIED_CORRECTION" | "SOFTWARE_TEST";
export type Matrix = [number, number, number, number, number, number];
export interface GtUnit { id: string; kind: Kind; strokeIds: string[]; transcript: string | null; readingOrder: number; childIds: string[]; relation?: "SYSTEM" | "ALTERNATIVES" | "INDEPENDENT" | "UNKNOWN"; confirmed: boolean; humanConfirmation?: { reviewer: string; at: string; assisted: boolean } }
export interface Annotation { status: "DRAFT" | "SOURCE_AUTHORITATIVE" | "GENERATED_DETERMINISTIC" | "HUMAN_CONFIRMED" | "SOFTWARE_SIMULATED"; origin: LabelOrigin; sourceChecksum: string; units: GtUnit[]; assisted: boolean; reviewer?: string; confirmedAt?: string; stale?: boolean }
export interface EvaluationPage {
  schemaVersion: "ocr-evaluation/1"; id: string; title: string; source: LabSource; sourceChecksum: string;
  sourceKind: "NATIVE_MATHCANVAS" | "EXTERNAL_HUMAN_INK" | "EXTERNAL_SYNTHETIC_INK" | "EXTERNAL_UNKNOWN_ORIGIN" | "SYNTHETIC_COMPOSED_REAL_INK" | "BROWSER_REPLAY";
  split: "DEV" | "HOLDOUT"; lineageIds: string[]; provenance: Record<string, unknown>; annotation: Annotation; softwareTestOnly?: boolean;
}
export interface RawVectorSource { id: string; dataset: string; checksum: string; sourcePath: string; license: string; url?: string; label?: string; labelField?: string; originalSplit: string; inkCreationMethod: string; writerId?: string; annotations?: Record<string, string>; traces: { id: string; points: { x: number; y: number; t?: number }[] }[] }
export async function hashValue(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(typeof value === "string" ? value : JSON.stringify(value));
  return sha256Hex(bytes);
}
export const inkHash = (s: LabSource) => hashValue([s.pageIndex, s.sourceRevision, s.strokes]);
const numberHash = (value: string) => { let h = 2166136261; for (const c of value) h = Math.imul(h ^ c.charCodeAt(0), 16777619); return h >>> 0; };
export function applyAffine(p: { x: number; y: number }, m: Matrix) { return { x: m[0] * p.x + m[2] * p.y + m[4], y: m[1] * p.x + m[3] * p.y + m[5] }; }
export function invertAffine(m: Matrix): Matrix {
  const det = m[0] * m[3] - m[1] * m[2]; if (Math.abs(det) < 1e-14) throw Error("NON_INVERTIBLE_TRANSFORM");
  return [m[3] / det, -m[1] / det, -m[2] / det, m[0] / det, (m[2] * m[5] - m[3] * m[4]) / det, (m[1] * m[4] - m[0] * m[5]) / det];
}
export function makeSource(strokes: InkStroke[], revision = 1, pageIndex = 0): LabSource { return { strokes: structuredClone(strokes), sourceRevision: revision, pageIndex, sourceKind: "IMPORTED_CAPTURE", datasetSplit: "DEV", consent: false }; }
export async function nativePage(strokes: InkStroke[], id: string, title: string, provenance: Record<string, unknown> = {}, revision = 1, pageIndex = 0): Promise<EvaluationPage> {
  const source = makeSource(strokes, revision, pageIndex); validateLabSource(source); const checksum = await inkHash(source);
  return { schemaVersion: "ocr-evaluation/1", id, title, source, sourceChecksum: checksum, split: "DEV", sourceKind: "NATIVE_MATHCANVAS", lineageIds: [`native-ink:${await hashValue(strokes.filter(s => s.tool === "PEN"))}`], provenance,
    annotation: { status: "DRAFT", origin: "HUMAN", sourceChecksum: checksum, units: [], assisted: false } };
}
/** Uniform physical-space scaling; x/y normalization uses A4 dimensions separately. */
export async function convertVectorSource(raw: RawVectorSource, officialVerified = false): Promise<EvaluationPage> {
  if (!raw.traces?.length || raw.traces.length > 400 || !/^[a-f0-9]{64}$/.test(raw.checksum)) throw Error("INVALID_VECTOR_SOURCE");
  const points = raw.traces.flatMap(t => t.points); if (!points.length || points.some(p => !Number.isFinite(p.x) || !Number.isFinite(p.y))) throw Error("INVALID_VECTOR_COORDINATES");
  if (new Set(raw.traces.map(t => t.id)).size !== raw.traces.length) throw Error("DUPLICATE_SOURCE_TRACE_ID");
  const l = Math.min(...points.map(p => p.x)), r = Math.max(...points.map(p => p.x)), t = Math.min(...points.map(p => p.y)), b = Math.max(...points.map(p => p.y));
  const scale = Math.min(560 / Math.max(1, r - l), 170 / Math.max(1, b - t));
  const matrix: Matrix = [scale / 794, 0, 0, scale / 1123, (80 - l * scale) / 794, (90 - t * scale) / 1123];
  const strokes: InkStroke[] = raw.traces.map(trace => ({ id: `${raw.id}:${trace.id}`, tool: "PEN", color: "#101010", width: 2, points: trace.points.map(p => ({ ...applyAffine(p, matrix), pressure: .5 })) }));
  const page = await nativePage(strokes, raw.id, raw.label ?? raw.id, { dataset: raw.dataset, sourcePath: raw.sourcePath, sourceChecksum: raw.checksum, license: raw.license, url: raw.url, originalSplit: raw.originalSplit, inkCreationMethod: raw.inkCreationMethod, labelField: raw.labelField,
    sourceLabel: raw.label, originalLabel: raw.annotations?.label, normalizedLabel: raw.annotations?.normalizedLabel, writerId: raw.writerId ?? "NOT_AVAILABLE", affine: matrix, inverseAffine: invertAffine(matrix), strokeMap: raw.traces.map((trace, i) => ({ sourceId: trace.id, targetId: strokes[i].id, pointCount: trace.points.length })), originalTraces: raw.traces, authority: officialVerified ? "OFFICIAL_ARCHIVE_CHECKSUM_VERIFIED" : "USER_IMPORTED_METADATA_UNVERIFIED" });
  page.sourceKind = raw.inkCreationMethod === "human" ? "EXTERNAL_HUMAN_INK" : raw.inkCreationMethod === "boundingBoxes" ? "EXTERNAL_SYNTHETIC_INK" : "EXTERNAL_UNKNOWN_ORIGIN";
  page.lineageIds = [`raw-ink:${raw.checksum}`];
  // Group repeated source expressions together; transformations can never change split.
  page.split = numberHash(raw.writerId ? `writer:${raw.writerId}` : `label:${raw.label ?? raw.id}`) % 5 === 0 ? "HOLDOUT" : "DEV";
  page.source.datasetSplit = page.split;
  page.annotation = { status: officialVerified && raw.label ? "SOURCE_AUTHORITATIVE" : "DRAFT", origin: "DATASET_METADATA", sourceChecksum: page.sourceChecksum, assisted: false,
    units: [{ id: "expression", kind: "MATH", strokeIds: strokes.map(s => s.id), transcript: raw.label ?? null, readingOrder: 0, childIds: [], confirmed: Boolean(officialVerified && raw.label) }] };
  return page;
}
export function validateAnnotation(page: EvaluationPage, complete = false): void {
  const a = page.annotation, penIds = new Set(validateLabSource(page.source).map(s => s.id));
  if (!["DRAFT", "SOURCE_AUTHORITATIVE", "GENERATED_DETERMINISTIC", "HUMAN_CONFIRMED", "SOFTWARE_SIMULATED"].includes(a.status) || !["DATASET_METADATA", "GENERATOR", "HUMAN", "MACHINE_PROPOSAL", "UNVERIFIED_CORRECTION", "SOFTWARE_TEST"].includes(a.origin) || a.units.length > 800) throw Error("INVALID_ANNOTATION_STATUS_OR_ORIGIN");
  if (a.sourceChecksum !== page.sourceChecksum || a.stale) throw Error("STALE_ANNOTATION_SOURCE");
  if (["MACHINE_PROPOSAL", "UNVERIFIED_CORRECTION"].includes(a.origin) && (a.status !== "DRAFT" || a.units.some(u => u.confirmed))) throw Error("MACHINE_PREDICTIONS_CANNOT_BECOME_GT_AUTOMATICALLY");
  if (a.status === "SOURCE_AUTHORITATIVE" && (a.origin !== "DATASET_METADATA" || page.provenance.authority !== "OFFICIAL_ARCHIVE_CHECKSUM_VERIFIED")) throw Error("SOURCE_LABEL_AUTHORITY_MISSING");
  if (a.status === "GENERATED_DETERMINISTIC" && (a.origin !== "GENERATOR" || page.sourceKind !== "SYNTHETIC_COMPOSED_REAL_INK")) throw Error("INVALID_GENERATED_AUTHORITY");
  if (a.status === "HUMAN_CONFIRMED" && (a.origin !== "HUMAN" || !a.confirmedAt || !a.reviewer?.trim())) throw Error("HUMAN_CONFIRMATION_REQUIRED");
  if ((a.status === "SOFTWARE_SIMULATED" || a.origin === "SOFTWARE_TEST") && !page.softwareTestOnly) throw Error("SOFTWARE_TEST_LABELS_CANNOT_BE_NATIVE_HUMAN_GT");
  const units = new Map<string, GtUnit>(), parents = new Map<string, string>();
  for (const u of a.units) {
    if (!u.id || units.has(u.id) || !["MATH", "TEXT", "UNKNOWN", "STRUCTURE"].includes(u.kind) || typeof u.confirmed !== "boolean" || (u.transcript !== null && typeof u.transcript !== "string") || !Number.isInteger(u.readingOrder) || u.readingOrder < 0 || !Array.isArray(u.strokeIds) || !Array.isArray(u.childIds) || !u.strokeIds.length || new Set(u.strokeIds).size !== u.strokeIds.length || u.strokeIds.some(id => !penIds.has(id))) throw Error("INVALID_GT_UNIT_OR_STROKES");
    if (new Set(u.childIds).size !== u.childIds.length || (u.childIds.length && u.kind !== "STRUCTURE")) throw Error("INVALID_GT_CHILDREN");
    if (u.confirmed && ["MATH", "TEXT"].includes(u.kind) && !u.transcript?.trim()) throw Error("CONFIRMED_TRANSCRIPT_REQUIRED");
    if (a.origin === "HUMAN" && u.confirmed && (!u.humanConfirmation?.reviewer?.trim() || !u.humanConfirmation.at)) throw Error("EXPLICIT_HUMAN_UNIT_CONFIRMATION_REQUIRED");
    if (a.status === "SOURCE_AUTHORITATIVE" && u.kind === "MATH" && u.transcript !== page.provenance.sourceLabel) throw Error("SOURCE_TRANSCRIPTION_CHANGED_WITHOUT_REVIEW");
    if (u.kind === "STRUCTURE" && (!u.childIds.length || !u.relation)) throw Error("STRUCTURE_RELATION_AND_CHILDREN_REQUIRED");
    units.set(u.id, u);
  }
  for (const u of units.values()) for (const childId of u.childIds) { const child = units.get(childId); if (!child || parents.has(childId) || child.strokeIds.some(id => !u.strokeIds.includes(id))) throw Error("INVALID_GT_PARENT_REFERENCE"); parents.set(childId, u.id); }
  const ancestors = (id: string) => { const seen = new Set<string>(); for (let p = parents.get(id); p; p = parents.get(p)) { if (p === id || seen.has(p)) throw Error("GT_CYCLE"); if (seen.size >= 64) throw Error("GT_NESTING_LIMIT"); seen.add(p); } return seen; };
  for (const u of units.values()) ancestors(u.id);
  const list = [...units.values()];
  for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) if (list[i].strokeIds.some(id => list[j].strokeIds.includes(id)) && !ancestors(list[i].id).has(list[j].id) && !ancestors(list[j].id).has(list[i].id)) throw Error("DUPLICATE_UNRELATED_GT_OWNERSHIP");
  if (complete) {
    const covered = new Set(list.flatMap(u => u.strokeIds));
    if (!list.length || [...penIds].some(id => !covered.has(id)) || list.some(u => !u.confirmed)) throw Error("GT_INCOMPLETE_COVERAGE_OR_UNCONFIRMED_UNITS");
    for (const group of [list.filter(u => !parents.has(u.id)), ...list.filter(u => u.childIds.length).map(u => list.filter(c => u.childIds.includes(c.id)))]) if (new Set(group.map(u => u.readingOrder)).size !== group.length) throw Error("GT_READING_ORDER_COLLISION");
  }
}
export async function validateEvaluationPage(input: unknown): Promise<EvaluationPage> {
  const page = structuredClone(input) as EvaluationPage;
  if (!page || page.schemaVersion !== "ocr-evaluation/1" || !page.id || !page.source || !page.annotation || !Array.isArray(page.annotation.units)) throw Error("INVALID_EVALUATION_PAGE");
  if (!["DEV", "HOLDOUT"].includes(page.split) || !Array.isArray(page.lineageIds) || !page.provenance || !["NATIVE_MATHCANVAS", "EXTERNAL_HUMAN_INK", "EXTERNAL_SYNTHETIC_INK", "EXTERNAL_UNKNOWN_ORIGIN", "SYNTHETIC_COMPOSED_REAL_INK", "BROWSER_REPLAY"].includes(page.sourceKind)) throw Error("INVALID_DATASET_PROVENANCE");
  validateLabSource(page.source);
  if (await inkHash(page.source) !== page.sourceChecksum) throw Error("SOURCE_CHECKSUM_MISMATCH; original ink not modified");
  // Strengthen old exported manifests without changing any source or annotation.
  if (page.sourceKind === "NATIVE_MATHCANVAS" || page.sourceKind === "BROWSER_REPLAY") page.lineageIds = [...new Set([...page.lineageIds, `native-ink:${await hashValue(page.source.strokes.filter(s => s.tool === "PEN"))}`])];
  if (page.sourceKind.startsWith("EXTERNAL") && typeof page.provenance.sourceChecksum === "string") page.lineageIds = [...new Set([...page.lineageIds, `raw-ink:${page.provenance.sourceChecksum}`])];
  if (page.sourceKind === "SYNTHETIC_COMPOSED_REAL_INK" && Array.isArray(page.provenance.transforms)) page.lineageIds = [...new Set([...page.lineageIds, ...page.provenance.transforms.filter(t => typeof t.rawSourceChecksum === "string").map(t => `raw-ink:${t.rawSourceChecksum}`)])];
  validateAnnotation(page, page.annotation.status !== "DRAFT"); return page;
}
export function trustedUnits(page: EvaluationPage): GtUnit[] {
  validateAnnotation(page); if (page.annotation.stale || ["MACHINE_PROPOSAL", "UNVERIFIED_CORRECTION"].includes(page.annotation.origin)) return [];
  const trusted = page.annotation.status === "SOURCE_AUTHORITATIVE" || page.annotation.status === "GENERATED_DETERMINISTIC" || page.annotation.origin === "HUMAN" || (page.softwareTestOnly && page.annotation.status === "SOFTWARE_SIMULATED");
  return trusted ? page.annotation.units.filter(u => u.kind !== "STRUCTURE" && u.confirmed) : [];
}
export function annotationCoverage(page: EvaluationPage) {
  const ids = new Set(page.annotation.units.flatMap(u => u.strokeIds)), pen = page.source.strokes.filter(s => s.tool === "PEN");
  return { covered: pen.filter(s => ids.has(s.id)).length, total: pen.length, missing: pen.filter(s => !ids.has(s.id)).map(s => s.id) };
}
export function setUnitMembership(page: EvaluationPage, unitId: string, ids: string[]): Annotation {
  if (!ids.length || new Set(ids).size !== ids.length || ids.some(id => !page.source.strokes.some(s => s.id === id && s.tool === "PEN"))) throw Error("INVALID_MEMBERSHIP_SELECTION");
  const next = structuredClone(page.annotation), target = next.units.find(u => u.id === unitId); if (!target || target.kind === "STRUCTURE") throw Error("SELECT_ATOMIC_UNIT");
  // Explicit user reassigns whole strokes; all impacted confirmations are invalidated.
  next.units = next.units.map(u => u.id === unitId ? { ...u, strokeIds: [...ids], confirmed: false } : u.kind === "STRUCTURE" ? u : { ...u, strokeIds: u.strokeIds.filter(id => !ids.includes(id)), confirmed: ids.some(id => u.strokeIds.includes(id)) ? false : u.confirmed }).filter(u => u.strokeIds.length);
  next.units.filter(u => u.kind === "STRUCTURE").forEach(u => { u.childIds = u.childIds.filter(id => next.units.some(c => c.id === id)); u.confirmed = false; u.strokeIds = [...new Set([...u.strokeIds.filter(id => !next.units.some(c => c.kind !== "STRUCTURE" && c.strokeIds.includes(id))), ...next.units.filter(c => u.childIds.includes(c.id)).flatMap(c => c.strokeIds)])]; });
  next.status = "DRAFT"; next.origin = "HUMAN"; delete next.confirmedAt;
  if (page.annotation.origin !== "HUMAN") next.units.forEach(u => { u.confirmed = false; });
  validateAnnotation({ ...page, annotation: next }); return next;
}
export type LayoutFamily = "SINGLE" | "ROWS" | "NEARBY" | "COLUMNS" | "INDENTED" | "SCALE_VARIATION" | "ALIGNED" | "SYSTEM_DEFINED";
export const LAYOUT_FAMILIES: LayoutFamily[] = ["SINGLE", "ROWS", "NEARBY", "COLUMNS", "INDENTED", "SCALE_VARIATION", "ALIGNED", "SYSTEM_DEFINED"];
export interface GenerateConfig { seed: number; count: number; split: "DEV" | "HOLDOUT"; family: LayoutFamily | "CYCLE"; expressions: number; gapPx: number; rotationDegrees: number; thickness: number; writerSplit?: boolean }
export async function generatePages(pool: EvaluationPage[], config: GenerateConfig): Promise<EvaluationPage[]> {
  if (!Number.isInteger(config.seed) || config.count < 1 || config.count > 300 || config.expressions < 1 || config.expressions > 6 || config.gapPx < 4 || config.gapPx > 100 || Math.abs(config.rotationDegrees) > 5 || config.thickness < .5 || config.thickness > 2) throw Error("INVALID_GENERATOR_LIMITS");
  const eligible = pool.filter(p => p.sourceKind === "EXTERNAL_HUMAN_INK" && p.provenance.originalSplit !== "symbols" && p.annotation.status === "SOURCE_AUTHORITATIVE" && trustedUnits(p).length === 1);
  const splitFor = (p: EvaluationPage) => config.writerSplit ? numberHash(`writer:${p.provenance.writerId}`) % 5 === 0 ? "HOLDOUT" : "DEV" : p.split;
  if (config.writerSplit && eligible.some(p => !p.provenance.writerId || p.provenance.writerId === "NOT_AVAILABLE")) throw Error("WRITER_SPLIT_BLOCKED_MISSING_WRITER_IDS");
  const sources = eligible.filter(p => splitFor(p) === config.split); if (!sources.length) throw Error("NO_LABELED_HUMAN_INK_IN_SELECTED_SPLIT");
  let state = config.seed >>> 0 || 1; const rand = () => { state ^= state << 13; state ^= state >>> 17; state ^= state << 5; return (state >>> 0) / 4294967296; };
  const pages: EvaluationPage[] = [];
  for (let index = 0; index < config.count; index++) {
    const family = config.family === "CYCLE" ? LAYOUT_FAMILIES[index % LAYOUT_FAMILIES.length] : config.family;
    const n = family === "SINGLE" ? 1 : family === "SYSTEM_DEFINED" ? 2 : config.expressions;
    const candidates = sources.filter(p => (family !== "SYSTEM_DEFINED" || trustedUnits(p)[0].transcript?.includes("=")) && p.source.strokes.length <= Math.floor(400 / n) && p.source.strokes.reduce((sum, s) => sum + s.points.length, 0) <= Math.floor(15000 / n));
    if (!candidates.length) throw Error("NO_SOURCE_MEETS_EQUATION_OR_PAGE_CAPACITY_CONSTRAINTS");
    const id = `composed-${config.split}-${config.seed}-${numberHash(JSON.stringify(config))}-${index}`;
    const strokes: InkStroke[] = [], units: GtUnit[] = [], transforms: unknown[] = [], lineage: string[] = [];
    for (let k = 0; k < n; k++) {
      let src = candidates[Math.floor(rand() * candidates.length)];
      for (let attempt = 0; attempt < candidates.length && strokes.length + src.source.strokes.length > 400; attempt++) src = candidates[(candidates.indexOf(src) + 1) % candidates.length];
      const ink = src.source.strokes.filter(s => s.tool === "PEN"), pts = ink.flatMap(s => s.points);
      const minX = Math.min(...pts.map(p => p.x * 794)), maxX = Math.max(...pts.map(p => p.x * 794)), minY = Math.min(...pts.map(p => p.y * 1123)), maxY = Math.max(...pts.map(p => p.y * 1123));
      const width = Math.max(1, maxX - minX), height = Math.max(1, maxY - minY);
      const col = family === "COLUMNS" ? k % 2 : 0, row = family === "COLUMNS" ? Math.floor(k / 2) : k;
      const maxWidth = family === "COLUMNS" ? 300 : 620, desiredHeight = family === "SCALE_VARIATION" ? 35 + rand() * 45 : 54;
      const angle = (rand() * 2 - 1) * config.rotationDegrees * Math.PI / 180, cos = Math.cos(angle), sin = Math.sin(angle);
      const scale = Math.min(maxWidth / (Math.abs(width * cos) + Math.abs(height * sin)), desiredHeight / (Math.abs(height * cos) + Math.abs(width * sin)));
      const cx = (minX + maxX) / 2, cy = (minY + maxY) / 2;
      const boxWidth = scale * (Math.abs(width * cos) + Math.abs(height * sin)), boxHeight = scale * (Math.abs(height * cos) + Math.abs(width * sin));
      const left = 45 + col * 380 + (family === "INDENTED" ? (k % 3) * 45 : family === "ALIGNED" ? 65 : 0), top = 50 + row * ((family === "NEARBY" ? 54 : 80) + config.gapPx);
      const centerX = left + boxWidth / 2, centerY = top + boxHeight / 2;
      const matrix: Matrix = [scale * cos, scale * sin * 794 / 1123, -scale * sin * 1123 / 794, scale * cos, (centerX - scale * cos * cx + scale * sin * cy) / 794, (centerY - scale * sin * cx - scale * cos * cy) / 1123];
      const target = ink.map(s => ({ ...structuredClone(s), id: `${id}:${k}:${s.id}`, width: s.width * config.thickness, points: s.points.map(p => ({ ...p, ...applyAffine(p, matrix) })) }));
      strokes.push(...target); lineage.push(...src.lineageIds);
      units.push({ id: `expression-${k}`, kind: "MATH", strokeIds: target.map(s => s.id), transcript: trustedUnits(src)[0].transcript, childIds: [], readingOrder: k, confirmed: true });
      transforms.push({ unitId: `expression-${k}`, sourceId: src.id, sourceChecksum: src.sourceChecksum, rawSourceChecksum: src.provenance.sourceChecksum,
        sourceDataset: src.provenance.dataset, sourcePath: src.provenance.sourcePath, sourceLicense: src.provenance.license, sourceUrl: src.provenance.url,
        sourceLabel: trustedUnits(src)[0].transcript, sourceNormalization: src.provenance.affine, labelField: src.provenance.labelField,
        matrix, inverse: invertAffine(matrix), originalPointCount: pts.length, strokeMap: ink.map((s, i) => ({ sourceId: s.id, transformedId: target[i].id })) });
    }
    const page = await nativePage(strokes, id, `${family} · ${config.split} · ${index + 1}`);
    page.sourceKind = "SYNTHETIC_COMPOSED_REAL_INK"; page.source.sourceKind = "SYNTHETIC_INK"; page.split = config.split; page.source.datasetSplit = config.split;
    if (family === "SYSTEM_DEFINED") units.push({ id: "system", kind: "STRUCTURE", relation: "SYSTEM", strokeIds: strokes.map(s => s.id), transcript: null, childIds: units.map(u => u.id), readingOrder: 0, confirmed: true });
    page.lineageIds = [...new Set(lineage)]; page.provenance = { generator: "affine-real-ink/1", config, family, index, transforms, pageSize: [794, 1123], originalWriters: "See source metadata; no invented IDs", relationDefinition: family === "SYSTEM_DEFINED" ? "Explicit generator relation, no invented brace strokes" : "INDEPENDENT_UNITS", alignment: family === "ALIGNED" ? "LEFT_BOUNDS_ALIGNED; no symbol-level equals GT in MathWriting" : undefined };
    page.annotation = { origin: "GENERATOR", status: "GENERATED_DETERMINISTIC", sourceChecksum: page.sourceChecksum, units, assisted: false };
    validateAnnotation(page, true); pages.push(page);
  }
  return pages;
}
export function assertNoSplitLeakage(pages: EvaluationPage[]) {
  const splits = new Map<string, string>(); for (const p of pages) for (const id of p.lineageIds) { if (splits.has(id) && splits.get(id) !== p.split) throw Error(`SPLIT_LEAKAGE:${id}`); splits.set(id, p.split); }
}
/** Browser XML parser. No DTD, external entity, delta syntax or raster substitution. */
export async function importInkML(text: string, name: string): Promise<EvaluationPage> {
  if (text.length > 2_000_000 || /<!DOCTYPE|<!ENTITY/i.test(text)) throw Error("UNSUPPORTED_XML");
  const xml = new DOMParser().parseFromString(text, "application/xml"); if (xml.querySelector("parsererror")) throw Error("INVALID_INKML");
  const nodes = [...xml.getElementsByTagName("*")], annotations = Object.fromEntries([...xml.documentElement.children].filter(n => n.localName === "annotation").map(n => [n.getAttribute("type") ?? "", n.textContent?.trim() ?? ""]));
  const channels = nodes.filter(n => n.localName === "channel").map(n => n.getAttribute("name")?.toUpperCase()); const x = Math.max(0, channels.indexOf("X")), y = channels.includes("Y") ? channels.indexOf("Y") : 1;
  const traces = nodes.filter(n => n.localName === "trace").map((node, i) => {
    if (/[!"']/.test(node.textContent ?? "")) throw Error("DELTA_INKML_UNSUPPORTED");
    return { id: node.getAttribute("id") ?? String(i), points: (node.textContent ?? "").split(",").filter(s => s.trim()).map(s => { const n = s.trim().split(/\s+/).map(Number); return { x: n[x], y: n[y], ...(channels.includes("T") ? { t: n[channels.indexOf("T")] } : {}) }; }) };
  });
  const page = await convertVectorSource({ id: `inkml-${(await hashValue(text)).slice(0, 16)}`, dataset: "USER_SUPPLIED_INKML", checksum: await hashValue(text), sourcePath: name, license: "USER_MUST_VERIFY_SOURCE_LICENSE", originalSplit: "UNKNOWN", inkCreationMethod: annotations.inkCreationMethod ?? "UNKNOWN", label: annotations.normalizedLabel || annotations.label || annotations.truth, labelField: annotations.normalizedLabel ? "normalizedLabel" : "label/truth", annotations, traces }, false);
  page.provenance.originalInkML = text; page.provenance.symbolAndMathMLMetadata = "Preserved in original XML; not interpreted as new structural GT";
  return page;
}
