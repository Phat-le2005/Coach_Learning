import { sampleScene } from "./scene-geometry";
import { sampleSceneCurves3D } from "./scene-curve-sampling";
import type { CompiledScene } from "./scene";
const scope = self as unknown as { onmessage: (event: MessageEvent<{ id: number; scene: CompiledScene; parameters: Record<string, number>; domain: number; spatialCurves?:boolean }>) => void; postMessage: (value: unknown, transfer?: Transferable[]) => void };
scope.onmessage = ({data}) => {
  try {
    const planar=sampleScene(data.scene,data.parameters,data.domain),drawing=data.spatialCurves?sampleSceneCurves3D(data.scene,data.parameters,data.domain,planar):planar, transfer:Transferable[]=[];
    for(const path of [...drawing.paths,...drawing.fills,...(drawing.betweenFills??[])]){const points=new Float32Array(path.points);path.points=points;transfer.push(points.buffer);}
    for(const path of drawing.paths)path.polylines=path.polylines.map((line)=>{const points=new Float32Array(line);transfer.push(points.buffer);return points;});
    scope.postMessage({id:data.id,drawing},transfer);
  }
  catch { scope.postMessage({ id: data.id, error: "Chưa dựng được bảng đồ thị. Hãy thử lại hoặc đơn giản hóa biểu thức." }); }
};
