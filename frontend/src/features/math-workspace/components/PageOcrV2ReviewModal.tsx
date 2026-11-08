"use client";
import { useEffect, useRef, useState } from "react";
import { Check, CheckCircle2, Download, FilePenLine, LoaderCircle, ScanLine, X } from "lucide-react";
import type { InkStroke, StepKind } from "@/lib/api/contracts";
import { STEP_KINDS } from "@/lib/api/contracts";
import type { PageOcrReviewModalProps } from "./PageOcrReviewModal";
import { OcrInkPreview } from "./OcrInkPreview";
import { OcrMathPreview } from "./OcrMathPreview";
import { recognizeCoreUnit, applyRecognition, declareStepBoundary, sourceIdentity, type CoreReview } from "../utils/ocr-v2-core";
import type { HandwrittenMathEvidence } from "../utils/handwritten-ocr";
import { buildScopeIR, groupIrUnits, ungroupIrUnit, reassignScope, lassoIds, type OcrSource, type RouteKind } from "../utils/ocr-v2-geometry";
import { approveContentUnit, editContentUnit, editContainerRelation, confirmTranscriptionReadingOrder, getOrderedReviewUnits, getRootContentUnits, setSiblingReadingOrder, type ContentUnitKind } from "../utils/structured-transcription-ir";
import { loadTranscription, saveTranscription, transcriptionKey } from "../utils/ocr-transcription-storage";
import { generateUuid } from "../utils/ink-math";
import { BrowserBatchLock, IndexedDbBatchJournal } from "../utils/batch-journal";
import { SequentialBatchManager, type BatchJournal, type BatchRunResult } from "../utils/batch-manager";
import { createBatchApi } from "../utils/ocr-batch-adapter";
import { buildGeminiStepReview, suggestedStepKind } from "../utils/gemini-step-review";
import styles from "../MathWorkspace.module.css";

const CONTENT_LABELS: Record<ContentUnitKind, string> = { MATH: "Công thức toán", TEXT: "Lời văn", UNKNOWN: "Chưa phân loại", STRUCTURE: "Nhóm nội dung" };
const STEP_LABELS: Record<StepKind, string> = {
  ASSUMPTION: "Giả thiết / điều kiện", DERIVATIVE_CALCULATION: "Tính đạo hàm",
  ROOT_FINDING: "Tìm nghiệm", SIGN_TABLE: "Bảng xét dấu", VARIATION_TABLE: "Bảng biến thiên",
  CONCLUSION: "Kết luận", EXPLANATION: "Diễn giải", CUSTOM: "Bước tự do",
};

