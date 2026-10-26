"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.generateUuid = generateUuid;
exports.clamp = clamp;
exports.normalizeCoordinate = normalizeCoordinate;
exports.denormalizeCoordinate = denormalizeCoordinate;
exports.distanceSquared = distanceSquared;
exports.distanceToSegmentSquared = distanceToSegmentSquared;
exports.strokeIntersectsPoint = strokeIntersectsPoint;
exports.calculateStrokeBoundingBox = calculateStrokeBoundingBox;
function generateUuid() {
    if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
        return crypto.randomUUID();
    }
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
        const r = (Math.random() * 16) | 0;
        const v = c === "x" ? r : (r & 0x3) | 0x8;
        return v.toString(16);
    });
}
function clamp(val, min, max) {
    return Math.max(min, Math.min(max, val));
}
function normalizeCoordinate(val, dimension) {
    if (dimension <= 0)
        return 0;
    return clamp(val / dimension, 0, 1);
}
function denormalizeCoordinate(normVal, dimension) {
    return normVal * dimension;
}
function distanceSquared(x1, y1, x2, y2) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    return dx * dx + dy * dy;
}
function distanceToSegmentSquared(px, py, x1, y1, x2, y2) {
    const l2 = distanceSquared(x1, y1, x2, y2);
    if (l2 === 0)
        return distanceSquared(px, py, x1, y1);
    let t = ((px - x1) * (x2 - x1) + (py - y1) * (y2 - y1)) / l2;
    t = clamp(t, 0, 1);
    return distanceSquared(px, py, x1 + t * (x2 - x1), y1 + t * (y2 - y1));
}
function strokeIntersectsPoint(stroke, normX, normY, thresholdNorm) {
    if (!stroke.points || stroke.points.length === 0)
        return false;
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
function calculateStrokeBoundingBox(stroke) {
    let minX = 1;
    let minY = 1;
    let maxX = 0;
    let maxY = 0;
    for (const pt of stroke.points) {
        if (pt.x < minX)
            minX = pt.x;
        if (pt.y < minY)
            minY = pt.y;
        if (pt.x > maxX)
            maxX = pt.x;
        if (pt.y > maxY)
            maxY = pt.y;
    }
    return { minX, minY, maxX, maxY };
}
