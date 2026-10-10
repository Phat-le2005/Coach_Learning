import type {
  KnowledgeChapterNode,
  KnowledgeProblemTypeNode,
  KnowledgeTopicNode,
} from "./types";

export interface TreePoint { x: number; y: number }
export interface TreeRect { x: number; y: number; width: number; height: number }
export interface TreeCurve {
  start: TreePoint;
  control1: TreePoint;
  control2: TreePoint;
  end: TreePoint;
  path: string;
}
export interface LivingTreeLeafLayout {
  node: KnowledgeProblemTypeNode;
  center: TreePoint;
  rotation: number;
  twig: TreeCurve;
  bounds: TreeRect;
  hasFruit: boolean;
}
export interface LivingTreeTopicLayout {
  node: KnowledgeTopicNode;
  center: TreePoint;
  junction: TreePoint;
  branch: TreeCurve;
  labelBounds: TreeRect;
  bounds: TreeRect;
  leaves: LivingTreeLeafLayout[];
}
export interface LivingTreeChapterLayout {
  node: KnowledgeChapterNode;
  side: -1 | 1;
  attach: TreePoint;
  branch: TreeCurve;
  labelBounds: TreeRect;
  bounds: TreeRect;
  topics: LivingTreeTopicLayout[];
}
export interface LivingTreeLayout {
  width: number;
  height: number;
  centerX: number;
  baseY: number;
  trunkPath: string;
  roots: TreeCurve[];
  chapters: LivingTreeChapterLayout[];
  leaves: LivingTreeLeafLayout[];
  bounds: TreeRect;
}
export interface TreeCamera { x: number; y: number; scale: number }
export interface TreeViewport { width: number; height: number }

const MIN_FIT_SCALE = 0.05;
const MIN_INTERACTIVE_SCALE = 0.08;
const MAX_SCALE = 2.4;

function rounded(value: number): number {
  return Math.round(value * 100) / 100;
}

function point(x: number, y: number): TreePoint {
  return { x: rounded(x), y: rounded(y) };
}

function curve(start: TreePoint, control1: TreePoint, control2: TreePoint, end: TreePoint): TreeCurve {
  return {
    start,
    control1,
    control2,
    end,
    path: `M ${start.x} ${start.y} C ${control1.x} ${control1.y}, ${control2.x} ${control2.y}, ${end.x} ${end.y}`,
  };
}

export function pointOnCurve(value: TreeCurve, t: number): TreePoint {
  const inverse = 1 - t;
  return point(
    inverse ** 3 * value.start.x + 3 * inverse ** 2 * t * value.control1.x + 3 * inverse * t ** 2 * value.control2.x + t ** 3 * value.end.x,
    inverse ** 3 * value.start.y + 3 * inverse ** 2 * t * value.control1.y + 3 * inverse * t ** 2 * value.control2.y + t ** 3 * value.end.y
  );
}

function pointRect(center: TreePoint, width: number, height: number): TreeRect {
  return { x: rounded(center.x - width / 2), y: rounded(center.y - height / 2), width, height };
}

function unionRects(rects: readonly TreeRect[]): TreeRect {
  if (rects.length === 0) return { x: 0, y: 0, width: 0, height: 0 };
  const minX = Math.min(...rects.map((rect) => rect.x));
  const minY = Math.min(...rects.map((rect) => rect.y));
  const maxX = Math.max(...rects.map((rect) => rect.x + rect.width));
  const maxY = Math.max(...rects.map((rect) => rect.y + rect.height));
  return { x: rounded(minX), y: rounded(minY), width: rounded(maxX - minX), height: rounded(maxY - minY) };
}

function topicColumns(topic: KnowledgeTopicNode): number {
  return Math.max(1, Math.ceil(Math.sqrt(Math.max(1, topic.problemTypes.length))));
}

function topicRows(topic: KnowledgeTopicNode): number {
  return Math.ceil(Math.max(1, topic.problemTypes.length) / topicColumns(topic));
}

function topicSlotWidth(topic: KnowledgeTopicNode): number {
  return Math.max(250, topicColumns(topic) * 72 + 120);
}

function chapterLength(chapter: KnowledgeChapterNode): number {
  return 360 + chapter.topics.reduce((sum, topic) => sum + topicSlotWidth(topic), 0);
}

