import type { InkStroke } from "@/lib/api/contracts";
import {
  segmentPageInk_v2,
  type PageOcrRegion,
  type InkBounds,
} from "./page-ocr";
import { getOcrPenStrokes } from "./ocr-ink";

const A4_WIDTH = 794;
const A4_HEIGHT = 1123;

// ============================================================================
// 1. Data Contracts for Structural Candidate Engine (Module B)
// ============================================================================

export type StructureKind =
  | "SYSTEM"        // Dấu ngoặc nhọn { bao 2+ biểu thức (hệ phương trình)
  | "ALTERNATIVES"  // Dấu ngoặc vuông [ bao 2+ biểu thức (nhánh nghiệm)
  | "FRACTION"      // Phân số: gạch phân số kết nối tử số và mẫu số
  | "INDEPENDENT"   // Biểu thức hoặc dòng độc lập
  | "UNKNOWN";      // Không đủ bằng chứng hình học tin cậy

export interface StructureCandidate {
  id: string;
  kind: StructureKind;
  sourceStrokeIds: string[];
  bounds: InkBounds;
  children: StructureCandidate[];
  reasons: string[];
}

export interface StructuralEngineOptions {
  /** Minimum vertical span relative to median character height to consider a multi-line bracket (default: 1.8) */
  minBracketSpanRatio?: number;
  /** Maximum width-to-height aspect ratio for vertical delimiter bracket (default: 0.48) */
  maxBracketAspectRatio?: number;
  /** Fraction horizontal overlap threshold (default: 0.35) */
  fractionOverlapThreshold?: number;
}

interface StrokeGeometry {
  stroke: InkStroke;
  bounds: InkBounds;
  widthPx: number;
  heightPx: number;
  aspectRatio: number; // width / height
  originalIndex: number;
}

// ============================================================================
// 2. Geometric Feature Extractors & Helper Functions
// ============================================================================

function computeBounds(strokes: readonly InkStroke[]): InkBounds {
  if (strokes.length === 0) {
    return { left: 0, top: 0, right: 0, bottom: 0 };
  }
  let left = Infinity, top = Infinity, right = -Infinity, bottom = -Infinity;
  for (const s of strokes) {
    for (const p of s.points) {
      if (p.x < left) left = p.x;
      if (p.y < top) top = p.y;
      if (p.x > right) right = p.x;
      if (p.y > bottom) bottom = p.y;
    }
  }
  return { left, top, right, bottom };
}

function computeOverlap(a: InkBounds, b: InkBounds): { horizontal: number; vertical: number } {
  const hOverlap = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
  const minWidth = Math.min(a.right - a.left, b.right - b.left);
  const hRatio = minWidth > 0 ? hOverlap / minWidth : 0;

  const vOverlap = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  const minHeight = Math.min(a.bottom - a.top, b.bottom - b.top);
  const vRatio = minHeight > 0 ? vOverlap / minHeight : 0;

  return { horizontal: hRatio, vertical: vRatio };
}

/**
 * Classifies whether a tall vertical stroke is a curly brace `{` or a square bracket `[`.
 * Analyzes curvature and x-profile along the vertical axis:
 * - Curly brace `{`: Has a central cusp/tip extending leftward around middle height (35%-65%), with top/bottom endpoints curving right.
 * - Square bracket `[`: Has a straight vertical spine (uniform x along middle) with horizontal orthogonal arms at top and bottom.
 */
