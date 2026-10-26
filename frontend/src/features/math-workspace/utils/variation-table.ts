import type { VariationTablePayload, VariationTablePoint, VariationTableInterval } from "@/lib/api/contracts";

export type DraftSign = VariationTableInterval["sign"] | "";
export interface VariationTableDraft {
  points: VariationTablePoint[];
  intervals: Array<{ sign: DraftSign; trend: VariationTableInterval["trend"] }>;
}

const blankPoint = (): VariationTablePoint => ({ x: "", derivative: "", y: "" });
const blankInterval = () => ({ sign: "" as DraftSign, trend: "UNKNOWN" as const });

export function createVariationTableDraft(): VariationTableDraft {
  return { points: [blankPoint(), blankPoint(), blankPoint()],
    intervals: [blankInterval(), blankInterval()] };
}

export function trendForSign(sign: DraftSign): VariationTableInterval["trend"] {
  return sign === "+" ? "UP" : sign === "-" ? "DOWN" : sign === "0" ? "FLAT" : "UNKNOWN";
}

export function addVariationPoint(draft: VariationTableDraft): VariationTableDraft {
  if (draft.points.length >= 12) return draft;
  return {
    points: [...draft.points.slice(0, -1), blankPoint(), draft.points[draft.points.length - 1]],
    intervals: [...draft.intervals.slice(0, -1), blankInterval(), blankInterval()],
  };
}

export function removeVariationPoint(draft: VariationTableDraft): VariationTableDraft {
  if (draft.points.length <= 2) return draft;
  return {
    points: [...draft.points.slice(0, -2), draft.points[draft.points.length - 1]],
    intervals: [...draft.intervals.slice(0, -2), blankInterval()],
  };
}

export function validateVariationTable(draft: VariationTableDraft): string | null {
  if (draft.points.length < 2 || draft.points.length > 12 || draft.intervals.length !== draft.points.length - 1) {
    return "TABLE_COLUMNS_INVALID";
  }
  const xs = draft.points.map((point) => point.x.trim());
  if (xs.some((value) => !value || value.length > 80) || new Set(xs).size !== xs.length) {
    return "TABLE_X_REQUIRED_OR_DUPLICATE";
  }
  if (draft.points.some((point) => point.y.length > 80)) return "TABLE_VALUE_TOO_LONG";
  if (draft.intervals.some((interval) => !interval.sign || interval.trend !== trendForSign(interval.sign))) {
    return "TABLE_SIGNS_REQUIRED";
  }
  return null;
}

export function toVariationTablePayload(draft: VariationTableDraft): VariationTablePayload {
  const error = validateVariationTable(draft);
  if (error) throw new Error(error);
  return {
    version: 1,
    points: draft.points.map((point) => ({ x: point.x.trim(), derivative: point.derivative, y: point.y.trim() })),
    intervals: draft.intervals.map((interval) => ({
      sign: interval.sign as VariationTableInterval["sign"], trend: trendForSign(interval.sign),
    })),
  };
}
