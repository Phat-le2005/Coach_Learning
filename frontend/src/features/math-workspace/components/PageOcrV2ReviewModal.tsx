"use client";
import { useEffect, useRef, useState } from "react";
import type { InkStroke, StepKind } from "@/lib/api/contracts";
import { STEP_KINDS } from "@/lib/api/contracts";
import { PageOcrReviewModal, STEP_LABELS, type PageOcrReviewModalProps, type PreparedOcrStep } from "./PageOcrReviewModal";
import { OcrInkPreview } from "./OcrInkPreview";
import { OcrMathPreview } from "./OcrMathPreview";
import { prepareCoreReview, recognizeCoreUnit, applyRecognition, declareStepBoundary, optionalLayout, sourceIdentity, type CoreReview } from "../utils/ocr-v2-core";
import { recognizeHandwrittenMathEvidence, type HandwrittenMathEvidence } from "../utils/handwritten-ocr";
import { buildScopeIR, groupIrUnits, ungroupIrUnit, reassignScope, lassoIds, type OcrSource, type RouteKind, type ScopeProposal } from "../utils/ocr-v2-geometry";
import { approveContentUnit, editContentUnit, editContainerRelation, confirmTranscriptionReadingOrder, getOrderedReviewUnits, getRootContentUnits, setSiblingReadingOrder, type ContentUnitKind } from "../utils/structured-transcription-ir";
import { loadTranscription, saveTranscription, transcriptionKey } from "../utils/ocr-transcription-storage";
import { generateUuid } from "../utils/ink-math";
import { IndexedDbBatchJournal } from "../utils/batch-journal";
import { createOcrReviewDraft, editOcrReviewDraft, selectOcrDraftKind, approveOcrDraft } from "../utils/ocr-review-draft";
import styles from "../MathWorkspace.module.css";

interface Props extends Omit<PageOcrReviewModalProps, "regions" | "pageStrokes" | "preparedSteps" | "onPreparedSaved"> {
  blockedByBatch?: boolean; source: OcrSource; isSourceCurrent: () => boolean; beforeSave: () => Promise<void>;
}
const contentLabels: Record<string, string> = { MATH: "Công thức", TEXT: "Văn bản", UNKNOWN: "Chưa xác định", STRUCTURE: "Nhóm nội dung" };
const relationLabels: Record<string, string> = { UNKNOWN: "Chưa xác định", SYSTEM: "Hệ phương trình", ALTERNATIVES: "Các trường hợp", FRACTION: "Phân số", INDEPENDENT: "Các phần độc lập" };
const reviewLabels: Record<string, string> = { NEEDS_REVIEW: "Cần đối chiếu", APPROVED: "Đã xác nhận", SKIPPED: "Để xem lại" };

