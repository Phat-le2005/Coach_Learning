import type { SceneDrawing } from "./scene-geometry";
import type { GraphBounds } from "./fit-camera";
import { frameCurve } from "./curve-framing";

/** The view changes the camera, never the equations or their common Oxy plane. */
export function sceneSpatialLines(drawing:SceneDrawing){
  return drawing.paths.map((path)=>({...path,lines:path.polylines.map((line)=>{
    const points:number[]=[];for(let i=0;i<line.length;i+=2)points.push(line[i],line[i+1],0);return points;
  })}));
}
export function sceneSpatialBounds(drawing:SceneDrawing,depth=0):GraphBounds|null{
  const min:[number,number,number]=[Infinity,Infinity,0],max:[number,number,number]=[-Infinity,-Infinity,0];
  const include=(x:number,y:number)=>{if(!Number.isFinite(x)||!Number.isFinite(y))return;min[0]=Math.min(min[0],x);min[1]=Math.min(min[1],y);max[0]=Math.max(max[0],x);max[1]=Math.max(max[1],y);};
  for(const path of drawing.paths)for(let i=0;i<path.points.length;i+=2)include(path.points[i],path.points[i+1]);
  for(const fill of drawing.fills)for(let i=0;i<fill.points.length;i+=2)include(fill.points[i],fill.points[i+1]);
  max[2]=depth;
  return Number.isFinite(min[0])?{min,max}:null;
}

/** A domain-sized focus keeps polynomial tails from shrinking intersections.
 * Full geometry remains available through the explicit full-view control. */
export function sceneSpatialFocus(drawing:SceneDrawing,domain:number,depth=0):GraphBounds|null{
  const full=sceneSpatialBounds(drawing,depth);if(!full)return null;
  if(full.min[0]>domain||full.max[0]<-domain||full.min[1]>domain||full.max[1]<-domain)return full;
  return {min:[Math.max(-domain,full.min[0]),Math.max(-domain,full.min[1]),0],max:[Math.min(domain,full.max[0]),Math.min(domain,full.max[1]),depth]};
}

/** Share the single-curve focus policy: preserve vertices, focus only long tails. */
export function sceneCurveFocus(drawing:SceneDrawing):GraphBounds|null{
  const full=sceneSpatialBounds(drawing);if(!full)return null;
  const segments=drawing.paths.flatMap((path)=>path.polylines.map((line)=>{
    const points:[number,number,number][]=[];for(let i=0;i<line.length;i+=2)points.push([line[i],line[i+1],0]);return points;
  }));
  return frameCurve(segments,full).bounds;
}

type Point=[number,number];
/** Caps and outward walls of a triangulated region, with internal edges removed.
 * The original Oxy region is the bottom cap; z in [0,depth] is an explicit model. */
export function extrudeSceneFill(points:ArrayLike<number>,depth:number):{points:number[];edges:number[]}{
  const vertices:number[]=[],edges:number[]=[],boundary=new Map<string,{a:Point;b:Point;count:number}>();
  if(!Number.isFinite(depth)||depth<=0||depth>10)return {points:vertices,edges};
  const key=(p:Point)=>`${Math.round(p[0]*1e7)},${Math.round(p[1]*1e7)}`;
  for(let i=0;i+5<points.length;i+=6){
    let a:Point=[points[i],points[i+1]],b:Point=[points[i+2],points[i+3]],c:Point=[points[i+4],points[i+5]];
    const area=(b[0]-a[0])*(c[1]-a[1])-(c[0]-a[0])*(b[1]-a[1]);
    if(![...a,...b,...c].every(Number.isFinite)||Math.abs(area)<1e-12)continue;
    if(area<0)[b,c]=[c,b];
    vertices.push(...a,depth,...b,depth,...c,depth,...a,0,...c,0,...b,0);
    for(const [p,q] of [[a,b],[b,c],[c,a]]){const pk=key(p),qk=key(q),id=pk<qk?`${pk}|${qk}`:`${qk}|${pk}`,edge=boundary.get(id);if(edge)edge.count++;else boundary.set(id,{a:p,b:q,count:1});}
  }
  for(const {a,b,count} of boundary.values())if(count===1){
    vertices.push(...a,0,...b,0,...b,depth,...a,0,...b,depth,...a,depth);
    edges.push(...a,0,...b,0,...a,depth,...b,depth);
  }
  return {points:vertices,edges};
}

/** Clip each separate polyline before extending it, preserving gaps and poles. */
export function sceneSpatialCurtains(drawing:SceneDrawing,domain:number,depth:number,clipHeight=true){
  if(!Number.isFinite(depth)||depth<=0||depth>10)return [];
  return drawing.paths.map((path)=>{
    const points:number[]=[],edges:number[]=[];
    for(const line of path.polylines)for(let i=0;i+3<line.length;i+=2){
      const a:Point=[line[i],line[i+1]],b:Point=[line[i+2],line[i+3]],delta:Point=[b[0]-a[0],b[1]-a[1]];
      if(![...a,...b].every(Number.isFinite))continue;
      let low=0,high=1,valid=true;
      for(let axis=0;axis<(clipHeight?2:1);axis++){
        if(Math.abs(delta[axis])<1e-12){if(Math.abs(a[axis])>domain)valid=false;continue;}
        const cuts=[(-domain-a[axis])/delta[axis],(domain-a[axis])/delta[axis]].sort((x,y)=>x-y);
        low=Math.max(low,cuts[0]);high=Math.min(high,cuts[1]);
      }
      if(!valid||low>=high)continue;
      const p:Point=[a[0]+delta[0]*low,a[1]+delta[1]*low],q:Point=[a[0]+delta[0]*high,a[1]+delta[1]*high];
      points.push(...p,0,...q,0,...q,depth,...p,0,...q,depth,...p,depth);
      edges.push(...p,depth,...q,depth);
    }
    return {color:path.color,points,edges};
  }).filter((surface)=>surface.points.length);
}
