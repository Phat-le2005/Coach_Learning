import type { GraphCamera } from "./expression";
import { fitGraphCamera, type GraphBounds } from "./fit-camera";

export type GraphCameraPreset = "PERSPECTIVE" | "OXY" | "OXZ" | "OYZ";

/** Surface renderers map mathematical (x,y,z) to scene (x,z,y); curves retain (x,y,z). */
export function fitCameraPreset(preset: GraphCameraPreset, bounds: GraphBounds, dimension: "2D" | "3D", aspect: number): GraphCamera | null {
  const fromAbove: GraphCamera["position"] = [0, 1, 0.0001];
  const fromFront: GraphCamera["position"] = [0, 0, 1];
  const position: GraphCamera["position"] = preset === "PERSPECTIVE" ? [11, 9, 13]
    : preset === "OYZ" ? [1, 0, 0]
    : (preset === "OXY") === (dimension === "3D") ? fromAbove : fromFront;
  return fitGraphCamera(bounds, { position, target: [0, 0, 0] }, { spatial: true, aspect, halfHeight: 4 });
}
