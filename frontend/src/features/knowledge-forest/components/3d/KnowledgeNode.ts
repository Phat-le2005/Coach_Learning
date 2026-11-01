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
    beaconRing: THREE.Mesh | null;
    satelliteSpark: THREE.Mesh;
    stemCurve: THREE.CatmullRomCurve3;
    sparkGeo: THREE.BufferGeometry;
    pt: KnowledgeProblemTypeNode;
    idx: number;
    isFog: boolean;
    isCurrentTeaching: boolean;
  }> = [];

  const disposables: Array<{ dispose: () => void }> = [];

  let highlightedId: string | null = null;
  let selectedId: string | null = null;

  nodes.forEach((node, nodeIdx) => {
    const pt = node.data;
    const isFog = pt.scopeState === "FOG_OF_WAR" && pt.attemptCount === 0;
    const isCurrentTeaching = pt.scopeState === "CURRENT_TEACHING";

    const colors = MASTERY_3D_COLORS[pt.state] ?? MASTERY_3D_COLORS.NOT_STARTED;
    const baseCol = isFog
      ? new THREE.Color("#334155")
      : isCurrentTeaching && pt.state === "NOT_STARTED"
        ? new THREE.Color("#fbbf24")
        : new THREE.Color(colors.base);
    const emissiveCol = isFog
      ? new THREE.Color("#1e293b")
      : isCurrentTeaching && pt.state === "NOT_STARTED"
        ? new THREE.Color("#d97706")
        : new THREE.Color(colors.emissive);
    const chapterCol = isFog ? new THREE.Color("#334155") : new THREE.Color(node.themeColor);

    // =========================================================================
    // 1. VOLUMETRIC ELECTRIC GLOW STEM & TRAVELING SPARK CURRENT
    // =========================================================================
    const splineVectors = node.branchletSpline.map((p) => new THREE.Vector3(p.x, p.y, p.z));
    const curve = new THREE.CatmullRomCurve3(splineVectors);

    // Outer Glow Aura
    const stemAuraGeo = new THREE.TubeGeometry(curve, 12, isFog ? 0.24 : 0.42, 6, false);
    const stemAuraMat = new THREE.MeshBasicMaterial({
      color: chapterCol,
      transparent: true,
      opacity: isFog ? 0.1 : isCurrentTeaching ? 0.5 : 0.35,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const stemAuraMesh = new THREE.Mesh(stemAuraGeo, stemAuraMat);
    group.add(stemAuraMesh);
    disposables.push(stemAuraGeo, stemAuraMat);

    // Mid Electric Tube
    const stemGeo = new THREE.TubeGeometry(curve, 12, isFog ? 0.11 : 0.18, 6, false);
    const stemMat = new THREE.MeshBasicMaterial({
      color: chapterCol,
      transparent: true,
      opacity: isFog ? 0.22 : 0.9,
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
      color: new THREE.Color(isCurrentTeaching ? "#fef08a" : "#ffffff"),
      size: isFog ? 1.1 : isCurrentTeaching ? 2.9 : 2.4,
      transparent: true,
      opacity: isFog ? 0.22 : 0.95,
      blending: THREE.AdditiveBlending,
    });
    const stemSparks = new THREE.Points(sparkGeo, sparkMat);
    group.add(stemSparks);
    disposables.push(sparkGeo, sparkMat);

    // =========================================================================
    // 2. LUMINOUS CRYSTAL NODE WITH ATOMIC GYROSCOPIC RINGS & SATELLITE
    // =========================================================================
    const gemGeo = new THREE.IcosahedronGeometry(1.35, 1);
    const initialEmissive = isFog
      ? 0.35
      : isCurrentTeaching
        ? 2.2
        : pt.state === "NOT_STARTED"
          ? 1.1
          : 1.9;

    const gemMat = new THREE.MeshStandardMaterial({
      color: baseCol,
      emissive: emissiveCol,
      emissiveIntensity: initialEmissive,
      roughness: isFog ? 0.45 : 0.1,
      metalness: isFog ? 0.4 : 0.85,
      transparent: isFog,
      opacity: isFog ? 0.55 : 1.0,
    });
    const gemMesh = new THREE.Mesh(gemGeo, gemMat);
    gemMesh.position.set(node.position.x, node.position.y, node.position.z);
    gemMesh.userData = {
      kind: "node",
      id: pt.id,
      code: pt.code,
      name: pt.name,
      data: pt,
      originalScale: isFog ? 0.78 : isCurrentTeaching ? 1.15 : 1.0,
      baseColor: baseCol,
      emissiveColor: emissiveCol,
    };

    // Fast Inner Orbital Energy Ring
    const ring1Geo = new THREE.TorusGeometry(1.95, 0.09, 6, 28);
    const ring1Mat = new THREE.MeshBasicMaterial({
      color: emissiveCol,
      transparent: true,
      opacity: isFog ? 0.25 : 0.9,
      blending: THREE.AdditiveBlending,
    });
    const ring1Mesh = new THREE.Mesh(ring1Geo, ring1Mat);
    gemMesh.add(ring1Mesh);
    disposables.push(ring1Geo, ring1Mat);

    // Fast Outer Tilted Polar Ring
    const ring2Geo = new THREE.TorusGeometry(2.35, 0.07, 6, 28);
    const ring2Mat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(isCurrentTeaching ? "#fde047" : "#ffffff"),
      transparent: true,
      opacity: isFog ? 0.18 : 0.72,
      blending: THREE.AdditiveBlending,
    });
    const ring2Mesh = new THREE.Mesh(ring2Geo, ring2Mat);
    ring2Mesh.rotation.x = Math.PI / 3;
    gemMesh.add(ring2Mesh);
    disposables.push(ring2Geo, ring2Mat);

    // Teacher Current Focus / Weak Alert Beacon Ring
    let beaconRing: THREE.Mesh | null = null;
    if (isCurrentTeaching || pt.state === "WEAK") {
      const beaconGeo = new THREE.TorusGeometry(2.95, 0.085, 8, 36);
      const beaconMat = new THREE.MeshBasicMaterial({
        color: new THREE.Color(pt.state === "WEAK" ? "#f87171" : "#fbbf24"),
        transparent: true,
        opacity: 0.85,
        blending: THREE.AdditiveBlending,
      });
      beaconRing = new THREE.Mesh(beaconGeo, beaconMat);
      beaconRing.rotation.x = Math.PI / 2;
      gemMesh.add(beaconRing);
      disposables.push(beaconGeo, beaconMat);
    }

    // Orbiting Satellite Spark Moon
    const satGeo = new THREE.SphereGeometry(isFog ? 0.2 : 0.32, 10, 10);
    const satMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color(isCurrentTeaching ? "#fef08a" : "#ffffff"),
      transparent: true,
      opacity: isFog ? 0.25 : 1.0,
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
      beaconRing,
      satelliteSpark,
      stemCurve: curve,
      sparkGeo,
      pt,
      idx: nodeIdx,
      isFog,
      isCurrentTeaching,
    });
  });

  const highlightNode = (id: string | null) => {
    highlightedId = id;
    nodeMeshes.forEach((mesh, nodeId) => {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      const origScale = (mesh.userData?.originalScale as number) || 1.0;
      if (nodeId === id) {
        mesh.scale.setScalar(1.65);
        mat.emissiveIntensity = 2.6;
      } else if (nodeId !== selectedId) {
        mesh.scale.setScalar(origScale);
        mat.emissiveIntensity = origScale < 0.85 ? 0.35 : 1.1;
      }
    });
  };

  const selectNode = (id: string | null) => {
    selectedId = id;
    nodeMeshes.forEach((mesh, nodeId) => {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      const origScale = (mesh.userData?.originalScale as number) || 1.0;
      if (nodeId === id) {
        mesh.scale.setScalar(1.85);
        mat.emissiveIntensity = 3.2;
      } else if (nodeId !== highlightedId) {
        mesh.scale.setScalar(origScale);
        mat.emissiveIntensity = origScale < 0.85 ? 0.35 : 1.1;
      }
    });
  };

  // =========================================================================
  // VIBRANT LIVING MOTION UPDATE
  // =========================================================================
  const update = (time: number) => {
    animatedNodes.forEach(
      ({
        mesh,
        basePos,
        ring1,
        ring2,
        beaconRing,
        satelliteSpark,
        stemCurve,
        sparkGeo,
        pt,
        idx,
        isFog,
        isCurrentTeaching,
      }) => {
        const isSelected = pt.id === selectedId;
        const isHighlighted = pt.id === highlightedId;

        const motionScale = isFog ? 0.35 : 1.0;
        const floatY = Math.sin(time * 2.2 + idx * 0.8) * 1.5 * motionScale;
        const floatX = Math.cos(time * 1.7 + idx * 0.6) * 1.0 * motionScale;
        const floatZ = Math.sin(time * 1.4 + idx * 0.7) * 0.8 * motionScale;
        mesh.position.set(basePos.x + floatX, basePos.y + floatY, basePos.z + floatZ);

        const spinSpeed = isFog ? 0.5 : isCurrentTeaching ? 2.6 : 2.0;
        mesh.rotation.y = time * spinSpeed + idx;
        mesh.rotation.x = Math.sin(time * 1.3 + idx) * 0.45 * motionScale;

        ring1.rotation.z = time * (isFog ? 1.1 : 3.8);
        ring1.rotation.x = Math.sin(time * 2.2) * 0.9;
        ring2.rotation.y = -time * (isFog ? 0.9 : 3.2);
        ring2.rotation.z = Math.cos(time * 2.0) * 0.7;

        if (beaconRing) {
          const beaconScale = 1.0 + Math.sin(time * 4.5 + idx) * 0.16;
          beaconRing.scale.setScalar(beaconScale);
          beaconRing.rotation.z = time * 1.8;
        }

        const sparkAngle = time * (isFog ? 1.2 : 3.6) + idx * 1.3;
        const sparkRadius = 2.4;
        satelliteSpark.position.set(
          Math.cos(sparkAngle) * sparkRadius,
          Math.sin(time * 4.2 + idx) * 0.9,
          Math.sin(sparkAngle) * sparkRadius
        );

        const baseScale = isFog ? 0.78 : isCurrentTeaching ? 1.16 : 1.0;
        const breathe = baseScale + Math.sin(time * 3.2 + idx * 0.7) * (isFog ? 0.04 : 0.14);
        if (isSelected) {
          mesh.scale.setScalar(1.85);
        } else if (isHighlighted) {
          mesh.scale.setScalar(1.6);
        } else if (pt?.isReviewDue || pt.state === "WEAK") {
          const alertPulse = baseScale + Math.sin(time * 5.2) * 0.22;
          mesh.scale.setScalar(alertPulse);
        } else {
          mesh.scale.setScalar(breathe);
        }

        const mat = mesh.material as THREE.MeshStandardMaterial;
        const baseEmissive = isFog
          ? 0.35
          : isCurrentTeaching
            ? 2.2
            : pt.state === "NOT_STARTED"
              ? 1.1
              : 1.9;
        mat.emissiveIntensity =
          baseEmissive + Math.sin(time * 3.6 + idx) * (isFog ? 0.08 : 0.45);

        const posArr = sparkGeo.attributes.position.array as Float32Array;
        const sparkCount = posArr.length / 3;
        const flowSpeed = isFog ? 0.18 : isCurrentTeaching ? 0.85 : 0.6;
        for (let s = 0; s < sparkCount; s++) {
          const t = (time * flowSpeed + s / sparkCount + idx * 0.12) % 1.0;
          const ptOnCurve = stemCurve.getPoint(t);
          posArr[s * 3] = ptOnCurve.x;
          posArr[s * 3 + 1] = ptOnCurve.y;
          posArr[s * 3 + 2] = ptOnCurve.z;
        }
        sparkGeo.attributes.position.needsUpdate = true;
      }
    );
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
