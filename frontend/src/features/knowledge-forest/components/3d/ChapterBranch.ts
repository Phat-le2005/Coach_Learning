import * as THREE from "three";
import type { Chapter3DLayout } from "../../tree-3d-layout";

export interface ChapterBranchesSystem {
  group: THREE.Group;
  chapterMeshes: Map<string, THREE.Mesh>;
  update: (time: number, cometAngle?: number) => void;
  dispose: () => void;
}

export function createChapterBranches(chapters: Chapter3DLayout[]): ChapterBranchesSystem {
  const group = new THREE.Group();
  group.name = "chapter-branches-group";

  const chapterMeshes = new Map<string, THREE.Mesh>();
  const animatedBranches: Array<{
    chapterId: string;
    orbitalAngle: number;
    basePos: THREE.Vector3;
    nexusGroup: THREE.Group;
    diamondMesh: THREE.Mesh;
    haloMesh: THREE.Mesh;
    auraMat: THREE.MeshBasicMaterial;
    plasmaMat: THREE.MeshBasicMaterial;
    sparkParticles: THREE.Points;
    sparkCurve: THREE.CatmullRomCurve3;
  }> = [];

  const disposables: Array<{ dispose: () => void }> = [];

  chapters.forEach((ch, chIdx) => {
    const themeCol = new THREE.Color(ch.themeColor);
    const branchGroup = new THREE.Group();

    // =========================================================================
    // 1. 3-LAYER VOLUMETRIC ELECTRIC NEON LIGHTNING TRUNK (Lõi Sét Đa Tầng Phát Quang)
    // =========================================================================
    const splineVectors = ch.branchSpline.map((p) => new THREE.Vector3(p.x, p.y, p.z));
    const curve = new THREE.CatmullRomCurve3(splineVectors);

    // Layer 1: Wide Outer Neon Glow Aura (Tán hào quang năng lượng)
    const auraGeo = new THREE.TubeGeometry(curve, 32, 1.05, 8, false);
    const auraMat = new THREE.MeshBasicMaterial({
      color: themeCol,
      transparent: true,
      opacity: 0.35,
      blending: THREE.AdditiveBlending,
      depthWrite: false,
    });
    const auraMesh = new THREE.Mesh(auraGeo, auraMat);
    branchGroup.add(auraMesh);
    disposables.push(auraGeo, auraMat);

    // Layer 2: Mid Plasma Mantle (Lõi Plasma điện quang)
    const plasmaGeo = new THREE.TubeGeometry(curve, 32, 0.44, 8, false);
    const plasmaMat = new THREE.MeshBasicMaterial({
      color: themeCol,
      transparent: true,
      opacity: 0.9,
      blending: THREE.AdditiveBlending,
    });
    const plasmaMesh = new THREE.Mesh(plasmaGeo, plasmaMat);
    branchGroup.add(plasmaMesh);
    disposables.push(plasmaGeo, plasmaMat);

    // Layer 3: Ultra-Hot White Core Filament (Dây tóc sét trắng nhiệt độ cao)
    const coreGeo = new THREE.TubeGeometry(curve, 32, 0.14, 6, false);
    const coreMat = new THREE.MeshBasicMaterial({
      color: new THREE.Color("#ffffff"),
      blending: THREE.AdditiveBlending,
    });
    const coreMesh = new THREE.Mesh(coreGeo, coreMat);
    branchGroup.add(coreMesh);
    disposables.push(coreGeo, coreMat);

    // =========================================================================
    // 2. DENDRITIC ELECTRIC FORK TENDRILS (Tia Sét Phân Nhánh Fractal)
    // =========================================================================
    for (let forkIdx = 0; forkIdx < 4; forkIdx++) {
      const forkT = 0.3 + forkIdx * 0.18;
      const forkStart = curve.getPoint(forkT);
      const tangent = curve.getTangent(forkT);
      const normal = new THREE.Vector3(-tangent.z, 0, tangent.x).normalize();

      const sideSign = forkIdx % 2 === 0 ? 1 : -1;
      const forkMid = forkStart
        .clone()
        .add(normal.clone().multiplyScalar(sideSign * (3.8 + forkIdx * 1.4)))
        .add(new THREE.Vector3(0, (forkIdx % 2 === 0 ? 1 : -1) * 1.5, 0));

      const forkEnd = forkMid
        .clone()
        .add(tangent.clone().multiplyScalar(4.5))
        .add(normal.clone().multiplyScalar(sideSign * 2.8));

      const forkCurve = new THREE.CatmullRomCurve3([forkStart, forkMid, forkEnd]);
      const forkGeo = new THREE.TubeGeometry(forkCurve, 12, 0.12, 4, false);
      const forkMat = new THREE.MeshBasicMaterial({
        color: themeCol,
        transparent: true,
        opacity: 0.75,
        blending: THREE.AdditiveBlending,
      });
      const forkMesh = new THREE.Mesh(forkGeo, forkMat);
      branchGroup.add(forkMesh);
      disposables.push(forkGeo, forkMat);
    }

    // =========================================================================
    // 3. ELECTRIC SPARK ENERGY CURRENT (Dòng Hạt Xung Sét Chạy Dọc Thân)
    // =========================================================================
    const sparkCount = 10;
    const sparkGeo = new THREE.BufferGeometry();
    const sparkPositions = new Float32Array(sparkCount * 3);
    sparkGeo.setAttribute("position", new THREE.BufferAttribute(sparkPositions, 3));
    const sparkMat = new THREE.PointsMaterial({
      color: new THREE.Color("#ffffff"),
      size: 2.2,
      transparent: true,
      opacity: 0.95,
      blending: THREE.AdditiveBlending,
    });
    const sparkPoints = new THREE.Points(sparkGeo, sparkMat);
    branchGroup.add(sparkPoints);
    disposables.push(sparkGeo, sparkMat);

    // =========================================================================
    // 4. CHAPTER NEXUS ISLAND PLATFORM (Trạm Tinh Thể Chương Phát Quang)
    // =========================================================================
    const nexusGroup = new THREE.Group();
    nexusGroup.position.set(ch.position.x, ch.position.y, ch.position.z);

    // Glowing Holographic Base Platform
    const platformGeo = new THREE.CylinderGeometry(2.6, 3.2, 0.45, 24);
    const platformMat = new THREE.MeshStandardMaterial({
      color: themeCol.clone().multiplyScalar(0.7),
      emissive: themeCol,
      emissiveIntensity: 1.2,
      roughness: 0.2,
      metalness: 0.8,
    });
    const platformMesh = new THREE.Mesh(platformGeo, platformMat);
    platformMesh.userData = { kind: "chapter", id: ch.data.id, name: ch.data.name };
    nexusGroup.add(platformMesh);
    chapterMeshes.set(ch.data.id, platformMesh);
    disposables.push(platformGeo, platformMat);

    // Floating Chapter Crystal Diamond
    const diamondGeo = new THREE.OctahedronGeometry(1.7, 0);
    const diamondMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color("#ffffff"),
      emissive: themeCol,
      emissiveIntensity: 1.8,
      roughness: 0.1,
      metalness: 0.9,
    });
    const diamondMesh = new THREE.Mesh(diamondGeo, diamondMat);
    diamondMesh.position.y = 1.7;
    nexusGroup.add(diamondMesh);
    disposables.push(diamondGeo, diamondMat);

    // Dual Glowing Halo Rings
    const halo1Geo = new THREE.RingGeometry(3.2, 4.4, 32);
    const halo1Mat = new THREE.MeshBasicMaterial({
      color: themeCol,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.55,
      blending: THREE.AdditiveBlending,
    });
    const halo1Mesh = new THREE.Mesh(halo1Geo, halo1Mat);
    halo1Mesh.rotation.x = -Math.PI / 2;
    halo1Mesh.position.y = -0.1;
    nexusGroup.add(halo1Mesh);
    disposables.push(halo1Geo, halo1Mat);

    const halo2Geo = new THREE.TorusGeometry(3.8, 0.08, 6, 32);
    const halo2Mat = new THREE.MeshBasicMaterial({
      color: new THREE.Color("#ffffff"),
      transparent: true,
      opacity: 0.7,
      blending: THREE.AdditiveBlending,
    });
    const halo2Mesh = new THREE.Mesh(halo2Geo, halo2Mat);
    halo2Mesh.rotation.x = Math.PI / 2;
    nexusGroup.add(halo2Mesh);
    disposables.push(halo2Geo, halo2Mat);

    branchGroup.add(nexusGroup);
    group.add(branchGroup);

    animatedBranches.push({
      chapterId: ch.data.id,
      orbitalAngle: ch.orbitalAngle,
      basePos: new THREE.Vector3(ch.position.x, ch.position.y, ch.position.z),
      nexusGroup,
      diamondMesh,
      haloMesh: halo1Mesh,
      auraMat,
      plasmaMat,
      sparkParticles: sparkPoints,
      sparkCurve: curve,
    });
  });

  // =========================================================================
  // ANIMATION LOOP UPDATE (Chuyển Động Linh Hoạt & Uốn Lượn Sống Động)
  // =========================================================================
  const update = (time: number, cometAngle: number = 0) => {
    animatedBranches.forEach((item, idx) => {
      // 1. Organic Floating & Harmonic Breathing (Nhấp nhô uốn lượn mềm mại)
      const floatY = Math.sin(time * 1.8 + idx * 0.9) * 0.45;
      const floatX = Math.cos(time * 1.3 + idx * 0.7) * 0.25;
      item.nexusGroup.position.set(
        item.basePos.x + floatX,
        item.basePos.y + floatY,
        item.basePos.z
      );

      // Rotate crystal diamond and halo
      item.diamondMesh.rotation.y = time * 1.6 + idx;
      item.diamondMesh.rotation.x = Math.sin(time * 0.8 + idx) * 0.25;
      item.haloMesh.rotation.z = -time * 0.8;

      // 2. Proximity to Orbital Comet -> Electric Lightning Surge
      let angleDiff = Math.abs(cometAngle - item.orbitalAngle);
      if (angleDiff > Math.PI) {
        angleDiff = 2 * Math.PI - angleDiff;
      }
      const isCometClose = angleDiff < 0.48;
      const surge = isCometClose ? Math.max(0, 1.0 - angleDiff / 0.48) : 0;

      // Breathing aura wave
      const pulse = 0.35 + Math.sin(time * 3.0 + idx * 1.2) * 0.12;
      item.auraMat.opacity = pulse + surge * 0.55;
      item.plasmaMat.opacity = 0.85 + surge * 0.15;
      item.diamondMesh.scale.setScalar(1.0 + surge * 0.4);

      // 3. Animate Electric Spark Energy Packets flowing down the branch
      const sparkPos = item.sparkParticles.geometry.attributes.position.array as Float32Array;
      const count = sparkPos.length / 3;
      for (let s = 0; s < count; s++) {
        const t = (time * 0.45 + s / count) % 1.0;
        const pt = item.sparkCurve.getPoint(t);
        sparkPos[s * 3] = pt.x;
        sparkPos[s * 3 + 1] = pt.y;
        sparkPos[s * 3 + 2] = pt.z;
      }
      item.sparkParticles.geometry.attributes.position.needsUpdate = true;
    });
  };

  const dispose = () => {
    disposables.forEach((d) => d.dispose());
  };

  return {
    group,
    chapterMeshes,
    update,
    dispose,
  };
}
