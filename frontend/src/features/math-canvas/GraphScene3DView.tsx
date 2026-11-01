"use client";
import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { defaultCamera, type GraphCamera } from "./expression";
import type { CompiledScene } from "./scene";
import { fitGraphCamera, type GraphBounds } from "./fit-camera";
import { fitCameraPreset, type GraphCameraPreset } from "./camera-presets";
import { extrudeSceneFill, sceneCurveFocus, sceneSpatialBounds, sceneSpatialCurtains, sceneSpatialFocus, sceneSpatialLines } from "./scene-spatial";
import { createReferenceGrid } from "./reference-grid";
import { useSceneDrawing } from "./useSceneDrawing";
import { SceneIntersectionList } from "./SceneIntersectionList";
import { ScenePlotToolbar } from "./ScenePlotToolbar";
import styles from "./MathCanvas.module.css";

interface Props {scene:CompiledScene;parameters:Record<string,number>;domain:number;initialCamera?:GraphCamera;onCameraChange?:(camera:GraphCamera)=>void;depth?:number;surfaceMode?:boolean;onDepthChange?:(depth:number)=>void}
interface State {scene:THREE.Scene;camera:THREE.PerspectiveCamera;controls:OrbitControls;render:()=>void;publish:()=>void}
function dispose(group:THREE.Object3D){group.traverse((object)=>{if(object instanceof THREE.Mesh||object instanceof THREE.Line||object instanceof THREE.Sprite){if("geometry" in object)object.geometry.dispose();for(const material of Array.isArray(object.material)?object.material:[object.material]){if("map" in material&&material.map instanceof THREE.Texture)material.map.dispose();material.dispose();}}});}
function textLabel(text:string,point:THREE.Vector3,color:string,size:number){
  const canvas=document.createElement("canvas");canvas.width=192;canvas.height=64;const context=canvas.getContext("2d")!;
  context.font="600 32px system-ui";context.textAlign="center";context.textBaseline="middle";context.fillStyle=color;context.fillText(text,96,32);
  const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(canvas),depthTest:false}));sprite.position.copy(point);sprite.scale.set(size*3,size,1);return sprite;
}
export function GraphScene3DView({scene,parameters,domain,initialCamera,onCameraChange,depth=0,surfaceMode=false,onDepthChange}:Props){
  const host=useRef<HTMLDivElement>(null),state=useRef<State|null>(null),bounds=useRef<GraphBounds|null>(null),fullBounds=useRef<GraphBounds|null>(null);
  const modelDepth=useRef(depth);modelDepth.current=depth;
  const initial=useRef(initialCamera),callback=useRef(onCameraChange);callback.current=onCameraChange;
  const sampling=useSceneDrawing(scene,parameters,domain,depth===0||surfaceMode),[graphicsError,setGraphicsError]=useState<string|null>(null);
  const [axes,setAxes]=useState(true),[grid,setGrid]=useState(true),[dragMode,setDragMode]=useState<"rotate"|"pan">("rotate"),[autoFit,setAutoFit]=useState(!initialCamera);
  const [expanded,setExpanded]=useState(false),[fillBetween,setFillBetween]=useState(true),[fillOpacity,setFillOpacity]=useState(.35);
  const [preset,setPreset]=useState<GraphCameraPreset|null>(initialCamera?null:"PERSPECTIVE");
  const previousExpanded=useRef(expanded);
  const auto=useRef(autoFit);auto.current=autoFit;
  const apply=(saved:GraphCamera)=>{const current=state.current;if(!current)return;current.camera.position.fromArray(saved.position);current.camera.zoom=saved.zoom??1;current.controls.target.fromArray(saved.target);current.camera.updateProjectionMatrix();current.controls.update();current.publish();};
  const fit=(preset?:GraphCameraPreset,full=false)=>{
    const current=state.current,element=host.current;if(!current||!element||!bounds.current||!element.clientHeight)return;
    const frame=full?fullBounds.current??bounds.current:bounds.current;
    const aspect=element.clientWidth/element.clientHeight;
    const saved=preset?fitCameraPreset(preset,frame,"2D",aspect):fitGraphCamera(frame,{position:current.camera.position.toArray() as GraphCamera["position"],target:current.controls.target.toArray() as GraphCamera["target"]},{spatial:true,aspect,halfHeight:4,planarCurve:modelDepth.current===0});
    if(saved){if(preset)setPreset(preset);apply(saved);}
  };
  useEffect(()=>{
    const changed=previousExpanded.current!==expanded;previousExpanded.current=expanded;
    const frame=changed?requestAnimationFrame(()=>fit()):undefined;
    if(!expanded)return()=>{if(frame!==undefined)cancelAnimationFrame(frame);};
    const escape=(event:KeyboardEvent)=>{if(event.key==="Escape"){event.preventDefault();event.stopPropagation();setExpanded(false);}};
    window.addEventListener("keydown",escape,true);
    return()=>{if(frame!==undefined)cancelAnimationFrame(frame);window.removeEventListener("keydown",escape,true);};
  },[expanded]);
  useEffect(()=>{
    const element=host.current;if(!element)return;
    let renderer:THREE.WebGLRenderer;
    try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});}catch{setGraphicsError("Chưa mở được WebGL. Em có thể chuyển về 2D để xem các phương trình.");return;}
    renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2));renderer.setClearColor(0x0b1627,0);
    renderer.domElement.tabIndex=0;renderer.domElement.setAttribute("role","img");element.appendChild(renderer.domElement);
    const world=new THREE.Scene(),camera=new THREE.PerspectiveCamera(42,1,.1,500),controls=new OrbitControls(camera,renderer.domElement);
    controls.minDistance=1;controls.maxDistance=120;controls.screenSpacePanning=true;controls.listenToKeyEvents(renderer.domElement);
    const saved=initial.current??defaultCamera("3D");
    camera.position.fromArray(saved.position);camera.zoom=saved.zoom??1;controls.target.fromArray(saved.target);camera.updateProjectionMatrix();controls.update();
    const render=()=>renderer.render(world,camera),publish=()=>{render();callback.current?.({position:camera.position.toArray() as GraphCamera["position"],target:controls.target.toArray() as GraphCamera["target"],zoom:camera.zoom});};
    const manual=()=>{auto.current=false;setAutoFit(false);setPreset(null);};controls.addEventListener("change",publish);controls.addEventListener("start",manual);
    const keyboard=(event:KeyboardEvent)=>{if(["+","="].includes(event.key)){event.preventDefault();zoom(1.25);}else if(event.key==="-"){event.preventDefault();zoom(.8);}else if(event.key.toLowerCase()==="f"){event.preventDefault();fit();}else if(event.key.toLowerCase()==="r"){event.preventDefault();reset();}else if(event.key.startsWith("Arrow"))manual();};
    renderer.domElement.addEventListener("keydown",keyboard);
    const lost=(event:Event)=>{event.preventDefault();setGraphicsError("Kết nối đồ họa bị ngắt. Chuyển sang 2D rồi mở lại 3D để khôi phục.");};renderer.domElement.addEventListener("webglcontextlost",lost);
    world.add(new THREE.HemisphereLight(0xddeeff,0x31405a,2));
    const light=new THREE.DirectionalLight(0xffffff,2.5);light.position.set(4,8,10);world.add(light);
    const rim=new THREE.DirectionalLight(0x82b7ff,1.2);rim.position.set(-7,1,-4);world.add(rim);
    state.current={scene:world,camera,controls,render,publish};
    const resize=new ResizeObserver(()=>{const width=element.clientWidth,height=element.clientHeight;if(!width||!height)return;renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix();if(auto.current&&bounds.current)fit();else render();});resize.observe(element);publish();
    return()=>{resize.disconnect();controls.removeEventListener("change",publish);controls.removeEventListener("start",manual);controls.dispose();renderer.domElement.removeEventListener("webglcontextlost",lost);renderer.domElement.removeEventListener("keydown",keyboard);dispose(world);renderer.dispose();renderer.domElement.remove();state.current=null;bounds.current=null;fullBounds.current=null;};
  },[]);
  useEffect(()=>{host.current?.querySelector("canvas")?.setAttribute("aria-label",surfaceMode?`Các bề mặt kéo dài theo z từ 0 đến ${depth}, mỗi công thức một màu. Kéo để xoay.`:depth>0?`Mô hình mặt hoặc khối tạo từ các phương trình, kéo theo trục z từ 0 đến ${depth}. Kéo để xoay.`:"Các phương trình x, y trên mặt phẳng Oxy trong không gian 3D. Kéo để xoay.");},[depth,surfaceMode]);
  useEffect(()=>{const current=state.current;if(!current)return;current.controls.mouseButtons.LEFT=dragMode==="rotate"?THREE.MOUSE.ROTATE:THREE.MOUSE.PAN;current.controls.touches.ONE=dragMode==="rotate"?THREE.TOUCH.ROTATE:THREE.TOUCH.PAN;},[dragMode]);
  useEffect(()=>{
    const current=state.current;if(!current)return;const group=new THREE.Group();
    if(grid){const lattice=createReferenceGrid(domain,true);group.add(lattice);
      if(depth>0&&!surfaceMode){const points:number[]=[];for(let i=0;i<=10;i++){const x=-domain+domain*2*i/10,z=depth*i/10;points.push(x,-domain,0,x,-domain,depth,-domain,-domain,z,domain,-domain,z);}group.add(new THREE.LineSegments(new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(points,3)),new THREE.LineBasicMaterial({color:0x38546d})));}}
    if(axes){for(let axis=0;axis<3;axis++){const direction=new THREE.Vector3().setComponent(axis,domain*1.12),color=["#fb7185","#6ee7b7","#7dbbff"][axis];group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([direction.clone().negate(),direction]),new THREE.LineBasicMaterial({color})));group.add(textLabel(["x","y","z"][axis],direction.clone().multiplyScalar(1.08),color,domain*.12));for(const tick of [-domain,-domain/2,domain/2,domain]){const point=new THREE.Vector3().setComponent(axis,tick);point.setComponent((axis+1)%3,-domain*.055);group.add(textLabel(Number(tick.toFixed(1)).toString(),point,"#a7bacf",domain*.085));}}group.add(textLabel("O",new THREE.Vector3(-domain*.07,-domain*.07,0),"#a7bacf",domain*.1));}
    current.scene.add(group);current.render();return()=>{current.scene.remove(group);dispose(group);};
  },[domain,axes,grid,depth,surfaceMode]);
  useEffect(()=>{
    const current=state.current,drawing=sampling.drawing;if(!current||!drawing)return;
    const group=new THREE.Group();
    for(const path of sceneSpatialLines(drawing))for(const points of path.lines){if(points.length<6)continue;const material=path.dashed?new THREE.LineDashedMaterial({color:path.color,dashSize:domain*.045,gapSize:domain*.035}):new THREE.LineBasicMaterial({color:path.color});const line=new THREE.Line(new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(points,3)),material);line.computeLineDistances();group.add(line);}
    const regions=[...drawing.fills,...(depth>0&&!surfaceMode||fillBetween?drawing.betweenFills??[]:[])].filter((fill)=>fill.points.length);
    for(const fill of regions){
      if(depth>0&&!surfaceMode){
        const solid=extrudeSceneFill(fill.points,depth),geometry=new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(solid.points,3));geometry.computeVertexNormals();
        group.add(new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:fill.color,roughness:.42,metalness:.08,side:THREE.DoubleSide})));
        group.add(new THREE.LineSegments(new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(solid.edges,3)),new THREE.LineBasicMaterial({color:fill.color})));
      }else{const points:number[]=[];for(let i=0;i<fill.points.length;i+=2)points.push(fill.points[i],fill.points[i+1],-.006);group.add(new THREE.Mesh(new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(points,3)),new THREE.MeshBasicMaterial({color:fill.color,transparent:true,opacity:drawing.fills.includes(fill)?.18:fillOpacity,side:THREE.DoubleSide,depthWrite:false})));}
    }
    const surfaceIds=new Set(scene.layers.filter((layer)=>layer.visible&&layer.relations.length===1&&layer.relations[0].operator==="=").map((layer)=>layer.id));
    const surfaceDrawing=surfaceMode?{...drawing,paths:drawing.paths.filter((path)=>surfaceIds.has(path.rowId))}:drawing;
    if(depth>0&&(surfaceMode||!regions.length))for(const surface of sceneSpatialCurtains(surfaceDrawing,domain,depth,!surfaceMode)){
      const geometry=new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(surface.points,3));geometry.computeVertexNormals();
      group.add(new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:surface.color,roughness:.5,side:THREE.DoubleSide})));
      group.add(new THREE.LineSegments(new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(surface.edges,3)),new THREE.LineBasicMaterial({color:surface.color})));
    }
    drawing.intersections.forEach(([x,y],index)=>{const dot=new THREE.Mesh(new THREE.SphereGeometry(domain*.018,12,8),new THREE.MeshBasicMaterial({color:0xffffff}));dot.position.set(x,y,0);group.add(dot);if(index<12)group.add(textLabel(`P${index+1}`,new THREE.Vector3(x+domain*.08,y+domain*.08,.025),"#ffffff",domain*.075));});
    if(surfaceMode)for(const [x,y] of drawing.intersections)group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(x,y,0),new THREE.Vector3(x,y,depth)]),new THREE.LineBasicMaterial({color:0xffffff,transparent:true,opacity:.75,depthTest:false})));
    const curveFocus=sceneCurveFocus(drawing);
    bounds.current=surfaceMode&&curveFocus?{min:curveFocus.min,max:[curveFocus.max[0],curveFocus.max[1],depth]}:depth>0?sceneSpatialFocus(drawing,domain,depth):curveFocus;fullBounds.current=sceneSpatialBounds(drawing,depth);current.scene.add(group);if(auto.current)fit();current.render();
    return()=>{current.scene.remove(group);dispose(group);bounds.current=null;fullBounds.current=null;};
  },[sampling.drawing,domain,fillBetween,fillOpacity,depth,surfaceMode,scene]);
  const zoom=(factor:number)=>{const current=state.current;if(!current)return;auto.current=false;setAutoFit(false);const offset=current.camera.position.clone().sub(current.controls.target);offset.setLength(THREE.MathUtils.clamp(offset.length()/factor,1,120));current.camera.position.copy(current.controls.target).add(offset);current.controls.update();current.publish();};
  const reset=()=>{auto.current=!initial.current;setAutoFit(!initial.current);if(initial.current){setPreset(null);apply(initial.current);}else fit("PERSPECTIVE");};
  const error=graphicsError??sampling.error;
  const unavailable=!!graphicsError||!sampling.drawing||!sampling.drawing.paths.some((path)=>path.points.length)&&!sampling.drawing.fills.some((fill)=>fill.points.length);
  return <div className={styles.sceneSpatialView} style={expanded?{position:"fixed",inset:12,zIndex:120,background:"#fff",padding:18,borderRadius:18,overflow:"auto",boxShadow:"0 20px 80px #102e3a66"}:undefined}>
    {surfaceMode?<p className={styles.surfaceViewHint}>Mỗi đường tạo một bề mặt cùng màu · 0 ≤ z ≤ {depth.toFixed(1)}. Chỉnh độ kéo dài ở cột Điều chỉnh.</p>:depth>0?<div className={styles.explorationCard} style={{marginTop:0,marginBottom:12}}><p className={styles.muted}>Bản lưu mô hình kéo theo z · chiều sâu {depth.toFixed(1)}.</p>{onDepthChange?<button type="button" className={styles.button} onClick={()=>{auto.current=true;setAutoFit(true);onDepthChange(0);fit("PERSPECTIVE");}}>Về đồ thị đường cong 3D</button>:null}</div>:null}
    <ScenePlotToolbar dimension="3D" disabled={unavailable} onZoom={zoom} onFit={()=>fit()} onReset={reset} expanded={expanded} onExpand={()=>setExpanded(!expanded)} dragMode={dragMode} onDragMode={setDragMode} preset={preset} onPreset={(next)=>{auto.current=true;setAutoFit(true);fit(next);}}>
      <label><input type="checkbox" checked={axes} onChange={(event)=>setAxes(event.target.checked)}/> Trục tọa độ</label>
      <label><input type="checkbox" checked={grid} onChange={(event)=>setGrid(event.target.checked)}/> Lưới ngang</label>
      <label><input type="checkbox" checked={autoFit} onChange={(event)=>{auto.current=event.target.checked;setAutoFit(event.target.checked);if(event.target.checked)fit();}}/> Tự căn khi đổi công thức</label>
      {!!sampling.drawing?.betweenFills?.length?<label><input type="checkbox" checked={depth>0&&!surfaceMode||fillBetween} disabled={depth>0&&!surfaceMode} onChange={(event)=>setFillBetween(event.target.checked)}/> Tô miền giữa hai đường</label>:null}
      {(depth===0||surfaceMode)&&fillBetween&&!!sampling.drawing?.betweenFills?.length?<label>Độ đậm màu<input type="range" aria-label="Độ đậm màu miền giữa hai đường" min={.1} max={.65} step={.05} value={fillOpacity} onChange={(event)=>setFillOpacity(Number(event.target.value))}/><span>{Math.round(fillOpacity*100)}%</span></label>:null}
      <button type="button" className={styles.plotTextButton} disabled={unavailable} onClick={()=>fit(undefined,true)}>Xem toàn bộ đường cong</button>
    </ScenePlotToolbar>
    <div className={`${styles.graphFrame} ${styles.studioFrame} ${styles.sceneSpatialFrame}`} style={{marginTop:0,flexShrink:0}}>
      <div ref={host} className={`${styles.graph} ${styles.sceneSpatialGraph}`} style={{height:expanded?"calc(100dvh - 150px)":"clamp(360px, calc(100dvh - 320px), 720px)",minHeight:360,width:"100%",touchAction:"none"}}/>
      <span className={styles.viewportBadge}><span/>{surfaceMode?"Bề mặt kéo dài":depth>0?"Mô hình 3D":"Không gian 3D"}</span><span className={styles.graphLegend}>x · đỏ &nbsp; y · xanh lá &nbsp; z · xanh dương</span>
      {sampling.pending?<span className={styles.graphPending}>Đang cập nhật đồ thị…</span>:null}
      {error?<div className={styles.graphError} role="alert"><p>{error}</p>{!graphicsError?<button type="button" className={styles.button} onClick={sampling.retry}>Thử lại</button>:null}</div>:null}
      {!sampling.pending&&!error&&unavailable?<div className={styles.plotEmptyState}><strong>{scene.layers.some((layer)=>layer.visible)?"Chưa có hình trong miền này":"Bắt đầu từ một công thức"}</strong><span>{scene.layers.some((layer)=>layer.visible)?"Thử đổi miền khảo sát hoặc kiểm tra công thức.":"Nhập ở cột bên trái hoặc chọn một ví dụ."}</span></div>:null}
    </div>
    <div className={styles.plotHint}><span>Kéo để {dragMode==="rotate"?"xoay":"di chuyển"} · Cuộn để zoom</span><span>Phím F: vừa hình · + / −: zoom</span></div>
    <SceneIntersectionList scene={scene} drawing={sampling.drawing} ready={!sampling.pending&&!error} onFocus={([x,y])=>{const current=state.current;if(!current)return;auto.current=false;setAutoFit(false);setPreset(null);const offset=current.camera.position.clone().sub(current.controls.target);current.controls.target.set(x,y,0);current.camera.position.copy(current.controls.target).add(offset);current.controls.update();current.publish();}}/>
  </div>;
}
