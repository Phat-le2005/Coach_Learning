import type { GraphCamera } from "./expression";
import type { SceneDrawing } from "./scene-geometry";
import { sceneSpatialBounds } from "./scene-spatial";
import { fitGraphCamera } from "./fit-camera";

/** Fit all currently sampled planar paths/regions with the same scale on both axes. */
export function fitScene2DCamera(drawing:SceneDrawing,domain:number,aspect:number):GraphCamera|null{
  const bounds=sceneSpatialBounds(drawing);if(!bounds)return null;
  const fitted=fitGraphCamera(bounds,{position:[0,0,16],target:[0,0,0],zoom:1},{spatial:false,aspect,halfHeight:domain*1.15});
  return fitted?{...fitted,zoom:Math.min(20,Math.max(.1,fitted.zoom??1))}:null;
}
