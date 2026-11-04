import test from "node:test";
import assert from "node:assert/strict";
import { Worker } from "node:worker_threads";
import { resolve } from "node:path";
import { readFileSync } from "node:fs";
import { PerspectiveCamera, Vector3 } from "three";
import { compileGraphScene, layerContains, SCENE_COLORS, type GraphSceneDocument } from "../src/features/math-canvas/scene.js";
import { sampleScene, connectContourSegments, type SceneDrawing } from "../src/features/math-canvas/scene-geometry.js";
import { appendSceneRow, importSceneFormula, importSceneFormulas, replaceSceneSelection, parseSceneDraft, restoreSceneSpatialDraft } from "../src/features/math-canvas/scene-draft.js";
import { extrudeSceneFill, sceneCurveFocus, sceneSpatialBounds, sceneSpatialCurtains, sceneSpatialFocus, sceneSpatialLines } from "../src/features/math-canvas/scene-spatial.js";
import { sampleSceneCurves3D } from "../src/features/math-canvas/scene-curve-sampling.js";
import { createReferenceGrid } from "../src/features/math-canvas/reference-grid.js";
import { defaultCamera } from "../src/features/math-canvas/expression.js";
import { fitGraphCamera } from "../src/features/math-canvas/fit-camera.js";
import { fitScene2DCamera } from "../src/features/math-canvas/scene-camera.js";
import { equationInkRows, recognizeFormulaRows, splitFormulaRows } from "../src/features/math-canvas/multi-formula.js";
import type { InkStroke } from "../src/lib/api/contracts.js";

const document=(expressions:string[],combine:GraphSceneDocument["combine"]="OVERLAY"):GraphSceneDocument=>({version:2,dimension:"2D",combine,rows:expressions.map((expression,i)=>({id:`row-${i}`,expression,visible:true,color:SCENE_COLORS[i]}))});
const compile=(expressions:string[],combine:GraphSceneDocument["combine"]="OVERLAY")=>compileGraphScene(document(expressions,combine));

function ink(id:string,x:number,y:number,w=.016,h=.012):InkStroke{return {id,tool:"PEN",color:"#000000",width:2,points:[{x,y,pressure:.5},{x:x+w,y:y+h,pressure:.5}]};}

test("multiple formula entry respects mathematical groups and explicit LaTeX row separators",()=>{
  assert.deepEqual(splitFormulaRows("y=x^2\ny=2x+1"),["y=x^2","y=2x+1"]);
  assert.deepEqual(splitFormulaRows("y=x^2; y=sin(x)+cos(x)"),["y=x^2","y=sin(x)+cos(x)"]);
  assert.deepEqual(splitFormulaRows(String.raw`\begin{cases}y&=x^2\\y&=2x+1\end{cases}`),["y=x^2","y=2x+1"]);
  assert.deepEqual(splitFormulaRows(String.raw`\left\{y=x^2\\y=1\right.`),["y=x^2","y=1"]);
  const fraction="y=\\frac{x+\n1}{2}";
  assert.deepEqual(splitFormulaRows(fraction),[fraction]);
  const wrapped="y=x^2+\n2x-3";
  assert.deepEqual(splitFormulaRows(wrapped),[wrapped]);
  assert.deepEqual(splitFormulaRows("y=x&&y=1"),["y=x&&y=1"]);
});

test("a system brace is excluded only from separate OCR rows while the original ink remains intact",()=>{
  const strokes=[ink("brace",.08,.09,.018,.15),ink("first-y",.14,.10),ink("second-y",.14,.20),
    ink("first-equals",.18,.10,.02,.005),ink("first-x",.24,.10),ink("second-equals",.18,.20,.02,.005),ink("second-sin",.24,.20,.1,.015)];
  const original=structuredClone(strokes),result=equationInkRows(strokes);
  assert.deepEqual(result.omittedIds,["brace"]);
  assert.equal(result.regions.length,2);
  assert.deepEqual(result.regions.map((row)=>row.strokes.map((s)=>s.id)),[["first-y","first-equals","first-x"],["second-y","second-equals","second-sin"]]);
  assert.deepEqual(strokes,original);
  const allIds=[...result.regions.flatMap((r)=>r.strokes.map((s)=>s.id)),...result.omittedIds];
  assert.equal(new Set(allIds).size,strokes.length);
});

