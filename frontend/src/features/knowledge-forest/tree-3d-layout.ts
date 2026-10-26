/**
 * 3D Spatial Layout Mathematics for EduMS — Living Cosmic Knowledge World
 *
 * Cosmic Decision Field & Neural Orbit coordinate system:
 * - Level 0: Central Singularity Core & Accretion Swirl (0, 0, 0).
 * - Level 1: 7 Chapters arranged uniformly along a 360° orbital ring in 3D space.
 * - Level 2: Topics radiating outward along electric dendritic lightning paths.
 * - Level 3: Problem Types branching out into deep space as glowing crystal embers.
 * - Level 4: Prerequisite Bézier arcs connecting competencies across the galaxy.
 */

import type {
  KnowledgeChapterNode,
  KnowledgeProblemTypeNode,
  KnowledgeTopicNode,
} from "./types";
import { VERIFIED_PREREQUISITE_EDGES } from "./prerequisite-graph";

export interface Point3D {
  x: number;
  y: number;
  z: number;
}

export interface Node3DLayout {
  data: KnowledgeProblemTypeNode;
  position: Point3D;
  topicId: string;
  chapterId: string;
  themeColor: string;
  branchletSpline: Point3D[];
}

export interface Topic3DLayout {
  data: KnowledgeTopicNode;
  position: Point3D;
  chapterId: string;
  themeColor: string;
  radius: number;
  subBranchSpline: Point3D[];
  nodes: Node3DLayout[];
}

export interface Chapter3DLayout {
  data: KnowledgeChapterNode;
  shortName: string;
  position: Point3D;
  themeColor: string;
  glowColor: string;
  branchSpline: Point3D[];
  topics: Topic3DLayout[];
  totalProblemTypes: number;
  masteredCount: number;
  completionPercent: number;
  orbitalAngle: number;
}

export interface PrerequisiteArc3D {
  sourceCode: string;
  targetCode: string;
  sourcePos: Point3D;
  targetPos: Point3D;
  controlPoint: Point3D;
}

export interface LivingWorld3DLayout {
  corePosition: Point3D;
  trunkSpline: Point3D[];
  ringRadius: number;
  chapters: Chapter3DLayout[];
  nodeMap: Map<string, Node3DLayout>;
  nodeByCodeMap: Map<string, Node3DLayout>;
  prerequisiteArcs: PrerequisiteArc3D[];
  overviewCamera: { position: Point3D; target: Point3D };
}

// 7 vibrant cosmic neon palettes matching the reference video & visualization
export const CHAPTER_3D_THEMES = [
  { color: "#00f0ff", glow: "rgba(0, 240, 255, 0.85)", name: "Ứng dụng Đạo hàm" }, // Ch 1: Electric Cyan
  { color: "#38bdf8", glow: "rgba(56, 189, 248, 0.85)", name: "Mũ & Logarit" }, // Ch 2: Sky Blue
  { color: "#a855f7", glow: "rgba(168, 85, 247, 0.85)", name: "Vectơ không gian" }, // Ch 3: Cosmic Violet
  { color: "#fbbf24", glow: "rgba(251, 191, 36, 0.85)", name: "Thống kê số liệu" }, // Ch 4: Amber Gold
  { color: "#ec4899", glow: "rgba(236, 72, 153, 0.85)", name: "Nguyên hàm & Tích phân" }, // Ch 5: Neon Magenta
  { color: "#10b981", glow: "rgba(16, 185, 129, 0.85)", name: "Tọa độ Oxyz" }, // Ch 6: Emerald Green
  { color: "#f97316", glow: "rgba(249, 115, 22, 0.85)", name: "Xác suất có điều kiện" }, // Ch 7: Vivid Coral
];

export const MASTERY_3D_COLORS: Record<string, { base: string; emissive: string; glow: string }> = {
  MASTERED: {
    base: "#10B981",
    emissive: "#059669",
    glow: "rgba(16, 185, 129, 0.95)",
  },
  PRACTICING: {
    base: "#22C55E",
    emissive: "#16a34a",
    glow: "rgba(34, 197, 94, 0.9)",
  },
  LEARNING: {
    base: "#38BDF8",
    emissive: "#0284c7",
    glow: "rgba(56, 189, 248, 0.9)",
  },
  WEAK: {
    base: "#F87171",
    emissive: "#dc2626",
    glow: "rgba(248, 113, 113, 0.95)",
  },
  REVIEW_DUE: {
    base: "#F59E0B",
    emissive: "#d97706",
    glow: "rgba(245, 158, 11, 0.95)",
  },
  NOT_STARTED: {
    base: "#67e8f9",
    emissive: "#0891b2",
    glow: "rgba(103, 232, 249, 0.75)",
  },
};

/**
 * Returns a concise, readable chapter name for 3D floating badges.
 */
