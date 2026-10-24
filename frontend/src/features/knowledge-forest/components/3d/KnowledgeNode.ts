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
  const disposables: Array<{ dispose: () => void }> = [];

  let highlightedId: string | null = null;
  let selectedId: string | null = null;

  nodes.forEach((node) => {
    const pt = node.data;
    const colors = MASTERY_3D_COLORS[pt.state] ?? MASTERY_3D_COLORS.NOT_STARTED;
    const baseCol = new THREE.Color(colors.base);
    const emissiveCol = new THREE.Color(colors.emissive);

    // 1. Luminous crystalline stem connecting Topic pod to the Problem Type node
    const splineVectors = node.branchletSpline.map((p) => new THREE.Vector3(p.x, p.y, p.z));
    const curve = new THREE.CatmullRomCurve3(splineVectors);
    const stemGeo = new THREE.TubeGeometry(curve, 10, 0.18, 6, false);
    const stemMat = new THREE.MeshBasicMaterial({
      color: baseCol.clone().multiplyScalar(0.75),
      transparent: true,
      opacity: 0.65,
    });
    const stemMesh = new THREE.Mesh(stemGeo, stemMat);
    group.add(stemMesh);
    disposables.push(stemGeo, stemMat);

    // 2. Main Crystalline Problem Type Node (Inner Gem Sphere)
    const gemGeo = new THREE.IcosahedronGeometry(1.25, 1);
    const gemMat = new THREE.MeshStandardMaterial({
      color: baseCol,
      emissive: emissiveCol,
      emissiveIntensity: pt.state === "NOT_STARTED" ? 0.7 : 1.1,
      roughness: 0.15,
      metalness: 0.75,
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

    // 3. Delicate Outer Orbital Energy Ring
    const ringGeo = new THREE.TorusGeometry(1.85, 0.08, 6, 28);
    const ringMat = new THREE.MeshBasicMaterial({
      color: emissiveCol,
      transparent: true,
      opacity: 0.75,
    });
    const ringMesh = new THREE.Mesh(ringGeo, ringMat);
    gemMesh.add(ringMesh);
    disposables.push(ringGeo, ringMat);

    group.add(gemMesh);
    nodeMeshes.set(pt.id, gemMesh);
    interactiveMeshes.push(gemMesh);
    disposables.push(gemGeo, gemMat);
  });

  const highlightNode = (id: string | null) => {
    highlightedId = id;
    nodeMeshes.forEach((mesh, nodeId) => {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      if (nodeId === id) {
        mesh.scale.setScalar(1.4);
        mat.emissiveIntensity = 1.6;
      } else if (nodeId !== selectedId) {
        mesh.scale.setScalar(1.0);
        mat.emissiveIntensity = 0.85;
      }
    });
  };

  const selectNode = (id: string | null) => {
    selectedId = id;
    nodeMeshes.forEach((mesh, nodeId) => {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      if (nodeId === id) {
        mesh.scale.setScalar(1.55);
        mat.emissiveIntensity = 2.0;
      } else if (nodeId !== highlightedId) {
        mesh.scale.setScalar(1.0);
        mat.emissiveIntensity = 0.85;
      }
    });
  };

  const update = (time: number) => {
    nodeMeshes.forEach((mesh, nodeId) => {
      // Rotate orbital rings
      const ring = mesh.children[0];
      if (ring) {
        ring.rotation.z = time * 0.9;
        ring.rotation.x = Math.sin(time * 0.6) * 0.35;
      }

      // Gentle floating bob
      const pt = (mesh.userData as { data?: KnowledgeProblemTypeNode }).data;
      if (pt?.isReviewDue && nodeId !== selectedId) {
        // Warning pulsing aura
        const pulse = 1.0 + Math.sin(time * 4) * 0.15;
        mesh.scale.setScalar(pulse);
      }
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