test("a fraction and superscript remain a single OCR expression instead of being guessed as a system",()=>{
  const fraction=[ink("y",.10,.20,.014,.018),ink("eq",.14,.20,.02,.004),ink("numerator",.21,.18,.045,.015),
    ink("bar",.20,.204,.065,.001),ink("denominator",.21,.22,.045,.015)];
  const split=equationInkRows(fraction);
  assert.equal(split.regions.length,1);assert.deepEqual(split.omittedIds,[]);
  const superscript=[ink("y",.10,.20),ink("eq",.14,.20,.02,.004),ink("x",.20,.20),ink("power",.22,.19,.009,.009),ink("constant",.26,.20)];
  assert.equal(equationInkRows(superscript).regions.length,1);
});

test("the reported tall two-equation layout forms two OCR rows, not eight fragments",()=>{
  const fixture=JSON.parse(readFileSync(resolve("tests/fixtures/math-canvas/tall-two-equation-layout.json"),"utf8")) as {boxes:number[][]};
  const strokes=fixture.boxes.map(([left,top,right,bottom],index)=>ink(`layout-${index}`,left,top,right-left,bottom-top));
  const result=equationInkRows(strokes);
  assert.equal(result.regions.length,2);
  assert.deepEqual(result.omittedIds,["layout-15"]);
  assert.deepEqual(result.regions.map((row)=>row.strokes.map((stroke)=>Number(stroke.id.slice(7)))),[[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14],Array.from({length:23},(_,index)=>index+16)]);
  assert.equal(new Set([...result.regions.flatMap((row)=>row.strokes.map((stroke)=>stroke.id)),...result.omittedIds]).size,strokes.length);
  for(const [sx,sy,tx,ty] of [[.6,.5,.12,.05],[.8,1.4,.1,.08]]){
    const transformed=strokes.map((stroke)=>({...stroke,points:stroke.points.map((point)=>({...point,x:point.x*sx+tx,y:point.y*sy+ty}))}));
    assert.equal(equationInkRows(transformed).regions.length,2,"the same layout at a different writing size must still have two equations");
  }
});

test("tall baseline symbols and detached powers group by equation without forcing two rows",()=>{
  const strokes=Array.from({length:3},(_,row)=>{
    const y=.1+row*.13;
    return [ink(`y-${row}`,.1,y,.03,.065),ink(`eq-${row}`,.16,y+.015,.03,.006),ink(`body-${row}`,.22,y+.012,.08,.033),ink(`power-${row}`,.30,y-.01,.015,.016)];
  }).flat();
  const result=equationInkRows(strokes);
  assert.equal(result.regions.length,3);assert.deepEqual(result.omittedIds,[]);
  assert.deepEqual(result.regions.map((row)=>row.strokes.map((stroke)=>stroke.id)),Array.from({length:3},(_,row)=>[`y-${row}`,`eq-${row}`,`body-${row}`,`power-${row}`]));
  const first=result.regions[0].strokes;
  const single=equationInkRows([ink("tall-left-parenthesis",.06,.07,.012,.13),...first]);
  assert.equal(single.regions.length,1);assert.deepEqual(single.omittedIds,[],"a tall parenthesis on a single formula must remain in its OCR input");
});

test("batch formula import preserves existing rows and updates the same OCR rows on retry",()=>{
  const existing=document(["y=-1"]).rows;
  const first=importSceneFormulas(existing,document(["y=x^2","y=2x+1"]).rows.map((row,i)=>({...row,id:`incoming-${i}`})));
  assert.ok(first);assert.equal(first.rows.length,3);assert.strictEqual(first.rows[0],existing[0]);
  const retry=importSceneFormulas(first.rows,document(["y=x^2+1","y=2x-1"]).rows,first.sourceRowIds);
  assert.ok(retry);assert.equal(retry.rows.length,3);assert.deepEqual(retry.sourceRowIds,first.sourceRowIds);
  assert.deepEqual(retry.rows.slice(1).map((row)=>row.expression),["y=x^2+1","y=2x-1"]);
  assert.deepEqual(first.rows.slice(1).map((row)=>row.expression),["y=x^2","y=2x+1"]);
});

