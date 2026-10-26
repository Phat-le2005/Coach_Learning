"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getOcrPenStrokes = getOcrPenStrokes;
/** OCR operates on saved pen ink only; highlights are annotations. */
function getOcrPenStrokes(strokes) {
    return strokes.filter((stroke) => stroke.tool === "PEN" && stroke.points.length > 0);
}
