import type { GraphBounds } from "./fit-camera";

type Point = [number, number, number];

/** Choose a readable window, retaining all curve vertices for an explicit full view.
 * Distant tails must not shrink roots/turning points to a few pixels. Coordinates
 * and axis scale are never changed, and gaps are not bridged when finding features.
 */
export function frameCurve(segments: readonly (readonly Point[])[], full: GraphBounds): { bounds: GraphBounds; focused: boolean } {
  const width = Math.max(1, full.max[0] - full.min[0]);
  const height = full.max[1] - full.min[1];
  if (height <= width * 2.5) return { bounds: full, focused: false };
  const middle = (full.min[0] + full.max[0]) / 2;
  const central = segments.flatMap((segment) => segment.filter((point) => Math.abs(point[0] - middle) <= width * .1).map((point) => point[1])).sort((a, b) => a - b);
  if (!central.length) return { bounds: full, focused: false };
  const centralY = central[Math.floor(central.length / 2)];
  const features = [centralY];
  for (const segment of segments) for (let i = 0; i < segment.length; i++) {
    const y = segment[i][1];
    // A distant crossing on a translated tail must not drag the view back to O.
    if (Math.abs(centralY) <= width * 2 && (y === 0 || i > 0 && (y < 0) !== (segment[i - 1][1] < 0))) features.push(0);
    if (i > 0 && i < segment.length - 1) {
      const before = y - segment[i - 1][1], after = segment[i + 1][1] - y;
      if (before * after <= 0 && (before !== 0 || after !== 0)) features.push(y);
    }
  }
  const low = Math.min(...features), high = Math.max(...features);
  const center = (low + high) / 2, half = Math.max(width, high - low) / 2;
  if (half * 2 >= height * .8) return { bounds: full, focused: false };
  return { bounds: { min: [full.min[0], center - half, full.min[2]], max: [full.max[0], center + half, full.max[2]] }, focused: true };
}