test("batch imports are atomic when the board is full and keep unread OCR rows independently editable",()=>{
  const full=document(Array.from({length:8},(_,i)=>`y=${i}`)).rows;
  full[7]={...full[7],expression:""};const original=structuredClone(full);
  const incoming=document(["y=x^2","y=sin(x)"]).rows.map((row,i)=>({...row,id:`new-${i}`}));
  assert.equal(importSceneFormulas(full,incoming),null);assert.deepEqual(full,original);
  const blanks=importSceneFormulas(document([""]).rows,incoming.map((row)=>({...row,expression:""})));
  assert.ok(blanks);assert.equal(blanks.rows.length,2);assert.equal(blanks.sourceRowIds.length,2);
  assert.notEqual(blanks.rows[0].id,blanks.rows[1].id);
});

test("two independently imported equations render colored paths and locate their intersections",()=>{
  const formulas=splitFormulaRows("y=x^3-3*x^2+2\ny=sin(x)+cos(x)");
  const scene=compile(formulas);assert.deepEqual(scene.errors,{});
  const drawing=sampleScene(scene,{},3);
  assert.equal(drawing.paths.length,2);assert.notEqual(drawing.paths[0].color,drawing.paths[1].color);
  assert.equal(drawing.intersections.length,3);
  for(const [x,y] of drawing.intersections){assert.ok(Math.abs(y-(x**3-3*x*x+2))<.025);assert.ok(Math.abs(y-Math.sin(x)-Math.cos(x))<.002);}
});

test("the OCR sin-squared/cos-squared row plots beside the cubic without a parentheses error",()=>{
  const scene=compile(["y=x^3-3x^2+2",String.raw`y = \sin ^ { 2 } ( x ) + \cos ^ { 2 } ( x )`]);
  assert.deepEqual(scene.errors,{});assert.equal(scene.layers.length,2);
  const drawing=sampleScene(scene,{},3);
  assert.equal(drawing.paths.length,2);assert.equal(drawing.intersections.length,3);
  for(const [,y] of drawing.intersections)assert.ok(Math.abs(y-1)<.002);
});

test("separate OCR rows retain a failed row for correction and stop after a manual edit",async()=>{
  const regions=equationInkRows([ink("a",.1,.1),ink("b",.2,.1),ink("c",.3,.1),ink("d",.1,.2),ink("e",.2,.2),ink("f",.3,.2)]).regions;
  assert.equal(regions.length,2);
  const calls:string[][]=[],progress:number[]=[];
  const result=await recognizeFormulaRows(regions,async(strokes)=>{calls.push(strokes.map((s)=>s.id));if(calls.length===2)throw new Error("unreadable");return {latex:"y=x^2"};},()=>true,(done)=>progress.push(done));
  assert.deepEqual(result,{formulas:["y=x^2",""],failed:[2]});assert.deepEqual(progress,[1,2]);
  assert.deepEqual(calls,[["a","b","c"],["d","e","f"]]);
  let active=true,count=0;
  const canceled=await recognizeFormulaRows(regions,async()=>{count++;active=false;return {latex:"obsolete"};},()=>active,()=>assert.fail("obsolete OCR must not publish progress"));
  assert.equal(canceled,null);assert.equal(count,1);
});

test("two OCR rows that read identically remain separate editable equations",()=>{
  const incoming=document(["y=x^2","y=x^2"]).rows.map((row,index)=>({...row,id:`ocr-${index}`}));
  const imported=importSceneFormulas(document([""]).rows,incoming);
  assert.ok(imported);assert.equal(imported.rows.length,2);assert.equal(imported.sourceRowIds.length,2);
  const corrected=importSceneFormulas(imported.rows,incoming.map((row,index)=>({...row,expression:index?"y=1":"y=x^2"})),imported.sourceRowIds);
  assert.ok(corrected);assert.deepEqual(corrected.rows.map((row)=>row.expression),["y=x^2","y=1"]);
});

test("a new selection replaces every old row and retains exactly the number of selected formulas",()=>{
  let previous=document(Array.from({length:8},(_,i)=>`y=x+${i}`)).rows;
  const old=structuredClone(previous);
  for(const count of [2,1,3,2]){
    const selected=document(Array.from({length:count},()=>"y=sin(x)")).rows;
    const result=replaceSceneSelection(selected);
    assert.ok(result);assert.equal(result.rows.length,count);assert.equal(result.sourceRowIds.length,count);
    assert.notStrictEqual(result.rows[0],selected[0]);previous=result.rows;
  }
  assert.equal(old.length,8);assert.equal(replaceSceneSelection(document(Array(9).fill("y=x")).rows),null);
  assert.equal(replaceSceneSelection([]),null);
});