export function classifyBracketGeometry(stroke: InkStroke): {
  type: "CURLY" | "SQUARE" | "UNKNOWN";
  /** Rule score only; NOT a calibrated probability. */
  heuristicScore: number;
  reasons: string[];
} {
  const points = stroke.points;
  if (points.length < 3) {
    return { type: "UNKNOWN", heuristicScore: 0, reasons: ["Too few points for bracket shape analysis"] };
  }

  const ys = points.map((p) => p.y);
  const xs = points.map((p) => p.x);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const totalH = maxY - minY;
  const totalW = maxX - minX;

  if (totalH <= 0 || totalW <= 0) {
    return { type: "UNKNOWN", heuristicScore: 0, reasons: ["Degenerate stroke dimensions"] };
  }

  // Divide stroke points into 3 vertical zones: Top (0%-30%), Middle (35%-65%), Bottom (70%-100%)
  const topPoints = points.filter((p) => (p.y - minY) / totalH <= 0.3);
  const midPoints = points.filter((p) => {
    const relY = (p.y - minY) / totalH;
    return relY >= 0.35 && relY <= 0.65;
  });
  const botPoints = points.filter((p) => (p.y - minY) / totalH >= 0.7);

  if (midPoints.length === 0) {
    return { type: "UNKNOWN", heuristicScore: 0, reasons: ["Missing middle segment"] };
  }

  const midMinX = Math.min(...midPoints.map((p) => p.x));
  const topMinX = topPoints.length > 0 ? Math.min(...topPoints.map((p) => p.x)) : minX;
  const botMinX = botPoints.length > 0 ? Math.min(...botPoints.map((p) => p.x)) : minX;
  const topMaxX = topPoints.length > 0 ? Math.max(...topPoints.map((p) => p.x)) : maxX;
  const botMaxX = botPoints.length > 0 ? Math.max(...botPoints.map((p) => p.x)) : maxX;

  // Geometric Invariant to separate Curly brace '{' from Square bracket '[':
  // - In '{' (CURLY), the central cusp points left (midMinX ≈ minX), while both top and bottom
  //   endpoints hook to the right (topMinX > minX + delta and botMinX > minX + delta).
  // - In '[' (SQUARE), the vertical spine forms a straight left wall from top to bottom
  //   (topMinX ≈ minX, midMinX ≈ minX, botMinX ≈ minX), with horizontal arms extending to the right
  //   at the top and bottom (topMaxX > minX + delta, botMaxX > minX + delta).
  const topIndent = topMinX - midMinX;
  const botIndent = botMinX - midMinX;
  const threshold = Math.max(0.003, totalW * 0.15);

  const centralLeftCusp = topIndent > threshold && botIndent > threshold;
  // A typical left curly brace can have a right-facing central cusp and
  // two left-facing outer lobes; do not require the synthetic reversed shape.
  const centralRightCusp = -topIndent > threshold && -botIndent > threshold;
  const isCurly = centralLeftCusp || centralRightCusp;
  const isSquare =
    Math.abs(topIndent) <= threshold &&
    Math.abs(botIndent) <= threshold &&
    (topMaxX - minX > threshold || botMaxX - minX > threshold);

  if (isCurly) {
    return {
      type: "CURLY",
      heuristicScore: 0.9,
      reasons: [
        centralRightCusp
          ? "Central rightward cusp detected between upper/lower left lobes"
          : "Central leftward cusp detected with indented top and bottom endpoints",
        `topIndent: ${topIndent.toFixed(4)}, botIndent: ${botIndent.toFixed(4)}`,
      ],
    };
  }

  if (isSquare) {
    return {
      type: "SQUARE",
      heuristicScore: 0.88,
      reasons: [
        "Straight vertical spine spanning top, middle, and bottom with horizontal arms",
        `topArm: ${(topMaxX - minX).toFixed(4)}, botArm: ${(botMaxX - minX).toFixed(4)}`,
      ],
    };
  }

  // Fallback heuristic: if middle has any leftward cusp relative to either endpoint
  if (topIndent > 0.002 || botIndent > 0.002) {
    return {
      type: "CURLY",
      heuristicScore: 0.65,
      reasons: ["Partial cusp indicates curly brace"],
    };
  }

  return {
    type: "UNKNOWN",
    heuristicScore: 0.4,
    reasons: ["Ambiguous bracket geometry; insufficient cusp or arm distinction"],
  };
}

/**
 * Checks if a candidate stroke is a genuine fraction bar with numerator and denominator.
 * Reuses strict parity with segmentation v2 (guards against '=' and minus sign).
 */