interface Props extends Omit<PageOcrReviewModalProps, "regions" | "pageStrokes" | "preparedSteps" | "onPreparedSaved"> {
  blockedByBatch?: boolean; source: OcrSource; isSourceCurrent: () => boolean; beforeSave: () => Promise<void>;
}
/** Reviews proposed steps on the existing MathWorkspace canvas before saving. */
export function PageOcrV2ReviewModal(props: Props) {
  const [review, setReview] = useState<CoreReview | null>(null), [busy, setBusy] = useState(true), [error, setError] = useState("");
  const [selected, setSelected] = useState(""), [checks, setChecks] = useState<string[]>([]), [picked, setPicked] = useState<string[]>([]);
  const [kind, setKind] = useState<RouteKind>("MATH"), [relation, setRelation] = useState<"SYSTEM" | "ALTERNATIVES" | "INDEPENDENT" | "UNKNOWN">("UNKNOWN");
  const [stepKind, setStepKind] = useState<StepKind | "">(""), [boundaryChecked, setBoundaryChecked] = useState(false);
  const [pausedJournal, setPausedJournal] = useState<BatchJournal | null>(null), [saving, setSaving] = useState(false);
  const [mobilePanel, setMobilePanel] = useState<"editor" | "source">("editor");
  const [storageStatus, setStorageStatus] = useState("Đang mở bản chép đã lưu…"), [lasso, setLasso] = useState(false);
  const [storageBlocked,setStorageBlocked]=useState(false), persistedVersion=useRef<string|undefined>(undefined);
  const skipStoredSave=useRef(false);
  const key = useRef(""), runId = useRef(0), live = useRef(true), latest = useRef(review), sourceGuard = useRef(props.isSourceCurrent), saveQueue = useRef<Promise<void>>(Promise.resolve());
  const path = useRef<{x:number;y:number;pressure:number}[]>([]), [polygon, setPolygon] = useState<typeof path.current>([]);
  const dialogRef=useRef<HTMLDivElement>(null);
  useEffect(()=>{const previous=document.activeElement instanceof HTMLElement?document.activeElement:null;const overflow=document.body.style.overflow;document.body.style.overflow="hidden";dialogRef.current?.querySelector<HTMLButtonElement>('button')?.focus();return()=>{document.body.style.overflow=overflow;previous?.focus();};},[]);
  latest.current = review; sourceGuard.current = props.isSourceCurrent;
  const stale = !props.isSourceCurrent();
  const unit = review?.ir.contentUnits.find(u => u.id === selected), rows = review ? getOrderedReviewUnits(review.ir.contentUnits) : [];
  const ink = review?.ir.sourceSnapshot.strokes ?? [], strokes = ink.filter(s => unit?.sourceStrokeIds.includes(s.id));
  const unitCommitted = Boolean(unit && review?.savedUnitIds.includes(unit.id));
  const isSaved = unitCommitted && !pausedJournal;
  const locked = busy || saving || stale || storageBlocked || Boolean(pausedJournal || props.blockedByBatch) || unitCommitted;
  const pendingUnits = review ? getRootContentUnits(review.ir.contentUnits).filter(u => !review.savedUnitIds.includes(u.id)) : [];
  const allSaved = Boolean(review && review.savedUnitIds.length && !pendingUnits.length && !pausedJournal);
  const canSaveAll = !busy && !saving && !stale && !storageBlocked && !pausedJournal && !props.blockedByBatch && boundaryChecked && pendingUnits.length > 0
    && pendingUnits.every(u => u.role === "ATOMIC" && ["MATH", "TEXT"].includes(u.kind) && (u.approvedContent ?? u.rawRecognition)?.trim()
      && Boolean(u.id === selected ? stepKind : suggestedStepKind(review, u.id)));
  async function persist(value:CoreReview){persistedVersion.current=await saveTranscription(key.current,value,persistedVersion.current);}
  async function runUnitRecognition(unitStrokes: InkStroke[]): Promise<HandwrittenMathEvidence> {
    if (!props.apiClient || !props.attemptId) {
      throw new Error("Chưa kết nối được Gemini OCR. Em có thể nhập và xác nhận bản chép thủ công.");
    }
    const started = performance.now();
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
      tokenIds: [],
      durationMs: performance.now() - started,
      encoderMs: 0,
      decoderMs: 0,
    };
  }

  async function recognize(ids: string[], base: CoreReview, generation: number) {
    let current = base;
    for (const id of ids) {
      if (!live.current || runId.current !== generation || !sourceGuard.current()) break;
      const evidence = await recognizeCoreUnit(current.ir, id, runUnitRecognition);
      if (!live.current || runId.current !== generation || !sourceGuard.current()) break;
      current = applyRecognition(latest.current ?? current, evidence); latest.current = current; setReview(current);
      if (evidence.error) setError(`${evidence.error.replace(/^Error: /, "")} Em có thể sửa bản chép thủ công rồi xác nhận.`);
    }
  }
  useEffect(() => {
    live.current = true; const generation = ++runId.current;
    void (async () => { try {
      key.current = `gemini-v2:${await transcriptionKey(props.attemptId!, sourceIdentity(props.source))}`;
      const stored = await loadTranscription(key.current);
      if (!live.current || generation !== runId.current) return;
      latest.current = stored ?? null;
      persistedVersion.current=stored?.localVersion;
      skipStoredSave.current=Boolean(stored);
      let initial = stored;
      const upgradeUneditedDraft = stored && !stored.segmentationVersion && !stored.savedUnitIds.length && !stored.boundaries.length && !stored.ir.contentUnits.some(u => u.isManuallyCorrected);
      if (!initial || upgradeUneditedDraft) {
        if (!props.apiClient || !props.attemptId) throw Error("Chưa kết nối được Gemini OCR.");
        const result = await props.apiClient.recognizeMathInk(props.accessToken ?? "", props.attemptId, {
          page_index: props.pageIndex, stroke_ids: props.source.strokes.filter(s => s.tool === "PEN").map(s => s.id), strokes: props.source.strokes,
        });
        initial = buildGeminiStepReview(props.source, props.attemptId, result);
        skipStoredSave.current = false;
      }
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
      const firstId = getRootContentUnits(initial.ir.contentUnits).find(u => !initial.savedUnitIds.includes(u.id))?.id ?? getRootContentUnits(initial.ir.contentUnits)[0]?.id ?? "";
      latest.current = initial; setReview(initial); setSelected(firstId); setStepKind(suggestedStepKind(initial, firstId));
      setStorageStatus(stored ? "Đã khôi phục bản chép" : "Đối chiếu, sửa bản chép và xác nhận trước khi lưu");
    } catch (e) { if (live.current && generation === runId.current) {
      setError(String(e));
      const fallback = latest.current ?? buildGeminiStepReview(props.source, props.attemptId!); latest.current = fallback; setReview(fallback); setSelected(fallback.ir.contentUnits[0]?.id ?? "");
    } } finally { if (live.current && generation === runId.current) setBusy(false); } })();
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
  async function retry() { if(!review||!unit||locked)return;setError("");setBoundaryChecked(false);setBusy(true);try{await recognize([unit.id],review,runId.current);}finally{setBusy(false);} }
  async function beforeStepSave() {
    await saveQueue.current;
    const stored = await loadTranscription(key.current);
    if (stored?.localVersion !== persistedVersion.current) throw Error("Bản chép đã đổi ở tab khác. Hãy đóng và mở lại để đối chiếu.");
    await props.beforeSave();
  }
  function applySaveResult(result: BatchRunResult, base: CoreReview) {
    if (result.status === "LOCKED") {
      setError("Một tab khác đang lưu bài. Hãy đợi hoàn tất rồi thử lại.");
      return;
    }
    const committed = result.journal.entries.filter(entry => entry.state === "COMMITTED" && entry.serverStepId);
    const fresh = committed.filter(entry => !base.savedUnitIds.includes(entry.draftId));
    const next = { ...base, savedUnitIds: [...base.savedUnitIds, ...fresh.map(entry => entry.draftId)],
      savedSteps: [...base.savedSteps, ...fresh.map(entry => ({ unitId: entry.draftId, stepId: entry.serverStepId, actionId: entry.actionId }))] };
    latest.current = next;
    setReview(next);
    if (result.status === "COMPLETE") {
      setPausedJournal(null);
      props.onBatchUpdate?.(null);
      props.onBatchComplete?.(result.attempt);
      setError("");
      setBoundaryChecked(false);
      const nextId = getRootContentUnits(next.ir.contentUnits).find(u => !next.savedUnitIds.includes(u.id))?.id;
      if (nextId) { setSelected(nextId); setStepKind(suggestedStepKind(next, nextId)); }
    } else {
      setPausedJournal(result.journal);
      props.onBatchUpdate?.(result.journal);
      setError("Chưa xác nhận được kết quả lưu. Nội dung được giữ nguyên; chọn “Thử lưu lại” để kiểm tra và tiếp tục.");
    }
  }
  async function prepareStep() {
    if (!review || !canSaveAll || !props.apiClient || !props.attemptId) return;
    setSaving(true); setError("");
    try {
      await props.beforeSave();
      // This action explicitly confirms the visible content, reading order and
      // selected step boundary together. The immutable source remains unchanged.
      let confirmed = review.ir;
      for (const candidate of pendingUnits) confirmed = approveContentUnit(confirmed, candidate.id);
      confirmed = confirmTranscriptionReadingOrder(confirmed);
      const plans = pendingUnits.map(candidate => {
        const type = candidate.id === selected ? stepKind : suggestedStepKind(review, candidate.id);
        const boundary = declareStepBoundary({ ...review, ir: confirmed }, candidate.id, type as StepKind, generateUuid());
        return review.boundaries.find(b => b.unitId === candidate.id && b.stepKind === type && b.contentLatex === boundary.contentLatex && b.explanationText === boundary.explanationText) ?? boundary;
      });
      const next = { ...review, ir: confirmed, boundaries: [...review.boundaries.filter(b => !pendingUnits.some(u => u.id === b.unitId)), ...plans] };
      await saveQueue.current;
      await persist(next);
      latest.current = next;
      const manager = new SequentialBatchManager(createBatchApi(props.apiClient, props.accessToken ?? "", beforeStepSave), new IndexedDbBatchJournal(), new BrowserBatchLock());
      const result = await manager.start(props.attemptId, generateUuid(), plans.map(plan => ({ draftId: plan.unitId, actionId: plan.actionId,
        approved: true as const, stepType: plan.stepKind, contentLatex: plan.contentLatex, explanationText: plan.explanationText || null })));
      applySaveResult(result, next);
    } catch (e) { setError(e instanceof Error && e.message.startsWith("LATEX_NOT_REPRESENTABLE")
      ? "Công thức chưa hiển thị được. Hãy kiểm tra lại ký hiệu; với lời văn, chọn loại nội dung “Lời văn”."
      : e instanceof Error ? e.message : "Chưa lưu được bước giải. Hãy thử lại."); }
    finally { setSaving(false); }
  }
  async function resumeSave() {
    if (!pausedJournal || saving || busy || stale || storageBlocked || !review || !props.apiClient || !props.attemptId) return;
    setSaving(true); setError("");
    try {
      const manager = new SequentialBatchManager(createBatchApi(props.apiClient, props.accessToken ?? "", beforeStepSave), new IndexedDbBatchJournal(), new BrowserBatchLock());
      applySaveResult(await manager.resume(props.attemptId), review);
    } catch (e) { setError(e instanceof Error ? e.message : "Chưa thể tiếp tục lưu."); }
    finally { setSaving(false); }
  }
  function download() { if(!review)return;const url=URL.createObjectURL(new Blob([JSON.stringify(review,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`transcription-${props.attemptId}-page-${props.pageIndex+1}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000); }
  async function close() { if(saving)return;runId.current++;live.current=false;try{await saveQueue.current;if(latest.current&&key.current&&!storageBlocked)await persist(latest.current);props.onClose();}catch(e){live.current=true;setStorageBlocked(true);setBusy(false);setError(`Chưa lưu được bản chép; hãy xuất backup: ${String(e)}`);} }
  return <div ref={dialogRef} className={`${styles.modalOverlay} ${styles.pageReviewOverlay} ${styles.transcriptionOverlay}`}
    role="dialog" aria-modal="true" aria-busy={busy || saving} aria-labelledby="gemini-transcription-title"
    data-testid="ocr-v2-main-review" data-engine="GEMINI" data-stale={String(stale)}
    onKeyDown={event => {
      event.stopPropagation();
      if (event.key === "Escape") { event.preventDefault(); void close(); }
      if (event.key === "Tab") {
        const fields = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), summary')].filter(e => e.getClientRects().length);
        const first = fields[0], last = fields.at(-1);
        if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
        else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
      }
    }}>
    <div className={styles.transcriptionModal}>
      <header className={styles.transcriptionHeader}>
        <div className={styles.transcriptionHeading}>
          <span className={styles.transcriptionIcon}><FilePenLine size={23} aria-hidden="true" /></span>
          <div><div className={styles.transcriptionEyebrow}>GEMINI OCR · TRANG {props.pageIndex + 1}</div>
            <h2 id="gemini-transcription-title">Kiểm tra bản chép</h2>
            <p>Đối chiếu nét gốc, sửa nội dung rồi lưu vào bài làm.</p>
          </div>
        </div>
        <button type="button" className={styles.transcriptionClose} aria-label="Đóng" disabled={saving} onClick={() => void close()}><X size={20} aria-hidden="true" /></button>
      </header>
      <div className={styles.transcriptionProgress} aria-label="Tiến trình bản chép">
        <span data-complete={!busy}><CheckCircle2 size={16} aria-hidden="true" /> Nhận diện</span><i aria-hidden="true" />
        <span aria-current={!isSaved ? "step" : undefined}><FilePenLine size={16} aria-hidden="true" /> Đối chiếu & sửa</span><i aria-hidden="true" />
        <span data-complete={isSaved}><CheckCircle2 size={16} aria-hidden="true" /> Lưu bước giải</span>
        <small role="status" aria-live="polite">{busy ? "Đang nhận diện…" : saving ? "Đang lưu bước…" : storageStatus}</small>
      </div>
      {(error || review?.segmentationWarning || stale || props.blockedByBatch && !pausedJournal) && <div className={styles.transcriptionAlert} role="alert">
        {stale ? "Nét viết đã thay đổi. Đóng cửa sổ và trích xuất lại trang mới nhất để lưu." : error || review?.segmentationWarning || "Có bước đang chờ phục hồi. Đóng cửa sổ để xử lý rồi tiếp tục."}
      </div>}
      <div className={styles.transcriptionMobileSwitch} role="group" aria-label="Chế độ đối chiếu">
        <button type="button" aria-pressed={mobilePanel === "editor"} onClick={() => setMobilePanel("editor")}><FilePenLine size={15} aria-hidden="true" /> Bản chép</button>
        <button type="button" aria-pressed={mobilePanel === "source"} onClick={() => setMobilePanel("source")}><ScanLine size={15} aria-hidden="true" /> Nét gốc</button>
      </div>
      <div className={styles.transcriptionBody} data-mobile-panel={mobilePanel}>
        <section className={styles.transcriptionSource} aria-label="Đối chiếu nét gốc">
          <div className={styles.transcriptionCardHeading}><h3>Nét viết gốc</h3><span>Trang {props.pageIndex + 1}</span></div>
          <p className={styles.transcriptionHint}>Giữ nguyên nét viết để đối chiếu từng ký hiệu.</p>
          <div className={styles.transcriptionInk}><OcrInkPreview strokes={strokes} label="" /></div>
          {review?.segmentationVersion && <p className={styles.transcriptionStepCount} data-testid="ocr-step-count">Đề xuất {rows.length} bước giải · kiểm tra trước khi lưu</p>}
          <nav className={styles.transcriptionUnits} aria-label="Các bước đề xuất">
            {rows.map(({ unit: u, depth }) => <button type="button" key={u.id}
              className={selected === u.id ? styles.transcriptionUnitActive : styles.transcriptionUnit}
              data-testid="ocr-v2-unit" aria-current={selected === u.id ? "true" : undefined} disabled={busy || saving}
              style={{ marginLeft: depth * 10 }} onClick={() => { setSelected(u.id); setBoundaryChecked(false); setStepKind(suggestedStepKind(review, u.id)); setPicked([]); setMobilePanel("editor"); }}>
              <span><strong>Bước {u.readingOrder + 1} · {review?.stepHints?.[u.id]?.title ?? CONTENT_LABELS[u.kind]}</strong><small>{STEP_LABELS[suggestedStepKind(review, u.id) as StepKind] ?? CONTENT_LABELS[u.kind]} · {u.sourceStrokeIds.length} nét</small></span>
              <span className={styles.transcriptionBadge}>{review?.savedUnitIds.includes(u.id) ? "Đã lưu" : u.reviewStatus === "APPROVED" ? "Đã xác nhận" : "Cần đối chiếu"}</span>
            </button>)}
          </nav>
          <details className={styles.transcriptionRaw}><summary>Kết quả Gemini ban đầu</summary>
            <pre data-testid="ocr-v2-raw">{unit?.rawRecognition || "Chưa có kết quả nhận diện."}</pre>
          </details>
          <button type="button" className={styles.transcriptionRetry} onClick={() => void retry()} disabled={locked || unit?.kind !== "MATH"}>
            <ScanLine size={16} aria-hidden="true" /> Nhận diện lại bằng Gemini
          </button>
        </section>
        <section className={styles.transcriptionEditor} aria-label="Chỉnh sửa bản chép">
          {unit && review ? <>
            <div className={styles.transcriptionCardHeading}><h3>{isSaved ? "Bản chép đã lưu" : "Bản chép của em"}</h3>
              {unit.role === "ATOMIC" && <select className={styles.transcriptionKind} aria-label="Loại nội dung" data-testid="ocr-v2-kind" value={unit.kind} disabled={locked}
                onChange={e => change(r => ({ ...r, ir: editContentUnit(r.ir, unit.id, { kind: e.target.value as ContentUnitKind }) }))}>
                {(["MATH", "TEXT", "UNKNOWN"] as const).map(k => <option key={k} value={k}>{CONTENT_LABELS[k]}</option>)}
              </select>}
            </div>
            {unit.role === "ATOMIC" ? <>
              <label className={styles.transcriptionField}>Nội dung có thể chỉnh sửa
                <textarea className={styles.transcriptionTextarea} rows={6} spellCheck={false} data-testid="ocr-v2-content"
                  placeholder="Nhập hoặc sửa nội dung theo nét viết gốc…" value={unit.approvedContent ?? unit.rawRecognition ?? ""} disabled={locked}
                  onChange={e => change(r => ({ ...r, ir: editContentUnit(r.ir, unit.id, { content: e.target.value }) }))} />
              </label>
              {unit.kind === "MATH" && review.stepHints?.[unit.id]?.explanationText && <label className={styles.transcriptionField}>Lời văn đi kèm
                <textarea className={styles.transcriptionTextarea} rows={2} value={review.stepHints[unit.id].explanationText} disabled={locked}
                  onChange={e => change(r => ({ ...r, stepHints: { ...r.stepHints, [unit.id]: { ...r.stepHints![unit.id], explanationText: e.target.value } } }))} />
              </label>}
              <div className={styles.transcriptionPreviewHeading}><span>Xem trước {unit.kind === "MATH" ? "công thức" : "nội dung"}</span><small>Cập nhật khi em sửa</small></div>
              <div className={styles.transcriptionPreview} data-testid="ocr-v2-math-preview">
                {unit.kind === "MATH" ? <OcrMathPreview latex={unit.approvedContent ?? unit.rawRecognition ?? ""} /> : <p>{unit.approvedContent ?? unit.rawRecognition ?? "Chưa có nội dung"}</p>}
              </div>
            </> : <p className={styles.transcriptionHint}>Đây là nhóm nội dung. Mở tùy chọn nâng cao để đối chiếu các phần con hoặc tháo nhóm trước khi lưu từng bước.</p>}
            <details className={styles.transcriptionAdvanced}>
              <summary>Thứ tự & phân chia nâng cao</summary>
              <div className={styles.transcriptionAdvancedBody}>
                <p>Chọn các phần cần gộp hoặc khoanh nét để chia lại. Nét gốc được giữ nguyên.</p>
                <div className={styles.transcriptionAdvancedActions}>
                  <button type="button" className={styles.buttonSecondary} disabled={locked} onClick={() => move(-1)}>Đưa lên</button>
                  <button type="button" className={styles.buttonSecondary} disabled={locked} onClick={() => move(1)}>Đưa xuống</button>
                  <button type="button" className={styles.buttonSecondary} disabled={locked} data-testid="ocr-v2-order" onClick={() => change(r => ({ ...r, ir: confirmTranscriptionReadingOrder(r.ir) }))}>Xác nhận thứ tự đọc</button>
                  <button type="button" className={styles.buttonSecondary} data-testid="ocr-v2-approve" disabled={locked} onClick={() => change(r => ({ ...r, ir: approveContentUnit(r.ir, unit.id) }))}>Xác nhận phần này</button>
                </div>
                <div className={styles.transcriptionAdvancedActions}>{rows.map(({ unit: u }) => <label key={u.id}><input type="checkbox" checked={checks.includes(u.id)} disabled={locked}
                  onChange={e => setChecks(a => e.target.checked ? [...a, u.id] : a.filter(id => id !== u.id))} /> Phần {u.readingOrder + 1}</label>)}</div>
                <select className={styles.formSelect} aria-label="Loại phạm vi mới" value={kind} disabled={locked} onChange={e => setKind(e.target.value as RouteKind)}>
                  {(["MATH", "TEXT", "UNKNOWN"] as const).map(k => <option key={k} value={k}>{CONTENT_LABELS[k]}</option>)}
                </select>
                <div className={styles.transcriptionAdvancedActions}>
                  <button type="button" className={styles.buttonSecondary} disabled={locked || checks.length < 2} onClick={() => reassign([...new Set(review.ir.contentUnits.filter(u => checks.includes(u.id)).flatMap(u => u.sourceStrokeIds))])}>Gộp phần đã chọn</button>
                  <button type="button" className={styles.buttonSecondary} disabled={locked} onClick={() => setLasso(!lasso)}>{lasso ? "Dừng khoanh nét" : "Khoanh nét để tách"}</button>
                </div>
                {lasso && <><svg width="794" height="1123" viewBox="0 0 794 1123" className={styles.transcriptionLasso}
                  onPointerDown={e => { if (locked) return; e.currentTarget.setPointerCapture(e.pointerId); const b = e.currentTarget.getBoundingClientRect(); path.current = [{ x: (e.clientX - b.left) / b.width, y: (e.clientY - b.top) / b.height, pressure: .5 }]; setPolygon(path.current); }}
                  onPointerMove={e => { if (!e.currentTarget.hasPointerCapture(e.pointerId)) return; const b = e.currentTarget.getBoundingClientRect(); path.current.push({ x: (e.clientX - b.left) / b.width, y: (e.clientY - b.top) / b.height, pressure: .5 }); setPolygon([...path.current]); }}
                  onPointerUp={e => { if (!e.currentTarget.hasPointerCapture(e.pointerId)) return; e.currentTarget.releasePointerCapture(e.pointerId); setPicked(lassoIds(props.source, path.current)); path.current = []; setPolygon([]); }}>
                  {ink.map(s => <polyline key={s.id} points={s.points.map(p => `${p.x * 794},${p.y * 1123}`).join(" ")} fill="none" stroke={picked.includes(s.id) ? "#1665bf" : "#17392d"} strokeWidth={Math.max(2, s.width)} />)}
                  <polyline points={polygon.map(p => `${p.x * 794},${p.y * 1123}`).join(" ")} fill="none" stroke="blue" />
                </svg><button type="button" className={styles.buttonSecondary} disabled={locked || !picked.length} onClick={() => reassign(picked)}>Tạo phần từ {picked.length} nét đã khoanh</button></>}
                <select className={styles.formSelect} aria-label="Quan hệ bản chép" value={relation} disabled={locked} onChange={e => setRelation(e.target.value as typeof relation)}>
                  <option value="UNKNOWN">Chưa xác định quan hệ</option><option value="SYSTEM">Hệ phương trình</option><option value="ALTERNATIVES">Các trường hợp</option><option value="INDEPENDENT">Các phần độc lập</option>
                </select>
                <button type="button" className={styles.buttonSecondary} disabled={locked || checks.length < 2 || review.savedUnitIds.length > 0} onClick={() => change(r => ({ ...r, ir: groupIrUnits(r.ir, checks, relation) }))}>Nhóm các phần đã chọn</button>
                {unit.role === "CONTAINER" && <>
                  <label>Quan hệ trong nhóm<select className={styles.formSelect} value={unit.structureKind ?? "UNKNOWN"} disabled={locked} onChange={e => change(r => ({ ...r, ir: editContainerRelation(r.ir, unit.id, e.target.value as typeof relation) }))}>
                    <option value="UNKNOWN">Chưa xác định</option><option value="SYSTEM">Hệ phương trình</option><option value="ALTERNATIVES">Các trường hợp</option><option value="INDEPENDENT">Độc lập</option><option value="FRACTION">Phân số</option>
                  </select></label>
                  <button type="button" className={styles.buttonSecondary} disabled={locked || review.savedUnitIds.length > 0} onClick={() => change(r => ({ ...r, ir: ungroupIrUnit(r.ir, unit.id) }))}>Tháo nhóm, giữ các phần con</button>
                </>}
              </div>
            </details>
          </> : <div className={styles.transcriptionEmpty}>{busy ? <><LoaderCircle className={styles.transcriptionSpinner} size={28} /><h3>Gemini đang đọc nét viết…</h3><p>Bản chép sẽ xuất hiện tại đây để em chỉnh sửa.</p></> : <><h3>Chưa mở được bản chép</h3><p>Nét gốc vẫn được giữ. Đóng cửa sổ và trích xuất lại.</p></>}</div>}
        </section>
      </div>
      <footer className={styles.transcriptionFooter}>
        {allSaved ? <div className={styles.transcriptionSaved} role="status"><CheckCircle2 size={22} aria-hidden="true" /><div><strong>Đã lưu {review?.savedUnitIds.length} bước giải vào bài làm</strong><p>Đóng cửa sổ, rồi chọn “Nộp bài & kiểm tra” để chấm từng bước.</p></div></div>
          : <div className={styles.transcriptionSaveFields}>
            <label className={styles.transcriptionConfirm}><input data-testid="ocr-v2-boundary" type="checkbox" checked={boundaryChecked} disabled={busy || saving || stale || storageBlocked || Boolean(pausedJournal || props.blockedByBatch)} onChange={e => setBoundaryChecked(e.target.checked)} />
              <span>Em đã đối chiếu nội dung, cách chia và thứ tự các bước giải.</span></label>
            <label className={styles.transcriptionStepKind}>Loại bước đang chọn<select data-testid="ocr-v2-step-kind" value={stepKind} disabled={locked} onChange={e => { const type = e.target.value as StepKind | ""; setStepKind(type); if (unit) change(r => ({ ...r, stepHints: { ...r.stepHints, [unit.id]: { ...r.stepHints?.[unit.id], title: r.stepHints?.[unit.id]?.title ?? (type ? STEP_LABELS[type] : "Bước giải"), stepKind: type } } })); }}>
              <option value="">Chọn loại bước…</option>{STEP_KINDS.map(k => <option key={k} value={k}>{STEP_LABELS[k]}</option>)}
            </select></label>
          </div>}
        <div className={styles.transcriptionFooterActions}>
          <button type="button" className={styles.transcriptionExport} disabled={!review || saving} onClick={download}><Download size={16} aria-hidden="true" /><span>Xuất bản chép</span></button>
          {allSaved ? <button type="button" className={styles.transcriptionPrimary} onClick={() => void close()}><Check size={17} aria-hidden="true" /> Đóng & tiếp tục</button>
            : pausedJournal ? <button type="button" className={styles.transcriptionPrimary} disabled={saving || stale || storageBlocked} onClick={() => void resumeSave()}>{saving ? <LoaderCircle className={styles.transcriptionSpinner} size={17} /> : <Check size={17} />} Thử lưu lại</button>
              : <button type="button" className={styles.transcriptionPrimary} data-testid="ocr-v2-prepare-save" disabled={!canSaveAll} onClick={() => void prepareStep()}>{saving ? <LoaderCircle className={styles.transcriptionSpinner} size={17} aria-hidden="true" /> : <Check size={17} aria-hidden="true" />}{saving ? "Đang lưu…" : pendingUnits.length > 1 ? `Xác nhận & lưu ${pendingUnits.length} bước` : "Xác nhận & lưu bước"}</button>}
        </div>
      </footer>
    </div>
  </div>;
}