/** Deterministic hierarchy layout. Mastery affects appearance and fruit only, never coordinates. */
export function buildLivingTreeLayout(chapters: readonly KnowledgeChapterNode[]): LivingTreeLayout {
  const lengths = chapters.map(chapterLength);
  const leftLength = Math.max(520, ...lengths.filter((_, index) => index % 2 === 0));
  const rightLength = Math.max(520, ...lengths.filter((_, index) => index % 2 === 1));
  const maxRows = Math.max(1, ...chapters.flatMap((chapter) => chapter.topics.map(topicRows)));
  const layerGap = Math.max(310, maxRows * 62 + 240);
  const pairCount = Math.max(1, Math.ceil(chapters.length / 2));
  const width = rounded(leftLength + rightLength + 560);
  const height = rounded(Math.max(1080, 400 + pairCount * layerGap));
  const centerX = rounded(leftLength + 280);
  const baseY = rounded(height - 105);

  const chapterLayouts: LivingTreeChapterLayout[] = chapters.map((chapter, chapterIndex) => {
    const side: -1 | 1 = chapterIndex % 2 === 0 ? -1 : 1;
    // Stagger each chapter vertically instead of mirroring pairs. This keeps the
    // hierarchy deterministic while giving the crown the irregular rhythm of a
    // living tree rather than a tiered diagram.
    const attach = point(centerX + side * 8, baseY - 190 - chapterIndex * (layerGap / 2));
    const length = lengths[chapterIndex];
    const end = point(centerX + side * length, attach.y - 68 - (chapterIndex % 3) * 14);
    const chapterBranch = curve(
      attach,
      point(centerX + side * length * 0.24, attach.y - 8),
      point(end.x - side * length * 0.28, end.y + 34),
      end
    );
    const totalTopicWidth = chapter.topics.reduce((sum, topic) => sum + topicSlotWidth(topic), 0);
    let consumedWidth = 0;

    const topics: LivingTreeTopicLayout[] = chapter.topics.map((topic, topicIndex) => {
      const slotWidth = topicSlotWidth(topic);
      const slotCenter = consumedWidth + slotWidth / 2;
      consumedWidth += slotWidth;
      const relative = totalTopicWidth > 0 ? slotCenter / totalTopicWidth : 0.5;
      const junction = pointOnCurve(chapterBranch, 0.24 + relative * 0.66);
      const rows = topicRows(topic);
      const topicCenter = point(junction.x + side * (18 + (topicIndex % 2) * 12), junction.y - (118 + (topicIndex % 2) * 22));
      const topicBranch = curve(
        junction,
        point(junction.x + side * 10, junction.y - 42),
        point(topicCenter.x - side * 18, topicCenter.y + 42),
        topicCenter
      );
      const columns = topicColumns(topic);
      const rowCount = topicRows(topic);
      const leaves: LivingTreeLeafLayout[] = topic.problemTypes.map((problemType, leafIndex) => {
        const column = leafIndex % columns;
        const row = Math.floor(leafIndex / columns);
        const leafCenter = point(
          topicCenter.x + (column - (columns - 1) / 2) * 68,
          topicCenter.y - 52 + (row - (rowCount - 1) / 2) * 58
        );
        return {
          node: problemType,
          center: leafCenter,
          rotation: rounded(side * 18 + (column - (columns - 1) / 2) * 9),
          twig: curve(
            topicCenter,
            point(topicCenter.x + (leafCenter.x - topicCenter.x) * 0.32, topicCenter.y - 20),
            point(leafCenter.x - (leafCenter.x - topicCenter.x) * 0.18, leafCenter.y + 18),
            leafCenter
          ),
          bounds: pointRect(leafCenter, 68, 58),
          hasFruit: problemType.state === "MASTERED",
        };
      });
      const labelCenter = point(topicCenter.x, topicCenter.y + rows * 31 + 38);
      const labelBounds = pointRect(labelCenter, Math.min(238, slotWidth - 20), 48);
      return {
        node: topic,
        center: topicCenter,
        junction,
        branch: topicBranch,
        labelBounds,
        bounds: unionRects([pointRect(topicCenter, 40, 40), labelBounds, ...leaves.map((leaf) => leaf.bounds)]),
        leaves,
      };
    });

    const labelBounds = pointRect(point(end.x + side * 28, end.y + 42), 250, 58);
    return {
      node: chapter,
      side,
      attach,
      branch: chapterBranch,
      labelBounds,
      bounds: unionRects([pointRect(attach, 48, 48), pointRect(end, 70, 70), labelBounds, ...topics.map((topic) => topic.bounds)]),
      topics,
    };
  });

  const topY = Math.max(120, Math.min(...chapterLayouts.map((chapter) => chapter.attach.y), baseY - 430) - 150);
  const trunkPath = [
    `M ${rounded(centerX - 66)} ${baseY}`,
    `C ${rounded(centerX - 86)} ${rounded(baseY - 210)}, ${rounded(centerX - 42)} ${rounded(topY + 140)}, ${rounded(centerX - 14)} ${topY}`,
    `L ${rounded(centerX + 14)} ${topY}`,
    `C ${rounded(centerX + 44)} ${rounded(topY + 140)}, ${rounded(centerX + 82)} ${rounded(baseY - 210)}, ${rounded(centerX + 66)} ${baseY}`,
    "Z",
  ].join(" ");
  const roots = ([-1, 1, -0.58, 0.58] as const).map((direction, index) => {
    const start = point(centerX + direction * 20, baseY - index * 3);
    const end = point(centerX + direction * (170 + (index % 2) * 90), height - 24 - (index % 2) * 22);
    return curve(start, point(centerX + direction * 70, baseY + 18), point(end.x - direction * 58, end.y - 12), end);
  });

  return {
    width,
    height,
    centerX,
    baseY,
    trunkPath,
    roots,
    chapters: chapterLayouts,
    leaves: chapterLayouts.flatMap((chapter) => chapter.topics.flatMap((topic) => topic.leaves)),
    bounds: { x: 0, y: 0, width, height },
  };
}