/** Uses the existing MathWorkspace canvas; no research routes, evaluator or new backend contract. */
export function PageOcrV2ReviewModal(props: Props) {
  const [review, setReview] = useState<CoreReview | null>(null), [busy, setBusy] = useState(true), [error, setError] = useState("");
  const [selected, setSelected] = useState(""), [checks, setChecks] = useState<string[]>([]), [picked, setPicked] = useState<string[]>([]);
  const [kind, setKind] = useState<RouteKind>("MATH"), [relation, setRelation] = useState<"SYSTEM" | "ALTERNATIVES" | "INDEPENDENT" | "UNKNOWN">("UNKNOWN");
  const [stepKind, setStepKind] = useState<StepKind | "">(""), [boundaryChecked, setBoundaryChecked] = useState(false), [prepared, setPrepared] = useState<PreparedOcrStep[] | null>(null);
  const [storageStatus, setStorageStatus] = useState("Đang mở bản chép đã lưu…"), [lasso, setLasso] = useState(false);
  const [storageBlocked,setStorageBlocked]=useState(false), persistedVersion=useRef<string|undefined>(undefined);
  const skipStoredSave=useRef(false);
  const key = useRef(""), runId = useRef(0), live = useRef(true), latest = useRef(review), sourceGuard = useRef(props.isSourceCurrent), saveQueue = useRef<Promise<void>>(Promise.resolve());
  const path = useRef<{x:number;y:number;pressure:number}[]>([]), [polygon, setPolygon] = useState<typeof path.current>([]);
  const dialogRef=useRef<HTMLDivElement>(null);
  useEffect(()=>{const previous=document.activeElement instanceof HTMLElement?document.activeElement:null;dialogRef.current?.querySelector<HTMLButtonElement>('button')?.focus();return()=>previous?.focus();},[]);
  latest.current = review; sourceGuard.current = props.isSourceCurrent;
  const stale = !props.isSourceCurrent();
  const unit = review?.ir.contentUnits.find(u => u.id === selected), rows = review ? getOrderedReviewUnits(review.ir.contentUnits) : [];
  const ink = review?.ir.sourceSnapshot.strokes ?? [], strokes = ink.filter(s => unit?.sourceStrokeIds.includes(s.id));
  const locked = busy || stale || storageBlocked || Boolean(props.blockedByBatch) || Boolean(unit && review?.savedUnitIds.includes(unit.id));
  async function persist(value:CoreReview){persistedVersion.current=await saveTranscription(key.current,value,persistedVersion.current);}
  function buildUnifiedGeminiReview(source: OcrSource, attemptId: string): CoreReview {
    const pen = source.strokes.filter(s => s.tool === "PEN");
    const scope: ScopeProposal = {
      id: "gemini-1",
      regionIds: ["gemini-region-1"],
      rawLabel: "formula",
      rawScore: 1,
      kind: "MATH",
      strokeIds: pen.map(s => s.id),
      candidateStrokeIds: pen.map(s => s.id),
      coverage: Object.fromEntries(pen.map(s => [s.id, 1])),
      flags: ["GEMINI_UNIFIED_PAGE_SCOPE"],
      method: "GEMINI_UNIFIED_PAGE_SCOPE",
    };
    const scopes = pen.length ? [scope] : [];
    const ir = { ...buildScopeIR(source, scopes), attemptId };
    return {
      schemaVersion: "ocr-core-review/1",
      ir,
      scopes,
      mode: "HYBRID",
      detectorStatus: "GEMINI_VISION",
      relations: [],
      evidence: [],
      savedUnitIds: [],
      savedSteps: [],
      boundaries: [],
    };
  }

  async function runUnitRecognition(unitStrokes: InkStroke[]): Promise<HandwrittenMathEvidence> {
    if (props.apiClient && props.attemptId) {
      try {
        const res = await props.apiClient.recognizeMathInk(props.accessToken ?? "", props.attemptId, {
          page_index: props.pageIndex,
          stroke_ids: unitStrokes.map(s => s.id),
          strokes: unitStrokes,
        });
        if (res.suggested_step_type && STEP_KINDS.includes(res.suggested_step_type)) {
          setStepKind(prev => prev || res.suggested_step_type);
        }
        return {
          rawLatex: res.latex,
          latex: res.latex,
          tokenIds: [1],
          durationMs: 1,
          encoderMs: 1,
          decoderMs: 1,
        };
      } catch (err: unknown) {
        console.warn("Gemini OCR recognition failed, falling back to local CoMER:", err);
      }
    }
    return recognizeHandwrittenMathEvidence(unitStrokes);
  }

  async function recognize(ids: string[], base: CoreReview, generation: number) {
    let current = base;
    for (const id of ids) {
      if (!live.current || runId.current !== generation || !sourceGuard.current()) break;
      const evidence = await recognizeCoreUnit(current.ir, id, runUnitRecognition);
      if (!live.current || runId.current !== generation || !sourceGuard.current()) break;
      current = applyRecognition(latest.current ?? current, evidence); latest.current = current; setReview(current);
      if (evidence.error) setError("Gemini OCR chưa nhận diện được hoặc có lỗi kết nối. Em có thể nhập tay và thử lại.");
    }
  }
  useEffect(() => {
    live.current = true; const generation = ++runId.current;
    void (async () => { try {
      key.current = `gemini-v2:${await transcriptionKey(props.attemptId!, sourceIdentity(props.source))}`;
      const stored = await loadTranscription(key.current);
      if (!live.current || generation !== runId.current) return;
      persistedVersion.current=stored?.localVersion;
      skipStoredSave.current=Boolean(stored);
      let initial = stored ?? (props.apiClient && props.attemptId ? buildUnifiedGeminiReview(props.source, props.attemptId) : await prepareCoreReview(props.source, props.attemptId!, optionalLayout));
      // A server commit can finish before the local transcription ledger is written.
      // Recover only frozen, explicit boundary actions verified against the actual server step.
      if(stored&&props.apiClient){
        const journal=await new IndexedDbBatchJournal().load(props.attemptId!);
        const committed=journal?.entries.filter(e=>e.state==='COMMITTED'&&e.serverStepId&&stored.boundaries.some(b=>b.actionId===e.actionId&&b.unitId===e.draftId)&&!stored.savedUnitIds.includes(e.draftId))??[];
        if(committed.length){const fresh=await props.apiClient.getMathAttempt(props.accessToken??'',props.attemptId!);
          const recovered=committed.filter(e=>(fresh.steps??[]).some(s=>s.id===e.serverStepId&&s.step_type===e.content.step_type&&s.content_latex===e.content.content_latex&&(s.explanation_text??null)===(e.content.explanation_text??null))).map(e=>({unitId:e.draftId,stepId:e.serverStepId,actionId:e.actionId}));
          if(recovered.length){initial={...initial,savedUnitIds:[...initial.savedUnitIds,...recovered.map(s=>s.unitId)],savedSteps:[...initial.savedSteps,...recovered]};skipStoredSave.current=false;}
        }
      }
      if (!live.current || generation !== runId.current || !sourceGuard.current()) return;
      if (JSON.stringify(initial.ir.sourceSnapshot.strokes) !== JSON.stringify(props.source.strokes.filter(s => s.tool === "PEN")) || initial.ir.sourceRevision !== props.source.sourceRevision) throw Error("STORED_SOURCE_MISMATCH");
      latest.current = initial; setReview(initial); setSelected(getRootContentUnits(initial.ir.contentUnits)[0]?.id ?? "");
      const pendingIds = initial.ir.contentUnits.filter(u => u.kind === "MATH" && u.role === "ATOMIC" && (!stored || !u.rawRecognition || u.rawRecognition === "UNRESOLVED")).slice(0,12).map(u=>u.id);
      if (pendingIds.length) await recognize(pendingIds, initial, generation);
      setStorageStatus(stored ? "Đã mở lại bản chép đã lưu" : "Bản chép mới; phần chưa nhận diện cần đối chiếu");

    } catch (e) { if (live.current && generation === runId.current) setError(String(e)); } finally { if (live.current && generation === runId.current) setBusy(false); } })();
    return () => { live.current = false; runId.current++; };
    // Snapshot identity is immutable for this modal session.
  }, []);
  useEffect(() => { if (!review || !key.current) return;
    if(skipStoredSave.current){skipStoredSave.current=false;return;}
    setStorageStatus("Đang lưu bản chép trên thiết bị…");
    const snapshot = structuredClone(review);
    saveQueue.current = saveQueue.current.catch(()=>undefined).then(()=>persist(snapshot)).then(()=>{if(live.current)setStorageStatus("Đã lưu bản chép trên thiết bị");}).catch(e=>{if(live.current){setStorageBlocked(true);setStorageStatus("Chưa lưu được bản chép — hãy xuất file backup rồi tải lại");setError(String(e));}});
  }, [review]);
  function change(fn: (r:CoreReview)=>CoreReview) { if (locked || !review) return; try { const next=fn(review);next.scopes=next.scopes.map(s=>{const u=next.ir.contentUnits.find(u=>u.id===`unit-${s.id}`);return u&&u.role==='ATOMIC'?{...s,kind:u.kind as RouteKind}:s;});setReview(next);latest.current=next;setError("");setBoundaryChecked(false); }catch(e){setError(String(e));} }
  function move(direction:number) { if(!review||!unit)return;if(review.savedUnitIds.length){setError("Không đổi thứ tự sau khi đã lưu bước. Các bước hiện có được giữ nguyên.");return;}const parent=rows.find(r=>r.unit.id===unit.id)!.parentId;const ids=rows.filter(r=>r.parentId===parent).map(r=>r.unit.id),i=ids.indexOf(unit.id),j=i+direction;if(j<0||j>=ids.length)return;[ids[i],ids[j]]=[ids[j],ids[i]];change(r=>({...r,ir:setSiblingReadingOrder(r.ir,parent,ids)})); }
  function reassign(ids:string[]) { change(r=>{
    if(r.ir.contentUnits.some(u=>u.role==='CONTAINER')||r.savedUnitIds.length)throw Error("Không đổi phạm vi sau khi tạo cấu trúc/lưu bước. Bản chép cũ được giữ; đối chiếu hoặc mở snapshot mới.");
    const scopes=reassignScope(r.scopes,ids,`manual-${generateUuid()}`,kind).filter(s=>s.strokeIds.length);
    return {...r,scopes,ir:{...buildScopeIR(props.source,scopes,r.ir),attemptId:props.attemptId}};
  });setChecks([]);setPicked([]); }
  async function retry() { if(!review||!unit||locked)return;setBusy(true);try{await recognize([unit.id],review,runId.current);}finally{setBusy(false);} }
  async function prepareStep() { if(!review||!unit||!stepKind||!boundaryChecked||locked)return;setBusy(true);
    try { await props.beforeSave(); const boundary=declareStepBoundary(review,unit.id,stepKind,generateUuid());
      const old=review.boundaries.find(b=>b.unitId===unit.id&&b.stepKind===stepKind&&b.contentLatex===boundary.contentLatex&&b.explanationText===boundary.explanationText);
      const plan=old??boundary;const next={...review,boundaries:[...review.boundaries.filter(b=>b.unitId!==unit.id),plan]};
      await saveQueue.current;await persist(next);setReview(next);
      const region={id:unit.id,strokes,bounds:unit.bounds};
      let draft=createOcrReviewDraft({localId:unit.id,pageIndex:props.pageIndex,regionIds:unit.sourceRegionIds,strokeIds:unit.sourceStrokeIds});
      draft=editOcrReviewDraft(draft,{contentLatex:plan.contentLatex??"",explanationText:plan.explanationText});draft=selectOcrDraftKind(draft,plan.stepKind);draft=approveOcrDraft(draft);
      setPrepared([{region,draft,actionId:plan.actionId}]);setError("");
    }catch(e){setError(String(e));}finally{setBusy(false);}
  }
  const preparedSaved=useRef((saved:{unitId:string;stepId?:string|null;actionId:string}[])=>{
    if(!saved.length)return;setReview(old=>{if(!old)return old;const fresh=saved.filter(s=>!old.savedUnitIds.includes(s.unitId));return fresh.length?{...old,savedUnitIds:[...old.savedUnitIds,...fresh.map(s=>s.unitId)],savedSteps:[...old.savedSteps,...fresh]}:old;});
  });
  function download() { if(!review)return;const url=URL.createObjectURL(new Blob([JSON.stringify(review,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`transcription-${props.attemptId}-page-${props.pageIndex+1}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
  async function close() { runId.current++;live.current=false;try{await saveQueue.current;if(latest.current&&key.current&&!storageBlocked)await persist(latest.current);props.onClose();}catch(e){live.current=true;setStorageBlocked(true);setBusy(false);setError(`Chưa lưu được bản chép; hãy xuất backup: ${String(e)}`);} }
  if(prepared)return <PageOcrReviewModal {...props} regions={prepared.map(p=>p.region)} pageStrokes={props.source.strokes} preparedSteps={prepared} beforePreparedSave={async()=>{await saveQueue.current;const stored=await loadTranscription(key.current);if(stored?.localVersion!==persistedVersion.current)throw Error("REVIEW_CHANGED_IN_ANOTHER_TAB");await props.beforeSave();}} onPreparedSaved={preparedSaved.current} onClose={()=>setPrepared(null)}/>;
  return <div ref={dialogRef} className={`${styles.modalOverlay} ${styles.pageReviewOverlay}`} role="dialog" aria-modal="true" aria-busy={busy} aria-label="Bản chép OCR V2" data-testid="ocr-v2-main-review" data-engine={review?.mode??"STARTING"} data-stale={String(stale)} onKeyDown={event=>{event.stopPropagation();if(event.key==='Escape'){event.preventDefault();void close();}if(event.key==='Tab'){const fields=[...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary')].filter(e=>e.getClientRects().length);const first=fields[0],last=fields.at(-1);if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}}}}>
    <div className={styles.pageReviewModal}>
      <header className={styles.pageReviewHeader}><div><h2>Kiểm tra bản chép · Trang {props.pageIndex+1}</h2><p>Đối chiếu nét viết và xác nhận nội dung trước khi chọn bước để lưu.</p></div><button className={styles.buttonSecondary} onClick={()=>void close()}>Đóng</button></header>
      <div className={styles.pageReviewNotice} role="status">{busy?"Đang nhận diện…":`${review?.ir.approvedUnitCount??0}/${review?.ir.contentUnits.length??0} phần đã xác nhận`} · {storageStatus}
        {stale&&<p role="alert">Nét viết đã thay đổi. Bản chép cũ vẫn được giữ; hãy đóng và trích xuất lại trang trước khi xác nhận hoặc lưu.</p>}{error&&<p role="alert">{error}</p>}

      </div>
      <div className={styles.pageReviewContent}>
        <nav className={styles.pageReviewList} aria-label="Đơn vị bản chép">{rows.map(({unit:u,depth})=><div key={u.id} style={{paddingLeft:depth*12}}><input type="checkbox" aria-label={`Chọn phần ${u.readingOrder+1}`} checked={checks.includes(u.id)} disabled={busy||stale} onChange={e=>setChecks(a=>e.target.checked?[...a,u.id]:a.filter(id=>id!==u.id))}/><button className={selected===u.id?styles.pageReviewRowActive:styles.pageReviewRow} data-testid="ocr-v2-unit" onClick={()=>{setSelected(u.id);setBoundaryChecked(false);setStepKind("");setPicked([]);}}>{u.readingOrder+1}. {contentLabels[u.kind]??u.kind}<small>{u.sourceStrokeIds.length} nét · {review?.savedUnitIds.includes(u.id)?"Đã lưu bước":reviewLabels[u.reviewStatus]??u.reviewStatus}</small></button></div>)}</nav>
        <div className={styles.pageReviewEditor}>{unit&&review?<>
          <h3 className={styles.reviewTaskTitle}>Đối chiếu với nét viết</h3><OcrInkPreview strokes={strokes}/><details className={styles.reviewEvidence}><summary>Kết quả nhận dạng ban đầu</summary><pre style={{margin:0,padding:8,maxHeight:160,overflow:"auto",whiteSpace:"pre-wrap",overflowWrap:"anywhere",background:"#f2f6f2"}} data-testid="ocr-v2-raw">{unit.rawRecognition??"Chưa nhận dạng được"}</pre></details>
          {unit.role==='CONTAINER'?<label>Quan hệ <select className={styles.formSelect} value={unit.structureKind??"UNKNOWN"} disabled={locked} onChange={e=>change(r=>({...r,ir:editContainerRelation(r.ir,unit.id,e.target.value as typeof relation)}))}>{["UNKNOWN","SYSTEM","ALTERNATIVES","FRACTION","INDEPENDENT"].map(k=><option key={k} value={k}>{relationLabels[k]}</option>)}</select></label>:<>
            <label>Loại nội dung <select className={styles.formSelect} data-testid="ocr-v2-kind" value={unit.kind} disabled={locked} onChange={e=>change(r=>({...r,ir:editContentUnit(r.ir,unit.id,{kind:e.target.value as ContentUnitKind})}))}>{["MATH","TEXT","UNKNOWN"].map(k=><option key={k} value={k}>{contentLabels[k]}</option>)}</select></label>
            <label>Bản chép đã đối chiếu <textarea className={styles.formInput} data-testid="ocr-v2-content" value={unit.approvedContent??unit.rawRecognition??""} disabled={locked} onChange={e=>change(r=>({...r,ir:editContentUnit(r.ir,unit.id,{content:e.target.value})}))}/></label>
            {unit.kind==='MATH'&&<div className={styles.mathPreviewBox} data-testid="ocr-v2-math-preview"><OcrMathPreview latex={unit.approvedContent??unit.rawRecognition??""}/></div>}
            <button className={styles.buttonSecondary} onClick={()=>void retry()} disabled={locked||unit.kind!=="MATH"}>Thử nhận dạng lại</button>

          </>}
          <button className={styles.buttonSecondary} data-testid="ocr-v2-approve" disabled={locked} onClick={()=>change(r=>({...r,ir:approveContentUnit(r.ir,unit.id)}))}>Xác nhận phần này</button>
          {unit.role==='CONTAINER'&&<button className={styles.buttonSecondary} disabled={locked||review.savedUnitIds.length>0} onClick={()=>change(r=>({...r,ir:ungroupIrUnit(r.ir,unit.id)}))}>Tháo cấu trúc, giữ các đơn vị con</button>}
          <div><button className={styles.buttonSecondary} disabled={locked} onClick={()=>move(-1)}>Đưa lên</button><button className={styles.buttonSecondary} disabled={locked} onClick={()=>move(1)}>Đưa xuống</button><button className={styles.buttonSecondary} disabled={busy||stale} data-testid="ocr-v2-order" onClick={()=>change(r=>({...r,ir:confirmTranscriptionReadingOrder(r.ir)}))}>Xác nhận thứ tự đọc</button> · {review.ir.readingOrderStatus==="CONFIRMED"?"Đã xác nhận thứ tự":"Thứ tự cần đối chiếu"}</div>
          {review.relations.length>0&&<p>Đề xuất quan hệ chưa xác định: {review.relations.length}. Dấu ngoặc không tự quyết định hệ hoặc bước chấm; chọn các đơn vị và xác nhận quan hệ nếu phù hợp.</p>}
          <details><summary>Điều chỉnh phạm vi / cấu trúc</summary><p>Chọn nhiều đơn vị bên trái để gộp; hoặc khoanh nét trong trang để tách/gán lại. Nét gốc không đổi.</p>
            <select className={styles.formSelect} aria-label="Loại phạm vi mới" value={kind} onChange={e=>setKind(e.target.value as RouteKind)}>{["MATH","TEXT","UNKNOWN"].map(k=><option key={k} value={k}>{contentLabels[k]}</option>)}</select>
            <button className={styles.buttonSecondary} disabled={locked||checks.length<2} onClick={()=>reassign([...new Set(review.ir.contentUnits.filter(u=>checks.includes(u.id)).flatMap(u=>u.sourceStrokeIds))])}>Gộp phạm vi đã chọn</button>
            <button className={styles.buttonSecondary} disabled={locked} onClick={()=>setLasso(!lasso)}>{lasso?"Dừng khoanh nét":"Khoanh nét để tách"}</button>
            <svg width="794" height="1123" viewBox="0 0 794 1123" style={{width:300,height:'auto',maxWidth:'100%',border:'1px solid #ccc',touchAction:'none'}} onPointerDown={e=>{if(!lasso||locked)return;e.currentTarget.setPointerCapture(e.pointerId);const b=e.currentTarget.getBoundingClientRect();path.current=[{x:(e.clientX-b.left)/b.width,y:(e.clientY-b.top)/b.height,pressure:.5}];setPolygon(path.current);}} onPointerMove={e=>{if(!lasso||!e.currentTarget.hasPointerCapture(e.pointerId))return;const b=e.currentTarget.getBoundingClientRect();path.current.push({x:(e.clientX-b.left)/b.width,y:(e.clientY-b.top)/b.height,pressure:.5});setPolygon([...path.current]);}} onPointerUp={e=>{if(!e.currentTarget.hasPointerCapture(e.pointerId))return;e.currentTarget.releasePointerCapture(e.pointerId);setPicked(lassoIds(props.source,path.current));path.current=[];setPolygon([]);}}>
              {ink.map(s=><polyline key={s.id} points={s.points.map(p=>`${p.x*794},${p.y*1123}`).join(' ')} fill="none" stroke={picked.includes(s.id)?'#1665bf':'#17392d'} strokeWidth={Math.max(2,s.width)}/>)}<polyline points={polygon.map(p=>`${p.x*794},${p.y*1123}`).join(' ')} fill="none" stroke="blue"/>
            </svg><p>{picked.length} nét được chọn</p><button className={styles.buttonSecondary} disabled={locked||!picked.length} onClick={()=>reassign(picked)}>Tạo phạm vi từ nét đã khoanh</button>
            <select className={styles.formSelect} aria-label="Quan hệ bản chép" value={relation} onChange={e=>setRelation(e.target.value as typeof relation)}>{["UNKNOWN","SYSTEM","ALTERNATIVES","INDEPENDENT"].map(k=><option key={k} value={k}>{relationLabels[k]}</option>)}</select><button className={styles.buttonSecondary} disabled={locked||checks.length<2||review.savedUnitIds.length>0} onClick={()=>change(r=>({...r,ir:groupIrUnits(r.ir,checks,relation)}))}>Tạo cấu trúc từ các đơn vị</button>
          </details>
          <details className={styles.reviewSave}><summary>Lưu thành bước giải</summary><section aria-label="Ranh giới bước giải"><p>Chọn phần đã đối chiếu, xác nhận thứ tự rồi quyết định có lưu thành một bước riêng hay không. Nhóm nội dung và phần chưa rõ được giữ trong bản chép để em xem lại.</p>
            <label><input data-testid="ocr-v2-boundary" type="checkbox" checked={boundaryChecked} disabled={locked||unit.role!=="ATOMIC"||!['MATH','TEXT'].includes(unit.kind)||rows.find(r=>r.unit.id===unit.id)?.parentId!==null} onChange={e=>setBoundaryChecked(e.target.checked)}/>Tôi chọn đơn vị này là một bước giải riêng</label>
            <label>Loại bước <select className={styles.formSelect} data-testid="ocr-v2-step-kind" value={stepKind} disabled={locked} onChange={e=>setStepKind(e.target.value as StepKind)}><option value="">Tự chọn loại bước</option>{STEP_KINDS.map(k=><option key={k} value={k}>{STEP_LABELS[k]}</option>)}</select></label>
            <button className={styles.buttonSecondary} data-testid="ocr-v2-prepare-save" disabled={locked||!boundaryChecked||!stepKind||unit.reviewStatus!=="APPROVED"||review.ir.readingOrderStatus!=="CONFIRMED"} onClick={()=>void prepareStep()}>Tiếp tục lưu bước đã chọn</button>
          </section></details>
        </>:!busy?<p>Chưa tạo được bản chép. Nét gốc vẫn được giữ; đóng và thử lại hoặc dùng nhập bước thủ công có sẵn.</p>:null}</div>
      </div>
      <footer className={styles.pageReviewFooter}><button className={styles.buttonSecondary} disabled={!review} onClick={download}>Xuất bản chép và nguồn nét</button><p>Bản chép được giữ trên thiết bị và chưa gửi đi chấm.</p><details className={styles.reviewEvidence}><summary>Thông tin xử lý</summary><p>Chế độ: {review?.mode??"STARTING"} · Phát hiện vùng: {review?.detectorStatus??"PENDING"}</p></details></footer>
    </div>
  </div>;
}
