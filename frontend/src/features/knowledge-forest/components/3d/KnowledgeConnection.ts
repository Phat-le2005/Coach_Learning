import * as THREE from "three";
import type { PrerequisiteArc3D } from "../../tree-3d-layout";

export interface ConnectionsSystem {
  group: THREE.Group;
  setVisible: (visible: boolean) => void;
  highlightConnections: (activeCode: string | null) => void;
  update: (time: number) => void;
  dispose: () => void;
}

export function createKnowledgeConnections(arcs: PrerequisiteArc3D[]): ConnectionsSystem {
  const group = new THREE.Group();
  group.name = "prerequisite-connections-group";
  group.visible = false;

  const arcMeshes: Array<{
    mesh: THREE.Line;
    mat: THREE.LineDashedMaterial;
    arc: PrerequisiteArc3D;
  }> = [];

  const disposables: Array<{ dispose: () => void }> = [];

  arcs.forEach((arc) => {
    const p0 = new THREE.Vector3(arc.sourcePos.x, arc.sourcePos.y, arc.sourcePos.z);
    const p1 = new THREE.Vector3(arc.controlPoint.x, arc.controlPoint.y, arc.controlPoint.z);
    const p2 = new THREE.Vector3(arc.targetPos.x, arc.targetPos.y, arc.targetPos.z);

    const curve = new THREE.QuadraticBezierCurve3(p0, p1, p2);
    const points = curve.getPoints(24);
    const geo = new THREE.BufferGeometry().setFromPoints(points);

    // Compute line distances for dash animation
    const lineDistances = new Float32Array(points.length);
    let dist = 0;
    for (let i = 1; i < points.length; i++) {
      dist += points[i].distanceTo(points[i - 1]);
      lineDistances[i] = dist;
    }
    geo.setAttribute("lineDistance", new THREE.BufferAttribute(lineDistances, 1));

    const mat = new THREE.LineDashedMaterial({
      color: new THREE.Color("#8be5c2"),
      dashSize: 1.2,
      gapSize: 0.8,
      linewidth: 1.5,
      transparent: true,
      opacity: 0.35,
    });

    const line = new THREE.Line(geo, mat);
    line.computeLineDistances();
    group.add(line);

    arcMeshes.push({ mesh: line, mat, arc });
    disposables.push(geo, mat);
  });

  const setVisible = (visible: boolean) => {
    group.visible = visible;
  };

  const highlightConnections = (activeCode: string | null) => {
    if (!activeCode) {
      arcMeshes.forEach(({ mat }) => {
        mat.color.set("#8be5c2");
        mat.opacity = 0.35;
      });
      return;
    }

    arcMeshes.forEach(({ mat, arc }) => {
      if (arc.targetCode === activeCode) {
        // Upstream prerequisite needed: warm gold
        mat.color.set("#e8bf6a");
        mat.opacity = 0.95;
      } else if (arc.sourceCode === activeCode) {
        // Downstream unlock: bright mint
        mat.color.set("#8be5c2");
        mat.opacity = 0.95;
      } else {
        // Non-relevant edge fades
        mat.opacity = 0.08;
      }
    });
  };

  const update = (time: number) => {
    if (!group.visible) return;
    // Animate dash offset for flowing energy pulse
    arcMeshes.forEach(({ mat }) => {
      mat.dashSize = 1.2 + Math.sin(time * 2) * 0.2;
    });
  };

  const dispose = () => {
    disposables.forEach((d) => d.dispose());
  };

  return {
    group,
    setVisible,
    highlightConnections,
    update,
    dispose,
  };
}