test("3D scene adapters keep both paths, colors, gaps and intersections on the same mathematical Oxy plane",()=>{
  const drawing=sampleScene(compile(["y=x^3-3*x^2+2","y=sin(x)"]),{},3);
  const original=structuredClone(drawing),spatial=sceneSpatialLines(drawing);
  assert.equal(spatial.length,2);assert.equal(drawing.intersections.length,3);
  for(let p=0;p<spatial.length;p++){
    assert.equal(spatial[p].rowId,drawing.paths[p].rowId);assert.equal(spatial[p].color,drawing.paths[p].color);
    for(let line=0;line<spatial[p].lines.length;line++)for(let i=0;i<spatial[p].lines[line].length;i+=3){
      assert.equal(spatial[p].lines[line][i],drawing.paths[p].polylines[line][i/3*2]);
      assert.equal(spatial[p].lines[line][i+1],drawing.paths[p].polylines[line][i/3*2+1]);
      assert.equal(spatial[p].lines[line][i+2],0);
    }
  }
  const bounds=sceneSpatialBounds(drawing);assert.ok(bounds);assert.equal(bounds.min[2],0);assert.equal(bounds.max[2],0);
  assert.deepEqual(drawing,original);assert.equal(sceneSpatialBounds({paths:[],fills:[],intersections:[]}),null);
});
function area(points:ArrayLike<number>):number{let result=0;for(let i=0;i<points.length;i+=6)result+=Math.abs((points[i+2]-points[i])*(points[i+5]-points[i+1])-(points[i+4]-points[i])*(points[i+3]-points[i+1]))/2;return result;}

test("2D fit centers visible paths and fills with equal coordinate scale in wide and narrow viewports",()=>{
  const scene=compile(["y>=x^2","y<=2*x+1"],"AND"),drawing=sampleScene(scene,{},3),before=structuredClone(drawing);
  for(const aspect of [.65,1,2.5]){
    const camera=fitScene2DCamera(drawing,3,aspect)!;assert.ok(camera);assert.equal(camera.position[2],16);assert.equal(camera.target[2],0);assert.ok(camera.zoom!>=.1&&camera.zoom!<=20);
    const half=3*1.15/camera.zoom!;
    for(const path of [...drawing.paths,...drawing.fills])for(let i=0;i<path.points.length;i+=2){assert.ok(Math.abs((path.points[i]-camera.target[0])/(half*aspect))<=1+1e-8);assert.ok(Math.abs((path.points[i+1]-camera.target[1])/half)<=1+1e-8);}
  }
  assert.deepEqual(drawing,before);
  const offset=sampleScene(compile(["x=2"]),{},3),camera=fitScene2DCamera(offset,3,2)!;assert.ok(Math.abs(camera.target[0]-2)<1e-6);assert.equal(camera.target[1],0);
  assert.equal(fitScene2DCamera({paths:[],fills:[],intersections:[]},3,1),null);assert.equal(fitScene2DCamera(drawing,3,0),null);
});

test("the reference parabola keeps its complete legs in 3D while planar fills and intersections stay unchanged",()=>{
  for(const expression of ["y=1-x^2","1-x^2=y","f(x)=1-x^2"]){
    const scene=compile([expression,"y=0"]),planar=sampleScene(scene,{},3),original=structuredClone(planar),spatial=sampleSceneCurves3D(scene,{},3,planar);
    const curve=spatial.paths[0];assert.equal(curve.color,planar.paths[0].color);assert.equal(curve.rowId,planar.paths[0].rowId);
    assert.equal(curve.polylines.length,1);assert.deepEqual(Array.from(curve.polylines[0].slice(0,2)),[-3,-8]);assert.deepEqual(Array.from(curve.polylines[0].slice(-2)),[3,-8]);
    for(let i=0;i<curve.points.length;i+=2)assert.ok(Math.abs(curve.points[i+1]-(1-curve.points[i]**2))<1e-10);
    assert.deepEqual(sceneSpatialBounds(spatial),{min:[-3,-8,0],max:[3,1,0]});
    assert.deepEqual(spatial.intersections,planar.intersections);assert.deepEqual(spatial.betweenFills,planar.betweenFills);assert.deepEqual(planar,original);
  }
});