export function getShortChapterName(fullName: string, index: number): string {
  const chNum = `Chương ${index + 1}`;
  const n = fullName.toLowerCase();
  if (n.includes("đạo hàm")) return `${chNum}: Khảo sát hàm số`;
  if (n.includes("mũ") || n.includes("logarit")) return `${chNum}: Mũ & Logarit`;
  if (n.includes("vectơ")) return `${chNum}: Vectơ không gian`;
  if (n.includes("phân tán") || n.includes("thống kê")) return `${chNum}: Thống kê số liệu`;
  if (n.includes("nguyên hàm") || n.includes("tích phân")) return `${chNum}: Nguyên hàm & Tích phân`;
  if (n.includes("tọa độ") || n.includes("oxyz")) return `${chNum}: Tọa độ Oxyz`;
  if (n.includes("xác suất")) return `${chNum}: Xác suất có điều kiện`;
  return `${chNum}: ${fullName.slice(0, 18)}…`;
}

/**
 * Generates deterministic jittered lightning points between start and end.
 * Creates an electric, dendritic fractal trajectory.
 */
function generateLightningSpline(
  start: Point3D,
  end: Point3D,
  segments: number = 7,
  jitterAmplitude: number = 1.8,
  seed: number = 1
): Point3D[] {
  const points: Point3D[] = [start];
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const dz = end.z - start.z;
  const len = Math.hypot(dx, dz) || 1;

  // Tangent perpendicular in X-Z plane
  const nx = -dz / len;
  const nz = dx / len;

  for (let i = 1; i < segments; i++) {
    const t = i / segments;
    // Envelope is 0 at both ends and peaks in the middle
    const envelope = Math.sin(t * Math.PI);
    const phase = seed * 17.13 + i * 29.47;
    const dispH = Math.sin(phase) * jitterAmplitude * envelope;
    const dispV = Math.cos(phase * 1.4) * (jitterAmplitude * 0.45) * envelope;

    points.push({
      x: start.x + dx * t + nx * dispH,
      y: start.y + dy * t + dispV,
      z: start.z + dz * t + nz * dispH,
    });
  }

  points.push(end);
  return points;
}

// 7 Chapter Angles matching the cosmic reference layout
// Ch 1: Top-Left (-40°)
// Ch 2: Mid-Left (-90°)
// Ch 3: Bottom-Left (-140°)
// Ch 4: Bottom Center (180°)
// Ch 5: Bottom-Right (135°)
// Ch 6: Mid-Right (85°)
// Ch 7: Top-Right (35°)
const CHAPTER_ANGLES_DEG = [-40, -90, -140, 180, 135, 85, 35];

/**
 * Computes deterministic, balanced 3D coordinates for all entities in the Cosmic Knowledge World.
 */