function isStructuralFraction(
  bar: StrokeGeometry,
  allGeoms: StrokeGeometry[],
  medianHeight: number,
): { isFraction: boolean; numeratorStrokes: InkStroke[]; denominatorStrokes: InkStroke[]; reasons: string[] } {
  const aspectRatio = bar.aspectRatio;
  const medianHeightPx = medianHeight * A4_HEIGHT;

  if (aspectRatio < 3.8 || bar.heightPx > Math.max(8, medianHeightPx * 0.6) || bar.widthPx < 14) {
    return { isFraction: false, numeratorStrokes: [], denominatorStrokes: [], reasons: ["Not a fraction bar geometry"] };
  }

  // Guard 1: Equals sign '=' check (parallel horizontal bars)
  for (const other of allGeoms) {
    if (other.stroke.id === bar.stroke.id) continue;
    if (other.aspectRatio >= 3.5 && other.heightPx <= medianHeightPx * 0.6) {
      const vDistPx = Math.abs((bar.bounds.top + bar.bounds.bottom) / 2 - (other.bounds.top + other.bounds.bottom) / 2) * A4_HEIGHT;
      const hOverlap = computeOverlap(bar.bounds, other.bounds).horizontal;
      const lenDiff = Math.abs(other.widthPx - bar.widthPx) / Math.max(bar.widthPx, other.widthPx);
      if (vDistPx < 14 && hOverlap > 0.65 && lenDiff < 0.35) {
        return { isFraction: false, numeratorStrokes: [], denominatorStrokes: [], reasons: ["Equals sign guard triggered"] };
      }
    }
  }

  // Guard 2: Find numerators and denominators
  const barY = (bar.bounds.top + bar.bounds.bottom) / 2;
  const maxGap = Math.max(0.045, medianHeight * 2.2);
  const numGeoms: StrokeGeometry[] = [];
  const denGeoms: StrokeGeometry[] = [];

  for (const other of allGeoms) {
    if (other.stroke.id === bar.stroke.id) continue;
    const hOverlap = computeOverlap(bar.bounds, other.bounds).horizontal;
    if (hOverlap > 0.35) {
      const otherY = (other.bounds.top + other.bounds.bottom) / 2;
      const vDist = otherY - barY;
      if (vDist < -0.004 && Math.abs(vDist) <= maxGap) {
        numGeoms.push(other);
      } else if (vDist > 0.004 && Math.abs(vDist) <= maxGap) {
        denGeoms.push(other);
      }
    }
  }

  if (numGeoms.length === 0 || denGeoms.length === 0) {
    return { isFraction: false, numeratorStrokes: [], denominatorStrokes: [], reasons: ["Missing numerator or denominator"] };
  }

  return {
    isFraction: true,
    numeratorStrokes: numGeoms.map((g) => g.stroke),
    denominatorStrokes: denGeoms.map((g) => g.stroke),
    reasons: ["Valid fraction bar with overlapping numerator and denominator"],
  };
}

// ============================================================================
// 3. Structural Candidate Engine Core (Prototype)
// ============================================================================

/**
 * Recognizes hierarchical mathematical structures (SYSTEM, ALTERNATIVES, FRACTION, INDEPENDENT).
 * Enforces key invariants:
 * - 100% stroke provenance conservation (no dropped strokes).
 * - Distinguishes SYSTEM ({) from ALTERNATIVES ([).
 * - Avoids false merges between independent lines (does not merge lines merely due to proximity).
 * - Invariant to drawing sequence: bracket drawn before or after equations yields identical grouping.
 */
