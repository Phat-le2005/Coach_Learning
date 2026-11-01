import * as THREE from "three";
import type { TheoryNode } from "./api";

export interface Node3DLayoutItem {
  node: TheoryNode;
  position: THREE.Vector3;
  color: THREE.Color;
  hexColor: string;
  size: number;
  depth: number;
  splineToParent?: THREE.Vector3[];
}

export interface Theory3DLayout {
  nodes: Node3DLayoutItem[];
  nodeMap: Map<string, Node3DLayoutItem>;
  connections: Array<{
    source: THREE.Vector3;
    target: THREE.Vector3;
    color: THREE.Color;
    sourceId: string;
    targetId: string;
    curve: THREE.CubicBezierCurve3;
  }>;
  sections: Array<{
    id: string;
    title: string;
    position: THREE.Vector3;
    color: string;
  }>;
}

const SECTION_PALETTE = [
  "#10b981", // Emerald
  "#06b6d4", // Cyan
  "#8b5cf6", // Violet
  "#f59e0b", // Amber
  "#f43f5e", // Rose
  "#3b82f6", // Blue
  "#ec4899", // Pink
];

export function getNodeKindColor(kind: TheoryNode["kind"], title: string, fallbackColor: string): string {
  if (kind === "FORMULA" || title.includes("📐") || title.includes("Công thức")) {
    return "#34d399"; // Mint emerald
  }
  if (kind === "EXAMPLE" || title.includes("💡") || title.includes("Ví dụ")) {
    return "#fbbf24"; // Warm gold
  }
  if (kind === "NOTE" || title.includes("⚠️") || title.includes("Bẫy") || title.includes("Lưu ý")) {
    return "#f87171"; // Coral alert
  }
  if (kind === "CONCEPT" || title.includes("📝") || title.includes("Phương pháp")) {
    return "#38bdf8"; // Vibrant sky
  }
  return fallbackColor;
}

/**
 * Computes deterministic 3D positions for a hierarchical TheoryNode tree.
 * Roots at center, Sections in orbital ring, Concepts branching outward,
 * and Formulas/Methods/Examples as satellite orbs.
 */
