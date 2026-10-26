"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const node_test_1 = __importDefault(require("node:test"));
const strict_1 = __importDefault(require("node:assert/strict"));
const ink_math_js_1 = require("../src/features/math-workspace/utils/ink-math.js");
const types_js_1 = require("../src/features/math-workspace/types.js");
(0, node_test_1.default)("A4 dimensions conform to standard 1 : sqrt(2) aspect ratio", () => {
    const ratio = types_js_1.A4_HEIGHT / types_js_1.A4_WIDTH;
    const sqrt2 = Math.SQRT2;
    // Standard A4 794x1123 is within 0.1% of sqrt(2)
    strict_1.default.ok(Math.abs(ratio - sqrt2) < 0.01);
    strict_1.default.equal(types_js_1.A4_ASPECT_RATIO, types_js_1.A4_HEIGHT / types_js_1.A4_WIDTH);
});
(0, node_test_1.default)("normalizeCoordinate clamps and normalizes within [0, 1]", () => {
    strict_1.default.equal((0, ink_math_js_1.normalizeCoordinate)(0, 1000), 0);
    strict_1.default.equal((0, ink_math_js_1.normalizeCoordinate)(500, 1000), 0.5);
    strict_1.default.equal((0, ink_math_js_1.normalizeCoordinate)(1000, 1000), 1);
    strict_1.default.equal((0, ink_math_js_1.normalizeCoordinate)(-50, 1000), 0);
    strict_1.default.equal((0, ink_math_js_1.normalizeCoordinate)(1200, 1000), 1);
});
(0, node_test_1.default)("denormalizeCoordinate maps normalized value back to target dimension", () => {
    strict_1.default.equal((0, ink_math_js_1.denormalizeCoordinate)(0.5, 794), 397);
    strict_1.default.equal((0, ink_math_js_1.denormalizeCoordinate)(0, 1123), 0);
    strict_1.default.equal((0, ink_math_js_1.denormalizeCoordinate)(1, 1123), 1123);
});
(0, node_test_1.default)("distanceToSegmentSquared calculates exact squared perpendicular distance", () => {
    // Segment along X axis from (0, 0) to (10, 0)
    // Point at (5, 4) -> perpendicular distance is 4, distance squared is 16
    const distSq = (0, ink_math_js_1.distanceToSegmentSquared)(5, 4, 0, 0, 10, 0);
    strict_1.default.equal(distSq, 16);
    // Point beyond the end at (15, 0) -> closest point is (10, 0), distance squared is 25
    const endDistSq = (0, ink_math_js_1.distanceToSegmentSquared)(15, 0, 0, 0, 10, 0);
    strict_1.default.equal(endDistSq, 25);
});
(0, node_test_1.default)("strokeIntersectsPoint detects intersection for stroke eraser", () => {
    const stroke = {
        id: "test-stroke-1",
        tool: "PEN",
        color: "#0f172a",
        width: 2,
        points: [
            { x: 0.1, y: 0.1, pressure: 0.5 },
            { x: 0.5, y: 0.5, pressure: 0.5 },
        ],
    };
    // Point exactly on the midpoint (0.3, 0.3)
    strict_1.default.ok((0, ink_math_js_1.strokeIntersectsPoint)(stroke, 0.3, 0.3, 0.02));
    // Point near the stroke (0.31, 0.3)
    strict_1.default.ok((0, ink_math_js_1.strokeIntersectsPoint)(stroke, 0.31, 0.3, 0.02));
    // Point far away from stroke (0.8, 0.2)
    strict_1.default.ok(!(0, ink_math_js_1.strokeIntersectsPoint)(stroke, 0.8, 0.2, 0.02));
});
(0, node_test_1.default)("calculateStrokeBoundingBox calculates correct normalized bounds", () => {
    const stroke = {
        id: "test-stroke-2",
        tool: "PEN",
        color: "#0f172a",
        width: 2,
        points: [
            { x: 0.2, y: 0.4, pressure: 0.5 },
            { x: 0.7, y: 0.1, pressure: 0.5 },
            { x: 0.5, y: 0.9, pressure: 0.5 },
        ],
    };
    const bbox = (0, ink_math_js_1.calculateStrokeBoundingBox)(stroke);
    strict_1.default.equal(bbox.minX, 0.2);
    strict_1.default.equal(bbox.minY, 0.1);
    strict_1.default.equal(bbox.maxX, 0.7);
    strict_1.default.equal(bbox.maxY, 0.9);
});
