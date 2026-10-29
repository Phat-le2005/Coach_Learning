"use client";
import { useEffect, useRef, useState } from "react";
import type { GraphCamera } from "./expression";
import type { CompiledScene } from "./scene";
import type { SceneDrawing } from "./scene-geometry";
import styles from "./MathCanvas.module.css";

interface Props { scene: CompiledScene; parameters: Record<string, number>; domain: number; initialCamera?: GraphCamera; onCameraChange?: (camera: GraphCamera) => void }
const clamp = (value: number, min: number, max: number) => Math.max(min,Math.min(max,value));
export function GraphSceneView({ scene, parameters, domain, initialCamera, onCameraChange }: Props) {
  const canvas = useRef<HTMLCanvasElement>(null), host = useRef<HTMLDivElement>(null);
  const [camera,setCamera] = useState<GraphCamera>(() => initialCamera ?? {position:[0,0,16],target:[0,0,0],zoom:1});
  const current = useRef(camera); current.current = camera;
  const callback = useRef(onCameraChange); callback.current = onCameraChange;
  const [drawing,setDrawing] = useState<SceneDrawing | null>(null), [pending,setPending] = useState(true), [error,setError] = useState<string | null>(null);
  const [grid,setGrid] = useState(true), [axes,setAxes] = useState(true), [generation,setGeneration] = useState(0), [size,setSize] = useState({width:0,height:0});
  const submit = useRef<((input: {scene: CompiledScene; parameters: Record<string,number>; domain:number}) => void) | null>(null);
  const domainRef = useRef(domain); domainRef.current = domain;
  const drag = useRef<{x:number;y:number;camera:GraphCamera} | null>(null);
  const pointers = useRef(new Map<number,{x:number;y:number}>());
  const pinch = useRef<{distance:number;camera:GraphCamera} | null>(null);
  const updateCamera = (next: GraphCamera) => { current.current=next;setCamera(next);callback.current?.(next); };
  useEffect(() => { callback.current?.(current.current); }, []);
  useEffect(() => {
    let worker: Worker;
    try { worker = new Worker(new URL("./scene.worker.ts",import.meta.url),{type:"module"}); }
    catch { setPending(false);setError("Chưa mở được bảng đồ thị. Bấm thử lại.");return; }
    let live=true, sequence=0, active=false, queued: (Parameters<NonNullable<typeof submit.current>>[0] & {id:number}) | null=null;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const fail = () => { if (!live) return; clearTimeout(timeout);submit.current=null;worker.terminate();setPending(false);setError("Bảng đồ thị tạm thời không phản hồi. Bấm thử lại."); };
    const send = (input: NonNullable<typeof queued>) => { active=true;clearTimeout(timeout);timeout=setTimeout(fail,10000);try { worker.postMessage(input); } catch { fail(); } };
    submit.current = (input) => { const request={...input,id:++sequence};setPending(true);setError(null);if (active) queued=request;else send(request); };
    worker.onmessage = ({data}: MessageEvent<{id:number;drawing?:SceneDrawing;error?:string}>) => {
      if (!live) return;clearTimeout(timeout);active=false;
      if (queued) { const latest=queued;queued=null;send(latest);return; }
      if (data.id!==sequence) return;
      setPending(false);if (data.drawing) {setDrawing(data.drawing);setError(null);}else setError(data.error ?? "Chưa dựng được hình.");
    };
    worker.onerror=(event)=>{event.preventDefault();fail();};worker.onmessageerror=fail;
    return ()=>{live=false;clearTimeout(timeout);worker.terminate();submit.current=null;};
  },[generation]);
  useEffect(()=>{submit.current?.({scene,parameters,domain});},[scene,parameters,domain,generation]);
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
      for(const fill of drawing.fills){context.fillStyle=fill.color;context.globalAlpha=.17;context.beginPath();for(let i=0;i<fill.points.length;i+=6){context.moveTo(px(fill.points[i]),py(fill.points[i+1]));context.lineTo(px(fill.points[i+2]),py(fill.points[i+3]));context.lineTo(px(fill.points[i+4]),py(fill.points[i+5]));context.closePath();}context.fill();}context.globalAlpha=1;
    }
    if(axes){context.strokeStyle="#64748b";context.lineWidth=1.3;context.beginPath();context.moveTo(px(0),0);context.lineTo(px(0),h);context.moveTo(0,py(0));context.lineTo(w,py(0));context.stroke();
      context.font="11px system-ui";context.fillStyle="#475569";context.textAlign="center";
      for(let x=Math.ceil(minX/step)*step;x<=maxX;x+=step)if(Math.abs(x)>step*.01)context.fillText(Number(x.toFixed(3)).toString(),px(x),clamp(py(0)+15,15,h-5));
      context.textAlign="left";for(let y=Math.ceil(minY/step)*step;y<=maxY;y+=step)if(Math.abs(y)>step*.01)context.fillText(Number(y.toFixed(3)).toString(),clamp(px(0)+6,5,w-35),py(y)-4);
      context.font="600 13px system-ui";context.fillText("x",w-15,clamp(py(0)-8,15,h-5));context.fillText("y",clamp(px(0)+8,5,w-15),17);
    }
    if(drawing){context.lineWidth=2;
      for(const path of drawing.paths){context.strokeStyle=path.color;context.setLineDash(path.dashed?[6,5]:[]);context.beginPath();for(const line of path.polylines){context.moveTo(px(line[0]),py(line[1]));for(let i=2;i<line.length;i+=2)context.lineTo(px(line[i]),py(line[i+1]));}context.stroke();}context.setLineDash([]);
      for(const point of drawing.intersections){context.beginPath();context.arc(px(point[0]),py(point[1]),4.5,0,Math.PI*2);context.fillStyle="#ffffff";context.fill();context.strokeStyle="#334155";context.lineWidth=2;context.stroke();}
    }
  },[drawing,camera,domain,size,grid,axes]);
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
  return <div>
    <div ref={host} className={styles.sceneViewport}>
      <canvas ref={canvas} tabIndex={0} role="img" aria-label="Bảng đồ thị 2D. Kéo để di chuyển; cuộn hoặc chụm hai ngón để zoom. Có các nút điều khiển bên dưới."
        onPointerDown={(event)=>{if(event.button!==0)return;event.currentTarget.setPointerCapture(event.pointerId);pointers.current.set(event.pointerId,{x:event.clientX,y:event.clientY});drag.current={x:event.clientX,y:event.clientY,camera:current.current};if(pointers.current.size===2){const [a,b]=[...pointers.current.values()];pinch.current={distance:Math.hypot(a.x-b.x,a.y-b.y),camera:current.current};}}}
        onPointerMove={(event)=>{if(!pointers.current.has(event.pointerId))return;pointers.current.set(event.pointerId,{x:event.clientX,y:event.clientY});if(pointers.current.size===2&&pinch.current){const[a,b]=[...pointers.current.values()];const start=pinch.current;const value=clamp((start.camera.zoom??1)*Math.hypot(a.x-b.x,a.y-b.y)/Math.max(start.distance,1),.1,20);updateCamera({...start.camera,zoom:value});return;}if(!drag.current)return;const start=drag.current,scale=size.height/(2*domain*1.15/(start.camera.zoom??1));const cx=clamp(start.camera.target[0]-(event.clientX-start.x)/scale,-500,500),cy=clamp(start.camera.target[1]+(event.clientY-start.y)/scale,-500,500);updateCamera({position:[cx,cy,16],target:[cx,cy,0],zoom:start.camera.zoom??1});}}
        onPointerUp={endPointer} onPointerCancel={endPointer} onKeyDown={(event)=>{if(["+","="].includes(event.key)){event.preventDefault();zoom(1.2);}else if(event.key==="-"){event.preventDefault();zoom(1/1.2);}else if(["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key)){event.preventDefault();const step=domain*.1/(current.current.zoom??1),cx=current.current.target[0]+(event.key==="ArrowRight"?step:event.key==="ArrowLeft"?-step:0),cy=current.current.target[1]+(event.key==="ArrowUp"?step:event.key==="ArrowDown"?-step:0);updateCamera({position:[clamp(cx,-500,500),clamp(cy,-500,500),16],target:[clamp(cx,-500,500),clamp(cy,-500,500),0],zoom:current.current.zoom??1});}}} />
      {pending?<span className={styles.sceneUpdating} aria-live="off">Đang cập nhật…</span>:null}
      {error?<div className={styles.sceneError} role="alert"><p>{error}</p><button type="button" className={styles.button} onClick={()=>setGeneration((n)=>n+1)}>Thử lại</button></div>:null}
    </div>
    <div className={styles.row} role="group" aria-label="Điều khiển bảng đồ thị">
      <button type="button" className={styles.button} aria-label="Phóng to bảng đồ thị" onClick={()=>zoom(1.25)}>+</button><button type="button" className={styles.button} aria-label="Thu nhỏ bảng đồ thị" onClick={()=>zoom(.8)}>−</button>
      <button type="button" className={styles.button} onClick={()=>updateCamera({position:[0,0,16],target:[0,0,0],zoom:1})}>Về gốc tọa độ</button>
      <label><input type="checkbox" checked={axes} onChange={(e)=>setAxes(e.target.checked)}/> Trục</label><label><input type="checkbox" checked={grid} onChange={(e)=>setGrid(e.target.checked)}/> Lưới</label>
    </div>
    <p className={styles.muted}>Nét liền: =, ≤, ≥. Nét đứt: không lấy biên (&lt;, &gt;). Miền khảo sát: −{domain} ≤ x, y ≤ {domain}.</p>
    {!pending&&!error&&drawing&&!drawing.paths.some((path)=>path.points.length)&&!drawing.fills.some((fill)=>fill.points.length)?<p className={styles.muted} role="status">{scene.layers.some((layer)=>layer.visible)?"Chưa lấy mẫu được hình trong miền này. Hãy kiểm tra biểu thức hoặc thu hẹp miền khảo sát; hình trống không có nghĩa là phương trình vô nghiệm.":"Nhập biểu thức hoặc bật một dòng để bắt đầu quan sát."}</p>:null}
    {drawing?.intersections.length?<details className={styles.muted}><summary>Giao điểm gần đúng ({drawing.intersections.length})</summary><p>{drawing.intersections.map((point)=>`(${point[0].toFixed(2)}; ${point[1].toFixed(2)})`).join(" · ")}</p><p>Các điểm được tìm bằng lấy mẫu; tiếp xúc hoặc chi tiết nhỏ có thể chưa được phát hiện.</p></details>:null}
  </div>;
}
