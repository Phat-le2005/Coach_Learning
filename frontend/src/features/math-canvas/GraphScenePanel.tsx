"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { InkStroke } from "@/lib/api/contracts";
import { recognizeHandwrittenMath } from "@/features/math-workspace/utils/handwritten-ocr";
import { OcrInkPreview } from "@/features/math-workspace/components/OcrInkPreview";
import { generateUuid } from "@/features/math-workspace/utils/ink-math";
import { canvasRequest, type CanvasSnapshot } from "./api";
import { DEFAULT_GRAPH, type GraphCamera } from "./expression";
import { compileGraphScene, SCENE_COLORS, type GraphSceneDocument, type SceneRow } from "./scene";
import { GraphSceneView } from "./GraphSceneView";
import { appendSceneRow, parseSceneDraft } from "./scene-draft";
import styles from "./MathCanvas.module.css";

export interface ScenePanelProps { attemptId:string; pageIndex:number; selectedStrokes:InkStroke[]; initialFormula?:string; ensureInkSaved:()=>Promise<void>; onClose:()=>void; active:boolean; onSingle:(snapshot?:CanvasSnapshot, formula?:string)=>void }
const createRow=(expression="", index=0):SceneRow=>({id:generateUuid(),expression,visible:true,color:SCENE_COLORS[index%SCENE_COLORS.length]});
const seedCamera:GraphCamera={position:[0,0,16],target:[0,0,0],zoom:1};
const examples=[{label:"Hai đồ thị",rows:["y=x²","y=2x+1"],combine:"OVERLAY" as const},{label:"Miền chung",rows:["y>=x²","y<=2x+1"],combine:"AND" as const},{label:"Hàm hợp",rows:["f(x)=x²+1","g(x)=sin(x)","y=f(g(x))"],combine:"OVERLAY" as const},{label:"Trong đường tròn",rows:["x²+y²<=r²","x>=0"],combine:"AND" as const}];
export function GraphScenePanel({attemptId,pageIndex,selectedStrokes,initialFormula="",ensureInkSaved,onClose,active,onSingle}:ScenePanelProps){
  const draftKey=`edums_math_scene_v2:${attemptId}:${pageIndex}`;
  const [recovered]=useState(()=>{try{return typeof window!=="undefined"?parseSceneDraft(window.sessionStorage.getItem(draftKey)):null;}catch{return null;}});
  const [rows,setRows]=useState<SceneRow[]>(()=>{const previous=recovered?.rows??[createRow()];return initialFormula&&!previous.some((row)=>row.expression===initialFormula)?appendSceneRow(previous,createRow(initialFormula,previous.length))??previous:previous;}),[settledRows,setSettledRows]=useState(rows);
  const [combine,setCombine]=useState<GraphSceneDocument["combine"]>(recovered?.combine??"OVERLAY"),[parameters,setParameters]=useState<Record<string,number>>(recovered?.parameters??{}),[domain,setDomain]=useState(recovered?.domain??3);
  const [camera,setCamera]=useState<GraphCamera>(recovered?.camera??seedCamera),[viewKey,setViewKey]=useState(0);
  const [note,setNote]=useState(recovered?.note??""),[snapshots,setSnapshots]=useState<CanvasSnapshot[]>([]),[viewing,setViewing]=useState<CanvasSnapshot|null>(null);
  const [draftSaved,setDraftSaved]=useState(!!recovered);
  const [error,setError]=useState<string|null>(null),[success,setSuccess]=useState<string|null>(null),[listError,setListError]=useState(false),[listRun,setListRun]=useState(0);
  const [busy,setBusy]=useState<"ocr"|"save"|null>(null),[ocrRun,setOcrRun]=useState(0),[needsConfirmation,setNeedsConfirmation]=useState(false);
  const [focusId,setFocusId]=useState<string|null>(null);
  const inputs=useRef(new Map<string,HTMLInputElement>()),editVersion=useRef(0),sourceRow=useRef<string|null>(null),saveAction=useRef<{signature:string;id:string}|null>(null);
  const endpoint=`attempts/${attemptId}`;
  const latestRows=useRef(rows);latestRows.current=rows;
  const latestDraft=useRef({rows,combine,parameters,domain,camera,note,viewing});latestDraft.current={rows,combine,parameters,domain,camera,note,viewing};
  useEffect(()=>{const flush=()=>{const {viewing:readOnly,...draft}=latestDraft.current;if(!readOnly)try{window.sessionStorage.setItem(draftKey,JSON.stringify(draft));}catch{}};window.addEventListener("pagehide",flush);return()=>{window.removeEventListener("pagehide",flush);flush();};},[draftKey]);
  useEffect(()=>{if(viewing)return;const timer=setTimeout(()=>{try{window.sessionStorage.setItem(draftKey,JSON.stringify({rows,combine,parameters,domain,camera,note}));setDraftSaved(true);}catch{setDraftSaved(false);}},400);return()=>clearTimeout(timer);},[draftKey,rows,combine,parameters,domain,camera,note,viewing]);
  useEffect(()=>{const timer=setTimeout(()=>setSettledRows(rows),250);return()=>clearTimeout(timer);},[rows]);
  useEffect(()=>{if(focusId)inputs.current.get(focusId)?.focus();},[focusId,rows]);
  const compiled=useMemo(()=>compileGraphScene({version:2,dimension:"2D",combine,rows:settledRows}),[settledRows,combine]);
  useEffect(()=>{setParameters((current)=>{const next=Object.fromEntries(compiled.parameters.map((name)=>[name,current[name]??1]));return JSON.stringify(next)===JSON.stringify(current)?current:next;});},[compiled.parameters.join(",")]);
  useEffect(()=>{if(!active)return;let live=true;setListError(false);canvasRequest<CanvasSnapshot[]>(`${endpoint}/snapshots`).then((data)=>{if(live)setSnapshots(data);}).catch(()=>{if(live)setListError(true);});return()=>{live=false;};},[endpoint,listRun,active]);
  useEffect(()=>{
    if(!selectedStrokes.length)return;let live=true;const version=editVersion.current;setBusy("ocr");setError(null);
    let timer:ReturnType<typeof setTimeout>;
    const deadline=new Promise<never>((_,reject)=>{timer=setTimeout(()=>reject(new Error("timeout")),45000);});
    Promise.race([recognizeHandwrittenMath(selectedStrokes),deadline]).then((result)=>{if(!live||editVersion.current!==version)return;const row=createRow(result.latex,latestRows.current.length),next=appendSceneRow(latestRows.current,row);if(!next){setError("Bảng đã đủ 8 dòng. Xóa một dòng trống hoặc không cần dùng rồi nhận dạng lại.");return;}sourceRow.current=row.id;setRows(next);setNeedsConfirmation(true);}).catch(()=>{if(live&&editVersion.current===version)setError("Chưa đọc được nét viết. Em có thể nhập công thức trực tiếp rồi tiếp tục.");}).finally(()=>{clearTimeout(timer);if(live&&editVersion.current===version)setBusy(null);});
    return()=>{live=false;clearTimeout(timer);};
    // The parent keys each panel by its original stroke selection.
  },[ocrRun]);
  const editing=()=>{editVersion.current++;if(busy==="ocr")setBusy(null);setViewing(null);setError(null);setSuccess(null);};
  // Only editing the recognized text counts as manual correction; colors/visibility do not confirm OCR.
  const changeRow=(id:string,patch:Partial<SceneRow>)=>{editing();if(id===sourceRow.current&&patch.expression!==undefined)setNeedsConfirmation(false);setRows((current)=>current.map((row)=>row.id===id?{...row,...patch}:row));};
  const addRow=()=>{if(rows.length>=8)return;editing();const row=createRow("",rows.length);setRows((current)=>[...current,row]);setFocusId(row.id);};
  const removeRow=(id:string)=>{editing();if(sourceRow.current===id){sourceRow.current=null;setNeedsConfirmation(false);}setRows((current)=>current.length===1?[{...current[0],expression:""}]:current.filter((row)=>row.id!==id));};
  const applyExample=(example:typeof examples[number])=>{editing();sourceRow.current=null;setNeedsConfirmation(false);setRows(example.rows.map((source,index)=>createRow(source,index)));setCombine(example.combine);setParameters({});setDomain(3);setCamera(seedCamera);setViewKey((n)=>n+1);};
  const openSnapshot=(snapshot:CanvasSnapshot)=>{
    if(!snapshot.settings.scene){onSingle(snapshot);return;}
    editVersion.current++;sourceRow.current=null;setBusy(null);setNeedsConfirmation(false);setError(null);setSuccess(null);
    setRows(snapshot.settings.scene.rows.map((row)=>({...row})));setSettledRows(snapshot.settings.scene.rows.map((row)=>({...row})));setCombine(snapshot.settings.scene.combine);
    setParameters({...snapshot.settings.parameters});setDomain(snapshot.settings.domain);setCamera(snapshot.camera);setViewKey((n)=>n+1);setNote(snapshot.note);setViewing(snapshot);
  };
  const typing=rows!==settledRows,hasErrors=Object.keys(compiled.errors).length>0;
  async function save(){
    if(typing||hasErrors||!compiled.layers.length||needsConfirmation)return;
    setBusy("save");setError(null);setSuccess(null);
    try{
      await ensureInkSaved();
      const payload={expression:"y=0",settings:{...DEFAULT_GRAPH,domain,parameters,view_mode:"2D",scene:compiled.document},camera,page_index:pageIndex,
        stroke_ids:sourceRow.current&&rows.some((row)=>row.id===sourceRow.current)?selectedStrokes.map((stroke)=>stroke.id):[],source_latex:"",note,explanation_id:null};
      const signature=JSON.stringify(payload);if(saveAction.current?.signature!==signature)saveAction.current={signature,id:generateUuid()};
      const saved=await canvasRequest<CanvasSnapshot>(`${endpoint}/snapshots`,{...payload,client_action_id:saveAction.current!.id});saveAction.current=null;
      setSnapshots((current)=>[saved,...current.filter((row)=>row.id!==saved.id)]);setListError(false);setSuccess("Đã lưu toàn bộ bảng đồ thị vào bài học. Giáo viên có thể mở lại đúng các biểu thức và tham số này.");
    }catch(err){setError(err instanceof Error?err.message:"Chưa lưu được bảng đồ thị.");}finally{setBusy(null);}
  }
  const locked=busy==="save"||!!viewing;
  return <aside hidden={!active} className={`${styles.panel} ${styles.scenePanel}`} aria-label="Math View — bảng đồ thị nhiều biểu thức">
    <header className={styles.sceneHeading}><div><span className={styles.eyebrow}>KHÁM PHÁ TOÁN HỌC</span><h2>Math View</h2><p>So sánh đồ thị · Quan sát miền thỏa mãn · Thử thay đổi tham số</p></div><div className={styles.row}>
      <button type="button" className={styles.button} onClick={()=>onSingle()}>Một công thức · 3D</button><button type="button" className={styles.close} aria-label="Đóng Math View" onClick={onClose}>×</button></div></header>
    <div className={styles.sceneLayout}>
      <section className={styles.expressionPane} aria-label="Danh sách biểu thức">
        <div className={styles.expressionTitle}><strong>Biểu thức</strong><span>{rows.length}/8 dòng</span></div>
        <p className={styles.muted}>Mỗi dòng một công thức. Bấm Enter để thêm dòng.</p><span className={styles.rowHint}>{draftSaved?"Bản nháp được giữ trong phiên làm việc này.":"Bấm Lưu bảng để giữ vào bài học."}</span>
        {rows.map((row,index)=><div key={row.id} className={`${styles.expressionCard} ${compiled.errors[row.id]?styles.expressionInvalid:""}`}>
          <div className={styles.expressionTop}><label><input type="checkbox" aria-label={`Hiện dòng ${index+1}`} checked={row.visible} disabled={locked} onChange={(event)=>changeRow(row.id,{visible:event.target.checked})}/> Dòng {index+1}</label>
            <input type="color" className={styles.rowColor} aria-label={`Màu dòng ${index+1}`} value={row.color} disabled={locked} onChange={(event)=>changeRow(row.id,{color:event.target.value})}/>
            <button type="button" className={styles.removeRow} aria-label={`Xóa dòng ${index+1}`} disabled={locked} onClick={()=>removeRow(row.id)}>×</button></div>
          <input ref={(element)=>{if(element)inputs.current.set(row.id,element);else inputs.current.delete(row.id);}} className={styles.expressionInput} aria-label={`Biểu thức dòng ${index+1}`} aria-invalid={!!compiled.errors[row.id]} aria-describedby={compiled.errors[row.id]?`error-${row.id}`:undefined}
            value={row.expression} maxLength={500} disabled={locked} placeholder={index?"y ≤ 2x + 1":"y ≥ x²"} autoComplete="off" spellCheck={false}
            onChange={(event)=>changeRow(row.id,{expression:event.target.value})} onKeyDown={(event)=>{if(event.key==="Enter"){event.preventDefault();addRow();}}}/>
          {compiled.errors[row.id]?<p id={`error-${row.id}`} className={styles.rowError}>{compiled.errors[row.id]}{compiled.errors[row.id].includes("3D")?<button type="button" className={styles.button} onClick={()=>onSingle(undefined,row.expression)}>Xem 3D</button>:null}</p>
            :row.expression.trim()?<span className={styles.rowHint}>{compiled.layers.find((layer)=>layer.id===row.id)?.label??"Đang nhận diện…"}</span>:null}
        </div>)}
        <button type="button" className={`${styles.button} ${styles.addExpression}`} disabled={rows.length>=8||locked} onClick={addRow}>+ Thêm dòng biểu thức</button>
        <label className={styles.modeLabel}>Cách tô miền<select value={combine} disabled={locked} onChange={(event)=>{editing();setCombine(event.target.value as GraphSceneDocument["combine"]);}}>
          <option value="OVERLAY">Tô riêng từng miền</option><option value="AND">Miền chung — thỏa mãn tất cả</option><option value="OR">Miền hợp — thỏa mãn ít nhất một</option></select></label>
        <p className={styles.muted}>Áp dụng cho các bất phương trình đang hiện. Các phương trình được vẽ để đối chiếu.</p>
        {!viewing?<details className={styles.examples}><summary>Khám phá từ ví dụ</summary><p className={styles.muted}>Chọn ví dụ sẽ thay các dòng hiện tại.</p><div className={styles.row}>{examples.map((example)=><button type="button" className={styles.button} key={example.label} disabled={busy==="save"} onClick={()=>applyExample(example)}>{example.label}</button>)}</div></details>:null}
        {selectedStrokes.length?<details className={styles.examples}><summary>Nét viết đã chọn</summary><OcrInkPreview strokes={selectedStrokes}/><p className={styles.muted}>Đối chiếu công thức nhận dạng trước khi lưu.</p><button type="button" className={styles.button} disabled={!!busy||!!viewing} onClick={()=>{editing();setOcrRun((n)=>n+1);}}>Nhận dạng lại</button></details>:null}
        {busy==="ocr"?<p className={styles.muted} role="status">Đang đọc nét viết… Em vẫn có thể nhập công thức.</p>:null}
        {needsConfirmation?<label className={styles.confirmOcr}><input type="checkbox" checked={false} onChange={()=>setNeedsConfirmation(false)}/> Em đã đối chiếu công thức với nét viết.</label>:null}
        <div className={styles.section}><h3>Bảng đã lưu ({snapshots.length})</h3>{listError?<p className={styles.rowError}>Chưa tải được bản lưu. <button type="button" className={styles.button} onClick={()=>setListRun((n)=>n+1)}>Thử lại</button></p>:null}
          {!snapshots.length&&!listError?<p className={styles.muted}>Chưa có bảng đồ thị được lưu.</p>:null}
          {snapshots.map((snapshot)=><button type="button" className={styles.saved} key={snapshot.id} disabled={busy==="save"} onClick={()=>openSnapshot(snapshot)}>
            <strong>{snapshot.settings.scene?`Bảng ${snapshot.settings.scene.rows.length} biểu thức`:snapshot.expression}</strong><small>Trang {snapshot.page_index+1} · {new Date(snapshot.created_at).toLocaleString("vi-VN")}</small></button>)}
        </div>
      </section>
      <section className={styles.sceneWork} aria-label="Đồ thị và tham số">
        <div className={styles.sceneStatus}><span className={styles.badge}>Mặt phẳng Oxy</span><span aria-live="polite">{typing?"Đang nhận diện…":hasErrors?"Có biểu thức cần sửa":`${compiled.layers.filter((layer)=>layer.visible).length} biểu thức đang hiện`}</span></div>
        {active?<GraphSceneView key={viewKey} scene={compiled} parameters={parameters} domain={domain} initialCamera={camera} onCameraChange={setCamera}/>:null}
        <div className={styles.sliders}>
          {compiled.parameters.map((name)=><label className={styles.slider} key={name}><span>Tham số {name}<strong>{(parameters[name]??1).toFixed(1)}</strong></span><input type="range" aria-label={`Tham số chung ${name}`} min={-5} max={5} step={.1} disabled={locked} value={parameters[name]??1} onChange={(event)=>{setParameters((current)=>({...current,[name]:Number(event.target.value)}));setSuccess(null);}}/></label>)}
          <label className={styles.slider}><span>Miền khảo sát ±<strong>{domain.toFixed(1)}</strong></span><input type="range" aria-label="Miền khảo sát bảng đồ thị" min={1} max={10} step={.5} disabled={locked} value={domain} onChange={(event)=>{setDomain(Number(event.target.value));setSuccess(null);}}/></label>
        </div>
        {viewing?<div className={styles.explorationCard}><strong>Đang xem bản lưu</strong><p>{viewing.note||"Có thể di chuyển và zoom để quan sát. Bắt đầu lượt khám phá mới để đổi tham số."}</p><button type="button" className={styles.primary} onClick={()=>{editing();sourceRow.current=null;setViewKey((n)=>n+1);}}>Tiếp tục khám phá</button></div>
          :<div className={styles.explorationCard}><label htmlFor="scene-note">Điều em quan sát được<textarea id="scene-note" className={styles.note} maxLength={1000} value={note} disabled={busy==="save"} onChange={(event)=>setNote(event.target.value)} placeholder="Miền chung thay đổi thế nào khi em kéo thanh tham số?"/></label>
            <div className={styles.row}><button type="button" className={styles.primary} disabled={!!busy||typing||hasErrors||!compiled.layers.length||needsConfirmation} onClick={save}>{busy==="save"?"Đang lưu…":"Lưu bảng vào bài học"}</button><span className={styles.muted}>Lưu cả biểu thức, màu, tham số và góc nhìn.</span></div></div>}
        {error?<p className={styles.error} role="alert">{error}</p>:null}{success?<p className={styles.success} role="status">{success}</p>:null}
      </section>
    </div>
  </aside>;
}