export function computeTheory3DLayout(nodes: TheoryNode[]): Theory3DLayout {
  const result: Theory3DLayout = {
    nodes: [],
    nodeMap: new Map(),
    connections: [],
    sections: [],
  };

  if (!nodes.length) return result;

  const root = nodes.find((n) => n.parent_id === null) ?? nodes[0];
  const rootId = root.id;

  // 1. Position ROOT at (0, 0, 0)
  const rootItem: Node3DLayoutItem = {
    node: root,
    position: new THREE.Vector3(0, 0, 0),
    color: new THREE.Color("#10b981"),
    hexColor: "#10b981",
    size: 7.5,
    depth: 0,
  };
  result.nodes.push(rootItem);
  result.nodeMap.set(rootId, rootItem);

  // 2. Identify SECTIONS
  const directSections = nodes.filter((n) => n.parent_id === rootId && n.kind === "SECTION");
  const sectionNodes = directSections.length > 0
    ? directSections
    : nodes.filter((n) => n.parent_id === rootId && n.id !== rootId);

  const secCount = Math.max(1, sectionNodes.length);
  const R_SECTION = 125;

  sectionNodes.forEach((sec, sIdx) => {
    const angle = (2 * Math.PI * sIdx) / secCount;
    const yOffset = Math.sin(sIdx * 1.7) * 20;
    const secPos = new THREE.Vector3(
      R_SECTION * Math.cos(angle),
      yOffset,
      R_SECTION * Math.sin(angle)
    );

    const themeHex = SECTION_PALETTE[sIdx % SECTION_PALETTE.length];
    const secColor = new THREE.Color(themeHex);

    const secItem: Node3DLayoutItem = {
      node: sec,
      position: secPos,
      color: secColor,
      hexColor: themeHex,
      size: 5.5,
      depth: 1,
    };

    result.nodes.push(secItem);
    result.nodeMap.set(sec.id, secItem);
    result.sections.push({
      id: sec.id,
      title: sec.title,
      position: secPos.clone(),
      color: themeHex,
    });

    // Connection Root -> Section (smooth arc)
    const midPoint = new THREE.Vector3(
      secPos.x * 0.5,
      Math.max(secPos.y, 0) + 18,
      secPos.z * 0.5
    );
    const curve = new THREE.CubicBezierCurve3(
      rootItem.position,
      new THREE.Vector3(rootItem.position.x, 12, rootItem.position.z),
      midPoint,
      secPos
    );
    result.connections.push({
      source: rootItem.position,
      target: secPos,
      color: secColor,
      sourceId: rootId,
      targetId: sec.id,
      curve,
    });

    // 3. Concepts under this Section
    const conceptNodes = nodes.filter((n) => n.parent_id === sec.id);
    const cCount = Math.max(1, conceptNodes.length);
    const R_CONCEPT = 46;

    conceptNodes.forEach((concept, cIdx) => {
      // Fan outward from section direction
      const spread = (cIdx - (cCount - 1) / 2) * (0.85 / Math.max(1, cCount));
      const cAngle = angle + spread;
      const cY = secPos.y + (cIdx - (cCount - 1) / 2) * 12 + (cIdx % 2 === 0 ? 6 : -6);

      const conceptPos = new THREE.Vector3(
        secPos.x + R_CONCEPT * Math.cos(cAngle),
        cY,
        secPos.z + R_CONCEPT * Math.sin(cAngle)
      );

      const conceptHex = getNodeKindColor(concept.kind, concept.title, themeHex);
      const conceptColor = new THREE.Color(conceptHex);

      const conceptItem: Node3DLayoutItem = {
        node: concept,
        position: conceptPos,
        color: conceptColor,
        hexColor: conceptHex,
        size: 4.2,
        depth: 2,
      };

      result.nodes.push(conceptItem);
      result.nodeMap.set(concept.id, conceptItem);

      // Connection Section -> Concept
      const cMid = new THREE.Vector3(
        (secPos.x + conceptPos.x) * 0.5,
        (secPos.y + conceptPos.y) * 0.5 + 8,
        (secPos.z + conceptPos.z) * 0.5
      );
      const cCurve = new THREE.CubicBezierCurve3(secPos, secPos, cMid, conceptPos);
      result.connections.push({
        source: secPos,
        target: conceptPos,
        color: conceptColor,
        sourceId: sec.id,
        targetId: concept.id,
        curve: cCurve,
      });

      // 4. Sub-items under Concept (Formulas, Methods, Examples, Notes)
      const leafNodes = nodes.filter((n) => n.parent_id === concept.id);
      const lCount = Math.max(1, leafNodes.length);
      const R_LEAF = 22;

      leafNodes.forEach((leaf, lIdx) => {
        const leafSpread = (lIdx - (lCount - 1) / 2) * (1.1 / Math.max(1, lCount));
        const lAngle = cAngle + leafSpread;
        const lY = conceptPos.y + (lIdx % 2 === 0 ? 1 : -1) * (7 + lIdx * 2);

        const leafPos = new THREE.Vector3(
          conceptPos.x + R_LEAF * Math.cos(lAngle),
          lY,
          conceptPos.z + R_LEAF * Math.sin(lAngle)
        );

        const leafHex = getNodeKindColor(leaf.kind, leaf.title, themeHex);
        const leafColor = new THREE.Color(leafHex);

        const leafItem: Node3DLayoutItem = {
          node: leaf,
          position: leafPos,
          color: leafColor,
          hexColor: leafHex,
          size: 2.9,
          depth: 3,
        };

        result.nodes.push(leafItem);
        result.nodeMap.set(leaf.id, leafItem);

        // Connection Concept -> Leaf
        const lMid = new THREE.Vector3(
          (conceptPos.x + leafPos.x) * 0.5,
          (conceptPos.y + leafPos.y) * 0.5 + 4,
          (conceptPos.z + leafPos.z) * 0.5
        );
        const lCurve = new THREE.CubicBezierCurve3(conceptPos, conceptPos, lMid, leafPos);
        result.connections.push({
          source: conceptPos,
          target: leafPos,
          color: leafColor,
          sourceId: concept.id,
          targetId: leaf.id,
          curve: lCurve,
        });
      });
    });
  });

  // 5. Handle any orphan nodes not yet placed
  const placedIds = new Set(result.nodes.map((n) => n.node.id));
  const orphans = nodes.filter((n) => !placedIds.has(n.id));
  if (orphans.length > 0) {
    orphans.forEach((orp, oIdx) => {
      const angle = (2 * Math.PI * oIdx) / orphans.length;
      const orpPos = new THREE.Vector3(
        155 * Math.cos(angle),
        -30 + (oIdx % 3) * 15,
        155 * Math.sin(angle)
      );
      const orpHex = getNodeKindColor(orp.kind, orp.title, "#94a3b8");
      const orpItem: Node3DLayoutItem = {
        node: orp,
        position: orpPos,
        color: new THREE.Color(orpHex),
        hexColor: orpHex,
        size: 3.2,
        depth: 2,
      };
      result.nodes.push(orpItem);
      result.nodeMap.set(orp.id, orpItem);
    });
  }

  return result;
}
