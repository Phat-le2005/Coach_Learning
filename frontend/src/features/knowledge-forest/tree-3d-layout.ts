/**
 * 3D Spatial Layout Mathematics for EduMS — Living Knowledge World
 *
 * Establishes a majestic stylized ancient tree coordinate system where:
 * - Level 0: Knowledge Core at the center of the trunk.
 * - Level 1: Chapters branch upward & outward in an amphitheater canopy fan.
 * - Level 2: Topics cluster as luminous celestial platforms.
 * - Level 3: Problem Types fan out in an elevated crown of glowing gem crystals.
 * - Level 4: Prerequisite Bézier arcs link interconnected competencies.
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
  chapters: Chapter3DLayout[];
  nodeMap: Map<string, Node3DLayout>;
  nodeByCodeMap: Map<string, Node3DLayout>;
  prerequisiteArcs: PrerequisiteArc3D[];
  overviewCamera: { position: Point3D; target: Point3D };
}

// 7 thematic palettes harmonized with EduMS Deep Forest & Emerald styling
export const CHAPTER_3D_THEMES = [
  { color: "#23A67A", glow: "rgba(35, 166, 122, 0.6)", name: "Ứng dụng Đạo hàm" },
  { color: "#38BDF8", glow: "rgba(56, 189, 248, 0.6)", name: "Mũ & Logarit" },
  { color: "#818CF8", glow: "rgba(129, 140, 248, 0.6)", name: "Vectơ không gian" },
  { color: "#F59E0B", glow: "rgba(245, 158, 11, 0.6)", name: "Thống kê số liệu" },
  { color: "#A855F7", glow: "rgba(168, 85, 247, 0.6)", name: "Nguyên hàm & Tích phân" },
  { color: "#0D9488", glow: "rgba(13, 148, 136, 0.6)", name: "Tọa độ Oxyz" },
  { color: "#FB7185", glow: "rgba(251, 113, 133, 0.6)", name: "Xác suất có điều kiện" },
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
    base: "#E2F8F0",
    emissive: "#38A185",
    glow: "rgba(139, 229, 194, 0.7)",
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
 * Computes deterministic, balanced 3D coordinates for all entities in the Knowledge World.
 */
