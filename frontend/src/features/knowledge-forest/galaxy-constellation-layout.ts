import type {
  KnowledgeChapterNode,
  KnowledgeProblemTypeNode,
  KnowledgeTopicNode,
} from "./types";

export interface GalaxyPoint {
  x: number;
  y: number;
}

export interface GalaxyRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface GalaxyStarLayout {
  node: KnowledgeProblemTypeNode;
  center: GalaxyPoint;
  radius: number;
  color: string;
  glowFilter: string;
  bounds: GalaxyRect;
  twigPath: string;
}

export interface GalaxyPlanetLayout {
  node: KnowledgeTopicNode;
  center: GalaxyPoint;
  radius: number;
  orbitRadius: number;
  angleDeg: number;
  bounds: GalaxyRect;
  labelBounds: GalaxyRect;
  stars: GalaxyStarLayout[];
  connectorPath: string;
}

export interface GalaxyCoreLayout {
  node: KnowledgeChapterNode;
  center: GalaxyPoint;
  radius: number;
  color: string;
  gradientId: string;
  orbitRadius: number;
  bounds: GalaxyRect;
  labelBounds: GalaxyRect;
  planets: GalaxyPlanetLayout[];
}

export interface GalaxyPrerequisiteBeam {
  fromNodeId: string;
  toNodeId: string;
  fromPoint: GalaxyPoint;
  toPoint: GalaxyPoint;
  path: string;
}

export interface GalaxyConstellationLayout {
  width: number;
  height: number;
  cores: GalaxyCoreLayout[];
  stars: GalaxyStarLayout[];
  prerequisiteBeams: GalaxyPrerequisiteBeam[];
  bounds: GalaxyRect;
}

export interface GalaxyCamera {
  x: number;
  y: number;
  scale: number;
}

export interface GalaxyViewport {
  width: number;
  height: number;
}

export const GALAXY_DIMENSIONS = {
  minScale: 0.25,
  maxScale: 2.4,
  coreRadius: 36,
  planetRadius: 18,
  starRadius: 7.5,
  masteredStarRadius: 9,
} as const;

// Chapter thematic color palettes matching Coach Learning tokens
const CHAPTER_COLORS = [
  "#63c99a", // Mint (Chương 1 - Khảo sát hàm số)
  "#5ca9d6", // Sky (Chương 2 - Tọa độ Oxyz)
  "#8578cf", // Violet (Chương 3 - Nguyên hàm, Tích phân)
  "#d8a143", // Amber (Chương 4 - Xác suất)
  "#3bb9b0", // Aqua (Chương 5 - Thống kê)
  "#de7d6b", // Coral (Chương 6 - Phương pháp số / Tọa độ nâng cao)
  "#4f9678", // Verdant
  "#c3edd5", // Light mint
];

function rounded(value: number): number {
  return Math.round(value * 100) / 100;
}

function point(x: number, y: number): GalaxyPoint {
  return { x: rounded(x), y: rounded(y) };
}

function pointRect(center: GalaxyPoint, width: number, height: number): GalaxyRect {
  return {
    x: rounded(center.x - width / 2),
    y: rounded(center.y - height / 2),
    width,
    height,
  };
}

function unionRects(rects: readonly GalaxyRect[]): GalaxyRect {
  if (rects.length === 0) return { x: 0, y: 0, width: 0, height: 0 };
  const minX = Math.min(...rects.map((r) => r.x));
  const minY = Math.min(...rects.map((r) => r.y));
  const maxX = Math.max(...rects.map((r) => r.x + r.width));
  const maxY = Math.max(...rects.map((r) => r.y + r.height));
  return {
    x: rounded(minX),
    y: rounded(minY),
    width: rounded(maxX - minX),
    height: rounded(maxY - minY),
  };
}

export function rectsOverlap(a: GalaxyRect, b: GalaxyRect): boolean {
  return (
    a.x < b.x + b.width &&
    a.x + a.width > b.x &&
    a.y < b.y + b.height &&
    a.y + a.height > b.y
  );
}

/**
 * Builds the Galaxy Constellation layout for given chapters.
 * Organizes each chapter into a Galaxy Core with Planets (topics) orbiting around it,
 * and Stars (problem types) clustering around each planet.
 */
