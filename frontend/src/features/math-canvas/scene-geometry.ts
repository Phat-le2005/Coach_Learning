import { evaluateMath, type GraphSettings, type MathExpression } from "./expression";
import { sampleImplicitGeometry } from "./geometry";
import { relationContains, type CompiledScene, type SceneRelation, type SceneLayer } from "./scene";

export interface ScenePath { rowId: string; color: string; dashed: boolean; points: number[] | Float32Array; polylines: (number[] | Float32Array)[] }
export interface SceneFill { color: string; points: number[] | Float32Array }
export interface SceneDrawing { paths: ScenePath[]; fills: SceneFill[]; intersections: [number, number][] }
type Point = [number, number];
/** Join contour edges so a dashed stroke keeps its phase across sampling triangles. */
export function connectContourSegments(points: ArrayLike<number>, tolerance: number): number[][] {
  const key=(x:number,y:number)=>`${Math.round(x/tolerance)},${Math.round(y/tolerance)}`;
  const nodes=new Map<string,{point:Point;edges:number[]}>(),edges:{a:string;b:string;used:boolean}[]=[];
  for(let i=0;i<points.length;i+=4){
    const a=key(points[i],points[i+1]),b=key(points[i+2],points[i+3]);if(a===b)continue;
    if(!nodes.has(a))nodes.set(a,{point:[points[i],points[i+1]],edges:[]});if(!nodes.has(b))nodes.set(b,{point:[points[i+2],points[i+3]],edges:[]});
    nodes.get(a)!.edges.push(edges.length);nodes.get(b)!.edges.push(edges.length);edges.push({a,b,used:false});
  }
  const lines:number[][]=[];
  const walk=(start:string,first:number)=>{const line=[...nodes.get(start)!.point];let cursor=start,index=first;while(!edges[index].used){const edge=edges[index];edge.used=true;cursor=edge.a===cursor?edge.b:edge.a;line.push(...nodes.get(cursor)!.point);const next=nodes.get(cursor)!.edges.find((candidate)=>!edges[candidate].used);if(next===undefined)break;index=next;}if(line.length>=4)lines.push(line);};
  for(const [name,node] of nodes)if(node.edges.length!==2)for(const index of node.edges)if(!edges[index].used)walk(name,index);
  for(let i=0;i<edges.length;i++)if(!edges[i].used)walk(edges[i].a,i);
  return lines;
}
function signed(relation: SceneRelation, values: Record<string, number>): number {
  const value = evaluateMath(relation.residual, values);
  return relation.operator === ">" || relation.operator === ">=" ? -value : value;
}
function fillRegion(field: (point: Point) => number, contains: (point: Point) => boolean, domain: number): number[] {
  const n = 72, points: Point[] = [], values: number[] = [], included: boolean[] = [], output: number[] = [];
  for (let j = 0; j <= n; j++) for (let i = 0; i <= n; i++) {
    const point: Point = [-domain + 2 * domain * i / n, -domain + 2 * domain * j / n];
    points.push(point); values.push(field(point)); included.push(contains(point));
  }
  const crossing = (a: Point, b: Point, va: number, vb: number): Point | null => {
    const tolerance = Math.max(1e-8, Math.min(Math.abs(va), Math.abs(vb)) * .01);
    const insideA = contains(a);
    for (let i = 0; i < 16; i++) {
      const p: Point = [(a[0]+b[0])/2, (a[1]+b[1])/2], value = field(p);
      if (!Number.isFinite(value)) return null;
      if (contains(p) === insideA) { a = p; va = value; } else { b = p; vb = value; }
    }
    const candidate = Math.abs(va) < Math.abs(vb) ? a : b;
    return Math.min(Math.abs(va),Math.abs(vb)) <= tolerance ? candidate : null;
  };
  for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) {
    const a = j * (n + 1) + i, b = a + 1, c = a + n + 1, d = c + 1;
    for (const triangle of [[a,b,d],[a,d,c]]) {
      if (triangle.some((index) => !Number.isFinite(values[index]))) continue;
      const polygon: Point[] = []; let valid = true;
      for (let k = 0; k < 3; k++) {
        const current = triangle[k], next = triangle[(k + 1) % 3], inside = included[current], nextInside = included[next];
        if (inside) polygon.push(points[current]);
        if (inside !== nextInside) { const p = crossing(points[current], points[next], values[current], values[next]); if (!p) { valid = false; break; } polygon.push(p); }
      }
      if (!valid) continue;
      for (let k = 1; k < polygon.length - 1; k++) {
        const centroid: Point = [(polygon[0][0]+polygon[k][0]+polygon[k+1][0])/3,(polygon[0][1]+polygon[k][1]+polygon[k+1][1])/3];
        if (Number.isFinite(field(centroid)) && contains(centroid)) output.push(...polygon[0], ...polygon[k], ...polygon[k+1]);
      }
    }
  }
  return output;
}

