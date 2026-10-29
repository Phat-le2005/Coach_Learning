import test from "node:test";
import assert from "node:assert/strict";
import { Worker } from "node:worker_threads";
import { resolve } from "node:path";
import { compileGraphScene, layerContains, SCENE_COLORS, type GraphSceneDocument } from "../src/features/math-canvas/scene.js";
import { sampleScene, connectContourSegments, type SceneDrawing } from "../src/features/math-canvas/scene-geometry.js";
import { appendSceneRow, parseSceneDraft } from "../src/features/math-canvas/scene-draft.js";

const document=(expressions:string[],combine:GraphSceneDocument["combine"]="OVERLAY"):GraphSceneDocument=>({version:2,dimension:"2D",combine,rows:expressions.map((expression,i)=>({id:`row-${i}`,expression,visible:true,color:SCENE_COLORS[i]}))});
const compile=(expressions:string[],combine:GraphSceneDocument["combine"]="OVERLAY")=>compileGraphScene(document(expressions,combine));
function area(points:ArrayLike<number>):number{let result=0;for(let i=0;i<points.length;i+=6)result+=Math.abs((points[i+2]-points[i])*(points[i+5]-points[i+1])-(points[i+4]-points[i])*(points[i+3]-points[i+1]))/2;return result;}

test("relation grammar normalizes inclusive signs and preserves strict membership",()=>{
  const scene=compile(["y ≥ x²","y < 1",String.raw`0\le x\leq 2`]);assert.deepEqual(scene.errors,{});
  assert.equal(scene.document.rows[0].expression,"y>=x^2");
  assert.equal(layerContains(scene.layers[0],1,1,{}),true);assert.equal(layerContains(scene.layers[1],0,1,{}),false);
  assert.equal(layerContains(scene.layers[2],0,0,{}),true);assert.equal(layerContains(scene.layers[2],2,0,{}),true);assert.equal(layerContains(scene.layers[2],3,0,{}),false);
  const coefficient=compile(["y=f*x"]);assert.deepEqual(coefficient.errors,{});assert.deepEqual(coefficient.parameters,["f"]);
});
test("named functions compose forward references and share real parameters",()=>{
  const scene=compile(["y=f(g(x))","f(x)=a*x²+1","g(x)=sin(x)"]);assert.deepEqual(scene.errors,{});assert.deepEqual(scene.parameters,["a"]);
  assert.equal(layerContains(scene.layers[0],Math.PI/2,3,{a:2}),true);
  const constant=compile(["f(x)=1","y=f(1/x)"]);assert.deepEqual(constant.errors,{});
  assert.equal(layerContains(constant.layers[1],0,1,{}),false,"undefined inner arguments must stay undefined even for a constant outer function");
});
test("cycles, missing functions, duplicates and expanded complexity are row errors",()=>{
  for(const rows of [["f(x)=g(x)","g(x)=f(x)"],["y=f(x)"],["f(x)=x","f(x)=x²"],["f(x)=x+x+x+x","g(x)=f(f(f(f(f(x)))))"]]){
    const scene=compile(rows);assert.ok(Object.keys(scene.errors).length>0,rows.join(";"));
  }
});
test("malformed relations and executable expressions never reach geometry",()=>{
  for(const expression of ["y=>x","y==x","y=window.alert(x)","y=x.constructor","y=[x]","y=sin(x", "x=y=1"]){assert.ok(Object.keys(compile([expression]).errors).length>0,expression);}
  const spatial=compile(["z=x²+y²"]);assert.match(spatial.errors["row-0"],/3D/);
});
test("a valid row remains available when another row needs correction",()=>{
  const scene=compile(["y=x²","y>="]);assert.equal(scene.layers.length,1);assert.ok(scene.errors["row-1"]);
});
test("filled common region between y=x² and y=1 has the expected area and boundaries",()=>{
  const scene=compile(["y>=x²","y<=1"],"AND"),drawing=sampleScene(scene,{},2);
  assert.equal(drawing.fills.length,1);assert.ok(Math.abs(area(drawing.fills[0].points)-4/3)<.015);
  assert.ok(drawing.paths.every((path)=>!path.dashed));
  for(let i=0;i<drawing.fills[0].points.length;i+=6){const p=drawing.fills[0].points,x=(p[i]+p[i+2]+p[i+4])/3,y=(p[i+1]+p[i+3]+p[i+5])/3;assert.ok(y>=x*x-.001&&y<=1.001);}
  const strict=sampleScene(compile(["y>x²","y<1"],"AND"),{},2);assert.ok(strict.paths.every((path)=>path.dashed));assert.ok(Math.abs(area(strict.fills[0].points)-area(drawing.fills[0].points))<.001);
});
test("overlay, AND, OR and hidden rows have different region semantics",()=>{
  const and=sampleScene(compile(["x<=0","y<=0"],"AND"),{},2);assert.ok(Math.abs(area(and.fills[0].points)-4)<.02);
  const or=sampleScene(compile(["x<=0","y<=0"],"OR"),{},2);assert.ok(Math.abs(area(or.fills[0].points)-12)<.03);
  const overlay=sampleScene(compile(["x<=0","y<=0"]),{},2);assert.equal(overlay.fills.length,2);
  const doc=document(["x<=0","y<=0"],"AND");doc.rows[1].visible=false;
  const hidden=sampleScene(compileGraphScene(doc),{},2);assert.equal(hidden.paths.length,1);assert.ok(Math.abs(area(hidden.fills[0].points)-8)<.02);
});
test("changing the radius scales the disk region and excludes undefined domains",()=>{
  const disk=compile(["x²+y²<=r²"]);
  for(const r of [1,2]){const drawing=sampleScene(disk,{r},3);assert.ok(Math.abs(area(drawing.fills[0].points)-Math.PI*r*r)<.035);}
  const undefinedRegion=sampleScene(compile(["y>=sqrt(-1)"]),{},2);assert.equal(undefinedRegion.fills[0].points.length,0);
});
test("coincident curves do not produce an arbitrary list of isolated intersections",()=>{
  const coincident=sampleScene(compile(["y=x","2y=2x"]),{},3);assert.equal(coincident.intersections.length,0);
  const crossing=sampleScene(compile(["y=x²","y=1"]),{},2);assert.equal(crossing.intersections.length,2);
  assert.ok(crossing.intersections.some(([x,y])=>Math.abs(x-1)<.01&&Math.abs(y-1)<.01));
});
test("scene limits and row identity are bounded",()=>{
  assert.throws(()=>compile(Array.from({length:9},()=>"y=x")));
  const doc=document(["y=x","y=x²"]);doc.rows[1].id=doc.rows[0].id;assert.throws(()=>compileGraphScene(doc));
  assert.ok(Object.keys(compile(["y=a+b+c+d+f+g+h+x"]).errors).length>0);
});
test("the scene worker transfers boundary and fill buffers for a composed inequality",{timeout:10000},async(t)=>{
  const worker=new Worker(resolve(__dirname,"../../tests/fixtures/math-sampling-worker.cjs"),{workerData:{entry:resolve(__dirname,"../src/features/math-canvas/scene.worker.js")}});t.after(()=>worker.terminate());
  const response=await new Promise<{id:number;drawing:SceneDrawing}>((accept,reject)=>{worker.once("message",accept);worker.once("error",reject);worker.postMessage({id:3,scene:compile(["f(x)=x²","y>=f(x)","y<=1"],"AND"),parameters:{},domain:2});});
  assert.equal(response.id,3);assert.ok(response.drawing.fills[0].points instanceof Float32Array);assert.ok(Math.abs(area(response.drawing.fills[0].points)-4/3)<.015);
});

