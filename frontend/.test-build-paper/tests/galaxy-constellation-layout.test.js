"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const galaxy_constellation_layout_1 = require("../src/features/knowledge-forest/galaxy-constellation-layout");
const states = [
    "MASTERED",
    "LEARNING",
    "PRACTICING",
    "WEAK",
    "REVIEW_DUE",
    "NOT_STARTED",
];
function problemType(chapter, topic, leaf) {
    const state = states[(chapter + topic + leaf) % states.length];
    const hasEvidence = state !== "NOT_STARTED";
    return {
        id: `pt-${chapter}-${topic}-${leaf}`,
        code: `PT_${chapter}_${topic}_${leaf}`,
        name: `Dạng bài ${chapter}.${topic}.${leaf}`,
        topicId: `topic-${chapter}-${topic}`,
        topicName: `Chủ đề ${chapter}.${topic}`,
        chapterId: `chapter-${chapter}`,
        chapterName: `Chương ${chapter}`,
        masteryScore: hasEvidence ? 64 : undefined,
        rawMasteryScore: hasEvidence ? 0.64 : 0,
        confidence: hasEvidence ? 70 : undefined,
        attemptCount: hasEvidence ? 4 : 0,
        correctCount: hasEvidence ? 3 : 0,
        state,
        lastPracticedAt: hasEvidence ? "2026-10-09T00:00:00Z" : null,
        isReviewDue: state === "REVIEW_DUE",
    };
}
function topic(chapter, index, leafCount) {
    const problemTypes = Array.from({ length: leafCount }, (_, leaf) => problemType(chapter, index, leaf));
    return {
        id: `topic-${chapter}-${index}`,
        code: `TOPIC_${chapter}_${index}`,
        name: `Chủ đề ${chapter}.${index}`,
        chapterId: `chapter-${chapter}`,
        problemTypeCount: problemTypes.length,
        startedProblemTypeCount: problemTypes.filter((item) => item.attemptCount > 0).length,
        masteryScore: 60,
        rawMasteryScore: 0.6,
        state: "LEARNING",
        attemptCount: 5,
        problemTypes,
    };
}
function chapter(index, topicCount, leafCount) {
    const topics = Array.from({ length: topicCount }, (_, topicIndex) => topic(index, topicIndex, leafCount));
    return {
        id: `chapter-${index}`,
        code: `CHAPTER_${index}`,
        name: `Chương ${index}: Miền tri thức`,
        biome: "forest",
        problemTypeCount: topicCount * leafCount,
        startedProblemTypeCount: topics.reduce((sum, item) => sum + item.startedProblemTypeCount, 0),
        masteryScore: 60,
        rawMasteryScore: 0.6,
        state: "LEARNING",
        attemptCount: 10,
        topics,
    };
}
(0, node_test_1.default)("empty curriculum yields empty galaxy constellation layout", () => {
    const layout = (0, galaxy_constellation_layout_1.buildGalaxyConstellationLayout)([]);
    strict_1.default.equal(layout.cores.length, 0);
    strict_1.default.equal(layout.stars.length, 0);
    strict_1.default.equal(layout.constellationLinks.length, 0);
    strict_1.default.deepEqual(layout.bounds, { x: 0, y: 0, width: 0, height: 0 });
});
(0, node_test_1.default)("six-chapter curriculum builds 6 galaxy cores, planets, stars, and decorative links", () => {
    const chapters = Array.from({ length: 6 }, (_, index) => chapter(index, 3, 5));
    const layout = (0, galaxy_constellation_layout_1.buildGalaxyConstellationLayout)(chapters);
    strict_1.default.equal(layout.cores.length, 6);
    strict_1.default.equal(layout.stars.length, 6 * 3 * 5); // 90 stars
    for (const core of layout.cores) {
        strict_1.default.equal(core.planets.length, 3);
        strict_1.default.ok(core.bounds.width > 0);
        strict_1.default.ok(core.bounds.height > 0);
        for (const planet of core.planets) {
            strict_1.default.equal(planet.stars.length, 5);
            strict_1.default.match(planet.connectorPath, /^M /);
            for (const star of planet.stars) {
                strict_1.default.match(star.twigPath, /^M /);
                strict_1.default.ok(star.radius >= galaxy_constellation_layout_1.GALAXY_DIMENSIONS.starRadius);
            }
        }
    }
    // Decorative trails connect only nodes supplied by the curriculum.
    strict_1.default.ok(layout.constellationLinks.length > 0);
    const suppliedNodeIds = new Set(chapters.flatMap((item) => [
        item.id,
        ...item.topics.flatMap((topic) => [topic.id, ...topic.problemTypes.map((problemType) => problemType.id)]),
    ]));
    for (const link of layout.constellationLinks) {
        strict_1.default.match(link.path, /^M /);
        strict_1.default.ok(suppliedNodeIds.has(link.fromNodeId));
        strict_1.default.ok(suppliedNodeIds.has(link.toNodeId));
    }
    strict_1.default.deepEqual((0, galaxy_constellation_layout_1.buildGalaxyConstellationLayout)(chapters), layout);
});
(0, node_test_1.default)("galaxy cores do not overlap with adjacent cores", () => {
    const chapters = Array.from({ length: 6 }, (_, index) => chapter(index, 3, 4));
    const layout = (0, galaxy_constellation_layout_1.buildGalaxyConstellationLayout)(chapters);
    for (let i = 0; i < layout.cores.length; i++) {
        for (let j = i + 1; j < layout.cores.length; j++) {
            const coreA = layout.cores[i];
            const coreB = layout.cores[j];
            const dist = Math.hypot(coreA.center.x - coreB.center.x, coreA.center.y - coreB.center.y);
            // Cores must have substantial distance between their centers
            strict_1.default.ok(dist >= 450, `Cores ${i} and ${j} too close: dist=${dist}`);
        }
    }
});
(0, node_test_1.default)("fitGalaxyCamera and zoomGalaxyCameraAt behave deterministically and maintain scale constraints", () => {
    const chapters = Array.from({ length: 4 }, (_, index) => chapter(index, 2, 3));
    const layout = (0, galaxy_constellation_layout_1.buildGalaxyConstellationLayout)(chapters);
    const viewport = { width: 1200, height: 800 };
    const camera = (0, galaxy_constellation_layout_1.fitGalaxyCamera)(viewport, layout.bounds, 40);
    strict_1.default.ok(camera.scale >= galaxy_constellation_layout_1.GALAXY_DIMENSIONS.minScale);
    strict_1.default.ok(camera.scale <= galaxy_constellation_layout_1.GALAXY_DIMENSIONS.maxScale);
    strict_1.default.ok(Number.isFinite(camera.x));
    strict_1.default.ok(Number.isFinite(camera.y));
    // Zoom in
    const zoomed = (0, galaxy_constellation_layout_1.zoomGalaxyCameraAt)(camera, { x: 600, y: 400 }, camera.scale * 1.5);
    strict_1.default.ok(zoomed.scale > camera.scale);
    // Focus on first core
    const focused = (0, galaxy_constellation_layout_1.focusGalaxyCamera)(viewport, layout.cores[0].bounds, 48);
    strict_1.default.ok(Number.isFinite(focused.x));
    strict_1.default.ok(Number.isFinite(focused.y));
    strict_1.default.ok(focused.scale >= galaxy_constellation_layout_1.GALAXY_DIMENSIONS.minScale);
    // Pan
    const panned = (0, galaxy_constellation_layout_1.panGalaxyCamera)(camera, { x: 50, y: -30 });
    strict_1.default.ok(Math.abs(panned.x - (camera.x + 50)) < 0.01);
    strict_1.default.ok(Math.abs(panned.y - (camera.y - 30)) < 0.01);
});
(0, node_test_1.default)("fitGalaxyCamera adapts cleanly to mobile viewports (360px and 390px)", () => {
    const chapters = Array.from({ length: 6 }, (_, index) => chapter(index, 3, 4));
    const layout = (0, galaxy_constellation_layout_1.buildGalaxyConstellationLayout)(chapters);
    for (const width of [360, 390]) {
        const mobileViewport = { width, height: 740 };
        const camera = (0, galaxy_constellation_layout_1.fitGalaxyCamera)(mobileViewport, layout.bounds, 16);
        strict_1.default.ok(camera.scale >= galaxy_constellation_layout_1.GALAXY_DIMENSIONS.minScale);
        strict_1.default.ok(Number.isFinite(camera.x));
        strict_1.default.ok(Number.isFinite(camera.y));
    }
});
