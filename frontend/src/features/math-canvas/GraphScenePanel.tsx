"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { ArrowUpRight, BookmarkCheck, BookOpen, Box, ChartNoAxesCombined, Check, CheckCircle2, ChevronRight, Eye, EyeOff, HelpCircle, Layers3, LoaderCircle, Orbit, Plus, Save, Settings2, Sparkles, Trash2, X } from "lucide-react";
import type { InkStroke } from "@/lib/api/contracts";
import { recognizeHandwrittenMath } from "@/features/math-workspace/utils/handwritten-ocr";
import { OcrInkPreview } from "@/features/math-workspace/components/OcrInkPreview";
import { OcrMathPreview } from "@/features/math-workspace/components/OcrMathPreview";
import { generateUuid } from "@/features/math-workspace/utils/ink-math";
import { canvasRequest, type CanvasSnapshot } from "./api";
import { DEFAULT_GRAPH, defaultCamera, type GraphCamera } from "./expression";
import { compileGraphScene, SCENE_COLORS, type GraphSceneDocument, type SceneRow } from "./scene";
import { GraphSceneView } from "./GraphSceneView";
import { importSceneFormulas, replaceSceneSelection, parseSceneDraft, restoreSceneSpatialDraft } from "./scene-draft";
import { equationInkRows, recognizeFormulaRows, splitFormulaRows } from "./multi-formula";
import { LAB_TITLES } from "./lab-spec";
import { GraphValueControl } from "./GraphValueControl";
import { insertMathSnippet } from "./formula-editing";
import styles from "./MathCanvas.module.css";