test("contour stitching keeps dash patterns continuous across unordered short edges",()=>{
  const lines=connectContourSegments([1,0,2,0, 3,0,2,0, 0,0,1,0, 10,0,11,0],.0001);
  assert.equal(lines.length,2);assert.ok(lines.some((line)=>line.length===8));assert.ok(lines.some((line)=>line.length===4));
  const curve=sampleScene(compile(["y>x²"]),{},3).paths[0];assert.equal(curve.dashed,true);
  assert.ok(curve.polylines.some((line)=>line.length>50),"short mesh segments must be joined into a visible dashed curve");
});

test("new selected formulas append to a draft without replacing earlier rows",()=>{
  const rows=document(["y=x²","y=1"]).rows,next=appendSceneRow(rows,{...rows[0],id:"new",expression:"y=sin(x)"});
  assert.equal(next!.length,3);assert.equal(next![0].expression,"y=x²");assert.equal(rows.length,2);
  assert.equal(appendSceneRow(document(Array.from({length:8},()=>"y=x")).rows,{...rows[0],id:"new"}),null);
  const empty=document(["y=x",""]).rows;assert.equal(appendSceneRow(empty,{...rows[0],id:"new"})!.length,2);
});
test("draft recovery accepts bounded editor values and rejects malformed local data",()=>{
  const draft={rows:document(["y>=x²","y<=1"]).rows,combine:"AND",parameters:{a:2},domain:3,camera:{position:[0,0,16],target:[0,0,0],zoom:1},note:"observe"};
  assert.deepEqual(parseSceneDraft(JSON.stringify(draft)),draft);
  for(const invalid of [{...draft,domain:100},{...draft,parameters:{x:2}},{...draft,rows:[...draft.rows,...draft.rows]},{...draft,camera:{...draft.camera,zoom:0}}])assert.equal(parseSceneDraft(JSON.stringify(invalid)),null);
  assert.equal(parseSceneDraft("not-json"),null);
});

test("strict identities never shade a region, including inside OR groups",()=>{
  assert.equal(sampleScene(compile(["y>y"]),{},2).fills[0].points.length,0);
  assert.ok(Math.abs(area(sampleScene(compile(["y>=y"]),{},2).fills[0].points)-16)<.02);
  assert.equal(sampleScene(compile(["y>y","x<=0"],"AND"),{},2).fills[0].points.length,0);
  assert.ok(Math.abs(area(sampleScene(compile(["y>y","x<=0"],"OR"),{},2).fills[0].points)-8)<.02);
});
