"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
const strict_1 = __importDefault(require("node:assert/strict"));
const node_test_1 = __importDefault(require("node:test"));
const living_tree_layout_1 = require("../src/features/knowledge-forest/living-tree-layout");
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
(0, node_test_1.default)("six-chapter curriculum becomes one continuous trunk, roots, branches, leaves and mastered fruit", () => {
    const chapters = Array.from({ length: 6 }, (_, index) => chapter(index, 3, 5));
    const layout = (0, living_tree_layout_1.buildLivingTreeLayout)(chapters);
    strict_1.default.equal(layout.chapters.length, 6);
    strict_1.default.equal(layout.roots.length, 4);
    strict_1.default.match(layout.trunkPath, /^M /);
    strict_1.default.equal(layout.leaves.length, 90);
    for (const chapterLayout of layout.chapters) {
        strict_1.default.deepEqual(chapterLayout.branch.start, chapterLayout.attach);
        for (const topicLayout of chapterLayout.topics) {
            strict_1.default.deepEqual(topicLayout.branch.start, topicLayout.junction);
            for (const leaf of topicLayout.leaves) {
                strict_1.default.deepEqual(leaf.twig.start, topicLayout.center);
                strict_1.default.deepEqual(leaf.twig.end, leaf.center);
                strict_1.default.equal(leaf.hasFruit, leaf.node.state === "MASTERED");
            }
        }
    }
    const masteredCount = layout.leaves.filter((leaf) => leaf.node.state === "MASTERED").length;
    strict_1.default.equal(layout.leaves.filter((leaf) => leaf.hasFruit).length, masteredCount);
    strict_1.default.equal(layout.leaves.filter((leaf) => leaf.node.state === "NOT_STARTED" && leaf.hasFruit).length, 0);
});
(0, node_test_1.default)("layout is deterministic and scales to a larger curriculum without duplicate leaf coordinates", () => {
    const chapters = Array.from({ length: 12 }, (_, index) => chapter(index, 5, 12));
    const first = (0, living_tree_layout_1.buildLivingTreeLayout)(chapters);
    const second = (0, living_tree_layout_1.buildLivingTreeLayout)(chapters);
    strict_1.default.deepEqual(second, first);
    strict_1.default.equal(first.leaves.length, 720);
    strict_1.default.ok(first.width > 1600);
    strict_1.default.ok(first.height > 1080);
    const coordinates = new Set(first.leaves.map((leaf) => `${leaf.center.x}:${leaf.center.y}`));
    strict_1.default.equal(coordinates.size, first.leaves.length);
    for (let firstLeaf = 0; firstLeaf < first.leaves.length; firstLeaf += 1) {
        for (let secondLeaf = firstLeaf + 1; secondLeaf < first.leaves.length; secondLeaf += 1) {
            strict_1.default.equal((0, living_tree_layout_1.rectsOverlap)(first.leaves[firstLeaf].bounds, first.leaves[secondLeaf].bounds), false);
        }
    }
});
(0, node_test_1.default)("deterministic topic and chapter labels do not overlap", () => {
    const layout = (0, living_tree_layout_1.buildLivingTreeLayout)(Array.from({ length: 6 }, (_, index) => chapter(index, 4, 9)));
    const labels = layout.chapters.flatMap((chapterLayout) => [
        chapterLayout.labelBounds,
        ...chapterLayout.topics.map((topicLayout) => topicLayout.labelBounds),
    ]);
    for (let first = 0; first < labels.length; first += 1) {
        for (let second = first + 1; second < labels.length; second += 1) {
            strict_1.default.equal((0, living_tree_layout_1.rectsOverlap)(labels[first], labels[second], 4), false);
        }
    }
});
(0, node_test_1.default)("fit and cursor-centered zoom camera math is stable", () => {
    const viewport = { width: 1000, height: 700 };
    const camera = (0, living_tree_layout_1.fitTreeCamera)(viewport, { x: 0, y: 0, width: 2000, height: 1200 }, 40);
    strict_1.default.ok(camera.scale > 0 && camera.scale < 1);
    const cursor = { x: 430, y: 280 };
    const before = {
        x: (cursor.x - camera.x) / camera.scale,
        y: (cursor.y - camera.y) / camera.scale,
    };
    const zoomed = (0, living_tree_layout_1.zoomTreeCameraAt)(camera, cursor, camera.scale * 1.5);
    const after = {
        x: (cursor.x - zoomed.x) / zoomed.scale,
        y: (cursor.y - zoomed.y) / zoomed.scale,
    };
    strict_1.default.ok(Math.abs(before.x - after.x) < 0.02);
    strict_1.default.ok(Math.abs(before.y - after.y) < 0.02);
    strict_1.default.deepEqual((0, living_tree_layout_1.panTreeCamera)(camera, { x: 24, y: -16 }), Object.assign(Object.assign({}, camera), { x: camera.x + 24, y: camera.y - 16 }));
    const focused = (0, living_tree_layout_1.focusTreeCamera)(viewport, { x: 700, y: 400, width: 220, height: 180 });
    strict_1.default.ok(focused.scale > camera.scale);
});
(0, node_test_1.default)("day-one 6/8/9 curriculum keeps every unstarted leaf visible without fake fruit", () => {
    const topicCounts = [2, 2, 1, 1, 1, 1];
    let leafIndex = 0;
    const chapters = topicCounts.map((count, chapterIndex) => {
        const topics = Array.from({ length: count }, (_, topicIndex) => {
            const problemCount = chapterIndex === 0 && topicIndex === 0 ? 2 : 1;
            const topicId = `day-one-topic-${chapterIndex}-${topicIndex}`;
            const problemTypes = Array.from({ length: problemCount }, () => {
                const index = leafIndex++;
                return {
                    id: `day-one-problem-${index}`,
                    code: `DAY_ONE_PROBLEM_${index}`,
                    name: `Day one problem type ${index + 1}`,
                    topicId,
                    topicName: `Day one topic ${chapterIndex + 1}.${topicIndex + 1}`,
                    chapterId: `day-one-chapter-${chapterIndex}`,
                    chapterName: `Day one chapter ${chapterIndex + 1}`,
                    rawMasteryScore: 0,
                    attemptCount: 0,
                    correctCount: 0,
                    state: "NOT_STARTED",
                    lastPracticedAt: null,
                    isReviewDue: false,
                };
            });
            return {
                id: topicId,
                code: `DAY_ONE_TOPIC_${chapterIndex}_${topicIndex}`,
                name: `Day one topic ${chapterIndex + 1}.${topicIndex + 1}`,
                chapterId: `day-one-chapter-${chapterIndex}`,
                problemTypeCount: problemTypes.length,
                startedProblemTypeCount: 0,
                rawMasteryScore: 0,
                state: "NOT_STARTED",
                attemptCount: 0,
                problemTypes,
            };
        });
        return {
            id: `day-one-chapter-${chapterIndex}`,
            code: `DAY_ONE_CHAPTER_${chapterIndex}`,
            name: `Day one chapter ${chapterIndex + 1}`,
            biome: "forest",
            problemTypeCount: topics.reduce((sum, item) => sum + item.problemTypeCount, 0),
            startedProblemTypeCount: 0,
            rawMasteryScore: 0,
            state: "NOT_STARTED",
            attemptCount: 0,
            topics,
        };
    });
    const layout = (0, living_tree_layout_1.buildLivingTreeLayout)(chapters);
    strict_1.default.equal(layout.chapters.length, 6);
    strict_1.default.equal(layout.chapters.flatMap((item) => item.topics).length, 8);
    strict_1.default.equal(layout.leaves.length, 9);
    strict_1.default.ok(layout.leaves.every((leaf) => leaf.node.state === "NOT_STARTED"));
    strict_1.default.ok(layout.leaves.every((leaf) => leaf.hasFruit === false));
});
(0, node_test_1.default)("fitTreeCamera scales tree to fit 360px and 390px mobile viewports without horizontal clipping", () => {
    const topicCounts = [2, 2, 1, 1, 1, 1];
    let leafIndex = 0;
    const chapters = topicCounts.map((count, chapterIndex) => {
        const topics = Array.from({ length: count }, (_, topicIndex) => {
            const problemCount = chapterIndex === 0 && topicIndex === 0 ? 2 : 1;
            const topicId = `test-topic-${chapterIndex}-${topicIndex}`;
            const problemTypes = Array.from({ length: problemCount }, () => {
                const index = leafIndex++;
                return {
                    id: `test-problem-${index}`,
                    code: `TEST_PROBLEM_${index}`,
                    name: `Problem ${index + 1}`,
                    topicId,
                    topicName: `Topic ${chapterIndex + 1}.${topicIndex + 1}`,
                    chapterId: `test-chapter-${chapterIndex}`,
                    chapterName: `Chapter ${chapterIndex + 1}`,
                    rawMasteryScore: 0,
                    attemptCount: 0,
                    correctCount: 0,
                    state: "NOT_STARTED",
                    lastPracticedAt: null,
                    isReviewDue: false,
                };
            });
            return {
                id: topicId,
                code: `TEST_TOPIC_${chapterIndex}_${topicIndex}`,
                name: `Topic ${chapterIndex + 1}.${topicIndex + 1}`,
                chapterId: `test-chapter-${chapterIndex}`,
                problemTypeCount: problemTypes.length,
                startedProblemTypeCount: 0,
                rawMasteryScore: 0,
                state: "NOT_STARTED",
                attemptCount: 0,
                problemTypes,
            };
        });
        return {
            id: `test-chapter-${chapterIndex}`,
            code: `TEST_CHAPTER_${chapterIndex}`,
            name: `Chapter ${chapterIndex + 1}`,
            biome: "forest",
            problemTypeCount: topics.reduce((sum, item) => sum + item.problemTypeCount, 0),
            startedProblemTypeCount: 0,
            rawMasteryScore: 0,
            state: "NOT_STARTED",
            attemptCount: 0,
            topics,
        };
    });
    const layout = (0, living_tree_layout_1.buildLivingTreeLayout)(chapters);
    // Assert MIN_FIT_SCALE separation from interactive zoom scale
    strict_1.default.equal(living_tree_layout_1.LIVING_TREE_DIMENSIONS.minFitScale, 0.05);
    strict_1.default.equal(living_tree_layout_1.LIVING_TREE_DIMENSIONS.minScale, 0.08);
    // Test 360px screen (e.g. inner tree canvas container ~320-360px wide)
    for (const viewportWidth of [320, 360, 390]) {
        const viewport = { width: viewportWidth, height: 600 };
        const padding = viewportWidth < 440 ? 16 : 24;
        const camera = (0, living_tree_layout_1.fitTreeCamera)(viewport, layout.bounds, padding, 0.92);
        strict_1.default.ok(camera.scale >= living_tree_layout_1.LIVING_TREE_DIMENSIONS.minFitScale);
        // Tree content width rendered must fit inside the viewport with padding
        const renderedWidth = layout.bounds.width * camera.scale;
        strict_1.default.ok(renderedWidth <= viewport.width, `Tree rendered width (${renderedWidth}) must fit within viewport width (${viewport.width}) at ${viewportWidth}px`);
        const renderedHeight = layout.bounds.height * camera.scale;
        strict_1.default.ok(renderedHeight <= viewport.height, `Tree rendered height (${renderedHeight}) must fit within viewport height (${viewport.height}) at ${viewportWidth}px`);
    }
});
