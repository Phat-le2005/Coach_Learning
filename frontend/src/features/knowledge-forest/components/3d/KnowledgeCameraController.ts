import * as THREE from "three";
import type { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

import type { Point3D } from "../../tree-3d-layout";

export class KnowledgeCameraController {
  private camera: THREE.PerspectiveCamera;
  private controls: OrbitControls;

  private targetCamPos: THREE.Vector3;
  private targetLookAt: THREE.Vector3;
  private isTransitioning: boolean = false;
  private transitionSpeed: number = 0.045;

  constructor(camera: THREE.PerspectiveCamera, controls: OrbitControls) {
    this.camera = camera;
    this.controls = controls;
    this.targetCamPos = camera.position.clone();
    this.targetLookAt = controls.target.clone();
  }

  public flyTo(
    targetPosition: Point3D,
    lookAtPoint: Point3D,
    speed: number = 0.05
  ): void {
    this.targetCamPos.set(targetPosition.x, targetPosition.y, targetPosition.z);
    this.targetLookAt.set(lookAtPoint.x, lookAtPoint.y, lookAtPoint.z);
    this.transitionSpeed = speed;
    this.isTransitioning = true;
  }

  public flyToOverview(overview: { position: Point3D; target: Point3D }): void {
    this.flyTo(overview.position, overview.target, 0.04);
  }

  public flyToChapter(pos: Point3D): void {
    const camDist = 36;
    const norm = Math.hypot(pos.x, pos.z) || 1;
    const camX = pos.x + (pos.x / norm) * camDist * 0.45;
    const camY = pos.y + 14;
    const camZ = pos.z + (pos.z / norm) * camDist * 0.45;
    this.flyTo({ x: camX, y: camY, z: camZ }, pos, 0.05);
  }

  public flyToNode(pos: Point3D): void {
    const camDist = 18;
    const norm = Math.hypot(pos.x, pos.z) || 1;
    const camX = pos.x + (pos.x / norm) * camDist * 0.35;
    const camY = pos.y + 4.5;
    const camZ = pos.z + (pos.z / norm) * camDist * 0.35;
    this.flyTo({ x: camX, y: camY, z: camZ }, pos, 0.06);
  }

  public update(): void {
    if (!this.isTransitioning) {
      this.controls.update();
      return;
    }

    this.camera.position.lerp(this.targetCamPos, this.transitionSpeed);
    this.controls.target.lerp(this.targetLookAt, this.transitionSpeed);
    this.controls.update();

    if (
      this.camera.position.distanceTo(this.targetCamPos) < 0.25 &&
      this.controls.target.distanceTo(this.targetLookAt) < 0.25
    ) {
      this.camera.position.copy(this.targetCamPos);
      this.controls.target.copy(this.targetLookAt);
      this.isTransitioning = false;
    }
  }

  public stopTransition(): void {
    this.isTransitioning = false;
  }
}
