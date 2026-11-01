"use client";
import { useEffect, useRef, useState } from "react";
import type { CompiledScene } from "./scene";
import type { SceneDrawing } from "./scene-geometry";

/** Shared planar regions/intersections; 3D explicit curves retain their full height. */
export function useSceneDrawing(scene:CompiledScene,parameters:Record<string,number>,domain:number,spatialCurves=false){
  const [drawing,setDrawing]=useState<SceneDrawing|null>(null),[pending,setPending]=useState(true),[error,setError]=useState<string|null>(null),[generation,setGeneration]=useState(0);
  type Input={scene:CompiledScene;parameters:Record<string,number>;domain:number;spatialCurves:boolean};
  const submit=useRef<((input:Input)=>void)|null>(null);
  useEffect(()=>{
    let worker:Worker;
    try{worker=new Worker(new URL("./scene.worker.ts",import.meta.url),{type:"module"});}
    catch{setPending(false);setError("Chưa mở được bảng đồ thị. Bấm thử lại.");return;}
    let live=true,sequence=0,active=false,queued:(Input&{id:number})|null=null;
    let timeout:ReturnType<typeof setTimeout>|undefined;
    const fail=()=>{if(!live)return;clearTimeout(timeout);submit.current=null;worker.terminate();setPending(false);setError("Bảng đồ thị tạm thời không phản hồi. Bấm thử lại.");};
    const send=(input:Input&{id:number})=>{active=true;clearTimeout(timeout);timeout=setTimeout(fail,10000);try{worker.postMessage(input);}catch{fail();}};
    submit.current=(input)=>{const request={...input,id:++sequence};setPending(true);setError(null);if(active)queued=request;else send(request);};
    worker.onmessage=({data}:MessageEvent<{id:number;drawing?:SceneDrawing;error?:string}>)=>{
      if(!live)return;clearTimeout(timeout);active=false;
      if(queued){const latest=queued;queued=null;send(latest);return;}
      if(data.id!==sequence)return;
      setPending(false);if(data.drawing){setDrawing(data.drawing);setError(null);}else setError(data.error??"Chưa dựng được hình.");
    };
    worker.onerror=(event)=>{event.preventDefault();fail();};worker.onmessageerror=fail;
    return()=>{live=false;clearTimeout(timeout);worker.terminate();submit.current=null;};
  },[generation]);
  useEffect(()=>{submit.current?.({scene,parameters,domain,spatialCurves});},[scene,parameters,domain,spatialCurves,generation]);
  return {drawing,pending,error,retry:()=>setGeneration((value)=>value+1)};
}