export function computeLivingWorld3DLayout(chapters: KnowledgeChapterNode[]): LivingWorld3DLayout {
  const corePosition: Point3D = { x: 0, y: 0, z: 0 };
  const orbitalRingRadius = 38.0;

  const nodeMap = new Map<string, Node3DLayout>();
  const nodeByCodeMap = new Map<string, Node3DLayout>();
  const chapterLayouts: Chapter3DLayout[] = [];

  const chapterCount = Math.max(1, chapters.length);

  chapters.forEach((chapter, chapterIdx) => {
    const theme = CHAPTER_3D_THEMES[chapterIdx % CHAPTER_3D_THEMES.length];
    
    // Determine angle around the 360° orbital loop
    const angleDeg =
      chapterCount === 7
        ? CHAPTER_ANGLES_DEG[chapterIdx]
        : -40 + (chapterIdx / chapterCount) * 360;
    const angleRad = (angleDeg * Math.PI) / 180;

    // Position of Chapter Nexus on the Orbital Ring
    const chapterX = orbitalRingRadius * Math.sin(angleRad);
    const chapterZ = -orbitalRingRadius * Math.cos(angleRad);
    const chapterY = Math.sin(chapterIdx * 1.5) * 1.2;
    const chapterPos: Point3D = { x: chapterX, y: chapterY, z: chapterZ };

    // Lightning fractal spline from central core to Chapter Nexus
    const branchSpline = generateLightningSpline(
      corePosition,
      chapterPos,
      8,
      2.6,
      chapterIdx + 1
    );

    // Compute Topics radiating outward from Chapter Nexus
    const topicLayouts: Topic3DLayout[] = [];
    let chapterTotalPts = 0;
    let chapterMasteredPts = 0;

    const topicCount = Math.max(1, chapter.topics.length);
    chapter.topics.forEach((topic, topicIdx) => {
      // Fan topics radially outward into space
      const topicSpread =
        topicCount === 1 ? 0 : (topicIdx - (topicCount - 1) / 2) * 0.28;
      const topicAngle = angleRad + topicSpread;
      const topicDist = 20 + (topicIdx % 2) * 4.0;

      const topicX = (orbitalRingRadius + topicDist) * Math.sin(topicAngle);
      const topicZ = -(orbitalRingRadius + topicDist) * Math.cos(topicAngle);
      const topicY = chapterY + (topicIdx - topicCount / 2) * 2.2 + Math.sin(topicIdx * 2.0) * 1.2;
      const topicPos: Point3D = { x: topicX, y: topicY, z: topicZ };

      // Sub-branch lightning spline from Chapter to Topic
      const subBranchSpline = generateLightningSpline(
        chapterPos,
        topicPos,
        6,
        1.8,
        chapterIdx * 10 + topicIdx + 2
      );

      // Compute Problem Types fanning out into space in a wide, spacious crescent canopy
      const nodeLayouts: Node3DLayout[] = [];
      const ptCount = topic.problemTypes.length;

      // Vectors for topic local coordinate frame (radial out & tangent sideways)
      const radialX = Math.sin(topicAngle);
      const radialZ = -Math.cos(topicAngle);
      const tangentX = Math.cos(topicAngle);
      const tangentZ = Math.sin(topicAngle);

      topic.problemTypes.forEach((pt, ptIdx) => {
        chapterTotalPts += 1;
        if (pt.state === "MASTERED") chapterMasteredPts += 1;

        // Wide lateral crescent fan: spreads sideways around the topic
        const fraction =
          ptCount === 1 ? 0 : (ptIdx - (ptCount - 1) / 2) / Math.max(1, ptCount - 1);
        const lateralOffset = fraction * (14.0 + Math.min(ptCount, 6) * 2.4);
        const forwardOffset =
          12.0 + (1.0 - Math.abs(fraction) * 0.45) * 6.0 + (ptIdx % 2) * 2.8;
        const elevY =
          topicY + (ptIdx % 2 === 0 ? 2.2 : -1.6) + Math.sin(ptIdx * 2.2) * 1.6;

        const nodeX = topicPos.x + radialX * forwardOffset + tangentX * lateralOffset;
        const nodeZ = topicPos.z + radialZ * forwardOffset + tangentZ * lateralOffset;
        const nodeY = elevY;
        const nodePos: Point3D = { x: nodeX, y: nodeY, z: nodeZ };

        // Branchlet lightning spline from Topic to Problem Type Node
        const branchletSpline = generateLightningSpline(
          topicPos,
          nodePos,
          5,
          1.2,
          chapterIdx * 100 + topicIdx * 10 + ptIdx + 3
        );

        const nodeLayout: Node3DLayout = {
          data: pt,
          position: nodePos,
          topicId: topic.id,
          chapterId: chapter.id,
          themeColor: theme.color,
          branchletSpline,
        };

        nodeLayouts.push(nodeLayout);
        nodeMap.set(pt.id, nodeLayout);
        nodeByCodeMap.set(pt.code, nodeLayout);
      });

      topicLayouts.push({
        data: topic,
        position: topicPos,
        chapterId: chapter.id,
        themeColor: theme.color,
        radius: 4.5,
        subBranchSpline,
        nodes: nodeLayouts,
      });
    });

    const completionPercent =
      chapterTotalPts > 0 ? Math.round((chapterMasteredPts / chapterTotalPts) * 100) : 0;

    chapterLayouts.push({
      data: chapter,
      shortName: getShortChapterName(chapter.name, chapterIdx),
      position: chapterPos,
      themeColor: theme.color,
      glowColor: theme.glow,
      branchSpline,
      topics: topicLayouts,
      totalProblemTypes: chapterTotalPts,
      masteredCount: chapterMasteredPts,
      completionPercent,
      orbitalAngle: angleRad,
    });
  });

  // Level 4: Prerequisite Bézier Arcs (rising above the galaxy plane)
  const prerequisiteArcs: PrerequisiteArc3D[] = [];
  VERIFIED_PREREQUISITE_EDGES.forEach((edge) => {
    const srcNode = nodeByCodeMap.get(edge.sourceCode);
    const tgtNode = nodeByCodeMap.get(edge.targetCode);
    if (!srcNode || !tgtNode) return;

    const midX = (srcNode.position.x + tgtNode.position.x) * 0.5;
    const midZ = (srcNode.position.z + tgtNode.position.z) * 0.5;
    const dist = Math.hypot(
      srcNode.position.x - tgtNode.position.x,
      srcNode.position.y - tgtNode.position.y,
      srcNode.position.z - tgtNode.position.z
    );
    const archHeight =
      Math.max(srcNode.position.y, tgtNode.position.y) + Math.min(22, Math.max(6, dist * 0.35));

    prerequisiteArcs.push({
      sourceCode: edge.sourceCode,
      targetCode: edge.targetCode,
      sourcePos: srcNode.position,
      targetPos: tgtNode.position,
      controlPoint: { x: midX, y: archHeight, z: midZ },
    });
  });

  return {
    corePosition,
    trunkSpline: branchSplineDefault(corePosition),
    ringRadius: orbitalRingRadius,
    chapters: chapterLayouts,
    nodeMap,
    nodeByCodeMap,
    prerequisiteArcs,
    overviewCamera: {
      position: { x: 0, y: 95, z: 105 },
      target: { x: 0, y: 0, z: -5 },
    },
  };
}

function branchSplineDefault(core: Point3D): Point3D[] {
  return [
    { x: 0, y: -4, z: 0 },
    core,
    { x: 0, y: 6, z: 0 },
  ];
}