export function buildGalaxyConstellationLayout(
  chapters: readonly KnowledgeChapterNode[]
): GalaxyConstellationLayout {
  const chapterCount = chapters.length;
  if (chapterCount === 0) {
    return {
      width: 0,
      height: 0,
      cores: [],
      stars: [],
      prerequisiteBeams: [],
      bounds: { x: 0, y: 0, width: 0, height: 0 },
    };
  }

  // Determine galaxy centers (arrange chapters in a 2-column or 3-column cosmic constellation layout)
  const cols = chapterCount <= 4 ? 2 : 3;
  const colSpacing = 680;
  const rowSpacing = 620;

  const nodeMap = new Map<string, GalaxyPoint>();
  const allStars: GalaxyStarLayout[] = [];

  const cores: GalaxyCoreLayout[] = chapters.map((chapterNode, chapterIndex) => {
    const col = chapterIndex % cols;
    const row = Math.floor(chapterIndex / cols);
    const offsetX = (row % 2) * 120; // stagger alternating rows for natural organic constellation look

    const coreCenter = point(
      380 + col * colSpacing + offsetX,
      350 + row * rowSpacing
    );
    nodeMap.set(chapterNode.id, coreCenter);

    const chapterColor = CHAPTER_COLORS[chapterIndex % CHAPTER_COLORS.length];
    const gradientId = `galaxy-grad-${chapterIndex % 6}`;

    // Layout Topics (Planets) orbiting around this Chapter Core
    const topicCount = chapterNode.topics.length;
    const baseOrbitRadius = Math.max(160, 110 + topicCount * 18);

    const planets: GalaxyPlanetLayout[] = chapterNode.topics.map((topicNode, topicIndex) => {
      // Calculate angular position with even distribution and starting angle offset
      const startAngle = (chapterIndex * 45) % 360;
      const angleStep = 360 / Math.max(1, topicCount);
      const angleDeg = (startAngle + topicIndex * angleStep) % 360;
      const angleRad = (angleDeg * Math.PI) / 180;

      // Small alternating radial distance for depth and label collision prevention
      const distOffset = (topicIndex % 2 === 0 ? 0 : 25);
      const topicOrbitRadius = baseOrbitRadius + distOffset;

      const planetCenter = point(
        coreCenter.x + topicOrbitRadius * Math.cos(angleRad),
        coreCenter.y + topicOrbitRadius * Math.sin(angleRad)
      );
      nodeMap.set(topicNode.id, planetCenter);

      // Connector line from Galaxy Core to Planet
      const connectorPath = `M ${coreCenter.x} ${coreCenter.y} L ${planetCenter.x} ${planetCenter.y}`;

      // Layout Stars (Problem Types) around each Planet
      const ptCount = topicNode.problemTypes.length;
      const starOrbitDist = Math.max(55, 42 + ptCount * 3.5);

      const stars: GalaxyStarLayout[] = topicNode.problemTypes.map((ptNode, starIndex) => {
        const starAngleStep = (Math.PI * 2) / Math.max(1, ptCount);
        const starAngle = angleRad + (starIndex - (ptCount - 1) / 2) * starAngleStep * 0.75 + Math.PI;
        const starCenter = point(
          planetCenter.x + starOrbitDist * Math.cos(starAngle),
          planetCenter.y + starOrbitDist * Math.sin(starAngle)
        );
        nodeMap.set(ptNode.id, starCenter);

        const isMastered = ptNode.state === "MASTERED";
        const isProgress = ptNode.state === "PRACTICING" || ptNode.state === "LEARNING";
        const isReview = ptNode.state === "REVIEW_DUE" || ptNode.state === "WEAK";

        let starColor = "rgb(156 163 175 / 60%)";
        let glowFilter = "none";
        if (isMastered) {
          starColor = "#d8a143";
          glowFilter = "url(#intenseGlow)";
        } else if (isProgress) {
          starColor = "#3bb9b0";
          glowFilter = "url(#glowEffect)";
        } else if (isReview) {
          starColor = "#de7d6b";
          glowFilter = "url(#glowEffect)";
        }

        const radius = isMastered
          ? GALAXY_DIMENSIONS.masteredStarRadius
          : GALAXY_DIMENSIONS.starRadius;

        const starBounds = pointRect(starCenter, radius * 2 + 10, radius * 2 + 10);
        const twigPath = `M ${planetCenter.x} ${planetCenter.y} L ${starCenter.x} ${starCenter.y}`;

        const starLayout: GalaxyStarLayout = {
          node: ptNode,
          center: starCenter,
          radius,
          color: starColor,
          glowFilter,
          bounds: starBounds,
          twigPath,
        };

        allStars.push(starLayout);
        return starLayout;
      });

      const planetBounds = pointRect(
        planetCenter,
        GALAXY_DIMENSIONS.planetRadius * 2 + 20,
        GALAXY_DIMENSIONS.planetRadius * 2 + 20
      );
      const labelBounds = pointRect(point(planetCenter.x, planetCenter.y + 26), 140, 32);

      return {
        node: topicNode,
        center: planetCenter,
        radius: GALAXY_DIMENSIONS.planetRadius,
        orbitRadius: topicOrbitRadius,
        angleDeg,
        bounds: unionRects([planetBounds, labelBounds, ...stars.map((s) => s.bounds)]),
        labelBounds,
        stars,
        connectorPath,
      };
    });

    const coreBounds = pointRect(
      coreCenter,
      GALAXY_DIMENSIONS.coreRadius * 2 + 30,
      GALAXY_DIMENSIONS.coreRadius * 2 + 30
    );
    const coreLabelBounds = pointRect(point(coreCenter.x, coreCenter.y + 54), 190, 42);

    return {
      node: chapterNode,
      center: coreCenter,
      radius: GALAXY_DIMENSIONS.coreRadius,
      color: chapterColor,
      gradientId,
      orbitRadius: baseOrbitRadius,
      bounds: unionRects([coreBounds, coreLabelBounds, ...planets.map((p) => p.bounds)]),
      labelBounds: coreLabelBounds,
      planets,
    };
  });

  // Synthesize prerequisite starlight beams connecting sequential and related nodes
  const prerequisiteBeams: GalaxyPrerequisiteBeam[] = [];

  // 1. Intra-topic beams connecting sequential problem types
  cores.forEach((core) => {
    core.planets.forEach((planet) => {
      for (let i = 0; i < planet.stars.length - 1; i++) {
        const fromStar = planet.stars[i];
        const toStar = planet.stars[i + 1];
        const dx = toStar.center.x - fromStar.center.x;
        const dy = toStar.center.y - fromStar.center.y;
        const cx = (fromStar.center.x + toStar.center.x) / 2 - dy * 0.15;
        const cy = (fromStar.center.y + toStar.center.y) / 2 + dx * 0.15;
        prerequisiteBeams.push({
          fromNodeId: fromStar.node.id,
          toNodeId: toStar.node.id,
          fromPoint: fromStar.center,
          toPoint: toStar.center,
          path: `M ${fromStar.center.x} ${fromStar.center.y} Q ${cx} ${cy} ${toStar.center.x} ${toStar.center.y}`,
        });
      }
    });

    // 2. Intra-chapter beams connecting sequential topics
    for (let i = 0; i < core.planets.length - 1; i++) {
      const fromP = core.planets[i];
      const toP = core.planets[i + 1];
      const cx = (fromP.center.x + toP.center.x) / 2;
      const cy = (fromP.center.y + toP.center.y) / 2;
      prerequisiteBeams.push({
        fromNodeId: fromP.node.id,
        toNodeId: toP.node.id,
        fromPoint: fromP.center,
        toPoint: toP.center,
        path: `M ${fromP.center.x} ${fromP.center.y} Q ${cx} ${cy} ${toP.center.x} ${toP.center.y}`,
      });
    }
  });

  // 3. Macro beams connecting sequential chapters
  for (let i = 0; i < cores.length - 1; i++) {
    const fromCore = cores[i];
    const toCore = cores[i + 1];
    const dx = toCore.center.x - fromCore.center.x;
    const dy = toCore.center.y - fromCore.center.y;
    const cx1 = fromCore.center.x + dx * 0.4;
    const cy1 = fromCore.center.y + dy * 0.1;
    const cx2 = fromCore.center.x + dx * 0.6;
    const cy2 = fromCore.center.y + dy * 0.9;
    prerequisiteBeams.push({
      fromNodeId: fromCore.node.id,
      toNodeId: toCore.node.id,
      fromPoint: fromCore.center,
      toPoint: toCore.center,
      path: `M ${fromCore.center.x} ${fromCore.center.y} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${toCore.center.x} ${toCore.center.y}`,
    });
  }

  const allBounds = unionRects(cores.map((c) => c.bounds));

  return {
    width: Math.max(1200, allBounds.x + allBounds.width + 120),
    height: Math.max(900, allBounds.y + allBounds.height + 120),
    cores,
    stars: allStars,
    prerequisiteBeams,
    bounds: allBounds,
  };
}