export function detectStructuralCandidates(
  strokes: readonly InkStroke[],
  options: StructuralEngineOptions = {},
): StructureCandidate[] {
  const pen = getOcrPenStrokes([...strokes]);
  if (pen.length === 0) {
    return [];
  }

  const minBracketSpanRatio = options.minBracketSpanRatio ?? 1.8;
  const maxBracketAspectRatio = options.maxBracketAspectRatio ?? 0.48;

  // 1. Calculate bounding boxes and median character height
  const geoms: StrokeGeometry[] = pen.map((stroke, originalIndex) => {
    const bounds = computeBounds([stroke]);
    const widthPx = (bounds.right - bounds.left) * A4_WIDTH;
    const heightPx = (bounds.bottom - bounds.top) * A4_HEIGHT;
    return {
      stroke,
      bounds,
      widthPx,
      heightPx,
      aspectRatio: widthPx / Math.max(0.5, heightPx),
      originalIndex,
    };
  });

  const charHeights = geoms
    .map((g) => g.bounds.bottom - g.bounds.top)
    .filter((h) => h * A4_HEIGHT >= 8)
    .sort((a, b) => a - b);
  const medianHeight = charHeights.length
    ? charHeights[Math.floor(charHeights.length / 2)]
    : 20 / A4_HEIGHT;

  // 2. Identify candidate multi-line grouping brackets
  // Conditions:
  // - Tall vertical stroke: height >= medianHeight * minBracketSpanRatio
  // - Narrow horizontal span: aspect ratio (width / height) <= maxBracketAspectRatio
  const bracketCandidates = geoms.filter(
    (g) =>
      g.bounds.bottom - g.bounds.top >= medianHeight * minBracketSpanRatio &&
      g.aspectRatio <= maxBracketAspectRatio,
  );

  const usedStrokeIds = new Set<string>();
  const candidates: StructureCandidate[] = [];

  // 3. Process Left Delimiter Brackets (Systems & Alternatives)
  for (const bracketGeom of bracketCandidates) {
    if (usedStrokeIds.has(bracketGeom.stroke.id)) continue;

    // A grouping bracket must sit on the LEFT side of the expressions it groups.
    // Candidate child strokes must have horizontal position mostly to the right of bracket.
    const bracketBounds = bracketGeom.bounds;
    const bracketRight = bracketBounds.right;
    const vSpanTop = bracketBounds.top - medianHeight * 0.4;
    const vSpanBottom = bracketBounds.bottom + medianHeight * 0.4;

    // First gather candidates at the correct height, then follow the
    // left-adjacent horizontal ink cluster. The previous half-plane rule
    // ("everything to the right") incorrectly swallowed other columns.
    // Prefer leaving an uncertain/long expression ungrouped to a false merge.
    const horizontalCandidates = geoms.filter((other) => {
      if (other.stroke.id === bracketGeom.stroke.id || usedStrokeIds.has(other.stroke.id)) return false;
      return other.bounds.left >= bracketRight - 0.005 &&
        other.bounds.top >= vSpanTop && other.bounds.bottom <= vSpanBottom;
    }).sort((a, b) => a.bounds.left - b.bounds.left);

    const maxHorizontalGap = Math.max(0.045, medianHeight * 2.3);
    const enclosedStrokes: StrokeGeometry[] = [];
    let connectedRightEdge = bracketRight;
    for (const other of horizontalCandidates) {
      if (other.bounds.left - connectedRightEdge > maxHorizontalGap) break;
      enclosedStrokes.push(other);
      connectedRightEdge = Math.max(connectedRightEdge, other.bounds.right);
    }

    // A multi-line bracket requires at least 2 distinct expressions / lines
    if (enclosedStrokes.length >= 2) {
      // Group enclosed strokes into lines using segmentation v2
      const innerStrokes = enclosedStrokes.map((g) => g.stroke);
      const innerRegions = segmentPageInk_v2(innerStrokes);

      if (innerRegions.length >= 2) {
        // Classify whether bracket is Curly { (SYSTEM) or Square [ (ALTERNATIVES)
        const bracketClass = classifyBracketGeometry(bracketGeom.stroke);
        // A tall stroke is not automatically a mathematical delimiter.
        // If its shape is ambiguous, retain the ink for the ordinary path;
        // never consume unrelated equations into an UNKNOWN parent.
        if (bracketClass.type === "UNKNOWN") continue;
        const structureKind: StructureKind =
          bracketClass.type === "CURLY"
            ? "SYSTEM"
            : bracketClass.type === "SQUARE"
              ? "ALTERNATIVES"
              : "UNKNOWN";

        const childCandidates: StructureCandidate[] = innerRegions.map((reg, idx) => ({
          id: `${reg.id}-sub-${idx}`,
          kind: "INDEPENDENT",
          sourceStrokeIds: reg.strokes.map((s) => s.id),
          bounds: { ...reg.bounds },
          children: [],
          reasons: [`Sub-expression ${idx + 1} enclosed by ${structureKind}`],
        }));

        const allGroupStrokes = [bracketGeom.stroke, ...innerStrokes];
        const groupBounds = computeBounds(allGroupStrokes);

        candidates.push({
          id: `struct-${bracketGeom.stroke.id}`,
          kind: structureKind,
          sourceStrokeIds: allGroupStrokes.map((s) => s.id),
          bounds: groupBounds,
          children: childCandidates,
          reasons: [
            `Left delimiter spans ${innerRegions.length} expressions`,
            ...bracketClass.reasons,
          ],
        });

        usedStrokeIds.add(bracketGeom.stroke.id);
        for (const s of innerStrokes) {
          usedStrokeIds.add(s.id);
        }
      }
    }
  }

  // 4. Process Remaining Strokes: Fraction checks & Independent expressions
  const remainingStrokes = pen.filter((s) => !usedStrokeIds.has(s.id));
  if (remainingStrokes.length > 0) {
    // Run base segmentation on remaining strokes
    const remainingRegions = segmentPageInk_v2(remainingStrokes);

    for (const reg of remainingRegions) {
      // Check if this region represents an isolated fraction structure
      const regGeoms = reg.strokes.map((s) => {
        const bounds = computeBounds([s]);
        const widthPx = (bounds.right - bounds.left) * A4_WIDTH;
        const heightPx = (bounds.bottom - bounds.top) * A4_HEIGHT;
        return {
          stroke: s,
          bounds,
          widthPx,
          heightPx,
          aspectRatio: widthPx / Math.max(0.5, heightPx),
          originalIndex: 0,
        };
      });

      // Find fraction bar within this region
      let fractionFound = false;
      for (const geom of regGeoms) {
        const fracCheck = isStructuralFraction(geom, regGeoms, medianHeight);
        if (fracCheck.isFraction) {
          const numBounds = computeBounds(fracCheck.numeratorStrokes);
          const denBounds = computeBounds(fracCheck.denominatorStrokes);

          const fractionIds = new Set([
            geom.stroke.id,
            ...fracCheck.numeratorStrokes.map((s) => s.id),
            ...fracCheck.denominatorStrokes.map((s) => s.id),
          ]);
          const fractionStrokes = reg.strokes.filter((s) => fractionIds.has(s.id));
          candidates.push({
            id: `frac-${reg.id}`,
            kind: "FRACTION",
            // Do not silently absorb an inline suffix/sibling into the fraction.
            sourceStrokeIds: fractionStrokes.map((s) => s.id),
            bounds: { ...reg.bounds },
            children: [
              {
                id: `frac-num-${reg.id}`,
                kind: "INDEPENDENT",
                sourceStrokeIds: fracCheck.numeratorStrokes.map((s) => s.id),
                bounds: numBounds,
                children: [],
                reasons: ["Fraction numerator"],
              },
              {
                id: `frac-den-${reg.id}`,
                kind: "INDEPENDENT",
                sourceStrokeIds: fracCheck.denominatorStrokes.map((s) => s.id),
                bounds: denBounds,
                children: [],
                reasons: ["Fraction denominator"],
              },
            ],
            reasons: ["Fraction structure: horizontal bar dividing numerator and denominator"],
          });
          // Preserve non-fraction strokes as standalone regions rather than
          // silently including them in the fraction parent.
          const remainder = reg.strokes.filter((s) => !fractionIds.has(s.id));
          if (remainder.length > 0) {
            for (const extra of segmentPageInk_v2(remainder)) {
              candidates.push({
                id: `residual-${extra.id}`,
                kind: "INDEPENDENT",
                sourceStrokeIds: extra.strokes.map((s) => s.id),
                bounds: { ...extra.bounds },
                children: [],
                reasons: ["Stroke group adjacent to, but not part of, the fraction"],
              });
            }
          }
          fractionFound = true;
          break;
        }
      }

      if (!fractionFound) {
        // Standalone independent expression / line
        candidates.push({
          id: reg.id,
          kind: "INDEPENDENT",
          sourceStrokeIds: reg.strokes.map((s) => s.id),
          bounds: { ...reg.bounds },
          children: [],
          reasons: ["Independent mathematical line without structural enclosing delimiter"],
        });
      }
    }
  }

  // Sort top-level candidates in natural visual reading order (top-to-bottom, left-to-right)
  return candidates.sort((a, b) => a.bounds.top - b.bounds.top || a.bounds.left - b.bounds.left);
}