test("3D curve framing fits the reference parabola at a readable size without cropping its vertex or legs",()=>{
  const scene=compile(["y=1-x^2"]),drawing=sampleSceneCurves3D(scene,{},3,sampleScene(scene,{},3)),bounds=sceneCurveFocus(drawing)!;
  assert.deepEqual(bounds,{min:[-3,-8,0],max:[3,1,0]});
  for(const aspect of [1,2.1]){
    const fitted=fitGraphCamera(bounds,defaultCamera("3D"),{spatial:true,aspect,halfHeight:4,planarCurve:true})!;
    const camera=new PerspectiveCamera(42,aspect,.1,500);camera.position.fromArray(fitted.position);camera.lookAt(new Vector3(...fitted.target));camera.updateMatrixWorld();
    let low=Infinity,high=-Infinity;
    for(const line of drawing.paths[0].polylines)for(let i=0;i<line.length;i+=2){const p=new Vector3(line[i],line[i+1],0).project(camera);assert.ok(Math.abs(p.x)<=1&&Math.abs(p.y)<=1);low=Math.min(low,p.y);high=Math.max(high,p.y);}
    assert.ok(high-low>1,"curve occupies more than half the viewport height");
    assert.ok(new Vector3(0,0,0).project(camera).y>0,"horizontal floor crosses above the center as in the reference");
  }
});

test("both viewers share a horizontal Oxz floor in 3D and an Oxy grid in 2D",()=>{
  for(const spatial of [true,false]){
    const grid=createReferenceGrid(3,spatial);grid.updateMatrixWorld();const positions=grid.geometry.getAttribute("position");
    for(let i=0;i<positions.count;i++){const p=new Vector3().fromBufferAttribute(positions,i).applyMatrix4(grid.matrixWorld);assert.ok(Math.abs(spatial?p.y:p.z)<1e-8);}
    grid.geometry.dispose();for(const material of Array.isArray(grid.material)?grid.material:[grid.material])material.dispose();
  }
});

test("3D sampling respects pole gaps, guarded functions, hidden definitions and shared coefficients",()=>{
  const scene=compile(["f(x)=a*x^2","y=f(1/x)","x^2+y^2=1"]);scene.layers[0].visible=false;
  const planar=sampleScene(scene,{a:2},3),spatial=sampleSceneCurves3D(scene,{a:2},3,planar);
  assert.equal(spatial.paths.length,2);assert.equal(spatial.paths[0].polylines.length,2);
  for(const line of spatial.paths[0].polylines){const xs=Array.from(line).filter((_,i)=>i%2===0);assert.ok(xs.every((x)=>x<0)||xs.every((x)=>x>0));for(let i=0;i<line.length;i+=2)assert.ok(Math.abs(line[i+1]-2/(line[i]**2))<1e-6);}
  assert.deepEqual(spatial.paths[1],planar.paths[1]);
});

test("legacy flat-view drafts keep equations but initialize the requested curve view with a fresh camera",()=>{
  const old={rows:document(["y=1-x^2","y=sin(x)"]).rows,combine:"OVERLAY" as const,parameters:{},domain:3,camera:{position:[0,0,16] as [number,number,number],target:[0,0,0] as [number,number,number],zoom:1},note:"keep",viewMode:"3D" as const,spatialCamera:{position:[0,0,50] as [number,number,number],target:[0,0,0] as [number,number,number]},spatialDepth:1.5};
  const original=structuredClone(old);assert.deepEqual(restoreSceneSpatialDraft(old),{camera:undefined,depth:0});assert.deepEqual(old,original);
  assert.deepEqual(restoreSceneSpatialDraft({...old,spatialStyle:"CURVE_3D"}),{camera:old.spatialCamera,depth:1.5});
  assert.equal(parseSceneDraft(JSON.stringify({...old,spatialStyle:"unknown"})),null);
});

test("3D focus retains the surveyed region instead of fitting distant cubic tails",()=>{
  const drawing=sampleScene(compile(["y=x^3-3*x^2+2","y=sin(x)"]),{},3);
  const focus=sceneSpatialFocus(drawing,3,1.5)!;
  assert.ok(focus.min[1]>=-3&&focus.max[1]<=3);assert.equal(focus.max[2],1.5);
  for(const [x,y] of drawing.intersections){assert.ok(x>=focus.min[0]&&x<=focus.max[0]&&y>=focus.min[1]&&y<=focus.max[1]);}
  const unclipped:SceneDrawing={paths:[{rowId:"cubic",color:"#112233",dashed:false,points:[-3,-52,3,2],polylines:[[-3,-52,3,2]]}],fills:[],intersections:[]};
  assert.ok(sceneSpatialBounds(unclipped)!.max[1]-sceneSpatialBounds(unclipped)!.min[1]>30);
  assert.deepEqual(sceneSpatialFocus(unclipped,3,1.5),{min:[-3,-3,0],max:[3,2,1.5]});
  const translated=sampleScene(compile(["y=x+20"]),{},3);
  assert.deepEqual(sceneSpatialFocus(translated,3),sceneSpatialBounds(translated));
});