export function fitGalaxyCamera(
  viewport: GalaxyViewport,
  bounds: GalaxyRect,
  padding = 48,
  fillRatio = 0.92
): GalaxyCamera {
  if (viewport.width <= 1 || viewport.height <= 1 || bounds.width <= 0 || bounds.height <= 0) {
    return { x: 0, y: 0, scale: 0.85 };
  }
  const availableWidth = Math.max(10, viewport.width - padding * 2);
  const availableHeight = Math.max(10, viewport.height - padding * 2);
  const scaleX = availableWidth / bounds.width;
  const scaleY = availableHeight / bounds.height;
  const rawScale = Math.min(scaleX, scaleY) * fillRatio;
  const scale = rounded(
    Math.min(GALAXY_DIMENSIONS.maxScale, Math.max(GALAXY_DIMENSIONS.minScale, rawScale))
  );

  const centerX = bounds.x + bounds.width / 2;
  const centerY = bounds.y + bounds.height / 2;
  const x = rounded(viewport.width / 2 - centerX * scale);
  const y = rounded(viewport.height / 2 - centerY * scale);
  return { x, y, scale };
}

export function focusGalaxyCamera(
  viewport: GalaxyViewport,
  targetBounds: GalaxyRect,
  padding = 64,
  maxScale = 1.35
): GalaxyCamera {
  if (viewport.width <= 1 || viewport.height <= 1 || targetBounds.width <= 0 || targetBounds.height <= 0) {
    return { x: 0, y: 0, scale: 1.0 };
  }
  const availableWidth = Math.max(10, viewport.width - padding * 2);
  const availableHeight = Math.max(10, viewport.height - padding * 2);
  const scaleX = availableWidth / targetBounds.width;
  const scaleY = availableHeight / targetBounds.height;
  const rawScale = Math.min(scaleX, scaleY);
  const scale = rounded(
    Math.min(maxScale, Math.max(GALAXY_DIMENSIONS.minScale, rawScale))
  );

  const centerX = targetBounds.x + targetBounds.width / 2;
  const centerY = targetBounds.y + targetBounds.height / 2;
  const x = rounded(viewport.width / 2 - centerX * scale);
  const y = rounded(viewport.height / 2 - centerY * scale);
  return { x, y, scale };
}

export function panGalaxyCamera(camera: GalaxyCamera, delta: GalaxyPoint): GalaxyCamera {
  return {
    x: rounded(camera.x + delta.x),
    y: rounded(camera.y + delta.y),
    scale: camera.scale,
  };
}

export function zoomGalaxyCameraAt(
  camera: GalaxyCamera,
  cursor: GalaxyPoint,
  nextScale: number
): GalaxyCamera {
  const boundedScale = Math.min(
    GALAXY_DIMENSIONS.maxScale,
    Math.max(GALAXY_DIMENSIONS.minScale, nextScale)
  );
  if (Math.abs(boundedScale - camera.scale) < 0.001) return camera;

  const currentScale = camera.scale;
  const worldX = (cursor.x - camera.x) / currentScale;
  const worldY = (cursor.y - camera.y) / currentScale;
  const x = rounded(cursor.x - worldX * boundedScale);
  const y = rounded(cursor.y - worldY * boundedScale);
  return { x, y, scale: rounded(boundedScale) };
}
