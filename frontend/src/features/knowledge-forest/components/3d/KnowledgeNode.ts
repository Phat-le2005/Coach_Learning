import * as THREE from "three";
import { MASTERY_3D_COLORS, type Node3DLayout } from "../../tree-3d-layout";
import type { KnowledgeProblemTypeNode } from "../../types";

export interface NodesSystem {
  group: THREE.Group;
  nodeMeshes: Map<string, THREE.Mesh>;
  interactiveMeshes: THREE.Mesh[];
  highlightNode: (id: string | null) => void;
  selectNode: (id: string | null) => void;
  update: (time: number) => void;
  dispose: () => void;
}

export function createKnowledgeNodes(nodes: Node3DLayout[]): NodesSystem {
  const group = new THREE.Group();
  group.name = "knowledge-nodes-group";

  const nodeMeshes = new Map<string, THREE.Mesh>();
  const interactiveMeshes: THREE.Mesh[] = [];
  const animatedNodes: Array<{
    mesh: THREE.Mesh;
    basePos: THREE.Vector3;
    ring1: THREE.Mesh;
    ring2: THREE.Mesh;
    satelliteSpark: THREE.Mesh;
    stemCurve: THREE.CatmullRomCurve3;
    sparkGeo: THREE.BufferGeometry;
    pt: KnowledgeProblemTypeNode;
    idx: number;
  }> = [];

  const disposables: Array<{ dispose: () => void }> = [];

  let highlightedId: string | null = null;
  let selectedId: string | null = null;

  nodes.forEach((node, nodeIdx) => {
    const pt = node.data;
    const colors = MASTERY_3D_COLORS[pt.state] ?? MASTERY_3D_COLORS.NOT_STARTED;
    const baseCol = new THREE.Color(colors.base);
    const emissiveCol = new THREE.Color(colors.emissive);
    const chapterCol = new THREE.Color(node.themeColor);

    // =========================================================================
    // 1. VOLUMETRIC ELECTRIC GLOW STEM & TRAVELING SPARK CURRENT
    // =========================================================================
    const splineVectors = node.branchletSpline.map((p) => new THREE.Vector3(p.x, p.y, p.z));
    const curve = new THREE.CatmullRomCurve3(splineVectors);

    // Outer Glow Aura
    const stemAuraGeo = new THREE.TubeGeometry(curve, 12, 0.42, 6, false);
    const stemAuraMat = new THREE.MeshBasicMaterial({
      color: chapterCol,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const stemAuraMesh = new THREE.Mesh(stemAuraGeo, stemAuraMat);
    group.add(stemAuraMesh);
    disposables.push(stemAuraGeo, stemAuraMat);

    // Mid Electric Tube
    const stemGeo = new THREE.TubeGeometry(curve, 12, 0.18, 6, false);
    const stemMat = new THREE.MeshBasicMaterial({
      color: chapterCol,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
    });
    const stemMesh = new THREE.Mesh(stemGeo, stemMat);
    group.add(stemMesh);
    disposables.push(stemGeo, stemMat);

    // 2 Traveling Energy Sparks along the stem feeding into the node
    const sparkCount = 2;
    const sparkGeo = new THREE.BufferGeometry();
    const sparkPositions = new Float32Array(sparkCount * 3);
    sparkGeo.setAttribute("position", new THREE.BufferAttribute(sparkPositions, 3));
    const sparkMat = new THREE.PointsMaterial({
      color: new THREE.Color("#ffffff"),
      size: 2.4,
      transparent: true,
      opacity: 0.95,
      blending: THREE.AdditiveBlending,
    });
    const stemSparks = new THREE.Points(sparkGeo, sparkMat);
    group.add(stemSparks);
    disposables.push(sparkGeo, sparkMat);

    // =========================================================================
    // 2. LUMINOUS CRYSTAL NODE WITH ATOMIC GYROSCOPIC RINGS & SATELLITE
    // =========================================================================
    const gemGeo = new THREE.IcosahedronGeometry(1.35, 1);
    const gemMat = new THREE.MeshStandardMaterial({
      color: baseCol,
      emissive: emissiveCol,
      emissiveIntensity: pt.state === "NOT_STARTED" ? 1.1 : 1.8,
      roughness: 0.1,
      metalness: 0.85,
    });
    const gemMesh = new THREE.Mesh(gemGeo, gemMat);
    gemMesh.position.set(node.position.x, node.position.y, node.position.z);
    gemMesh.userData = {
      kind: "node",
      id: pt.id,
      code: pt.code,
      name: pt.name,
      data: pt,
      originalScale: 1.0,
      baseColor: baseCol,
      emissiveColor: emissiveCol,
    };

    // Fast Inner Orbital Energy Ring
    const ring1Geo = new THREE.TorusGeometry(1.95, 0.09, 6, 28);
    const ring1Mat = new THREE.MeshBasicMaterial({
      color: emissiveCol,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
    });
    const ring1Mesh = new THREE.Mesh(ring1Geo, ring1Mat);
    gemMesh.add(ring1Mesh);
    disposables.push(ring1Geo, ring1Mat);

    // Fast Outer Tilted Polar Ring
    const ring2Geo = new THREE.TorusGeometry(2.35, 0.07, 6, 28);
    const ring2Mat = new THREE.MeshBasicMaterial({
      color: new THREE.Color("#ffffff"),
      transparent: true,
      opacity: 0.7,
      blending: THREE.AdditiveBlending,
    });
    const ring2Mesh = new THREE.Mesh(ring2Geo, ring2Mat);
    ring2Mesh.rotation.x = Math.PI / 3;
    gemMesh.add(ring2Mesh);
    disposables.push(ring2Geo, ring2Mat);

    // Orbiting Satellite Spark Moon (Vệ tinh năng lượng bay tròn quanh cục nhỏ)
    const satGeo = new THREE.SphereGeometry(0.32, 10, 10);
    const satMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color("#ffffff"),
      blending: THREE.AdditiveBlending,
    });
    const satelliteSpark = new THREE.Mesh(satGeo, satMat);
    gemMesh.add(satelliteSpark);
    disposables.push(satGeo, satMat);

    group.add(gemMesh);
    nodeMeshes.set(pt.id, gemMesh);
    interactiveMeshes.push(gemMesh);
    disposables.push(gemGeo, gemMat);

    animatedNodes.push({
      mesh: gemMesh,
      basePos: new THREE.Vector3(node.position.x, node.position.y, node.position.z),
      ring1: ring1Mesh,
      ring2: ring2Mesh,
      satelliteSpark,
      stemCurve: curve,
      sparkGeo,
      pt,
      idx: nodeIdx,
    });
  });

  const highlightNode = (id: string | null) => {
    highlightedId = id;
    nodeMeshes.forEach((mesh, nodeId) => {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      if (nodeId === id) {
        mesh.scale.setScalar(1.65);
        mat.emissiveIntensity = 2.6;
      } else if (nodeId !== selectedId) {
        mesh.scale.setScalar(1.0);
        mat.emissiveIntensity = 1.1;
      }
    });
  };

  const selectNode = (id: string | null) => {
    selectedId = id;
    nodeMeshes.forEach((mesh, nodeId) => {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      if (nodeId === id) {
        mesh.scale.setScalar(1.85);
        mat.emissiveIntensity = 3.2;
      } else if (nodeId !== highlightedId) {
        mesh.scale.setScalar(1.0);
        mat.emissiveIntensity = 1.1;
      }
    });
  };

  // =========================================================================
  // VIBRANT LIVING MOTION UPDATE (CHUYỂN ĐỘNG LINH HOẠT, BỒNG BỀNH & QUAY TRÒN)
  // =========================================================================
  const update = (time: number) => {
    animatedNodes.forEach(({ mesh, basePos, ring1, ring2, satelliteSpark, stemCurve, sparkGeo, pt, idx }) => {
      const isSelected = pt.id === selectedId;
      const isHighlighted = pt.id === highlightedId;

      // 1. Clearly Visible 3D Microgravity Floating (Biên độ dao động rõ rệt 1.5 đơn vị)
      const floatY = Math.sin(time * 2.2 + idx * 0.8) * 1.5;
      const floatX = Math.cos(time * 1.7 + idx * 0.6) * 1.0;
      const floatZ = Math.sin(time * 1.4 + idx * 0.7) * 0.8;
      mesh.position.set(basePos.x + floatX, basePos.y + floatY, basePos.z + floatZ);

      // 2. Continuous Axial Spin of the Crystal Gem (Cục tinh thể tự xoay quanh trục)
      mesh.rotation.y = time * 2.0 + idx;
      mesh.rotation.x = Math.sin(time * 1.3 + idx) * 0.45;

      // 3. Fast Atomic Gyroscopic Rings Precession (Hai vòng quay điện tử con quay)
      ring1.rotation.z = time * 3.8;
      ring1.rotation.x = Math.sin(time * 2.2) * 0.9;
      ring2.rotation.y = -time * 3.2;
      ring2.rotation.z = Math.cos(time * 2.0) * 0.7;

      // 4. Orbiting Spark Moon around each node (Hạt vệ tinh sáng bay lượn quanh cục nhỏ)
      const sparkAngle = time * 3.6 + idx * 1.3;
      const sparkRadius = 2.4;
      satelliteSpark.position.set(
        Math.cos(sparkAngle) * sparkRadius,
        Math.sin(time * 4.2 + idx) * 0.9,
        Math.sin(sparkAngle) * sparkRadius
      );

      // 5. Breathing Scale & Emissive Glow Pulsation (Nhịp thở phồng xẹp & bừng sáng)
      const breathe = 1.0 + Math.sin(time * 3.2 + idx * 0.7) * 0.14;
      if (isSelected) {
        mesh.scale.setScalar(1.85);
      } else if (isHighlighted) {
        mesh.scale.setScalar(1.6);
      } else {
        mesh.scale.setScalar(breathe);
      }

      const mat = mesh.material as THREE.MeshStandardMaterial;
      const baseEmissive = pt.state === "NOT_STARTED" ? 1.1 : 1.8;
      mat.emissiveIntensity = baseEmissive + Math.sin(time * 3.6 + idx) * 0.45;

      // 6. Review-due warning pulse
      if (pt?.isReviewDue && !isSelected) {
        const alertPulse = 1.0 + Math.sin(time * 5.5) * 0.25;
        mesh.scale.setScalar(alertPulse);
      }

      // 7. Update Traveling Energy Sparks down the stem into the node
      const posArr = sparkGeo.attributes.position.array as Float32Array;
      const sparkCount = posArr.length / 3;
      for (let s = 0; s < sparkCount; s++) {
        const t = (time * 0.6 + s / sparkCount + idx * 0.12) % 1.0;
        const ptOnCurve = stemCurve.getPoint(t);
        posArr[s * 3] = ptOnCurve.x;
        posArr[s * 3 + 1] = ptOnCurve.y;
        posArr[s * 3 + 2] = ptOnCurve.z;
      }
      sparkGeo.attributes.position.needsUpdate = true;
    });
  };

  const dispose = () => {
    disposables.forEach((d) => d.dispose());
  };

  return {
    group,
    nodeMeshes,
    interactiveMeshes,
    highlightNode,
    selectNode,
    update,
    dispose,
  };
}
