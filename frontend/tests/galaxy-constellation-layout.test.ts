import assert from "node:assert/strict";
import test from "node:test";

import {
  GALAXY_DIMENSIONS,
  buildGalaxyConstellationLayout,
  fitGalaxyCamera,
  focusGalaxyCamera,
  panGalaxyCamera,
  rectsOverlap,
  zoomGalaxyCameraAt,
} from "../src/features/knowledge-forest/galaxy-constellation-layout";
import type {
  KnowledgeChapterNode,
  KnowledgeProblemTypeNode,
  KnowledgeTopicNode,
} from "../src/features/knowledge-forest/types";
import type { DerivedMasteryState } from "../src/lib/api/contracts";

const states: DerivedMasteryState[] = [
  "MASTERED",
  "LEARNING",
  "PRACTICING",
  "WEAK",
  "REVIEW_DUE",
  "NOT_STARTED",
];

function problemType(chapter: number, topic: number, leaf: number): KnowledgeProblemTypeNode {
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

function topic(chapter: number, index: number, leafCount: number): KnowledgeTopicNode {
  const problemTypes = Array.from({ length: leafCount }, (_, leaf) =>
    problemType(chapter, index, leaf)
  );
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

function chapter(index: number, topicCount: number, leafCount: number): KnowledgeChapterNode {
  const topics = Array.from({ length: topicCount }, (_, topicIndex) =>
    topic(index, topicIndex, leafCount)
  );
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

test("empty curriculum yields empty galaxy constellation layout", () => {
  const layout = buildGalaxyConstellationLayout([]);
  assert.equal(layout.cores.length, 0);
  assert.equal(layout.stars.length, 0);
  assert.equal(layout.prerequisiteBeams.length, 0);
  assert.deepEqual(layout.bounds, { x: 0, y: 0, width: 0, height: 0 });
});

test("six-chapter curriculum builds 6 galaxy cores, planets, stars, and prerequisite beams", () => {
  const chapters = Array.from({ length: 6 }, (_, index) => chapter(index, 3, 5));
  const layout = buildGalaxyConstellationLayout(chapters);

  assert.equal(layout.cores.length, 6);
  assert.equal(layout.stars.length, 6 * 3 * 5); // 90 stars

  for (const core of layout.cores) {
    assert.equal(core.planets.length, 3);
    assert.ok(core.bounds.width > 0);
    assert.ok(core.bounds.height > 0);
    for (const planet of core.planets) {
      assert.equal(planet.stars.length, 5);
      assert.match(planet.connectorPath, /^M /);
      for (const star of planet.stars) {
        assert.match(star.twigPath, /^M /);
        assert.ok(star.radius >= GALAXY_DIMENSIONS.starRadius);
      }
    }
  }

  // Prerequisite beams are generated
  assert.ok(layout.prerequisiteBeams.length > 0);
  for (const beam of layout.prerequisiteBeams) {
    assert.match(beam.path, /^M /);
  }
});

test("galaxy cores do not overlap with adjacent cores", () => {
  const chapters = Array.from({ length: 6 }, (_, index) => chapter(index, 3, 4));
  const layout = buildGalaxyConstellationLayout(chapters);

  for (let i = 0; i < layout.cores.length; i++) {
    for (let j = i + 1; j < layout.cores.length; j++) {
      const coreA = layout.cores[i];
      const coreB = layout.cores[j];
      const dist = Math.hypot(coreA.center.x - coreB.center.x, coreA.center.y - coreB.center.y);
      // Cores must have substantial distance between their centers
      assert.ok(dist >= 450, `Cores ${i} and ${j} too close: dist=${dist}`);
    }
  }
});

test("fitGalaxyCamera and zoomGalaxyCameraAt behave deterministically and maintain scale constraints", () => {
  const chapters = Array.from({ length: 4 }, (_, index) => chapter(index, 2, 3));
  const layout = buildGalaxyConstellationLayout(chapters);

  const viewport = { width: 1200, height: 800 };
  const camera = fitGalaxyCamera(viewport, layout.bounds, 40);

  assert.ok(camera.scale >= GALAXY_DIMENSIONS.minScale);
  assert.ok(camera.scale <= GALAXY_DIMENSIONS.maxScale);
  assert.ok(Number.isFinite(camera.x));
  assert.ok(Number.isFinite(camera.y));

  // Zoom in
  const zoomed = zoomGalaxyCameraAt(camera, { x: 600, y: 400 }, camera.scale * 1.5);
  assert.ok(zoomed.scale > camera.scale);

  // Focus on first core
  const focused = focusGalaxyCamera(viewport, layout.cores[0].bounds, 48);
  assert.ok(Number.isFinite(focused.x));
  assert.ok(Number.isFinite(focused.y));
  assert.ok(focused.scale >= GALAXY_DIMENSIONS.minScale);

  // Pan
  const panned = panGalaxyCamera(camera, { x: 50, y: -30 });
  assert.ok(Math.abs(panned.x - (camera.x + 50)) < 0.01);
  assert.ok(Math.abs(panned.y - (camera.y - 30)) < 0.01);
});

test("fitGalaxyCamera adapts cleanly to mobile viewports (360px and 390px)", () => {
  const chapters = Array.from({ length: 6 }, (_, index) => chapter(index, 3, 4));
  const layout = buildGalaxyConstellationLayout(chapters);

  for (const width of [360, 390]) {
    const mobileViewport = { width, height: 740 };
    const camera = fitGalaxyCamera(mobileViewport, layout.bounds, 16);

    assert.ok(camera.scale >= GALAXY_DIMENSIONS.minScale);
    assert.ok(Number.isFinite(camera.x));
    assert.ok(Number.isFinite(camera.y));
  }
});
