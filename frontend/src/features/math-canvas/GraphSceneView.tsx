"use client";
import { useEffect, useRef, useState } from "react";
import type { GraphCamera } from "./expression";
import type { CompiledScene } from "./scene";
import { useSceneDrawing } from "./useSceneDrawing";
import { SceneIntersectionList } from "./SceneIntersectionList";
import { ScenePlotToolbar } from "./ScenePlotToolbar";
import { fitScene2DCamera } from "./scene-camera";
import styles from "./MathCanvas.module.css";

interface Props { scene: CompiledScene; parameters: Record<string, number>; domain: number; initialCamera?: GraphCamera; onCameraChange?: (camera: GraphCamera) => void }
const clamp = (value: number, min: number, max: number) => Math.max(min,Math.min(max,value));
export function GraphSceneView({ scene, parameters, domain, initialCamera, onCameraChange }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null), host = useRef<HTMLDivElement>(null);
  const [camera,setCamera] = useState<GraphCamera>(() => initialCamera ?? {position:[0,0,16],target:[0,0,0],zoom:1});
  const current = useRef(camera); current.current = camera;
  const callback = useRef(onCameraChange); callback.current = onCameraChange;
  const sampling=useSceneDrawing(scene,parameters,domain),{drawing,pending}=sampling;
  const [graphicsError,setError]=useState<string|null>(null),error=graphicsError??sampling.error;
  const [grid,setGrid] = useState(true), [axes,setAxes] = useState(true), [size,setSize] = useState({width:0,height:0});
  const [fillBetween,setFillBetween]=useState(true);
  const [expanded,setExpanded]=useState(false);
  const domainRef = useRef(domain); domainRef.current = domain;
  const drag = useRef<{x:number;y:number;camera:GraphCamera} | null>(null);
  const pointers = useRef(new Map<number,{x:number;y:number}>());
  const pinch = useRef<{distance:number;camera:GraphCamera} | null>(null);
  const updateCamera = (next: GraphCamera) => { current.current=next;setCamera(next);callback.current?.(next); };
  useEffect(() => { callback.current?.(current.current); }, []);
  useEffect(()=>{if(!expanded)return;const escape=(event:KeyboardEvent)=>{if(event.key==="Escape"){event.preventDefault();event.stopPropagation();setExpanded(false);}};window.addEventListener("keydown",escape,true);return()=>window.removeEventListener("keydown",escape,true);},[expanded]);
  useEffect(()=>{
    const element=host.current;if(!element)return;
    const observer=new ResizeObserver(()=>setSize({width:element.clientWidth,height:element.clientHeight}));observer.observe(element);return()=>observer.disconnect();
  },[]);
  useEffect(()=>{
    const element=canvas.current;if(!element||!size.width||!size.height)return;
    const context=element.getContext("2d");if(!context){setError("Thiết bị chưa mở được khung vẽ.");return;}
    const ratio=Math.min(window.devicePixelRatio||1,2), w=size.width,h=size.height;
    element.width=w*ratio;element.height=h*ratio;context.setTransform(ratio,0,0,ratio,0,0);
    context.fillStyle="#f8fafc";context.fillRect(0,0,w,h);
    const half=domain*1.15/(camera.zoom??1), scale=h/(2*half),cx=camera.target[0],cy=camera.target[1];
    const px=(x:number)=>w/2+(x-cx)*scale,py=(y:number)=>h/2-(y-cy)*scale;
    const rawStep=2*half/8,power=10**Math.floor(Math.log10(rawStep)),fraction=rawStep/power,step=(fraction<2?1:fraction<5?2:5)*power;
    const minX=cx-w/2/scale,maxX=cx+w/2/scale,minY=cy-half,maxY=cy+half;
    if(grid){context.strokeStyle="#e2e8f0";context.lineWidth=1;context.beginPath();
      for(let x=Math.ceil(minX/step)*step;x<=maxX;x+=step){context.moveTo(px(x),0);context.lineTo(px(x),h);}
      for(let y=Math.ceil(minY/step)*step;y<=maxY;y+=step){context.moveTo(0,py(y));context.lineTo(w,py(y));}context.stroke();}
    if(drawing){
      for(const fill of [...drawing.fills,...(fillBetween?drawing.betweenFills??[]:[])]){context.fillStyle=fill.color;context.globalAlpha=.23;context.beginPath();for(let i=0;i<fill.points.length;i+=6){context.moveTo(px(fill.points[i]),py(fill.points[i+1]));context.lineTo(px(fill.points[i+2]),py(fill.points[i+3]));context.lineTo(px(fill.points[i+4]),py(fill.points[i+5]));context.closePath();}context.fill();}context.globalAlpha=1;
    }
    if(axes){context.strokeStyle="#64748b";context.lineWidth=1.3;context.beginPath();context.moveTo(px(0),0);context.lineTo(px(0),h);context.moveTo(0,py(0));context.lineTo(w,py(0));context.stroke();
      context.font="11px system-ui";context.fillStyle="#475569";context.textAlign="center";
      for(let x=Math.ceil(minX/step)*step;x<=maxX;x+=step)if(Math.abs(x)>step*.01)context.fillText(Number(x.toFixed(3)).toString(),px(x),clamp(py(0)+15,15,h-5));
      context.textAlign="left";for(let y=Math.ceil(minY/step)*step;y<=maxY;y+=step)if(Math.abs(y)>step*.01)context.fillText(Number(y.toFixed(3)).toString(),clamp(px(0)+6,5,w-35),py(y)-4);
      context.font="600 13px system-ui";context.fillText("x",w-15,clamp(py(0)-8,15,h-5));context.fillText("y",clamp(px(0)+8,5,w-15),17);
    }
    if(drawing){context.lineWidth=2;
      for(const path of drawing.paths){context.strokeStyle=path.color;context.setLineDash(path.dashed?[6,5]:[]);context.beginPath();for(const line of path.polylines){context.moveTo(px(line[0]),py(line[1]));for(let i=2;i<line.length;i+=2)context.lineTo(px(line[i]),py(line[i+1]));}context.stroke();}context.setLineDash([]);
      drawing.intersections.forEach((point,index)=>{context.beginPath();context.arc(px(point[0]),py(point[1]),4.5,0,Math.PI*2);context.fillStyle="#ffffff";context.fill();context.strokeStyle="#334155";context.lineWidth=2;context.stroke();if(index<12){context.font="600 11px system-ui";context.textAlign="left";context.fillStyle="#0f172a";context.fillText(`P${index+1}`,px(point[0])+7,py(point[1])-7);}});
    }
  },[drawing,camera,domain,size,grid,axes,fillBetween]);
  const zoom=(factor:number, anchor?:{x:number;y:number})=>{
    if(!size.width||!size.height)return;
    const previous=current.current,oldZoom=previous.zoom??1,nextZoom=clamp(oldZoom*factor,.1,20),half=domainRef.current*1.15/oldZoom;
    const x=anchor?.x??size.width/2,y=anchor?.y??size.height/2,dx=(x-size.width/2)*2*half/size.height,dy=-(y-size.height/2)*2*half/size.height;
    const cx=clamp(previous.target[0]+dx*(1-oldZoom/nextZoom),-500,500),cy=clamp(previous.target[1]+dy*(1-oldZoom/nextZoom),-500,500);
    updateCamera({position:[cx,cy,16],target:[cx,cy,0],zoom:nextZoom});
  };
  const zoomRef=useRef(zoom);zoomRef.current=zoom;
  useEffect(()=>{const element=canvas.current;if(!element)return;const wheel=(event:WheelEvent)=>{event.preventDefault();const rect=element.getBoundingClientRect();zoomRef.current(Math.exp(-event.deltaY*.0015),{x:event.clientX-rect.left,y:event.clientY-rect.top});};element.addEventListener("wheel",wheel,{passive:false});return()=>element.removeEventListener("wheel",wheel);},[]);
  const endPointer=(event:React.PointerEvent<HTMLCanvasElement>)=>{pointers.current.delete(event.pointerId);drag.current=null;pinch.current=null;if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);};
  const fit=()=>{if(!drawing||!size.height)return;const next=fitScene2DCamera(drawing,domain,size.width/size.height);if(next)updateCamera(next);};
  const reset=()=>updateCamera(initialCamera??{position:[0,0,16],target:[0,0,0],zoom:1});
  const unavailable=!!graphicsError||!drawing||!drawing.paths.some((path)=>path.points.length)&&!drawing.fills.some((fill)=>fill.points.length);
  return <div className={styles.scenePlanarView} style={expanded?{position:"fixed",inset:12,zIndex:120,background:"#fff",padding:18,borderRadius:18,overflow:"auto",boxShadow:"0 20px 80px #102e3a66"}:undefined}>
    <ScenePlotToolbar dimension="2D" disabled={unavailable} onZoom={zoom} onFit={fit} onReset={reset} expanded={expanded} onExpand={()=>setExpanded(!expanded)}>
      <label><input type="checkbox" checked={axes} onChange={(e)=>setAxes(e.target.checked)}/> Trục tọa độ</label><label><input type="checkbox" checked={grid} onChange={(e)=>setGrid(e.target.checked)}/> Lưới</label>
      {!!drawing?.betweenFills?.length?<label><input type="checkbox" checked={fillBetween} onChange={(event)=>setFillBetween(event.target.checked)}/> Tô miền giữa hai đường</label>:null}
      <span>Nét đứt: biên không được lấy (&lt;, &gt;).</span>
    </ScenePlotToolbar>
    <div ref={host} className={styles.sceneViewport} style={{height:expanded?"calc(100dvh - 150px)":"clamp(360px, calc(100dvh - 320px), 720px)",minHeight:360}}>
      <canvas ref={canvas} tabIndex={0} role="img" aria-label="Bảng đồ thị 2D. Kéo để di chuyển; cuộn hoặc chụm hai ngón để zoom. Các nút điều khiển ở phía trên."
        onPointerDown={(event)=>{if(event.button!==0)return;event.currentTarget.setPointerCapture(event.pointerId);pointers.current.set(event.pointerId,{x:event.clientX,y:event.clientY});drag.current={x:event.clientX,y:event.clientY,camera:current.current};if(pointers.current.size===2){const [a,b]=[...pointers.current.values()];pinch.current={distance:Math.hypot(a.x-b.x,a.y-b.y),camera:current.current};}}}
        onPointerMove={(event)=>{if(!pointers.current.has(event.pointerId))return;pointers.current.set(event.pointerId,{x:event.clientX,y:event.clientY});if(pointers.current.size===2&&pinch.current){const[a,b]=[...pointers.current.values()];const start=pinch.current;const value=clamp((start.camera.zoom??1)*Math.hypot(a.x-b.x,a.y-b.y)/Math.max(start.distance,1),.1,20);updateCamera({...start.camera,zoom:value});return;}if(!drag.current)return;const start=drag.current,scale=size.height/(2*domain*1.15/(start.camera.zoom??1));const cx=clamp(start.camera.target[0]-(event.clientX-start.x)/scale,-500,500),cy=clamp(start.camera.target[1]+(event.clientY-start.y)/scale,-500,500);updateCamera({position:[cx,cy,16],target:[cx,cy,0],zoom:start.camera.zoom??1});}}
        onPointerUp={endPointer} onPointerCancel={endPointer} onKeyDown={(event)=>{if(["+","="].includes(event.key)){event.preventDefault();zoom(1.2);}else if(event.key==="-"){event.preventDefault();zoom(1/1.2);}else if(event.key.toLowerCase()==="f"){event.preventDefault();fit();}else if(event.key.toLowerCase()==="r"){event.preventDefault();reset();}else if(["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key)){event.preventDefault();const step=domain*.1/(current.current.zoom??1),cx=current.current.target[0]+(event.key==="ArrowRight"?step:event.key==="ArrowLeft"?-step:0),cy=current.current.target[1]+(event.key==="ArrowUp"?step:event.key==="ArrowDown"?-step:0);updateCamera({position:[clamp(cx,-500,500),clamp(cy,-500,500),16],target:[clamp(cx,-500,500),clamp(cy,-500,500),0],zoom:current.current.zoom??1});}}} />
      {pending?<span className={styles.sceneUpdating} aria-live="off">Đang cập nhật…</span>:null}
      {error?<div className={styles.sceneError} role="alert"><p>{error}</p><button type="button" className={styles.button} onClick={sampling.retry}>Thử lại</button></div>:null}
    </div>
    <div className={styles.plotHint}><span>Kéo để di chuyển · Cuộn để zoom</span><span>Phím F: vừa hình · + / −: zoom</span></div>
    {!pending&&!error&&drawing&&!drawing.paths.some((path)=>path.points.length)&&!drawing.fills.some((fill)=>fill.points.length)?<p className={styles.muted} role="status">{scene.layers.some((layer)=>layer.visible)?"Chưa lấy mẫu được hình trong miền này. Hãy kiểm tra biểu thức hoặc thu hẹp miền khảo sát; hình trống không có nghĩa là phương trình vô nghiệm.":"Nhập biểu thức hoặc bật một dòng để bắt đầu quan sát."}</p>:null}
    <SceneIntersectionList scene={scene} drawing={drawing} ready={!pending&&!error} onFocus={(point)=>updateCamera({position:[point[0],point[1],16],target:[point[0],point[1],0],zoom:Math.max(1,current.current.zoom??1)})}/>
  </div>;
}