export interface SceneImportRequest { key:string;source:string;readInk:boolean;needsConfirmation:boolean }
export interface ScenePanelProps { attemptId:string; pageIndex:number; selectedStrokes:InkStroke[]; initialFormula?:string; importRequest?:SceneImportRequest; ensureInkSaved:()=>Promise<void>; onClose:()=>void; active:boolean; onSingle:(snapshot?:CanvasSnapshot, formula?:string)=>void; onLab:(snapshot?:CanvasSnapshot)=>void }
const createRow=(expression="", index=0):SceneRow=>({id:generateUuid(),expression,visible:true,color:SCENE_COLORS[index%SCENE_COLORS.length]});
const seedCamera:GraphCamera={position:[0,0,16],target:[0,0,0],zoom:1};
const GraphScene3DView=dynamic(()=>import("./GraphScene3DView").then((module)=>module.GraphScene3DView),{ssr:false,loading:()=> <p className={styles.muted}>Đang mở bảng 3D…</p>});
const examples=[{label:"Hai đồ thị",rows:["y=x²","y=2x+1"],combine:"OVERLAY" as const},{label:"Miền chung",rows:["y>=x²","y<=2x+1"],combine:"AND" as const},{label:"Hàm hợp",rows:["f(x)=x²+1","g(x)=sin(x)","y=f(g(x))"],combine:"OVERLAY" as const},{label:"Trong đường tròn",rows:["x²+y²<=r²","x>=0"],combine:"AND" as const}];
export function GraphScenePanel({attemptId,pageIndex,selectedStrokes,initialFormula="",importRequest,ensureInkSaved,onClose,active,onSingle,onLab}:ScenePanelProps){
  const draftKey=`edums_math_scene_v2:${attemptId}:${pageIndex}`;
  const [recovered]=useState(()=>{try{return typeof window!=="undefined"?parseSceneDraft(window.sessionStorage.getItem(draftKey)):null;}catch{return null;}});
  const freshInput=!!(importRequest?.readInk||importRequest?.source.trim()||initialFormula.trim()||selectedStrokes.length);
  const [rows,setRows]=useState<SceneRow[]>(()=>freshInput?[createRow()]:recovered?.rows??[createRow()]),[settledRows,setSettledRows]=useState(rows);
  const [combine,setCombine]=useState<GraphSceneDocument["combine"]>(recovered?.combine??"OVERLAY"),[parameters,setParameters]=useState<Record<string,number>>(recovered?.parameters??{}),[domain,setDomain]=useState(recovered?.domain??3);
  const [camera,setCamera]=useState<GraphCamera>(recovered?.camera??seedCamera),[viewKey,setViewKey]=useState(0);
  const [viewMode,setViewMode]=useState<"2D"|"3D">("2D"),[spatialCamera,setSpatialCamera]=useState<GraphCamera|undefined>(freshInput?undefined:restoreSceneSpatialDraft(recovered).camera);
  const [spatialDepth,setSpatialDepth]=useState(freshInput?0:restoreSceneSpatialDraft(recovered).depth);
  const [spatialSurface,setSpatialSurface]=useState(!freshInput&&recovered?.spatialStyle==="CURVE_3D"&&!!recovered.spatialSurface);
  const [note,setNote]=useState(recovered?.note??""),[snapshots,setSnapshots]=useState<CanvasSnapshot[]>([]),[viewing,setViewing]=useState<CanvasSnapshot|null>(null);
  const [mobilePane,setMobilePane]=useState<"editor"|"graph">("graph");
  const [draftSaved,setDraftSaved]=useState(!!recovered);
  const [error,setError]=useState<string|null>(null),[success,setSuccess]=useState<string|null>(null),[listError,setListError]=useState(false),[listRun,setListRun]=useState(0);
  const [busy,setBusy]=useState<"ocr"|"save"|null>(null),[ocrRun,setOcrRun]=useState(0),[pendingOcr,setPendingOcr]=useState<string[]>([]);
  const [ocrProgress,setOcrProgress]=useState({done:0,total:0});
  const needsConfirmation=pendingOcr.length>0;
  const [focusId,setFocusId]=useState<string|null>(null);
  const inkRows=useMemo(()=>equationInkRows(selectedStrokes),[selectedStrokes]);
  const inputs=useRef(new Map<string,HTMLTextAreaElement>()),editVersion=useRef(0),sourceRows=useRef<string[]>([]),saveAction=useRef<{signature:string;id:string}|null>(null);
  const rowInk=useRef(new Map<string,InkStroke[]>());
  const editorPane=useRef<HTMLElement>(null);
  const lastOcrRun=useRef(0);
  const endpoint=`attempts/${attemptId}`;
  const latestRows=useRef(rows);latestRows.current=rows;
  const latestDraft=useRef({rows,combine,parameters,domain,camera,note,viewing,viewMode,spatialCamera,spatialDepth,spatialSurface,spatialStyle:"CURVE_3D"});latestDraft.current={rows,combine,parameters,domain,camera,note,viewing,viewMode,spatialCamera,spatialDepth,spatialSurface,spatialStyle:"CURVE_3D"};
  useEffect(()=>{const flush=()=>{const {viewing:readOnly,...draft}=latestDraft.current;if(!readOnly)try{window.sessionStorage.setItem(draftKey,JSON.stringify(draft));}catch{}};window.addEventListener("pagehide",flush);return()=>{window.removeEventListener("pagehide",flush);flush();};},[draftKey]);
  useEffect(()=>{if(viewing)return;const timer=setTimeout(()=>{try{window.sessionStorage.setItem(draftKey,JSON.stringify({rows,combine,parameters,domain,camera,note,viewMode,spatialCamera,spatialDepth,spatialSurface,spatialStyle:"CURVE_3D"}));setDraftSaved(true);}catch{setDraftSaved(false);}},400);return()=>clearTimeout(timer);},[draftKey,rows,combine,parameters,domain,camera,note,viewing,viewMode,spatialCamera,spatialDepth,spatialSurface]);
  useEffect(()=>{const timer=setTimeout(()=>setSettledRows(rows),250);return()=>clearTimeout(timer);},[rows]);
  useEffect(()=>{if(focusId)inputs.current.get(focusId)?.focus();},[focusId]);
  const compiled=useMemo(()=>compileGraphScene({version:2,dimension:"2D",combine,rows:settledRows}),[settledRows,combine]);
  useEffect(()=>{setParameters((current)=>{const next=Object.fromEntries(compiled.parameters.map((name)=>[name,current[name]??1]));return JSON.stringify(next)===JSON.stringify(current)?current:next;});},[compiled.parameters.join(",")]);
  useEffect(()=>{if(!active)return;let live=true;setListError(false);canvasRequest<CanvasSnapshot[]>(`${endpoint}/snapshots`).then((data)=>{if(live)setSnapshots(data);}).catch(()=>{if(live)setListError(true);});return()=>{live=false;};},[endpoint,listRun,active]);
  useEffect(()=>{
    setViewing(null);setBusy(null);
    const retry=lastOcrRun.current!==ocrRun;lastOcrRun.current=ocrRun;
    const readInk=retry||!!(importRequest?.readInk??selectedStrokes.length);
    if(!readInk){
      const formulas=splitFormulaRows(importRequest?.source??initialFormula);
      if(!formulas.length)return;
      const imported=replaceSceneSelection(formulas.map((formula,index)=>createRow(formula,index)));
      if(!imported){setError("Bảng chỉ chứa tối đa 8 dòng. Các dòng hiện tại được giữ nguyên.");return;}
      sourceRows.current=selectedStrokes.length?imported.sourceRowIds:[];rowInk.current.clear();
      setPendingOcr(importRequest?.needsConfirmation?imported.sourceRowIds:[]);
      setCombine("OVERLAY");setParameters({});setNote("");setCamera(seedCamera);setSpatialCamera(undefined);setSpatialDepth(0);setSpatialSurface(false);setViewMode("2D");setViewKey((value)=>value+1);
      setRows(imported.rows);setFocusId(imported.sourceRowIds[0]);setError(null);return;
    }
    if(!selectedStrokes.length)return;
    const groups=inkRows.regions;
    if(!groups.length)return;
    if(groups.length>8){setError("Vùng chọn có hơn 8 dòng. Hãy khoanh vùng ít phương trình hơn.");return;}
    const placeholders=groups.map((_,index)=>{const previous=retry?latestRows.current.find((row)=>row.id===sourceRows.current[index]):undefined;return previous?{...previous,expression:""}:createRow("",index);});
    sourceRows.current=placeholders.map((row)=>row.id);rowInk.current=new Map(placeholders.map((row,index)=>[row.id,groups[index].strokes]));
    setRows(placeholders);setSettledRows(placeholders);setPendingOcr(placeholders.map((row)=>row.id));
    setCombine("OVERLAY");setParameters({});setCamera(seedCamera);setSpatialCamera(undefined);setSpatialDepth(0);setSpatialSurface(false);setViewMode("2D");setViewKey((value)=>value+1);if(!retry)setNote("");
    let live=true,expired=false;const version=editVersion.current;setBusy("ocr");setError(null);setOcrProgress({done:0,total:groups.length});
    let timer:ReturnType<typeof setTimeout>;
    const deadline=new Promise<never>((_,reject)=>{timer=setTimeout(()=>{expired=true;reject(new Error("timeout"));},90000);});
    const recognition=recognizeFormulaRows(groups,recognizeHandwrittenMath,()=>live&&!expired&&editVersion.current===version,(done)=>setOcrProgress({done,total:groups.length}));
    Promise.race([recognition,deadline]).then((result)=>{if(!result||!live||editVersion.current!==version)return;
      const imported=replaceSceneSelection(result.formulas.map((formula,index)=>({...placeholders[index],expression:formula})));
      if(!imported){setError("Bảng đã đủ 8 dòng. Các dòng hiện tại được giữ nguyên; xóa một dòng không cần dùng rồi nhận dạng lại.");return;}
      sourceRows.current=imported.sourceRowIds;setRows(imported.rows);setFocusId(imported.sourceRowIds[(result.failed[0]??1)-1]);setPendingOcr(imported.sourceRowIds);
      rowInk.current=new Map(imported.sourceRowIds.map((id,index)=>[id,groups[index].strokes]));
      if(result.failed.length)setError(`Chưa đọc được dòng ${result.failed.join(", ")} trong vùng viết. Em nhập lại các dòng trống bên dưới.`);
    }).catch(()=>{if(live&&editVersion.current===version)setError("Chưa đọc được nét viết. Em có thể nhập mỗi phương trình vào một dòng rồi tiếp tục.");}).finally(()=>{clearTimeout(timer);if(live&&editVersion.current===version)setBusy(null);});
    return()=>{live=false;clearTimeout(timer);};
    // The parent keys each panel by its original stroke selection.
  },[ocrRun,importRequest?.key,initialFormula]);
  const editing=()=>{editVersion.current++;if(busy==="ocr")setBusy(null);setViewing(null);setError(null);setSuccess(null);};
  // Only editing the recognized text counts as manual correction; colors/visibility do not confirm OCR.
  const changeRow=(id:string,patch:Partial<SceneRow>)=>{editing();if(patch.expression!==undefined)setPendingOcr((current)=>current.filter((rowId)=>rowId!==id));setRows((current)=>current.map((row)=>row.id===id?{...row,...patch}:row));};
  const addRow=()=>{if(rows.length>=8)return;editing();const row=createRow("",rows.length);setRows((current)=>[...current,row]);setFocusId(row.id);};
  const removeRow=(id:string)=>{editing();sourceRows.current=sourceRows.current.filter((rowId)=>rowId!==id);setPendingOcr((current)=>current.filter((rowId)=>rowId!==id));const index=rows.findIndex((row)=>row.id===id),next=rows[index+1]??rows[index-1]??rows[index];setRows((current)=>current.length===1?[{...current[0],expression:""}]:current.filter((row)=>row.id!==id));if(next){setFocusId(next.id);requestAnimationFrame(()=>inputs.current.get(next.id)?.focus());}};
  const applyExample=(example:typeof examples[number])=>{editing();sourceRows.current=[];setPendingOcr([]);setRows(example.rows.map((source,index)=>createRow(source,index)));setCombine(example.combine);setParameters({});setDomain(3);setCamera(seedCamera);setSpatialCamera(undefined);setSpatialDepth(0);setSpatialSurface(false);setViewMode("2D");setViewKey((n)=>n+1);};
  const openSnapshot=(snapshot:CanvasSnapshot)=>{
    if(snapshot.settings.lab){onLab(snapshot);return;}
    if(!snapshot.settings.scene){onSingle(snapshot);return;}
    editVersion.current++;sourceRows.current=[];setBusy(null);setPendingOcr([]);setError(null);setSuccess(null);
    setRows(snapshot.settings.scene.rows.map((row)=>({...row})));setSettledRows(snapshot.settings.scene.rows.map((row)=>({...row})));setCombine(snapshot.settings.scene.combine);
    const spatial=snapshot.settings.view_mode==="3D";setViewMode(spatial?"3D":"2D");setSpatialCamera(spatial?snapshot.camera:undefined);setSpatialDepth(snapshot.settings.scene_depth??0);setSpatialSurface(snapshot.settings.scene_surface??false);
    setParameters({...snapshot.settings.parameters});setDomain(snapshot.settings.domain);setCamera(spatial?seedCamera:snapshot.camera);setViewKey((n)=>n+1);setNote(snapshot.note);setViewing(snapshot);
  };
  const typing=rows!==settledRows,hasErrors=Object.keys(compiled.errors).length>0;
  async function save(){
    if(busy||viewing||typing||hasErrors||!compiled.layers.length)return;
    if(needsConfirmation)setPendingOcr([]);
    setBusy("save");setError(null);setSuccess(null);
    try{
      await ensureInkSaved();
      const payload={expression:"y=0",settings:{...DEFAULT_GRAPH,domain,parameters,view_mode:viewMode,scene_depth:viewMode==="3D"?spatialDepth:0,scene_surface:viewMode==="3D"&&spatialSurface,scene:compiled.document},camera:viewMode==="3D"?spatialCamera??defaultCamera("3D"):camera,page_index:pageIndex,
        stroke_ids:rows.some((row)=>sourceRows.current.includes(row.id))?selectedStrokes.map((stroke)=>stroke.id):[],source_latex:"",note,explanation_id:null};
      const signature=JSON.stringify(payload);if(saveAction.current?.signature!==signature)saveAction.current={signature,id:generateUuid()};
      const saved=await canvasRequest<CanvasSnapshot>(`${endpoint}/snapshots`,{...payload,client_action_id:saveAction.current!.id});saveAction.current=null;
      setSnapshots((current)=>[saved,...current.filter((row)=>row.id!==saved.id)]);setListError(false);setSuccess("Đã lưu toàn bộ bảng đồ thị vào bài học. Giáo viên có thể mở lại đúng các biểu thức và tham số này.");
    }catch(err){setError(err instanceof Error?err.message:"Chưa lưu được bảng đồ thị.");}finally{setBusy(null);}
  }
  const locked=busy==="save"||!!viewing;
  const recognizedRows=rows.filter((row)=>pendingOcr.includes(row.id));
  const visibleCount=compiled.layers.filter((layer)=>layer.visible).length;
  const hasRegions=compiled.layers.some((layer)=>layer.visible&&layer.relations.some((relation)=>relation.operator!=="="));
  const canCreateSurfaces=compiled.layers.some((layer)=>layer.visible&&layer.relations.length===1&&layer.relations[0].operator==="=");
  const surfaceActive=viewMode==="3D"&&spatialSurface;
  const canSave=!busy&&!viewing&&!typing&&!hasErrors&&!!compiled.layers.length&&!needsConfirmation;
  const saveHint=viewing?"Bản lưu chỉ đọc · Có thể xoay và zoom.":busy==="save"?"Đang lưu đồ thị và góc nhìn…":busy==="ocr"?`Đang đọc nét viết ${ocrProgress.done}/${ocrProgress.total}…`:needsConfirmation?"Kiểm tra công thức nhận dạng trước khi lưu.":typing?"Đang cập nhật công thức…":hasErrors?"Sửa công thức được đánh dấu để lưu bài.":!compiled.layers.length?"Nhập một công thức để bắt đầu.":success?"Đã lưu vào bài học.":"Sẵn sàng lưu công thức, màu và góc nhìn.";
  function insertSnippet(prefix:string,suffix:string,placeholder:string){
    const row=rows.find((item)=>item.id===focusId)??rows[rows.length-1];if(!row||locked)return;
    const input=inputs.current.get(row.id),result=insertMathSnippet(row.expression,input?.selectionStart??row.expression.length,input?.selectionEnd??row.expression.length,prefix,suffix,placeholder);
    if(!result)return;changeRow(row.id,{expression:result.text});setFocusId(row.id);
    requestAnimationFrame(()=>{const element=inputs.current.get(row.id);element?.focus();element?.setSelectionRange(result.selectionStart,result.selectionEnd);});
  }
  return <aside hidden={!active} className={`${styles.panel} ${styles.scenePanel}`} data-mobile-pane={mobilePane} aria-label="Math View — bảng đồ thị nhiều biểu thức" onKeyDown={(event)=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==="s"){event.preventDefault();void save();}}}>
    <header className={styles.sceneHeading}>
      <div className={styles.sceneBrand}><span className={styles.sceneBrandIcon}><Orbit size={24}/></span><div><h2>Math View <span>Không gian toán học</span></h2><p>Viết công thức. Nhìn thấy mối liên hệ.</p></div></div>
      <div className={styles.sceneHeaderActions}>
        <button type="button" className={styles.button} aria-label="Mở chế độ một công thức" title="Mở chế độ một công thức" onClick={()=>onSingle()}><ChartNoAxesCombined size={16}/><span>Một công thức</span></button>
        <button type="button" className={styles.sceneExploreButton} onClick={()=>onLab()} aria-label="Khám phá nâng cao" title="Khám phá hàm tham số, vectơ và phép tính"><span>Khám phá nâng cao</span><ArrowUpRight size={15}/></button>
        <button type="button" className={styles.close} aria-label="Đóng Math View" onClick={onClose}><X size={19}/></button>
      </div>
    </header>
    <div className={styles.sceneMobileTabs} role="group" aria-label="Nội dung Math View"><button type="button" aria-pressed={mobilePane==="editor"} onClick={()=>setMobilePane("editor")}><Layers3 size={15}/> Công thức <span>{rows.length}</span></button><button type="button" aria-pressed={mobilePane==="graph"} onClick={()=>setMobilePane("graph")}><ChartNoAxesCombined size={15}/> Đồ thị</button></div>
    <div className={styles.sceneLayout}>
      <section ref={editorPane} className={styles.expressionPane} aria-label="Danh sách biểu thức">
        <div className={styles.expressionTitle}><div><Layers3 size={16}/><strong>Công thức của bạn</strong></div><span>{rows.length}/8</span></div>
        <p className={styles.sceneEditorHint}>Mỗi dòng một công thức · Enter để thêm dòng</p>
        {needsConfirmation?<section className={styles.ocrReview} aria-label="Kiểm tra công thức nhận dạng">
          <strong><HelpCircle size={15}/> Kiểm tra {recognizedRows.length} dòng nhận dạng</strong>
          <details><summary>Đối chiếu với nét viết</summary>{recognizedRows.map((row)=><div key={row.id}><span>Dòng {rows.findIndex((item)=>item.id===row.id)+1}</span>{rowInk.current.has(row.id)?<OcrInkPreview strokes={rowInk.current.get(row.id)!}/>:null}{row.expression?<OcrMathPreview latex={row.expression}/>:<p>Chưa đọc được. Nhập lại ở ô bên dưới.</p>}</div>)}{recognizedRows.some((row)=>!rowInk.current.has(row.id))?<OcrInkPreview strokes={selectedStrokes}/>:null}</details>
          <p>Sửa trực tiếp những ký hiệu chưa đúng.</p><button type="button" className={styles.primary} disabled={!!busy||typing||recognizedRows.some((row)=>!row.expression.trim()||!!compiled.errors[row.id])} onClick={()=>setPendingOcr([])}><Check size={15}/> Công thức đã đúng</button>
        </section>:null}
        <div className={styles.sceneExpressionList}>
        {rows.map((row,index)=><div key={row.id} className={`${styles.expressionCard} ${compiled.errors[row.id]?styles.expressionInvalid:""} ${!row.visible?styles.expressionHidden:""}`} style={{borderLeftColor:row.color}}>
          <div className={styles.expressionTop}>
            <span className={styles.expressionNumber}>Dòng {String(index+1).padStart(2,"0")}</span>
            <div className={styles.expressionActions}><input type="color" className={styles.rowColor} aria-label={`Màu dòng ${index+1}`} title="Đổi màu đường" value={row.color} disabled={locked} onChange={(event)=>changeRow(row.id,{color:event.target.value})}/>
            <button type="button" className={styles.expressionVisibility} aria-label={`${row.visible?"Ẩn":"Hiện"} dòng ${index+1}`} aria-pressed={row.visible} title={row.visible?"Ẩn đường này":"Hiện đường này"} disabled={locked} onClick={()=>changeRow(row.id,{visible:!row.visible})}>{row.visible?<Eye size={15}/>:<EyeOff size={15}/>}</button>
            <button type="button" className={styles.removeRow} aria-label={`Xóa dòng ${index+1}`} title="Xóa công thức" disabled={locked} onClick={()=>removeRow(row.id)}><Trash2 size={14}/></button></div>
          </div>
          <textarea ref={(element)=>{if(element)inputs.current.set(row.id,element);else inputs.current.delete(row.id);}} rows={2} className={styles.expressionInput} aria-label={`Biểu thức dòng ${index+1}`} aria-invalid={!!compiled.errors[row.id]} aria-describedby={compiled.errors[row.id]?`error-${row.id}`:undefined}
            value={row.expression} maxLength={500} disabled={locked} placeholder={index?"y = 2x + 1":"y = x²"} autoComplete="off" spellCheck={false} onFocus={()=>setFocusId(row.id)}
            onChange={(event)=>changeRow(row.id,{expression:event.target.value})} onKeyDown={(event)=>{if(event.key==="Enter"&&!event.shiftKey){event.preventDefault();addRow();}}}
            onPaste={(event)=>{const formulas=splitFormulaRows(event.clipboardData.getData("text"));if(formulas.length<2)return;event.preventDefault();editing();const imported=formulas.length<=8?importSceneFormulas(rows,formulas.map((formula,index)=>createRow(formula,rows.length+index)),[row.id]):null;if(!imported){setError("Không đủ chỗ cho các phương trình vừa dán. Bảng hiện tại được giữ nguyên.");return;}setRows(imported.rows);setPendingOcr((current)=>current.filter((id)=>id!==row.id));setFocusId(imported.sourceRowIds[0]);}}/>
          {compiled.errors[row.id]?<p id={`error-${row.id}`} className={styles.rowError}>{compiled.errors[row.id]}{compiled.errors[row.id].includes("3D")?<button type="button" className={styles.button} onClick={()=>onSingle(undefined,row.expression)}>Mở công thức 3D <ArrowUpRight size={13}/></button>:null}</p>
            :row.expression.trim()?<div className={styles.expressionMeta}><span>{compiled.layers.find((layer)=>layer.id===row.id)?.label??"Đang nhận diện…"}</span>{!row.visible?<span>Đang ẩn</span>:pendingOcr.includes(row.id)?<span className={styles.sceneReviewTag}>Cần kiểm tra</span>:<Check size={12}/>}</div>:<span className={styles.rowHint}>Ví dụ: y = sin(x) hoặc y ≥ x²</span>}
          {compiled.layers.find((layer)=>layer.id===row.id)?.hint?<p className={styles.rowNotice}>{compiled.layers.find((layer)=>layer.id===row.id)!.hint}</p>:null}
        </div>)}
        </div>
        <div className={styles.sceneMathKeys} role="group" aria-label="Chèn nhanh vào công thức đang chọn">{[{label:"x²",prefix:"",suffix:"^2",placeholder:"x"},{label:"sin",prefix:"sin(",suffix:")",placeholder:"x"},{label:"cos",prefix:"cos(",suffix:")",placeholder:"x"},{label:"√",prefix:"sqrt(",suffix:")",placeholder:"x"},{label:"π",prefix:"pi",suffix:"",placeholder:""}].map((key)=><button type="button" key={key.label} disabled={locked} onMouseDown={(event)=>event.preventDefault()} onClick={()=>insertSnippet(key.prefix,key.suffix,key.placeholder)}>{key.label}</button>)}</div>
        <button type="button" className={`${styles.button} ${styles.addExpression}`} disabled={rows.length>=8||locked} onClick={addRow}><Plus size={16}/> Thêm công thức</button>
        {hasRegions?<section className={styles.sceneRegionSection} aria-label="Chọn miền tô"><div className={styles.sceneSectionTitle}><Layers3 size={15}/><strong>Miền cần quan sát</strong></div><div className={styles.sceneRegionModes} role="group" aria-label="Cách tô miền">{([{value:"OVERLAY",title:"Từng miền",hint:"Tô mỗi bất phương trình riêng"},{value:"AND",title:"Miền chung",hint:"Thỏa mãn tất cả bất phương trình"},{value:"OR",title:"Miền hợp",hint:"Thỏa mãn ít nhất một bất phương trình"}] as const).map((mode)=><button type="button" key={mode.value} title={mode.hint} aria-pressed={combine===mode.value} disabled={locked} onClick={()=>{editing();setCombine(mode.value);}}>{mode.title}</button>)}</div><p>{combine==="AND"?"Phần tô thỏa mãn đồng thời các bất phương trình.":combine==="OR"?"Phần tô thỏa mãn ít nhất một bất phương trình.":"Mỗi bất phương trình có một miền tô riêng."}</p></section>:null}
        <section className={styles.sceneParameterSection} aria-label="Điều chỉnh miền và hệ số"><div className={styles.sceneSectionTitle}><Settings2 size={15}/><strong>Điều chỉnh</strong></div>
          <div className={styles.sceneValueCard}><GraphValueControl label="Miền khảo sát ±" value={domain} min={1} max={10} step={.5} defaultValue={3} disabled={locked} onChange={(value)=>{setDomain(value);setSuccess(null);}}/></div>
          {surfaceActive?<div className={styles.sceneValueCard}><GraphValueControl label="Độ kéo dài theo z" value={spatialDepth} min={.2} max={10} step={.1} defaultValue={3} disabled={locked} onChange={(value)=>{setSpatialDepth(value);setSuccess(null);}}/></div>:null}
          {compiled.parameters.map((name)=><div className={styles.sceneValueCard} key={name}><GraphValueControl label={`Hệ số ${name}`} value={parameters[name]??1} defaultValue={1} disabled={locked} onChange={(value)=>{setParameters((current)=>({...current,[name]:value}));setSuccess(null);}}/></div>)}
          {!compiled.parameters.length?<p className={styles.sceneParameterHint}>Dùng a, b, c trong công thức để có thanh chỉnh hệ số.</p>:null}
        </section>
        <details className={styles.sceneDrawer}><summary><BookOpen size={15}/> Công thức mẫu <ChevronRight size={14}/></summary><p>Chọn mẫu sẽ thay các công thức hiện tại.</p><div className={styles.sceneExampleGrid}>{examples.map((example)=><button type="button" key={example.label} disabled={locked} onClick={()=>applyExample(example)}>{example.label}<ArrowUpRight size={13}/></button>)}</div></details>
        {selectedStrokes.length?<details className={styles.sceneDrawer}><summary><Eye size={15}/> Nét viết đã chọn <ChevronRight size={14}/></summary><OcrInkPreview strokes={selectedStrokes}/><p>Khoanh vùng mới sẽ thay đúng các dòng đã chọn.</p><button type="button" className={styles.button} disabled={!!busy||!!viewing} onClick={()=>{editing();setOcrRun((n)=>n+1);}}>Nhận dạng lại</button></details>:null}
        <details className={styles.sceneDrawer}><summary><BookmarkCheck size={15}/> Đã lưu trong bài học <span>{snapshots.length}</span><ChevronRight size={14}/></summary>{listError?<p className={styles.rowError}>Chưa tải được bản lưu. <button type="button" className={styles.button} onClick={()=>setListRun((n)=>n+1)}>Thử lại</button></p>:!snapshots.length?<p>Chưa có bản lưu.</p>:snapshots.map((snapshot)=><button type="button" className={styles.saved} key={snapshot.id} disabled={busy==="save"} onClick={()=>openSnapshot(snapshot)}><strong>{snapshot.settings.lab?LAB_TITLES[snapshot.settings.lab.kind]:snapshot.settings.scene?`Bảng ${snapshot.settings.scene.rows.length} công thức`:snapshot.expression}</strong><small>{new Date(snapshot.created_at).toLocaleString("vi-VN")}</small></button>)}</details>
        <details className={styles.sceneDrawer}><summary><HelpCircle size={15}/> Cách sử dụng <ChevronRight size={14}/></summary><p>Viết y=x², y=sin(x), x²+y²=4 hoặc bất phương trình y≥x². Có thể dán nhiều phương trình, mỗi dòng một công thức.</p><p>Kéo trên hình để xoay trong 3D hoặc di chuyển trong 2D. Cuộn chuột để zoom. Nút Vừa hình đưa đồ thị về khung nhìn dễ quan sát.</p><p>Ctrl / ⌘ + S: lưu vào bài học. Bản nháp chỉ được giữ trong phiên làm việc này.</p></details>
      </section>
      <section className={styles.sceneWork} aria-label="Đồ thị">
        <div className={styles.sceneStatus}><div><span className={styles.scenePlotDot}/><strong>{viewing?"Bản lưu của bạn":"Đồ thị của bạn"}</strong><span>{typing?"Đang cập nhật…":`${visibleCount} công thức đang hiện`}</span></div><div className={styles.sceneDisplayModes}><button type="button" className={styles.sceneSurfaceButton} aria-pressed={surfaceActive} disabled={locked||!!busy||typing||!canCreateSurfaces} onClick={()=>{setSuccess(null);setSpatialSurface(!surfaceActive);setSpatialDepth(surfaceActive?0:spatialDepth>0?spatialDepth:3);setViewMode("3D");setSpatialCamera(undefined);setViewKey((n)=>n+1);}}><Layers3 size={15}/>{surfaceActive?"Về đường cong":"Tạo bề mặt kéo dài"}</button><div className={styles.singleViewTabs} role="group" aria-label="Chế độ bảng đồ thị"><button type="button" aria-pressed={viewMode==="2D"} onClick={()=>{setViewMode("2D");setSuccess(null);}}><ChartNoAxesCombined size={15}/> 2D</button><button type="button" aria-pressed={viewMode==="3D"&&!spatialSurface} onClick={()=>{setViewMode("3D");setSuccess(null);if(spatialSurface||spatialDepth>0){setSpatialSurface(false);setSpatialDepth(0);setSpatialCamera(undefined);setViewKey((n)=>n+1);}}}><Box size={15}/> 3D</button></div></div></div>
        {active?viewMode==="3D"?<GraphScene3DView key={`3D:${viewKey}`} scene={compiled} parameters={parameters} domain={domain} initialCamera={spatialCamera} onCameraChange={(value)=>{setSpatialCamera(value);setSuccess(null);}} depth={spatialDepth} surfaceMode={spatialSurface} onDepthChange={locked?undefined:(depth)=>{editing();setSpatialDepth(depth);if(depth===0)setSpatialSurface(false);}}/>:<GraphSceneView key={`2D:${viewKey}`} scene={compiled} parameters={parameters} domain={domain} initialCamera={camera} onCameraChange={(value)=>{setCamera(value);setSuccess(null);}}/>:null}
        <details className={styles.sceneObservation}><summary><BookOpen size={15}/> {viewing?"Ghi chú đã lưu":"Ghi lại điều bạn quan sát"}<ChevronRight size={14}/></summary>{viewing?<p>{viewing.note||"Bản lưu này chưa có ghi chú."}</p>:<textarea aria-label="Điều bạn quan sát được" className={styles.note} maxLength={1000} value={note} disabled={busy==="save"} onChange={(event)=>{setNote(event.target.value);setSuccess(null);}} placeholder="Hai đường gặp nhau ở đâu? Điều gì thay đổi khi bạn chỉnh hệ số?"/>}</details>
      </section>
    </div>
    <footer className={styles.sceneFooter}>
      <div className={styles.sceneFooterStatus} role="status" aria-live="polite">{error?<><HelpCircle size={17}/><span className={styles.sceneFooterError}>{error}</span></>:busy?<><LoaderCircle size={17} className={styles.sceneSpinner}/><span>{saveHint}</span></>:needsConfirmation||hasErrors?<><HelpCircle size={17}/><span>{saveHint} <button type="button" className={styles.plotTextButton} onClick={()=>{setMobilePane("editor");editorPane.current?.scrollTo({top:0});if(hasErrors)setFocusId(Object.keys(compiled.errors)[0]);}}>Kiểm tra công thức</button></span></>:<><CheckCircle2 size={17}/><span>{saveHint}<small>{draftSaved&&!viewing?"Bản nháp được giữ trong phiên hiện tại":""}</small></span></>}</div>
      {viewing?<button type="button" className={styles.primary} onClick={()=>{editing();sourceRows.current=[];setViewKey((n)=>n+1);}}>Tiếp tục khám phá <ArrowUpRight size={16}/></button>:<button type="button" className={styles.primary} disabled={!canSave} title={saveHint} onClick={save}>{busy==="save"?<LoaderCircle size={16} className={styles.sceneSpinner}/>:<Save size={16}/>} {busy==="save"?"Đang lưu…":"Lưu vào bài học"}</button>}
    </footer>
  </aside>;
}
