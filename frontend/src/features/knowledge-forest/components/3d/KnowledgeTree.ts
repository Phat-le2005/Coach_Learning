import * as THREE from "three";
import type { Point3D } from "../../tree-3d-layout";

export interface TreeSystem {
  group: THREE.Group;
  spores: THREE.Points;
  coreMesh: THREE.Mesh;
  rings: THREE.Group;
  update: (time: number) => void;
  dispose: () => void;
}

export function createKnowledgeTree(corePos: Point3D, trunkPoints: Point3D[]): TreeSystem {
  const group = new THREE.Group();
  group.name = "ancient-knowledge-tree";
  const disposables: Array<{ dispose: () => void }> = [];

  // --- 1. Celestial Sanctuary Island Pedestal (Ground Platform) ---
  const islandGeo = new THREE.CylinderGeometry(32, 36, 3.5, 36);
  const islandMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#082c23"),
    emissive: new THREE.Color("#051c16"),
    roughness: 0.85,
    metalness: 0.2,
  });
  const islandMesh = new THREE.Mesh(islandGeo, islandMat);
  islandMesh.position.y = -8.5;
  group.add(islandMesh);
  disposables.push(islandGeo, islandMat);

  // Concentric Luminous Energy Rings on the Island
  const ring1Geo = new THREE.RingGeometry(12, 12.3, 48);
  const ring1Mat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#8be5c2"),
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.45,
  });
  const ring1 = new THREE.Mesh(ring1Geo, ring1Mat);
  ring1.rotation.x = -Math.PI / 2;
  ring1.position.y = -6.7;
  group.add(ring1);
  disposables.push(ring1Geo, ring1Mat);

  const ring2Geo = new THREE.RingGeometry(22, 22.4, 48);
  const ring2Mat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#23a67a"),
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.35,
  });
  const ring2 = new THREE.Mesh(ring2Geo, ring2Mat);
  ring2.rotation.x = -Math.PI / 2;
  ring2.position.y = -6.68;
  group.add(ring2);
  disposables.push(ring2Geo, ring2Mat);

  const ring3Geo = new THREE.RingGeometry(30, 30.5, 48);
  const ring3Mat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#e8bf6a"),
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.25,
  });
  const ring3 = new THREE.Mesh(ring3Geo, ring3Mat);
  ring3.rotation.x = -Math.PI / 2;
  ring3.position.y = -6.66;
  group.add(ring3);
  disposables.push(ring3Geo, ring3Mat);

  // --- 2. Flared Root Buttresses (Cội Rễ Cổ Thụ) ---
  const rootAngles = [0, Math.PI / 2, Math.PI, (3 * Math.PI) / 2];
  rootAngles.forEach((angle) => {
    const rootPoints: THREE.Vector3[] = [
      new THREE.Vector3(Math.cos(angle) * 11, -7, Math.sin(angle) * 11),
      new THREE.Vector3(Math.cos(angle) * 6, -2, Math.sin(angle) * 6),
      new THREE.Vector3(Math.cos(angle) * 2.5, 4, Math.sin(angle) * 2.5),
      new THREE.Vector3(0, 10, 0),
    ];
    const rootCurve = new THREE.CatmullRomCurve3(rootPoints);
    const rootGeo = new THREE.TubeGeometry(rootCurve, 16, 0.9, 8, false);
    const rootMat = new THREE.MeshStandardMaterial({
      color: new THREE.Color("#0c3f33"),
      emissive: new THREE.Color("#164e3f"),
      emissiveIntensity: 0.4,
      roughness: 0.6,
      metalness: 0.3,
    });
    const rootMesh = new THREE.Mesh(rootGeo, rootMat);
    group.add(rootMesh);
    disposables.push(rootGeo, rootMat);
  });

  // --- 3. Sculpted Luminous Tree Trunk ---
  const vPoints = trunkPoints.map((p) => new THREE.Vector3(p.x, p.y, p.z));
  const trunkCurve = new THREE.CatmullRomCurve3(vPoints);
  const trunkGeo = new THREE.TubeGeometry(trunkCurve, 32, 2.2, 16, false);
  const trunkMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#0d483a"),
    emissive: new THREE.Color("#072b22"),
    emissiveIntensity: 0.6,
    roughness: 0.5,
    metalness: 0.35,
  });
  const trunkMesh = new THREE.Mesh(trunkGeo, trunkMat);
  group.add(trunkMesh);
  disposables.push(trunkGeo, trunkMat);

  // Double-helix Glowing Light Veins intertwining around the trunk
  const strand1Points: THREE.Vector3[] = [];
  const strand2Points: THREE.Vector3[] = [];
  for (let t = -7; t <= 26; t += 0.8) {
    const angle1 = t * 0.45;
    const angle2 = t * 0.45 + Math.PI;
    const radius = 2.4 + Math.sin(t * 0.2) * 0.5;
    strand1Points.push(new THREE.Vector3(Math.cos(angle1) * radius, t, Math.sin(angle1) * radius));
    strand2Points.push(new THREE.Vector3(Math.cos(angle2) * radius, t, Math.sin(angle2) * radius));
  }

  const strand1Curve = new THREE.CatmullRomCurve3(strand1Points);
  const strand1Geo = new THREE.TubeGeometry(strand1Curve, 48, 0.22, 6, false);
  const strand1Mat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#8be5c2"),
    transparent: true,
    opacity: 0.75,
  });
  const strand1Mesh = new THREE.Mesh(strand1Geo, strand1Mat);
  group.add(strand1Mesh);
  disposables.push(strand1Geo, strand1Mat);

  const strand2Curve = new THREE.CatmullRomCurve3(strand2Points);
  const strand2Geo = new THREE.TubeGeometry(strand2Curve, 48, 0.22, 6, false);
  const strand2Mat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#23a67a"),
    transparent: true,
    opacity: 0.75,
  });
  const strand2Mesh = new THREE.Mesh(strand2Geo, strand2Mat);
  group.add(strand2Mesh);
  disposables.push(strand2Geo, strand2Mat);

  // --- 4. Upper Tree Crown (Tán Cổ Thụ Phát Quang) ---
  const crownGeo = new THREE.TorusGeometry(5.5, 0.45, 8, 36);
  const crownMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#8be5c2"),
    transparent: true,
    opacity: 0.5,
  });
  const crownMesh = new THREE.Mesh(crownGeo, crownMat);
  crownMesh.rotation.x = Math.PI / 2;
  crownMesh.position.y = 25.5;
  group.add(crownMesh);
  disposables.push(crownGeo, crownMat);

  // --- 5. Level 0 Knowledge Core (Trái Tim Tri Thức) ---
  const coreGroup = new THREE.Group();
  coreGroup.position.set(corePos.x, corePos.y, corePos.z);

  // Outer Icosahedron Crystal
  const outerCoreGeo = new THREE.IcosahedronGeometry(3.0, 1);
  const outerCoreMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#8be5c2"),
    emissive: new THREE.Color("#23a67a"),
    emissiveIntensity: 0.9,
    roughness: 0.15,
    metalness: 0.85,
    wireframe: true,
  });
  const outerCore = new THREE.Mesh(outerCoreGeo, outerCoreMat);
  coreGroup.add(outerCore);
  disposables.push(outerCoreGeo, outerCoreMat);

  // Inner Solid Crystal Core
  const innerCoreGeo = new THREE.OctahedronGeometry(2.0, 0);
  const innerCoreMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#ffffff"),
    emissive: new THREE.Color("#8be5c2"),
    emissiveIntensity: 1.2,
    roughness: 0.1,
    metalness: 0.9,
  });
  const innerCore = new THREE.Mesh(innerCoreGeo, innerCoreMat);
  coreGroup.add(innerCore);
  disposables.push(innerCoreGeo, innerCoreMat);

  // Revolving Celestial Rings
  const rings = new THREE.Group();
  const ringMat1 = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#e8bf6a"),
    transparent: true,
    opacity: 0.55,
  });
  const r1 = new THREE.Mesh(new THREE.TorusGeometry(4.4, 0.1, 8, 48), ringMat1);
  rings.add(r1);
  disposables.push(r1.geometry, ringMat1);

  const ringMat2 = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#67bfd4"),
    transparent: true,
    opacity: 0.55,
  });
  const r2 = new THREE.Mesh(new THREE.TorusGeometry(5.2, 0.1, 8, 48), ringMat2);
  r2.rotation.x = Math.PI / 3;
  rings.add(r2);
  disposables.push(r2.geometry, ringMat2);

  coreGroup.add(rings);
  group.add(coreGroup);

  // --- 6. Ascending Bioluminescent Embers / Spores ---
  const sporeCount = 280;
  const sporePositions = new Float32Array(sporeCount * 3);
  for (let i = 0; i < sporeCount; i++) {
    const angle = Math.random() * Math.PI * 2;
    const r = 4 + Math.random() * 52;
    const x = Math.sin(angle) * r;
    const z = Math.cos(angle) * r;
    const y = -6 + Math.random() * 48;
    sporePositions[i * 3] = x;
    sporePositions[i * 3 + 1] = y;
    sporePositions[i * 3 + 2] = z;
  }

  const sporeGeo = new THREE.BufferGeometry();
  sporeGeo.setAttribute("position", new THREE.BufferAttribute(sporePositions, 3));
  const sporeMat = new THREE.PointsMaterial({
    color: new THREE.Color("#8be5c2"),
    size: 0.85,
    transparent: true,
    opacity: 0.65,
    blending: THREE.AdditiveBlending,
  });
  const spores = new THREE.Points(sporeGeo, sporeMat);
  group.add(spores);
  disposables.push(sporeGeo, sporeMat);

  // Animation Update Loop
  const update = (time: number) => {
    // Rotate Core
    outerCore.rotation.y = time * 0.35;
    outerCore.rotation.x = Math.sin(time * 0.25) * 0.2;
    innerCore.rotation.y = -time * 0.5;
    innerCore.rotation.z = Math.cos(time * 0.3) * 0.2;

    // Orbit Rings
    rings.rotation.y = -time * 0.28;
    r2.rotation.z = time * 0.32;

    // Slowly rotate ground rings
    ring1.rotation.z = time * 0.05;
    ring2.rotation.z = -time * 0.04;
    ring3.rotation.z = time * 0.03;

    // Upward drifting fireflies
    const pos = sporeGeo.attributes.position.array as Float32Array;
    for (let i = 0; i < sporeCount; i++) {
      let y = pos[i * 3 + 1] + 0.05;
      if (y > 45) {
        y = -6;
      }
      pos[i * 3 + 1] = y;
    }
    sporeGeo.attributes.position.needsUpdate = true;
  };

  const dispose = () => {
    disposables.forEach((d) => d.dispose());
  };

  return {
    group,
    spores,
    coreMesh: innerCore,
    rings,
    update,
    dispose,
  };
}