function signedVolume(points:ArrayLike<number>){
  let result=0;for(let i=0;i<points.length;i+=9){const [ax,ay,az,bx,by,bz,cx,cy,cz]=Array.from({length:9},(_,k)=>points[i+k]);result+=(ax*(by*cz-bz*cy)+ay*(bz*cx-bx*cz)+az*(bx*cy-by*cx))/6;}return result;
}

test("closed-region extrusion has outward caps, no internal walls and the expected volume",()=>{
  const rectangle=[0,0,2,0,2,1,0,0,2,1,0,1],solid=extrudeSceneFill(rectangle,3);
  assert.equal(solid.points.length,12*9,"two caps and four walls");
  assert.equal(solid.edges.length,8*6,"only four perimeter edges on each cap");
  assert.ok(Math.abs(signedVolume(solid.points)-6)<1e-9);
  const scene=compile(["y=x^2","y=1"]),drawing=sampleScene(scene,{},2),original=structuredClone(drawing);
  for(const depth of [.2,1.5,10]){
    const mesh=extrudeSceneFill(drawing.betweenFills![0].points,depth);
    assert.ok(Math.abs(signedVolume(mesh.points)-4/3*depth)<.002*depth);
    for(let i=2;i<mesh.points.length;i+=3)assert.ok(mesh.points[i]===0||mesh.points[i]===depth);
    // Every undirected edge must be paired, including walls and cap diagonals.
    const edges=new Map<string,number>(),key=(i:number)=>mesh.points.slice(i,i+3).map((v)=>Math.round(v*1e7)).join(",");
    for(let i=0;i<mesh.points.length;i+=9)for(const [a,b] of [[i,i+3],[i+3,i+6],[i+6,i]]){const edge=[key(a),key(b)].sort().join("|");edges.set(edge,(edges.get(edge)??0)+1);}
    assert.ok([...edges.values()].every((count)=>count===2),"mesh must be closed without duplicate internal walls");
  }
  assert.deepEqual(drawing,original);assert.deepEqual(extrudeSceneFill(rectangle,0),{points:[],edges:[]});
});

test("surface extension clips tails to the domain and never bridges separate polylines",()=>{
  const drawing:SceneDrawing={paths:[{rowId:"gap",color:"#112233",dashed:false,points:[],polylines:[[-2,0,-1,0],[1,0,2,0]]}],fills:[],intersections:[]};
  const surfaces=sceneSpatialCurtains(drawing,3,2);
  assert.equal(surfaces.length,1);assert.equal(surfaces[0].color,"#112233");assert.equal(surfaces[0].points.length,36);
  for(let i=0;i<surfaces[0].points.length;i+=9){const xs=[0,3,6].map((k)=>surfaces[0].points[i+k]);assert.ok(xs.every((x)=>x<=-1)||xs.every((x)=>x>=1));}
  const steep=sceneSpatialCurtains(sampleScene(compile(["y=100*x"]),{},3),3,2);
  assert.ok(steep[0].points.length);for(let i=0;i<steep[0].points.length;i+=3){assert.ok(Math.abs(steep[0].points[i])<=3+1e-8&&Math.abs(steep[0].points[i+1])<=3+1e-8);}
  assert.deepEqual(sceneSpatialCurtains(drawing,3,Infinity),[]);
});