export function computeLivingWorld3DLayout(chapters: KnowledgeChapterNode[]): LivingWorld3DLayout {
  const corePosition: Point3D = { x: 0, y: 10, z: 0 };
  const trunkSpline: Point3D[] = [
    { x: 0, y: -7, z: 0 },
    { x: 0.8, y: 0, z: -0.5 },
    { x: -0.8, y: 7, z: 0.5 },
    { x: 0, y: 15, z: 0 },
    { x: 0, y: 26, z: 0 },
  ];

  const nodeMap = new Map<string, Node3DLayout>();
  const nodeByCodeMap = new Map<string, Node3DLayout>();
  const chapterLayouts: Chapter3DLayout[] = [];

  const chapterCount = Math.max(1, chapters.length);
  // Distribute chapters in a wide amphitheater arc (-135 deg to +135 deg) facing the camera
  const startAngleDeg = -135;
  const sweepAngleDeg = 270;

  chapters.forEach((chapter, chapterIdx) => {
    const theme = CHAPTER_3D_THEMES[chapterIdx % CHAPTER_3D_THEMES.length];
    const fraction = chapterCount === 1 ? 0.5 : chapterIdx / (chapterCount - 1);
    const angleRad = ((startAngleDeg + sweepAngleDeg * fraction) * Math.PI) / 180;

    // Radius staggered for spatial depth: 44 to 52
    const chapterRadius = 44 + (chapterIdx % 2 === 0 ? 0 : 7);
    // Elevation waves gently between 18 and 26 units
    const chapterElevation = 20 + Math.sin(chapterIdx * 1.4) * 5;

    const chapterX = chapterRadius * Math.sin(angleRad);
    const chapterZ = chapterRadius * Math.cos(angleRad);
    const chapterPos: Point3D = { x: chapterX, y: chapterElevation, z: chapterZ };

    // Spline curve for the main chapter branch extending upward and outward from the trunk
    const branchTrunkAttach: Point3D = { x: 0, y: 13 + (chapterIdx % 3) * 3, z: 0 };
    const branchMid: Point3D = {
      x: chapterX * 0.42,
      y: (branchTrunkAttach.y + chapterElevation) * 0.5 + 4.5,
      z: chapterZ * 0.42,
    };
    const branchSpline: Point3D[] = [branchTrunkAttach, branchMid, chapterPos];

    // Compute topics along this branch
    const topicLayouts: Topic3DLayout[] = [];
    let chapterTotalPts = 0;
    let chapterMasteredPts = 0;

    const topicCount = Math.max(1, chapter.topics.length);
    chapter.topics.forEach((topic, topicIdx) => {
      // Fan topics outward in a stepped halo around the chapter joint
      const topicFraction = topicCount === 1 ? 0 : (topicIdx - (topicCount - 1) / 2) / Math.max(1, topicCount);
      const topicOffsetAngle = angleRad + topicFraction * 0.85;
      const topicDist = 16 + (topicIdx % 2) * 5.5;
      const topicY = chapterElevation + 2.5 + (topicIdx - topicCount / 2) * 2.2;

      const topicX = chapterX + topicDist * Math.sin(topicOffsetAngle);
      const topicZ = chapterZ + topicDist * Math.cos(topicOffsetAngle);
      const topicPos: Point3D = { x: topicX, y: topicY, z: topicZ };

      const subBranchMid: Point3D = {
        x: (chapterX + topicX) * 0.5,
        y: Math.max(chapterElevation, topicY) + 2.0,
        z: (chapterZ + topicZ) * 0.5,
      };
      const subBranchSpline: Point3D[] = [chapterPos, subBranchMid, topicPos];

      // Compute problem type nodes in an elevated, spacious crown around the topic
      const nodeLayouts: Node3DLayout[] = [];
      const ptCount = topic.problemTypes.length;

      topic.problemTypes.forEach((pt, ptIdx) => {
        chapterTotalPts += 1;
        if (pt.state === "MASTERED") chapterMasteredPts += 1;

        // Spread nodes radially with wide angular spacing so they NEVER clump or overlap
        const spreadAngle =
          topicOffsetAngle + (ptCount === 1 ? 0 : ((ptIdx - (ptCount - 1) / 2) * 1.35) / Math.max(1, ptCount));
        const orbitRadius = 7.5 + (ptIdx % 2) * 2.6;
        // Elevate nodes upwards like blossoming celestial crystals
        const nodeY = topicY + 2.4 + Math.sin(ptIdx * 1.4) * 2.2;

        const nodeX = topicX + orbitRadius * Math.sin(spreadAngle);
        const nodeZ = topicZ + orbitRadius * Math.cos(spreadAngle);
        const nodePos: Point3D = { x: nodeX, y: nodeY, z: nodeZ };

        const branchletSpline: Point3D[] = [
          topicPos,
          { x: (topicX + nodeX) * 0.5, y: Math.max(topicY, nodeY) + 1.2, z: (topicZ + nodeZ) * 0.5 },
          nodePos,
        ];

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
        radius: 5.0,
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
    });
  });

  // Level 4: Prerequisite Bézier Arcs (only where both source and target exist in layout)
  const prerequisiteArcs: PrerequisiteArc3D[] = [];
  VERIFIED_PREREQUISITE_EDGES.forEach((edge) => {
    const srcNode = nodeByCodeMap.get(edge.sourceCode);
    const tgtNode = nodeByCodeMap.get(edge.targetCode);
    if (!srcNode || !tgtNode) return;

    // Compute arched control point rising gracefully above both endpoints
    const midX = (srcNode.position.x + tgtNode.position.x) * 0.5;
    const midZ = (srcNode.position.z + tgtNode.position.z) * 0.5;
    const dist = Math.hypot(
      srcNode.position.x - tgtNode.position.x,
      srcNode.position.y - tgtNode.position.y,
      srcNode.position.z - tgtNode.position.z
    );
    const archHeight = Math.max(srcNode.position.y, tgtNode.position.y) + Math.min(22, Math.max(5, dist * 0.38));

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
    trunkSpline,
    chapters: chapterLayouts,
    nodeMap,
    nodeByCodeMap,
    prerequisiteArcs,
    overviewCamera: {
      position: { x: 0, y: 55, z: 135 },
      target: { x: 0, y: 18, z: 0 },
    },
  };
}
