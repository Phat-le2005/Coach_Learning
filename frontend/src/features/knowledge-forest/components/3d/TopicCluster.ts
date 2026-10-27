import * as THREE from "three";
import type { Chapter3DLayout, Topic3DLayout } from "../../tree-3d-layout";

export interface TopicClustersSystem {
  group: THREE.Group;
  topicMeshes: Map<string, THREE.Mesh>;
  update: (time: number) => void;
  dispose: () => void;
}

export function createTopicClusters(chapters: Chapter3DLayout[]): TopicClustersSystem {
  const group = new THREE.Group();
  group.name = "topic-clusters-group";

  const topicMeshes = new Map<string, THREE.Mesh>();
  const animatedTopics: Array<{
    podGroup: THREE.Group;
    basePos: THREE.Vector3;
    crystalMesh: THREE.Mesh;
    rimMesh: THREE.Mesh;
    haloMesh: THREE.Mesh;
  }> = [];

  const disposables: Array<{ dispose: () => void }> = [];

  chapters.forEach((ch) => {
    const themeCol = new THREE.Color(ch.themeColor);

    ch.topics.forEach((topic: Topic3DLayout, topicIdx) => {
      const topicBranchGroup = new THREE.Group();

      // =========================================================================
      // 1. VOLUMETRIC ELECTRIC GLOW SUB-BRANCH (Nhánh Sét Phát Quang Nối Topic)
      // =========================================================================
      const splineVectors = topic.subBranchSpline.map((p) => new THREE.Vector3(p.x, p.y, p.z));
      const curve = new THREE.CatmullRomCurve3(splineVectors);

      // Outer Glow Aura
      const auraGeo = new THREE.TubeGeometry(curve, 20, 0.75, 6, false);
      const auraMat = new THREE.MeshBasicMaterial({
        color: themeCol,
        transparent: true,
        opacity: 0.32,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      });
      const auraMesh = new THREE.Mesh(auraGeo, auraMat);
      topicBranchGroup.add(auraMesh);
      disposables.push(auraGeo, auraMat);

      // Mid Plasma Tube
      const tubeGeo = new THREE.TubeGeometry(curve, 20, 0.32, 6, false);
      const tubeMat = new THREE.MeshBasicMaterial({
        color: themeCol,
        transparent: true,
        opacity: 0.85,
        blending: THREE.AdditiveBlending,
      });
      const tubeMesh = new THREE.Mesh(tubeGeo, tubeMat);
      topicBranchGroup.add(tubeMesh);
      disposables.push(tubeGeo, tubeMat);

      // Inner Core Filament
      const coreGeo = new THREE.TubeGeometry(curve, 20, 0.1, 4, false);
      const coreMat = new THREE.MeshBasicMaterial({
        color: new THREE.Color("#ffffff"),
        blending: THREE.AdditiveBlending,
      });
      const coreMesh = new THREE.Mesh(coreGeo, coreMat);
      topicBranchGroup.add(coreMesh);
      disposables.push(coreGeo, coreMat);

      // =========================================================================
      // 2. FLOATING LUMINOUS TOPIC POD (Đài Tinh Thể Chuyên Đề)
      // =========================================================================
      const podGroup = new THREE.Group();
      podGroup.position.set(topic.position.x, topic.position.y, topic.position.z);

      const podGeo = new THREE.CylinderGeometry(1.6, 2.1, 0.35, 20);
      const podMat = new THREE.MeshStandardMaterial({
        color: themeCol.clone().multiplyScalar(0.7),
        emissive: themeCol,
        emissiveIntensity: 1.1,
        roughness: 0.2,
        metalness: 0.8,
      });
      const podMesh = new THREE.Mesh(podGeo, podMat);
      podMesh.userData = { kind: "topic", id: topic.data.id, name: topic.data.name };
      podGroup.add(podMesh);
      topicMeshes.set(topic.data.id, podMesh);
      disposables.push(podGeo, podMat);

      // Floating Topic Crystal Gem (Dodecahedron)
      const gemGeo = new THREE.DodecahedronGeometry(1.0, 0);
      const gemMat = new THREE.MeshStandardMaterial({
        color: new THREE.Color("#ffffff"),
        emissive: themeCol,
        emissiveIntensity: 1.6,
        roughness: 0.1,
        metalness: 0.9,
      });
      const gemMesh = new THREE.Mesh(gemGeo, gemMat);
      gemMesh.position.y = 1.1;
      podGroup.add(gemMesh);
      disposables.push(gemGeo, gemMat);

      // Glowing Rim Ring
      const rimGeo = new THREE.RingGeometry(2.1, 2.7, 24);
      const rimMat = new THREE.MeshBasicMaterial({
        color: themeCol,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.55,
        blending: THREE.AdditiveBlending,
      });
      const rimMesh = new THREE.Mesh(rimGeo, rimMat);
      rimMesh.rotation.x = -Math.PI / 2;
      rimMesh.position.y = 0.05;
      podGroup.add(rimMesh);
      disposables.push(rimGeo, rimMat);

      // Outer Spinning Torus Ring
      const haloGeo = new THREE.TorusGeometry(2.5, 0.06, 6, 24);
      const haloMat = new THREE.MeshBasicMaterial({
        color: new THREE.Color("#ffffff"),
        transparent: true,
        opacity: 0.65,
        blending: THREE.AdditiveBlending,
      });
      const haloMesh = new THREE.Mesh(haloGeo, haloMat);
      haloMesh.rotation.x = Math.PI / 3;
      podGroup.add(haloMesh);
      disposables.push(haloGeo, haloMat);

      topicBranchGroup.add(podGroup);
      group.add(topicBranchGroup);

      animatedTopics.push({
        podGroup,
        basePos: new THREE.Vector3(topic.position.x, topic.position.y, topic.position.z),
        crystalMesh: gemMesh,
        rimMesh,
        haloMesh,
      });
    });
  });

  const update = (time: number) => {
    animatedTopics.forEach((item, idx) => {
      // Harmonic floating undulation
      const floatY = Math.sin(time * 2.0 + idx * 0.9) * 0.9;
      const floatX = Math.cos(time * 1.5 + idx * 0.7) * 0.6;
      item.podGroup.position.set(
        item.basePos.x + floatX,
        item.basePos.y + floatY,
        item.basePos.z
      );

      item.crystalMesh.rotation.y = time * 2.2 + idx;
      item.crystalMesh.rotation.z = Math.sin(time * 1.0 + idx) * 0.35;
      item.rimMesh.rotation.z = -time * 1.1;
      item.haloMesh.rotation.y = time * 1.6;
    });
  };

  const dispose = () => {
    disposables.forEach((d) => d.dispose());
  };

  return {
    group,
    topicMeshes,
    update,
    dispose,
  };
}