function clampInteractiveScale(scale: number): number {
  return Math.min(MAX_SCALE, Math.max(MIN_INTERACTIVE_SCALE, scale));
}

export function fitTreeCamera(viewport: TreeViewport, bounds: TreeRect, padding = 36, maxScale = 1): TreeCamera {
  const safePadding = viewport.width < 440 ? Math.min(padding, 16) : viewport.width < 640 ? Math.min(padding, 24) : padding;
  const availableWidth = Math.max(1, viewport.width - safePadding * 2);
  const availableHeight = Math.max(1, viewport.height - safePadding * 2);
  const rawFitScale = Math.min(maxScale, availableWidth / Math.max(1, bounds.width), availableHeight / Math.max(1, bounds.height));
  const scale = Math.min(MAX_SCALE, Math.max(MIN_FIT_SCALE, rawFitScale));
  return {
    x: rounded((viewport.width - bounds.width * scale) / 2 - bounds.x * scale),
    y: rounded((viewport.height - bounds.height * scale) / 2 - bounds.y * scale),
    scale: rounded(scale),
  };
}

export function focusTreeCamera(viewport: TreeViewport, bounds: TreeRect, padding = 88, maxScale = 1.35): TreeCamera {
  return fitTreeCamera(viewport, bounds, padding, maxScale);
}

export function zoomTreeCameraAt(camera: TreeCamera, viewportPoint: TreePoint, requestedScale: number): TreeCamera {
  const scale = clampInteractiveScale(requestedScale);
  const worldX = (viewportPoint.x - camera.x) / camera.scale;
  const worldY = (viewportPoint.y - camera.y) / camera.scale;
  return {
    x: rounded(viewportPoint.x - worldX * scale),
    y: rounded(viewportPoint.y - worldY * scale),
    scale: rounded(scale),
  };
}

export function panTreeCamera(camera: TreeCamera, delta: TreePoint): TreeCamera {
  return {
    ...camera,
    x: rounded(camera.x + delta.x),
    y: rounded(camera.y + delta.y),
  };
}

export function rectsOverlap(first: TreeRect, second: TreeRect, gap = 0): boolean {
  const epsilon = 0.01;
  return !(
    first.x + first.width + gap <= second.x + epsilon ||
    second.x + second.width + gap <= first.x + epsilon ||
    first.y + first.height + gap <= second.y + epsilon ||
    second.y + second.height + gap <= first.y + epsilon
  );
}

export const LIVING_TREE_DIMENSIONS = {
  minScale: MIN_INTERACTIVE_SCALE,
  minFitScale: MIN_FIT_SCALE,
  maxScale: MAX_SCALE,
} as const;