export function sampleScene(scene: CompiledScene, parameters: Record<string, number>, domain: number): SceneDrawing {
  const drawing: SceneDrawing = { paths: [], fills: [], intersections: [] };
  const layers = scene.layers.filter((layer) => layer.visible);
  const settings: GraphSettings = { parameters, domain, scale: 1, offset: 0, shift_x: 0, shift_y: 0 };
  const regions: SceneLayer[] = [];
  for (const layer of layers) {
    for (const relation of layer.relations) {
      const model: MathExpression = { kind: "implicit", dimension: "2D", parameters: scene.parameters, expression: layer.expression, node: relation.residual };
      const sampled = sampleImplicitGeometry(model, settings, false, 56);
      const points: number[] = [];
      for (let i = 0; i < sampled.positions.length; i += 3) points.push(sampled.positions[i], sampled.positions[i+1]);
      drawing.paths.push({ rowId: layer.id, color: layer.color, dashed: relation.operator === "<" || relation.operator === ">", points, polylines: connectContourSegments(points, domain*1e-4) });
    }
    if (layer.relations.every((relation) => relation.operator !== "=")) regions.push(layer);
  }
  const scope = { ...parameters, x: 0, y: 0 };
  const layerField = (layer: SceneLayer, p: Point) => {
    [scope.x, scope.y] = p;
    const values = layer.relations.map((relation) => signed(relation, scope));
    return values.every(Number.isFinite) ? Math.max(...values) : NaN;
  };
  const membership = (layer: SceneLayer, p: Point) => { [scope.x,scope.y]=p;return layer.relations.every((relation)=>relationContains(relation,scope)); };
  if (scene.document.combine === "OVERLAY") {
    for (const layer of regions) drawing.fills.push({ color: layer.color, points: fillRegion((p) => layerField(layer,p), (p)=>membership(layer,p), domain) });
  } else if (regions.length) {
    const combined = (p: Point) => {
      const values = regions.map((layer) => layerField(layer,p));
      if (scene.document.combine === "AND") return values.every(Number.isFinite) ? Math.max(...values) : NaN;
      const finite = values.filter(Number.isFinite); return finite.length ? Math.min(...finite) : NaN;
    };
    const contains=(p:Point)=>scene.document.combine==="AND"?regions.every((layer)=>membership(layer,p)):regions.some((layer)=>membership(layer,p));
    drawing.fills.push({ color: "#07856b", points: fillRegion(combined, contains, domain) });
  }
  // Numerical intersections are visual hints. Coincident segments are not isolated points.
  const equations = layers.filter((layer) => layer.relations.length === 1 && layer.relations[0].operator === "=");
  for (let i = 0; i < equations.length; i++) for (let j = i+1; j < equations.length; j++) {
    const path = drawing.paths.find((path) => path.rowId === equations[i].id)!;
    const other = equations[j].relations[0].residual;
    for (let k = 0; k < path.points.length && drawing.intersections.length < 50; k += 4) {
      let a: Point = [path.points[k],path.points[k+1]], b: Point = [path.points[k+2],path.points[k+3]];
      const value = (p: Point) => evaluateMath(other,{...parameters,x:p[0],y:p[1]});
      let va = value(a), vb = value(b);
      if (![va,vb].every(Number.isFinite) || (Math.abs(va)<1e-9 && Math.abs(vb)<1e-9)) continue;
      let found: Point | null = Math.abs(va)<1e-6?a:Math.abs(vb)<1e-6?b:null;
      if (!found && va*vb>0) continue;
      for (let step = 0; !found && step < 16; step++) {
        const t = va === vb ? .5 : Math.max(0,Math.min(1,va/(va-vb)));
        const p: Point = [a[0]+t*(b[0]-a[0]),a[1]+t*(b[1]-a[1])], v = value(p);
        if (!Number.isFinite(v)) break;
        if (Math.abs(v)<1e-5) { found = p; break; }
        if ((v<0)===(va<0)) { a=p;va=v; } else { b=p;vb=v; }
      }
      if (found && !drawing.intersections.some((p) => Math.hypot(p[0]-found![0],p[1]-found![1])<domain/100)) drawing.intersections.push(found);
    }
  }
  return drawing;
}
