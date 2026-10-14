import type { InkPoint, InkStroke } from "../types";

export function generateUuid(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

export function normalizeCoordinate(val: number, dimension: number): number {
  if (dimension <= 0) return 0;
  return clamp(val / dimension, 0, 1);
}

export function denormalizeCoordinate(normVal: number, dimension: number): number {
  return normVal * dimension;
}

export function distanceSquared(x1: number, y1: number, x2: number, y2: number): number {
  const dx = x2 - x1;
  const dy = y2 - y1;
  return dx * dx + dy * dy;
}

export function distanceToSegmentSquared(
  px: number,
  py: number,
  x1: number,
  y1: number,
  x2: number,
  y2: number,
): number {
  const l2 = distanceSquared(x1, y1, x2, y2);
  if (l2 === 0) return distanceSquared(px, py, x1, y1);
  let t = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2;
  t = clamp(t, 0, 1);
  return distanceSquared(px, py, x1 + t * (x2 - x1), y1 + t * (y2 - y1));
}

export function strokeIntersectsPoint(
  stroke: InkStroke,
  normX: number,
  normY: number,
  thresholdNorm: number,
): boolean {
  if (!stroke.points || stroke.points.length === 0) return false;
  const thresholdSq = thresholdNorm * thresholdNorm;

  if (stroke.points.length === 1) {
    const p = stroke.points[0];
    return distanceSquared(normX, normY, p.x, p.y) <= thresholdSq;
  }

  for (let i = 0; i < stroke.points.length - 1; i++) {
    const p1 = stroke.points[i];
    const p2 = stroke.points[i + 1];
    const distSq = distanceToSegmentSquared(normX, normY, p1.x, p1.y, p2.x, p2.y);
    if (distSq <= thresholdSq) {
      return true;
    }
  }

  return false;
}

export function calculateStrokeBoundingBox(stroke: InkStroke): {
  minX: number;
  minY: number;
  maxX: number;
  maxY: number;
} {
  let minX = 1;
  let minY = 1;
  let maxX = 0;
  let maxY = 0;

  for (const pt of stroke.points) {
    if (pt.x < minX) minX = pt.x;
    if (pt.y < minY) minY = pt.y;
    if (pt.x > maxX) maxX = pt.x;
    if (pt.y > maxY) maxY = pt.y;
  }

  return { minX, minY, maxX, maxY };
}
