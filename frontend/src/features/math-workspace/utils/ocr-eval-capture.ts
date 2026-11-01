import type { InkStroke } from "@/lib/api/contracts";
import type { PageOcrRegion } from "./page-ocr";

/**
 * Developer-only OCR troubleshooting snapshot. Contains raw handwriting.
 * Do not commit or share student captures without appropriate permission.
 *
 * This is NOT annotated ground truth and is never submitted for grading.
 */
export interface OcrEvalCaptureV1 {
  schemaVersion: 1;
  sourceKind: "MATHCANVAS_INK";
  pageIndex: number;
  strokes: InkStroke[];
  segmentation: {
    algorithm: "v2";
    regions: Array<{
      id: string;
      strokeIds: string[];
      bounds: PageOcrRegion["bounds"];
    }>;
  };
  diagnostics: {
    missingPenStrokeIds: string[];
    repeatedPenStrokeIds: string[];
    unknownRegionStrokeIds: string[];
  };
}

/** Preserve raw ink even if segmentation is incomplete or incorrect. */
export function createOcrEvalCapture(
  pageIndex: number,
  strokes: readonly InkStroke[],
  regions: readonly PageOcrRegion[],
): OcrEvalCaptureV1 {
  if (!Number.isInteger(pageIndex) || pageIndex < 0) {
    throw new Error("OCR_CAPTURE_INVALID_PAGE");
  }

  // Copy points as well: subsequent pen edits must never mutate this snapshot.
  const snapshot = strokes.map((stroke) => ({
    ...stroke,
    points: stroke.points.map((point) => ({ ...point })),
  }));

  const penIds = new Set(
    snapshot.filter((stroke) => stroke.tool === "PEN" && stroke.points.length > 0)
      .map((stroke) => stroke.id),
  );
  const counts = new Map<string, number>();
  const unknown = new Set<string>();

  const capturedRegions = regions.map((region) => {
    const strokeIds = region.strokes.map((stroke) => stroke.id);
    for (const id of strokeIds) {
      if (!penIds.has(id)) {
        unknown.add(id);
      } else {
        counts.set(id, (counts.get(id) ?? 0) + 1);
      }
    }
    return {
      id: region.id,
      strokeIds,
      bounds: { ...region.bounds },
    };
  });

  return {
    schemaVersion: 1,
    sourceKind: "MATHCANVAS_INK",
    pageIndex,
    strokes: snapshot,
    segmentation: { algorithm: "v2", regions: capturedRegions },
    diagnostics: {
      missingPenStrokeIds: [...penIds].filter((id) => !counts.has(id)),
      repeatedPenStrokeIds: [...counts].filter(([, n]) => n > 1).map(([id]) => id),
      unknownRegionStrokeIds: [...unknown],
    },
  };
}
