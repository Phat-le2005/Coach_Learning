import * as THREE from "three";
import type { Chapter3DLayout, Topic3DLayout } from "../../tree-3d-layout";

export interface TopicClustersSystem {
  group: THREE.Group;
  topicMeshes: Map<string, THREE.Mesh>;
  dispose: () => void;
}

export function createTopicClusters(chapters: Chapter3DLayout[]): TopicClustersSystem {
  const group = new THREE.Group();
  group.name = "topic-clusters-group";

  const topicMeshes = new Map<string, THREE.Mesh>();
  const disposables: Array<{ dispose: () => void }> = [];

  chapters.forEach((ch) => {
    const themeCol = new THREE.Color(ch.themeColor);

    ch.topics.forEach((topic: Topic3DLayout) => {
      // 1. Sub-branch tube from Chapter nexus to Topic pedestal
      const splineVectors = topic.subBranchSpline.map((p) => new THREE.Vector3(p.x, p.y, p.z));
      const curve = new THREE.CatmullRomCurve3(splineVectors);
      const tubeGeo = new THREE.TubeGeometry(curve, 16, 0.5, 8, false);
      const tubeMat = new THREE.MeshStandardMaterial({
        color: themeCol.clone().multiplyScalar(0.45),
        emissive: themeCol.clone().multiplyScalar(0.35),
        emissiveIntensity: 0.5,
        roughness: 0.5,
        metalness: 0.35,
      });
      const tubeMesh = new THREE.Mesh(tubeGeo, tubeMat);
      group.add(tubeMesh);
      disposables.push(tubeGeo, tubeMat);

      // 2. Floating Topic Island / Pedestal
      const podGroup = new THREE.Group();
      podGroup.position.set(topic.position.x, topic.position.y, topic.position.z);

      const podGeo = new THREE.CylinderGeometry(2.0, 2.5, 0.45, 16);
      const podMat = new THREE.MeshStandardMaterial({
        color: themeCol.clone().multiplyScalar(0.8),
        emissive: themeCol.clone().multiplyScalar(0.4),
        emissiveIntensity: 0.55,
        roughness: 0.35,
        metalness: 0.5,
      });
      const podMesh = new THREE.Mesh(podGeo, podMat);
      podMesh.userData = { kind: "topic", id: topic.data.id, name: topic.data.name };
      podGroup.add(podMesh);
      topicMeshes.set(topic.data.id, podMesh);
      disposables.push(podGeo, podMat);

      // Glowing rim
      const rimGeo = new THREE.RingGeometry(2.5, 2.9, 20);
      const rimMat = new THREE.MeshBasicMaterial({
        color: themeCol,
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.4,
      });
      const rimMesh = new THREE.Mesh(rimGeo, rimMat);
      rimMesh.rotation.x = -Math.PI / 2;
      rimMesh.position.y = 0.05;
      podGroup.add(rimMesh);
      disposables.push(rimGeo, rimMat);

      group.add(podGroup);
    });
  });

  const dispose = () => {
    disposables.forEach((d) => d.dispose());
  };

  return {
    group,
    topicMeshes,
    dispose,
  };
}
