import * as THREE from "three";
import type { Chapter3DLayout } from "../../tree-3d-layout";

export interface ChapterBranchesSystem {
  group: THREE.Group;
  chapterMeshes: Map<string, THREE.Mesh>;
  dispose: () => void;
}

export function createChapterBranches(chapters: Chapter3DLayout[]): ChapterBranchesSystem {
  const group = new THREE.Group();
  group.name = "chapter-branches-group";

  const chapterMeshes = new Map<string, THREE.Mesh>();
  const disposables: Array<{ dispose: () => void }> = [];

  chapters.forEach((ch) => {
    const themeCol = new THREE.Color(ch.themeColor);

    // 1. Curved Luminous Branch Tube from trunk to chapter nexus
    const splineVectors = ch.branchSpline.map((p) => new THREE.Vector3(p.x, p.y, p.z));
    const curve = new THREE.CatmullRomCurve3(splineVectors);

    // Outer crystalline branch
    const tubeGeo = new THREE.TubeGeometry(curve, 28, 0.95, 10, false);
    const tubeMat = new THREE.MeshStandardMaterial({
      color: themeCol.clone().multiplyScalar(0.6),
      emissive: themeCol.clone().multiplyScalar(0.4),
      emissiveIntensity: 0.6,
      roughness: 0.4,
      metalness: 0.4,
    });
    const tubeMesh = new THREE.Mesh(tubeGeo, tubeMat);
    group.add(tubeMesh);
    disposables.push(tubeGeo, tubeMat);

    // Inner Glowing Energy Core Strand
    const innerGeo = new THREE.TubeGeometry(curve, 28, 0.28, 6, false);
    const innerMat = new THREE.MeshBasicMaterial({
      color: themeCol.clone().addScalar(0.2),
      transparent: true,
      opacity: 0.85,
    });
    const innerMesh = new THREE.Mesh(innerGeo, innerMat);
    group.add(innerMesh);
    disposables.push(innerGeo, innerMat);

    // 2. Chapter Nexus Island Platform (Đài Tinh Thể Chương)
    const islandGroup = new THREE.Group();
    islandGroup.position.set(ch.position.x, ch.position.y, ch.position.z);

    const platformGeo = new THREE.CylinderGeometry(3.2, 3.8, 0.65, 20);
    const platformMat = new THREE.MeshStandardMaterial({
      color: themeCol.clone().multiplyScalar(0.85),
      emissive: themeCol.clone().multiplyScalar(0.5),
      emissiveIntensity: 0.65,
      roughness: 0.3,
      metalness: 0.6,
    });
    const platformMesh = new THREE.Mesh(platformGeo, platformMat);
    platformMesh.userData = { kind: "chapter", id: ch.data.id, name: ch.data.name };
    islandGroup.add(platformMesh);
    chapterMeshes.set(ch.data.id, platformMesh);
    disposables.push(platformGeo, platformMat);

    // Floating Chapter Crystal Diamond
    const diamondGeo = new THREE.OctahedronGeometry(1.6, 0);
    const diamondMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color("#ffffff"),
      emissive: themeCol,
      emissiveIntensity: 1.1,
      roughness: 0.1,
      metalness: 0.9,
    });
    const diamondMesh = new THREE.Mesh(diamondGeo, diamondMat);
    diamondMesh.position.y = 1.6;
    islandGroup.add(diamondMesh);
    disposables.push(diamondGeo, diamondMat);

    // Glowing Halo Ring around platform
    const haloGeo = new THREE.RingGeometry(3.9, 4.8, 32);
    const haloMat = new THREE.MeshBasicMaterial({
      color: themeCol,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.45,
    });
    const haloMesh = new THREE.Mesh(haloGeo, haloMat);
    haloMesh.rotation.x = -Math.PI / 2;
    haloMesh.position.y = -0.15;
    islandGroup.add(haloMesh);
    disposables.push(haloGeo, haloMat);

    group.add(islandGroup);
  });

  const dispose = () => {
    disposables.forEach((d) => d.dispose());
  };

  return {
    group,
    chapterMeshes,
    dispose,
  };
}
