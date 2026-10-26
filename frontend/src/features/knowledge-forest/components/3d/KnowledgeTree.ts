import * as THREE from "three";
import type { Point3D } from "../../tree-3d-layout";

export interface TreeSystem {
  group: THREE.Group;
  spores: THREE.Points;
  coreMesh: THREE.Mesh;
  rings: THREE.Group;
  cometLight: THREE.PointLight;
  getCometAngle: () => number;
  update: (time: number) => void;
  dispose: () => void;
}

/**
 * Creates a circular soft Gaussian glow sprite texture via HTML Canvas.
 * Gives particles a realistic smoky cosmic nebula appearance.
 */
function createRadialGlowTexture(size = 64): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;

  const gradient = ctx.createRadialGradient(
    size / 2,
    size / 2,
    0,
    size / 2,
    size / 2,
    size / 2
  );
  gradient.addColorStop(0, "rgba(255, 255, 255, 1.0)");
  gradient.addColorStop(0.2, "rgba(103, 232, 249, 0.85)");
  gradient.addColorStop(0.5, "rgba(168, 85, 247, 0.45)");
  gradient.addColorStop(1, "rgba(0, 0, 0, 0)");

  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);

  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  return texture;
}

export function createKnowledgeTree(
  corePos: Point3D,
  _trunkPoints: Point3D[],
  orbitalRadius: number = 38.0
): TreeSystem {
  const group = new THREE.Group();
  group.name = "cosmic-singularity-system";
  const disposables: Array<{ dispose: () => void }> = [];

  const glowTexture = createRadialGlowTexture(64);
  disposables.push(glowTexture);

  // =========================================================================
  // 1. CENTRAL SINGULARITY NUCLEUS (Lõi Kỳ Dị Phát Quang & Lồng Lượng Tử)
  // =========================================================================
  const coreGroup = new THREE.Group();
  coreGroup.position.set(corePos.x, corePos.y, corePos.z);

  // Inner Ultra-Bright White/Cyan Star (Ngôi sao trung tâm)
  const innerCoreGeo = new THREE.SphereGeometry(2.5, 32, 32);
  const innerCoreMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#ffffff"),
    emissive: new THREE.Color("#00f0ff"),
    emissiveIntensity: 2.5,
    roughness: 0.1,
    metalness: 0.9,
  });
  const innerCoreMesh = new THREE.Mesh(innerCoreGeo, innerCoreMat);
  coreGroup.add(innerCoreMesh);
  disposables.push(innerCoreGeo, innerCoreMat);

  // Mid Holographic Energy Shell (Vỏ năng lượng icosahedron)
  const midCoreGeo = new THREE.IcosahedronGeometry(3.8, 2);
  const midCoreMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#38bdf8"),
    emissive: new THREE.Color("#818cf8"),
    emissiveIntensity: 1.6,
    wireframe: true,
    transparent: true,
    opacity: 0.85,
  });
  const midCoreMesh = new THREE.Mesh(midCoreGeo, midCoreMat);
  coreGroup.add(midCoreMesh);
  disposables.push(midCoreGeo, midCoreMat);

  // Outer Crystalline Cage (Lồng bát diện)
  const outerCoreGeo = new THREE.OctahedronGeometry(5.2, 1);
  const outerCoreMat = new THREE.MeshStandardMaterial({
    color: new THREE.Color("#c084fc"),
    emissive: new THREE.Color("#a855f7"),
    emissiveIntensity: 1.1,
    wireframe: true,
    transparent: true,
    opacity: 0.55,
  });
  const outerCoreMesh = new THREE.Mesh(outerCoreGeo, outerCoreMat);
  coreGroup.add(outerCoreMesh);
  disposables.push(outerCoreGeo, outerCoreMat);

  // Quantum Gyroscopic Precession Rings
  const quantumRings = new THREE.Group();
  const ringMat1 = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#00f0ff"),
    transparent: true,
    opacity: 0.75,
    blending: THREE.AdditiveBlending,
  });
  const qr1 = new THREE.Mesh(new THREE.TorusGeometry(6.6, 0.12, 8, 64), ringMat1);
  quantumRings.add(qr1);
  disposables.push(qr1.geometry, ringMat1);

  const ringMat2 = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#ec4899"),
    transparent: true,
    opacity: 0.7,
    blending: THREE.AdditiveBlending,
  });
  const qr2 = new THREE.Mesh(new THREE.TorusGeometry(7.8, 0.12, 8, 64), ringMat2);
  qr2.rotation.x = Math.PI / 3;
  quantumRings.add(qr2);
  disposables.push(qr2.geometry, ringMat2);

  const ringMat3 = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#fbbf24"),
    transparent: true,
    opacity: 0.65,
    blending: THREE.AdditiveBlending,
  });
  const qr3 = new THREE.Mesh(new THREE.TorusGeometry(9.0, 0.12, 8, 64), ringMat3);
  qr3.rotation.y = Math.PI / 4;
  quantumRings.add(qr3);
  disposables.push(qr3.geometry, ringMat3);

  coreGroup.add(quantumRings);

  // Expanding Gravitational Shockwave Rings (Sóng xung kích lan tỏa từ tâm)
  const shockwaveGeo = new THREE.RingGeometry(1.0, 1.4, 48);
  const shockwaveMat1 = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#00f0ff"),
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.8,
    blending: THREE.AdditiveBlending,
  });
  const shockwave1 = new THREE.Mesh(shockwaveGeo, shockwaveMat1);
  shockwave1.rotation.x = -Math.PI / 2;
  coreGroup.add(shockwave1);
  disposables.push(shockwaveGeo, shockwaveMat1);

  const shockwaveMat2 = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#a855f7"),
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.8,
    blending: THREE.AdditiveBlending,
  });
  const shockwave2 = new THREE.Mesh(shockwaveGeo, shockwaveMat2);
  shockwave2.rotation.x = -Math.PI / 2;
  coreGroup.add(shockwave2);
  disposables.push(shockwaveMat2);

  group.add(coreGroup);

  // =========================================================================
  // 2. COSMIC ACCRETION SPIRAL GALAXY SWIRL (Đĩa Bồi Tụ Tinh Vân Xoắn Ốc Mềm Mại)
  // =========================================================================
  const particleCount = 4600;
  const particlePositions = new Float32Array(particleCount * 3);
  const particleColors = new Float32Array(particleCount * 3);
  const particleOrbitData = new Float32Array(particleCount * 3); // [radius, baseAngle, speed]

  const colWhite = new THREE.Color("#ffffff");
  const colCyan = new THREE.Color("#00f0ff");
  const colViolet = new THREE.Color("#8b5cf6");
  const colMagenta = new THREE.Color("#ec4899");
  const tempCol = new THREE.Color();

  const arms = 3;
  for (let i = 0; i < particleCount; i++) {
    const armIndex = i % arms;
    const armOffset = (armIndex * 2 * Math.PI) / arms;

    const normR = Math.pow(Math.random(), 0.72);
    const r = 3.2 + normR * 44.0;

    const spiralAngle = armOffset + Math.log(r / 3.0) * 1.9 + (Math.random() - 0.5) * 0.42;
    const thickness = (0.25 + (r / 44.0) * 2.0) * (Math.random() - 0.5);

    const x = r * Math.sin(spiralAngle);
    const z = -r * Math.cos(spiralAngle);
    const y = thickness;

    particlePositions[i * 3] = x;
    particlePositions[i * 3 + 1] = y;
    particlePositions[i * 3 + 2] = z;

    const speed = 0.58 / Math.sqrt(Math.max(3.5, r));
    particleOrbitData[i * 3] = r;
    particleOrbitData[i * 3 + 1] = spiralAngle;
    particleOrbitData[i * 3 + 2] = speed;

    if (r < 9) {
      tempCol.copy(colWhite).lerp(colCyan, r / 9);
    } else if (r < 26) {
      tempCol.copy(colCyan).lerp(colViolet, (r - 9) / 17);
    } else {
      tempCol.copy(colViolet).lerp(colMagenta, (r - 26) / 18);
    }

    particleColors[i * 3] = tempCol.r;
    particleColors[i * 3 + 1] = tempCol.g;
    particleColors[i * 3 + 2] = tempCol.b;
  }

  const particleGeo = new THREE.BufferGeometry();
  particleGeo.setAttribute("position", new THREE.BufferAttribute(particlePositions, 3));
  particleGeo.setAttribute("color", new THREE.BufferAttribute(particleColors, 3));

  const particleMat = new THREE.PointsMaterial({
    size: 2.2,
    map: glowTexture,
    vertexColors: true,
    transparent: true,
    opacity: 0.85,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });

  const accretionSwirl = new THREE.Points(particleGeo, particleMat);
  group.add(accretionSwirl);
  disposables.push(particleGeo, particleMat);

  // =========================================================================
  // 3. MAIN LUMINOUS ORBITAL RING (Vòng Quỹ Đạo 7 Chương 360°)
  // =========================================================================
  const ringGeo = new THREE.TorusGeometry(orbitalRadius, 0.32, 12, 128);
  const ringMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#00f0ff"),
    transparent: true,
    opacity: 0.75,
    blending: THREE.AdditiveBlending,
  });
  const orbitalRingMesh = new THREE.Mesh(ringGeo, ringMat);
  orbitalRingMesh.rotation.x = Math.PI / 2;
  group.add(orbitalRingMesh);
  disposables.push(ringGeo, ringMat);

  // Outer Volumetric Aura Ring
  const ringAuraGeo = new THREE.RingGeometry(orbitalRadius - 1.8, orbitalRadius + 1.8, 96);
  const ringAuraMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#818cf8"),
    side: THREE.DoubleSide,
    transparent: true,
    opacity: 0.3,
    blending: THREE.AdditiveBlending,
  });
  const ringAuraMesh = new THREE.Mesh(ringAuraGeo, ringAuraMat);
  ringAuraMesh.rotation.x = -Math.PI / 2;
  group.add(ringAuraMesh);
  disposables.push(ringAuraGeo, ringAuraMat);

  // Secondary Concentric Harmonic Ring
  const innerHarmonicGeo = new THREE.TorusGeometry(orbitalRadius * 0.62, 0.15, 8, 96);
  const innerHarmonicMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#a855f7"),
    transparent: true,
    opacity: 0.45,
    blending: THREE.AdditiveBlending,
  });
  const innerHarmonicMesh = new THREE.Mesh(innerHarmonicGeo, innerHarmonicMat);
  innerHarmonicMesh.rotation.x = Math.PI / 2;
  group.add(innerHarmonicMesh);
  disposables.push(innerHarmonicGeo, innerHarmonicMat);

  // =========================================================================
  // 4. ANIMATED ORBITAL ENERGY COMET (Sao Chổi Quỹ Đạo Năng Lượng)
  // =========================================================================
  const cometGroup = new THREE.Group();

  const cometHeadGeo = new THREE.SphereGeometry(1.6, 16, 16);
  const cometHeadMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#ffffff"),
    blending: THREE.AdditiveBlending,
  });
  const cometHead = new THREE.Mesh(cometHeadGeo, cometHeadMat);
  cometGroup.add(cometHead);
  disposables.push(cometHeadGeo, cometHeadMat);

  const cometHaloGeo = new THREE.SphereGeometry(2.8, 16, 16);
  const cometHaloMat = new THREE.MeshBasicMaterial({
    color: new THREE.Color("#00f0ff"),
    transparent: true,
    opacity: 0.7,
    blending: THREE.AdditiveBlending,
  });
  const cometHalo = new THREE.Mesh(cometHaloGeo, cometHaloMat);
  cometGroup.add(cometHalo);
  disposables.push(cometHaloGeo, cometHaloMat);

  const cometLight = new THREE.PointLight(0x00f0ff, 5.0, 50);
  cometGroup.add(cometLight);

  // Trailing Energy Spark Tail
  const cometTailCount = 16;
  const cometTailGeo = new THREE.BufferGeometry();
  const cometTailPositions = new Float32Array(cometTailCount * 3);
  cometTailGeo.setAttribute("position", new THREE.BufferAttribute(cometTailPositions, 3));
  const cometTailMat = new THREE.PointsMaterial({
    size: 2.8,
    map: glowTexture,
    color: new THREE.Color("#38bdf8"),
    transparent: true,
    opacity: 0.85,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const cometTailPoints = new THREE.Points(cometTailGeo, cometTailMat);
  group.add(cometTailPoints);
  disposables.push(cometTailGeo, cometTailMat);

  group.add(cometGroup);

  let currentCometAngle = 0;

  // =========================================================================
  // 5. DEEP SPACE NEBULA & STARFIELD (Bầu Trời Sao Sâu)
  // =========================================================================
  const starCount = 2400;
  const starPositions = new Float32Array(starCount * 3);
  const starColors = new Float32Array(starCount * 3);
  for (let i = 0; i < starCount; i++) {
    const dist = 140 + Math.random() * 160;
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);

    starPositions[i * 3] = dist * Math.sin(phi) * Math.cos(theta);
    starPositions[i * 3 + 1] = dist * Math.sin(phi) * Math.sin(theta);
    starPositions[i * 3 + 2] = dist * Math.cos(phi);

    const tint = Math.random();
    if (tint < 0.6) {
      tempCol.set("#ffffff");
    } else if (tint < 0.8) {
      tempCol.set("#67e8f9");
    } else {
      tempCol.set("#c084fc");
    }
    starColors[i * 3] = tempCol.r;
    starColors[i * 3 + 1] = tempCol.g;
    starColors[i * 3 + 2] = tempCol.b;
  }

  const starGeo = new THREE.BufferGeometry();
  starGeo.setAttribute("position", new THREE.BufferAttribute(starPositions, 3));
  starGeo.setAttribute("color", new THREE.BufferAttribute(starColors, 3));
  const starMat = new THREE.PointsMaterial({
    size: 1.2,
    map: glowTexture,
    vertexColors: true,
    transparent: true,
    opacity: 0.8,
    blending: THREE.AdditiveBlending,
    depthWrite: false,
  });
  const starField = new THREE.Points(starGeo, starMat);
  group.add(starField);
  disposables.push(starGeo, starMat);

  // =========================================================================
  // ANIMATION LOOP UPDATE (Xoay Vi Sai & Sóng Xung Kích)
  // =========================================================================
  const update = (time: number) => {
    // 1. Quantum Singularity Core Rotation
    innerCoreMesh.rotation.y = -time * 0.5;
    midCoreMesh.rotation.y = time * 0.35;
    midCoreMesh.rotation.x = Math.sin(time * 0.4) * 0.3;
    outerCoreMesh.rotation.z = time * 0.25;
    outerCoreMesh.rotation.y = -time * 0.3;

    // Spin Gyroscopic Rings
    quantumRings.rotation.y = time * 0.55;
    qr2.rotation.z = -time * 0.65;
    qr3.rotation.x = time * 0.45;

    // Expanding Shockwave Wave 1 & 2
    const wave1T = (time * 0.35) % 1.0;
    const wave1Scale = 1.0 + wave1T * 26.0;
    shockwave1.scale.set(wave1Scale, wave1Scale, 1.0);
    shockwaveMat1.opacity = Math.max(0, (1.0 - wave1T) * 0.65);

    const wave2T = (time * 0.35 + 0.5) % 1.0;
    const wave2Scale = 1.0 + wave2T * 26.0;
    shockwave2.scale.set(wave2Scale, wave2Scale, 1.0);
    shockwaveMat2.opacity = Math.max(0, (1.0 - wave2T) * 0.65);

    // 2. Swirl the Cosmic Accretion Galaxy Swirl (Keplerian differential rotation)
    const pos = particleGeo.attributes.position.array as Float32Array;
    for (let i = 0; i < particleCount; i++) {
      const r = particleOrbitData[i * 3];
      const baseAngle = particleOrbitData[i * 3 + 1];
      const speed = particleOrbitData[i * 3 + 2];

      const currentAngle = baseAngle + time * speed;
      pos[i * 3] = r * Math.sin(currentAngle);
      pos[i * 3 + 2] = -r * Math.cos(currentAngle);
      pos[i * 3 + 1] = Math.sin(time * 1.5 + r * 0.25) * 0.35;
    }
    particleGeo.attributes.position.needsUpdate = true;

    // 3. Move the Orbital Energy Comet
    const cometSpeed = 0.45;
    currentCometAngle = (time * cometSpeed) % (Math.PI * 2);

    const cometX = orbitalRadius * Math.sin(currentCometAngle);
    const cometZ = -orbitalRadius * Math.cos(currentCometAngle);
    cometGroup.position.set(cometX, 0, cometZ);

    // Update trailing comet tail sparks
    const tailPos = cometTailGeo.attributes.position.array as Float32Array;
    for (let i = 0; i < cometTailCount; i++) {
      const lagAngle = currentCometAngle - (i + 1) * 0.04;
      tailPos[i * 3] = orbitalRadius * Math.sin(lagAngle);
      tailPos[i * 3 + 1] = Math.sin(time * 9 + i) * 0.4;
      tailPos[i * 3 + 2] = -orbitalRadius * Math.cos(lagAngle);
    }
    cometTailGeo.attributes.position.needsUpdate = true;

    // 4. Subtle breathing pulse on the orbital ring
    ringMat.opacity = 0.7 + Math.sin(time * 2.8) * 0.18;
    ringAuraMesh.rotation.z = time * 0.1;
  };

  const dispose = () => {
    disposables.forEach((d) => d.dispose());
  };

  return {
    group,
    spores: accretionSwirl,
    coreMesh: innerCoreMesh,
    rings: quantumRings,
    cometLight,
    getCometAngle: () => currentCometAngle,
    update,
    dispose,
  };
}
