import { evaluateMath } from "./expression";
import type { CompiledScene } from "./scene";
import type { SceneDrawing, ScenePath } from "./scene-geometry";
import { explicitSceneCurve } from "./scene-curve";

/** Match the single-formula 3D curve: domain limits x, not the curve's height.
 * Keep planar fills/intersections and implicit contours from the scene worker. */
export function sampleSceneCurves3D(scene:CompiledScene,parameters:Record<string,number>,domain:number,drawing:SceneDrawing):SceneDrawing{
  const nodes=new Map(scene.layers.filter((layer)=>layer.visible).map((layer)=>[layer.id,explicitSceneCurve(layer)]));
  const paths=drawing.paths.map((path):ScenePath=>{
    const node=nodes.get(path.rowId);if(!node)return path;
    const polylines:number[][]=[],points:number[]=[],values={...parameters,x:0};let line:number[]=[];
    const flush=()=>{if(line.length>=4){polylines.push(line);for(let i=0;i+3<line.length;i+=2)points.push(line[i],line[i+1],line[i+2],line[i+3]);}line=[];};
    for(let i=0;i<=900;i++){
      const x=-domain+2*domain*i/900;values.x=x;const y=evaluateMath(node,values);
      if(!Number.isFinite(y)||Math.abs(y)>1000){flush();continue;}
      if(line.length&&Math.abs(y-line[line.length-1])>domain*2)flush();
      line.push(x,y);
    }
    flush();return {...path,points,polylines};
  });
  return {...drawing,paths};
}