test("multi-equation surface mode extends each full-height curve separately with its original color and equation",()=>{
  const scene=compile(["y=x^3+2","y=sin(x)"]),planar=sampleScene(scene,{},3),drawing=sampleSceneCurves3D(scene,{},3,planar),before=structuredClone(drawing);
  for(const depth of [.2,3,10]){
    const surfaces=sceneSpatialCurtains(drawing,3,depth,false);assert.equal(surfaces.length,2);assert.deepEqual(surfaces.map((surface)=>surface.color),drawing.paths.map((path)=>path.color));
    assert.ok(surfaces[0].points.some((v,i)=>i%3===1&&Math.abs(v)>3),"surface must retain the cubic height outside the survey square");
    for(let row=0;row<surfaces.length;row++)for(let i=0;i<surfaces[row].points.length;i+=3){const [x,y,z]=surfaces[row].points.slice(i,i+3);assert.ok(Math.abs(y-(row?Math.sin(x):x**3+2))<1e-8);assert.ok(z===0||z===depth);}
  }
  assert.deepEqual(drawing,before);assert.deepEqual(drawing.intersections,planar.intersections);
  const closed=compile(["y=x^2","y=1"]),closedDrawing=sampleSceneCurves3D(closed,{},3,sampleScene(closed,{},3));
  assert.ok(closedDrawing.betweenFills!.length);assert.equal(sceneSpatialCurtains(closedDrawing,3,3,false).length,2,"two surfaces remain distinct even when the original curves enclose a filled region");
});

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

test("bounded interiors between two curves have the expected area and do not change the equations",()=>{
  for(const expressions of [["y=x^2","y=1"],["x^2=y","1=y"]]){
    const scene=compile(expressions),original=structuredClone(scene.document),drawing=sampleScene(scene,{},2);
    assert.equal(drawing.betweenFills?.length,1);
    const fill=drawing.betweenFills![0];assert.ok(Math.abs(area(fill.points)-4/3)<.002);
    for(let i=0;i<fill.points.length;i+=2){const x=fill.points[i],y=fill.points[i+1];assert.ok(x>=-1.0001&&x<=1.0001);assert.ok(y>=x*x-1e-5&&y<=1.0001);}
    assert.deepEqual(scene.document,original);
  }
  const shifted=sampleScene(compile(["y=a*x^2","y=b"]),{a:2,b:2},3);
  assert.ok(Math.abs(area(shifted.betweenFills![0].points)-8/3)<.003);
});

