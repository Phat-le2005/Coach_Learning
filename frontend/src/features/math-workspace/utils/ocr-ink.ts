import type { InkStroke } from "@/lib/api/contracts";

/** OCR operates on saved pen ink only; highlights are annotations. */
export function getOcrPenStrokes(strokes: InkStroke[]): InkStroke[] {
  return strokes.filter((stroke) => stroke.tool === "PEN" && stroke.points.length > 0);
}
