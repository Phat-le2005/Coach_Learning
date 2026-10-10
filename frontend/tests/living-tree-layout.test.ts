import assert from "node:assert/strict";
import test from "node:test";

import {
  buildLivingTreeLayout,
  fitTreeCamera,
  focusTreeCamera,
  panTreeCamera,
  rectsOverlap,
  zoomTreeCameraAt,
} from "../src/features/knowledge-forest/living-tree-layout";
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

test("six-chapter curriculum becomes one continuous trunk, roots, branches, leaves and mastered fruit", () => {
  const chapters = Array.from({ length: 6 }, (_, index) => chapter(index, 3, 5));
  const layout = buildLivingTreeLayout(chapters);

  assert.equal(layout.chapters.length, 6);
  assert.equal(layout.roots.length, 4);
  assert.match(layout.trunkPath, /^M /);
  assert.equal(layout.leaves.length, 90);

  for (const chapterLayout of layout.chapters) {
    assert.deepEqual(chapterLayout.branch.start, chapterLayout.attach);
    for (const topicLayout of chapterLayout.topics) {
      assert.deepEqual(topicLayout.branch.start, topicLayout.junction);
      for (const leaf of topicLayout.leaves) {
        assert.deepEqual(leaf.twig.start, topicLayout.center);
        assert.deepEqual(leaf.twig.end, leaf.center);
        assert.equal(leaf.hasFruit, leaf.node.state === "MASTERED");
      }
    }
  }

  const masteredCount = layout.leaves.filter((leaf) => leaf.node.state === "MASTERED").length;
  assert.equal(layout.leaves.filter((leaf) => leaf.hasFruit).length, masteredCount);
  assert.equal(
    layout.leaves.filter((leaf) => leaf.node.state === "NOT_STARTED" && leaf.hasFruit).length,
    0
  );
});

test("layout is deterministic and scales to a larger curriculum without duplicate leaf coordinates", () => {
  const chapters = Array.from({ length: 12 }, (_, index) => chapter(index, 5, 12));
  const first = buildLivingTreeLayout(chapters);
  const second = buildLivingTreeLayout(chapters);

  assert.deepEqual(second, first);
  assert.equal(first.leaves.length, 720);
  assert.ok(first.width > 1600);
  assert.ok(first.height > 1080);
  const coordinates = new Set(first.leaves.map((leaf) => `${leaf.center.x}:${leaf.center.y}`));
  assert.equal(coordinates.size, first.leaves.length);
  for (let firstLeaf = 0; firstLeaf < first.leaves.length; firstLeaf += 1) {
    for (let secondLeaf = firstLeaf + 1; secondLeaf < first.leaves.length; secondLeaf += 1) {
      assert.equal(
        rectsOverlap(first.leaves[firstLeaf].bounds, first.leaves[secondLeaf].bounds),
        false
      );
    }
  }
});

test("deterministic topic and chapter labels do not overlap", () => {
  const layout = buildLivingTreeLayout(
    Array.from({ length: 6 }, (_, index) => chapter(index, 4, 9))
  );
  const labels = layout.chapters.flatMap((chapterLayout) => [
    chapterLayout.labelBounds,
    ...chapterLayout.topics.map((topicLayout) => topicLayout.labelBounds),
  ]);

  for (let first = 0; first < labels.length; first += 1) {
    for (let second = first + 1; second < labels.length; second += 1) {
      assert.equal(rectsOverlap(labels[first], labels[second], 4), false);
    }
  }
});

test("fit and cursor-centered zoom camera math is stable", () => {
  const viewport = { width: 1000, height: 700 };
  const camera = fitTreeCamera(viewport, { x: 0, y: 0, width: 2000, height: 1200 }, 40);
  assert.ok(camera.scale > 0 && camera.scale < 1);

  const cursor = { x: 430, y: 280 };
  const before = {
    x: (cursor.x - camera.x) / camera.scale,
    y: (cursor.y - camera.y) / camera.scale,
  };
  const zoomed = zoomTreeCameraAt(camera, cursor, camera.scale * 1.5);
  const after = {
    x: (cursor.x - zoomed.x) / zoomed.scale,
    y: (cursor.y - zoomed.y) / zoomed.scale,
  };
  assert.ok(Math.abs(before.x - after.x) < 0.02);
  assert.ok(Math.abs(before.y - after.y) < 0.02);

  assert.deepEqual(panTreeCamera(camera, { x: 24, y: -16 }), {
    ...camera,
    x: camera.x + 24,
    y: camera.y - 16,
  });
  const focused = focusTreeCamera(viewport, { x: 700, y: 400, width: 220, height: 180 });
  assert.ok(focused.scale > camera.scale);
});