test("colored interiors follow closed lobes while poles, coincident curves and extra rows do not create a fake solid",()=>{
  const sinusoid=sampleScene(compile(["y=sin(x)","y=0"]),{},4);
  assert.equal(sinusoid.betweenFills?.length,2);assert.ok(Math.abs(sinusoid.betweenFills!.reduce((sum,fill)=>sum+area(fill.points),0)-4)<.003);
  assert.notEqual(sinusoid.betweenFills![0].color,sinusoid.betweenFills![1].color);
  assert.equal(sampleScene(compile(["y=1/x","y=x"]),{},2).betweenFills?.length,0);
  assert.equal(sampleScene(compile(["y=x","y=x"]),{},2).betweenFills?.length,0);
  assert.equal(sampleScene(compile(["y=x","y=x+1"]),{},2).betweenFills?.length,0);
  assert.equal(sampleScene(compile(["x^2+y^2=1","y=0"]),{},2).betweenFills,null);
  assert.equal(sampleScene(compile(["y=x^2","y=1","y=0"]),{},2).betweenFills,null);
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
  const interior=await new Promise<{id:number;drawing:SceneDrawing}>((accept,reject)=>{worker.once("message",accept);worker.once("error",reject);worker.postMessage({id:4,scene:compile(["y=x^2","y=1"]),parameters:{},domain:2});});
  assert.ok(interior.drawing.betweenFills![0].points instanceof Float32Array);assert.ok(Math.abs(area(interior.drawing.betweenFills![0].points)-4/3)<.002);
  const spatial=await new Promise<{id:number;drawing:SceneDrawing}>((accept,reject)=>{worker.once("message",accept);worker.once("error",reject);worker.postMessage({id:5,scene:compile(["y=1-x^2","y=0"]),parameters:{},domain:3,spatialCurves:true});});
  assert.equal(spatial.id,5);assert.ok(spatial.drawing.paths[0].polylines[0] instanceof Float32Array);
  assert.deepEqual(Array.from(spatial.drawing.paths[0].polylines[0].slice(0,2)),[-3,-8]);
  assert.equal(spatial.drawing.intersections.length,2);assert.ok(spatial.drawing.betweenFills![0].points instanceof Float32Array);
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

test("reopening recognized LaTeX reuses the same row and retrying OCR corrects it in place",()=>{
  const rows=document([String.raw`y = t ^ { 2 } - 1`,"y=x"]).rows;
  const reopened=importSceneFormula(rows,{...rows[0],id:"new",expression:"y=t²-1"})!;
  assert.equal(reopened.rows.length,2);assert.equal(reopened.sourceRowId,rows[0].id);
  const retried=importSceneFormula(reopened.rows,{...rows[0],id:"retry",expression:"y=x^2-1"},reopened.sourceRowId)!;
  assert.equal(retried.rows.length,2);assert.equal(retried.rows[0].id,rows[0].id);
  assert.equal(retried.rows[0].expression,"y=x^2-1");assert.deepEqual(retried.rows[1],rows[1]);
  assert.equal(rows[0].expression,String.raw`y = t ^ { 2 } - 1`,"the existing draft is not mutated");
  const full=document(Array.from({length:8},(_,i)=>`y=x+${i}`)).rows;
  assert.equal(importSceneFormula(full,{...full[0],id:"retry",expression:"y=x²-1"},full[0].id)!.rows.length,8);
  assert.equal(importSceneFormula(full,{...full[0],id:"new",expression:"y=sin(x)"}),null);
});

test("parameter-only y formulas explain the horizontal line without silently changing OCR",()=>{
  const scene=compile([String.raw`y = t ^ { 2 } - 1`]);
  assert.deepEqual(scene.errors,{});assert.deepEqual(scene.parameters,["t"]);
  assert.equal(scene.layers[0].label,"Đường thẳng ngang");assert.match(scene.layers[0].hint!,/t là tham số/);
  for(const x of [-2,0,2])assert.equal(layerContains(scene.layers[0],x,0,{t:1}),true);
  assert.equal(layerContains(scene.layers[0],2,3,{t:1}),false);
  const parabola=compile(["y=x²-1"]);
  assert.equal(parabola.layers[0].hint,undefined);assert.deepEqual(parabola.parameters,[]);
  assert.equal(layerContains(parabola.layers[0],2,3,{}),true);
  assert.equal(compile(["y=x+t"]).layers[0].hint,undefined);
  assert.equal(compile(["y²=t"]).layers[0].hint,undefined);
  assert.equal(compile(["y=y+t"]).layers[0].hint,undefined);
});
test("draft recovery accepts bounded editor values and rejects malformed local data",()=>{
  const draft={rows:document(["y>=x²","y<=1"]).rows,combine:"AND",parameters:{a:2},domain:3,camera:{position:[0,0,16],target:[0,0,0],zoom:1},note:"observe"};
  assert.deepEqual(parseSceneDraft(JSON.stringify(draft)),draft);
  for(const invalid of [{...draft,domain:100},{...draft,parameters:{x:2}},{...draft,rows:[...draft.rows,...draft.rows]},{...draft,camera:{...draft.camera,zoom:0}}])assert.equal(parseSceneDraft(JSON.stringify(invalid)),null);
  assert.equal(parseSceneDraft("not-json"),null);
  const spatial={...draft,viewMode:"3D",spatialCamera:{position:[4,2,14],target:[0,0,0],zoom:1},spatialDepth:1.5};
  assert.deepEqual(parseSceneDraft(JSON.stringify(spatial)),spatial);
  const surfaces={...spatial,spatialSurface:true};assert.deepEqual(parseSceneDraft(JSON.stringify(surfaces)),surfaces);
  for(const patch of [{spatialSurface:"true"},{spatialSurface:true,spatialDepth:0},{spatialSurface:true,spatialDepth:undefined}])assert.equal(parseSceneDraft(JSON.stringify({...spatial,...patch})),null);
  for(const invalid of [{...spatial,viewMode:"4D"},{...spatial,spatialCamera:{...spatial.spatialCamera,zoom:0}},{...spatial,spatialCamera:{position:[0,0,0],target:[0,0,0],zoom:1}}])assert.equal(parseSceneDraft(JSON.stringify(invalid)),null);
  for(const depth of [-1,11,"1.5",null])assert.equal(parseSceneDraft(JSON.stringify({...spatial,spatialDepth:depth})),null);
});

test("strict identities never shade a region, including inside OR groups",()=>{
  assert.equal(sampleScene(compile(["y>y"]),{},2).fills[0].points.length,0);
  assert.ok(Math.abs(area(sampleScene(compile(["y>=y"]),{},2).fills[0].points)-16)<.02);
  assert.equal(sampleScene(compile(["y>y","x<=0"],"AND"),{},2).fills[0].points.length,0);
  assert.ok(Math.abs(area(sampleScene(compile(["y>y","x<=0"],"OR"),{},2).fills[0].points)-8)<.02);
});
