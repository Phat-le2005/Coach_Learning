import type { InkStroke } from "@/lib/api/contracts";
import type { PageOcrRegion } from "./page-ocr";
import { getOcrPenStrokes } from "./ocr-ink";
import {
  detectStructuralCandidates,
  type StructureCandidate,
  type StructureKind,
} from "./structural-candidate-engine";

/**
 * Read-only comparison of the ORIGINAL page segmentation and structural proposals.
 * Never passes these candidates into OCR drafts or student step persistence.
 *
 * Parent nodes intentionally list all descendant stroke IDs. Provenance
 * diagnostics therefore count TOP-LEVEL candidates only, not child references.
 */
export interface OcrShadowRegionOverlap {
  index: number;
  regionId: string;
  strokeCount: number;
}

export interface OcrShadowCandidate {
  id: string;
  kind: StructureKind;
  strokeIds: string[];
  children: Array<{ id: string; kind: StructureKind; strokeIds: string[] }>;
  reasons: string[];
  overlappingBaselineRegions: OcrShadowRegionOverlap[];
}

export interface OcrShadowQaReport {
  sourcePenStrokeCount: number;
  baselineRegionCount: number;
  structuralCandidateCount: number;
  baselineMissingStrokeIds: string[];
  baselineDuplicateStrokeIds: string[];
  shadowMissingStrokeIds: string[];
  shadowDuplicateStrokeIds: string[];
  shadowUnknownStrokeIds: string[];
  candidates: OcrShadowCandidate[];
}

function membershipCounts(groups: readonly (readonly string[])[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const ids of groups) {
    for (const id of ids) counts.set(id, (counts.get(id) ?? 0) + 1);
  }
  return counts;
}

function missingAndDuplicates(
  expected: ReadonlySet<string>,
  counts: ReadonlyMap<string, number>,
): { missing: string[]; duplicates: string[]; unknown: string[] } {
  return {
    missing: [...expected].filter((id) => !counts.has(id)),
    duplicates: [...counts].filter(([, count]) => count > 1).map(([id]) => id),
    unknown: [...counts.keys()].filter((id) => !expected.has(id)),
  };
}

function describeCandidate(
  candidate: StructureCandidate,
  regions: readonly PageOcrRegion[],
): OcrShadowCandidate {
  const ids = new Set(candidate.sourceStrokeIds);
  const overlappingBaselineRegions = regions.flatMap((region, index) => {
    const strokeCount = region.strokes.filter((stroke) => ids.has(stroke.id)).length;
    return strokeCount > 0 ? [{ index, regionId: region.id, strokeCount }] : [];
  });
  return {
    id: candidate.id,
    kind: candidate.kind,
    strokeIds: [...candidate.sourceStrokeIds],
    children: candidate.children.map((child) => ({
      id: child.id,
      kind: child.kind,
      strokeIds: [...child.sourceStrokeIds],
    })),
    reasons: [...candidate.reasons],
    overlappingBaselineRegions,
  };
}

export function buildOcrShadowQaReport(
  pageStrokes: readonly InkStroke[],
  initialRegions: readonly PageOcrRegion[],
): OcrShadowQaReport {
  const pen = getOcrPenStrokes([...pageStrokes]);
  const expectedIds = new Set(pen.map((stroke) => stroke.id));

  const baselineCounts = membershipCounts(
    initialRegions.map((region) => region.strokes.map((stroke) => stroke.id)),
  );
  const baseline = missingAndDuplicates(expectedIds, baselineCounts);

  const proposed = detectStructuralCandidates([...pageStrokes]);
  const shadowCounts = membershipCounts(proposed.map((node) => node.sourceStrokeIds));
  const shadow = missingAndDuplicates(expectedIds, shadowCounts);

  return {
    sourcePenStrokeCount: pen.length,
    baselineRegionCount: initialRegions.length,
    structuralCandidateCount: proposed.length,
    baselineMissingStrokeIds: baseline.missing,
    baselineDuplicateStrokeIds: baseline.duplicates,
    shadowMissingStrokeIds: shadow.missing,
    shadowDuplicateStrokeIds: shadow.duplicates,
    shadowUnknownStrokeIds: shadow.unknown,
    candidates: proposed.map((node) => describeCandidate(node, initialRegions)),
  };
}
