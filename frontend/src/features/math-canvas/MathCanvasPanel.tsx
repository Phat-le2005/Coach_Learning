"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { Box, ChartNoAxesCombined, Maximize2, Minimize2, X, Orbit, Waves, Mountain, Play, Pause, RotateCcw, ArrowUpRight, Check, PencilLine, Layers3 } from "lucide-react";
import type { InkStroke } from "@/lib/api/contracts";
import { OcrInkPreview } from "@/features/math-workspace/components/OcrInkPreview";
import { OcrMathPreview } from "@/features/math-workspace/components/OcrMathPreview";
import { recognizeHandwrittenMath } from "@/features/math-workspace/utils/handwritten-ocr";
import { generateUuid } from "@/features/math-workspace/utils/ink-math";
import { canvasRequest, type CanvasExplanation, type CanvasSnapshot } from "./api";
import { DEFAULT_GRAPH, defaultCamera, parseMathExpression, type MathExpression, type GraphSettings, type GraphCamera, type NumericGraphSetting } from "./expression";
import { describeGraphView, isSpatialView, recommendGraph, resolveGraphView, type GraphRenderMode } from "./presentation";
import { createExplorationDraft } from "./exploration";
import { GraphScenePanel, type SceneImportRequest } from "./GraphScenePanel";
import { GraphValueControl } from "./GraphValueControl";
import { analyzeXPolynomialEquation, describeEquationRoot } from "./univariate-equation";
import { insertMathSnippet } from "./formula-editing";
import { createCoefficientExploration } from "./coefficient-exploration";
import { equationInkRows, splitFormulaRows } from "./multi-formula";
import styles from "./MathCanvas.module.css";

const GraphView = dynamic(() => import("./GraphView").then((module) => module.GraphView), {
  ssr: false,
  loading: () => <p className={styles.muted} role="status">Đang mở khung nhìn công thức…</p>,
});
const MathLab = dynamic(() => import("./MathLab").then((module) => module.MathLab), { ssr: false });
const GRAPH_EXAMPLES = [
  { label: "Mặt cong", hint: "Chỉnh độ cong theo hai trục", formula: "z=a*x²+b*y²", icon: Mountain },
  { label: "Mặt cầu", hint: "Thử thay đổi bán kính r", formula: "x²+y²+z²=r²", icon: Orbit },
  { label: "Mặt yên ngựa", hint: "Hai chiều cong ngược nhau", formula: "z=a*x²-b*y²", icon: Box },
  { label: "Sóng không gian", hint: "Quan sát biên độ của sóng", formula: "z=a*sin(x)*cos(y)", icon: Waves },
  { label: "Parabol 2D", hint: "Một đường cong trên mặt phẳng", formula: "y=a*x²+b", icon: ChartNoAxesCombined },
];

interface Props { attemptId: string; pageIndex: number; selectedStrokes: InkStroke[]; initialFormula?: string; ensureInkSaved: () => Promise<void>; onClose: () => void }
export function MathCanvasPanel({ attemptId, pageIndex, selectedStrokes, initialFormula = "", ensureInkSaved, onClose }: Props) {
  const initialRows=useMemo(()=>equationInkRows(selectedStrokes),[selectedStrokes]);
  const multiSelection=!initialFormula.trim()&&initialRows.regions.length>1&&initialRows.regions.length<=8;
  const [mode,setMode]=useState<"scene"|"single"|"lab">(multiSelection?"scene":"single");
  const [sceneOpened,setSceneOpened]=useState(multiSelection);
  const [sceneImport,setSceneImport]=useState<SceneImportRequest|undefined>(()=>multiSelection?{key:JSON.stringify(["ink",selectedStrokes.map((stroke)=>stroke.id)]),source:"",readInk:true,needsConfirmation:true}:undefined);
  const [labSnapshot,setLabSnapshot]=useState<CanvasSnapshot|undefined>();
  const [single,setSingle]=useState<{snapshot?:CanvasSnapshot;formula?:string}>({});
  const props={attemptId,pageIndex,selectedStrokes,initialFormula,ensureInkSaved,onClose};
  return <>
    {sceneOpened?<GraphScenePanel {...props} importRequest={sceneImport} active={mode==="scene"} onLab={(snapshot)=>{setLabSnapshot(snapshot);setMode("lab");}} onSingle={(snapshot,formula)=>{setSingle({snapshot,formula});setMode("single");}}/>:null}
    <SingleFormulaPanel key={single.snapshot?.id??single.formula??"single"} {...props} initialFormula={single.formula??initialFormula} selectedStrokes={single.formula?[]:selectedStrokes} initialSnapshot={single.snapshot} active={mode==="single"} onScene={(source,readInk,needsConfirmation=false)=>{setSceneImport({key:JSON.stringify([source,readInk,needsConfirmation,selectedStrokes.map((s)=>s.id)]),source,readInk,needsConfirmation});setSceneOpened(true);setMode("scene");}}/>
    {mode==="lab"?<aside className={`${styles.panel} ${styles.labPanel}`} aria-label="Math Lab trong bài học"><div className={styles.labPanelNav}><button className={styles.button} onClick={()=>setMode("scene")}>← Bảng biểu thức</button><button className={styles.close} aria-label="Đóng phòng khám phá" onClick={onClose}>×</button></div><MathLab key={labSnapshot?.id??"draft"} attemptId={attemptId} pageIndex={pageIndex} ensureInkSaved={ensureInkSaved} initialSnapshot={labSnapshot}/></aside>:null}
  </>;
}

function SingleFormulaPanel({ attemptId, pageIndex, selectedStrokes, initialFormula = "", ensureInkSaved, onClose, initialSnapshot, active, onScene }: Props & {initialSnapshot?:CanvasSnapshot;active:boolean;onScene:(source:string,readInk:boolean,needsConfirmation?:boolean)=>void}) {
  const [source, setSource] = useState(initialSnapshot?.source_latex||initialSnapshot?.expression||initialFormula);
  const [plottedSource, setPlottedSource] = useState(initialSnapshot?.source_latex||initialSnapshot?.expression||"");
  const [model, setModel] = useState<MathExpression | null>(()=>initialSnapshot?parseMathExpression(initialSnapshot.expression):null);
  const [graphVisible, setGraphVisible] = useState(!!initialSnapshot);
  const [settings, setSettings] = useState<GraphSettings>(initialSnapshot?.settings??{ ...DEFAULT_GRAPH, view_mode: "2D" });
  const [parameterDefaults, setParameterDefaults] = useState<Record<string, number>>({ ...initialSnapshot?.settings.parameters });
  const [camera, setCamera] = useState<GraphCamera>(initialSnapshot?.camera??defaultCamera("2D"));
  const [explanation, setExplanation] = useState<CanvasExplanation | null>(initialSnapshot?.explanation??null);
  const [busy, setBusy] = useState<"ocr" | "ai" | "save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [snapshots, setSnapshots] = useState<CanvasSnapshot[]>([]);
  const [listError, setListError] = useState(false);
  const [viewing, setViewing] = useState<CanvasSnapshot | null>(initialSnapshot??null);
  const [isSnapshotCopy, setIsSnapshotCopy] = useState(false);
  const [resumedCamera, setResumedCamera] = useState<{ mode: GraphRenderMode; camera: GraphCamera } | null>(null);
  const [run, setRun] = useState(0);
  const [readSingleInk, setReadSingleInk] = useState(false);
  const [animating, setAnimating] = useState<string | null>(null);
  const [needsOcrConfirm, setNeedsOcrConfirm] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [graphReset, setGraphReset] = useState(0);
  const [equationSource, setEquationSource] = useState<string | null>(null);
  const formulaInput = useRef<HTMLTextAreaElement>(null);
  const parameterControls = useRef<HTMLElement>(null);
  const editVersion = useRef(0);
  const analyzedSource = useRef<string | null>(null);
  const liveSettings = useRef(settings); liveSettings.current = settings;
  const pendingSave = useRef<{ signature: string; action: string } | null>(null);
  const inkRows = useMemo(() => equationInkRows(selectedStrokes), [selectedStrokes]);
  const formulaRows = useMemo(() => splitFormulaRows(source), [source]);
  const endpoint = `attempts/${attemptId}`;

  useEffect(() => {
    if (!active) return;
    let live = true;
    canvasRequest<CanvasSnapshot[]>(`${endpoint}/snapshots`).then((rows) => { if (live) setSnapshots(rows.filter((row)=>!row.settings.scene&&!row.settings.lab)); })
      .catch(() => { if (live) setListError(true); });
    return () => { live = false; };
  }, [endpoint, active]);

  useEffect(() => {
    if (!selectedStrokes.length || viewing) return;
    if (inkRows.regions.length > 1 && !readSingleInk) { setError(null); setBusy(null); return; }
    let live = true;
    const version = editVersion.current;
    analyzedSource.current = null;
    setAnimating(null); setBusy("ocr"); setError(null); setModel(null); setGraphVisible(false); setExplanation(null);
    let timer: ReturnType<typeof setTimeout>;
    const deadline = new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error("OCR_TIMEOUT")), 45000); });
    Promise.race([recognizeHandwrittenMath(selectedStrokes), deadline]).then((result) => {
      if (live && version === editVersion.current) { setSource(result.latex); setNeedsOcrConfirm(true); }
    }).catch(() => {
      if (live && version === editVersion.current) setError("Chưa nhận dạng được vùng viết. Bạn có thể sửa hoặc nhập công thức bên dưới rồi phân tích.");
    }).finally(() => { clearTimeout(timer); if (live && version === editVersion.current) setBusy(null); });
    return () => { live = false; clearTimeout(timer); };
    // Each panel is keyed by the selected stroke IDs and page. Manual edits must not restart OCR.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run]);

  // Local classification works without an AI provider or an API round trip.
  useEffect(() => {
    if (viewing || !source.trim() || busy === "ocr") return;
    const timer = setTimeout(() => { if (analyzedSource.current !== source) analyze(source); }, 350);
    return () => clearTimeout(timer);
    // analyze reads only source; settings are reset for a newly entered formula.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, viewing, busy === "ocr"]);

  useEffect(() => {
    if (!animating || busy || viewing || !active) return;
    let frame = 0, last = 0, elapsedSeconds = 0;
    const start = (liveSettings.current.parameters[animating] ?? 1) + 5;
    const tick = (time: number) => {
      if (document.hidden) { last = time; frame = requestAnimationFrame(tick); return; }
      if (!last) last = time;
      const elapsed = time - last;
      if (elapsed >= (model?.kind === "implicit" ? 100 : 50)) {
        last = time;
        elapsedSeconds += Math.min(elapsed, 150) / 1000;
        const phase = (start + elapsedSeconds) % 20;
        const value = phase <= 10 ? phase - 5 : 15 - phase;
        setSettings((current) => {
          return { ...current, parameters: { ...current.parameters, [animating]: value } };
        });
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [animating, busy, viewing, active, model?.kind]);

  function changeSource(value: string) {
    setEquationSource(null);
    setIsSnapshotCopy((copy) => copy || !!viewing); setResumedCamera(null);
    analyzedSource.current = null;
    setAnimating(null); setNeedsOcrConfirm(false);
    editVersion.current++; setSource(value); setExplanation(null); setViewing(null); setSuccess(null); setError(null);
    if (!value.trim()) { setModel(null); setGraphVisible(false); }
    setBusy((current) => current === "ocr" ? null : current);
  }
  function analyze(value = source) {
    analyzedSource.current = value;
    if (splitFormulaRows(value).length > 1) { setError("Có nhiều phương trình. Chọn Vẽ các phương trình cùng nhau để xem chung trên hệ trục."); return; }
    try {
      const parsed = parseMathExpression(value);
      editVersion.current++;
      setBusy((current) => current === "ocr" ? null : current);
      setAnimating(null); setGraphVisible(true);
      const current = liveSettings.current;
      const sameFamily = model?.kind === parsed.kind && model.dimension === parsed.dimension;
      setModel(parsed); setPlottedSource(value);
      const parameters = Object.fromEntries(parsed.parameters.map((p) => [p, current.parameters[p] ?? 1]));
      setSettings({ ...(sameFamily ? current : { ...DEFAULT_GRAPH, view_mode: "2D" as const }), parameters });
      if (model?.expression !== parsed.expression) setParameterDefaults({ ...parameters });
      setCamera(defaultCamera(parsed.dimension)); setExplanation(null); setViewing(null); setError(null); setSuccess(null);
    } catch (err) { setError(err instanceof Error ? err.message : "Không thể phân tích công thức."); }
  }
  function changeSetting(key: NumericGraphSetting, value: number) {
    setSettings((current) => ({ ...current, [key]: value })); setExplanation(null); setSuccess(null);
  }
  function chooseView(viewMode: NonNullable<GraphSettings["view_mode"]>) {
    if (!model || source !== plottedSource) return;
    const next = { ...settings, view_mode: viewMode };
    if (resolveGraphView(model, next) !== resolveGraphView(model, settings)) {
      setResumedCamera(null);
      setCamera(defaultCamera(isSpatialView(resolveGraphView(model, next)) ? "3D" : "2D"));
      if (!viewing) setExplanation(null);
    }
    setSettings(next); setGraphVisible(true); setError(null); setSuccess(null);
  }
  async function explain() {
    if (!model || source !== plottedSource || needsOcrConfirm) return;
    setAnimating(null);
    setBusy("ai"); setError(null);
    try { setExplanation(await canvasRequest<CanvasExplanation>(`${endpoint}/explain`, { expression: model.expression, settings })); }
    catch (err) { setError(err instanceof Error ? err.message : "AI chưa sẵn sàng."); }
    finally { setBusy(null); }
  }
  async function save() {
    if (!model || source !== plottedSource || needsOcrConfirm) return;
    setAnimating(null);
    setBusy("save"); setError(null); setSuccess(null);
    try {
      await ensureInkSaved();
      const body = { expression: model.expression, settings, camera, page_index: pageIndex,
        stroke_ids: isSnapshotCopy ? [] : selectedStrokes.map((s) => s.id), source_latex: source, note, explanation_id: explanation?.id ?? null };
      const signature = JSON.stringify(body);
      if (pendingSave.current?.signature !== signature) pendingSave.current = { signature, action: generateUuid() };
      const saved = await canvasRequest<CanvasSnapshot>(`${endpoint}/snapshots`, { ...body, client_action_id: pendingSave.current!.action });
      pendingSave.current = null;
      setSnapshots((rows) => [saved, ...rows.filter((row) => row.id !== saved.id)]); setListError(false);
      setSuccess("Đã lưu vào bài học. Giáo viên đang phụ trách lớp có thể xem lại trong Math Canvas.");
    } catch (err) { setError(err instanceof Error ? err.message : "Chưa lưu được đồ thị."); }
    finally { setBusy(null); }
  }
  function continueExploration() {
    if (!viewing || !model) return;
    const draft = createExplorationDraft(viewing, settings, camera);
    editVersion.current++; analyzedSource.current = draft.source;
    setSource(draft.source); setPlottedSource(draft.source); setSettings(draft.settings); setParameterDefaults({ ...draft.settings.parameters }); setCamera(draft.camera); setNote(draft.note);
    setResumedCamera({ mode: resolveGraphView(model, settings), camera: draft.camera });
    setIsSnapshotCopy(true); setViewing(null); setNeedsOcrConfirm(false); setAnimating(null);
    setExplanation(null); setError(null); setSuccess("Đã mở một lượt khám phá mới. Kéo thanh tham số để tiếp tục quan sát.");
  }
  const formulaDirty = source !== plottedSource;
  const graphReady = !!model && !formulaDirty;
  const controlsLocked = !!busy || !!viewing || formulaDirty;
  const slider = (label: string, key: NumericGraphSetting, min = -5, max = 5, step = 0.1) =>
    <GraphValueControl key={key} label={label} value={settings[key] ?? 0} min={min} max={max} step={step} defaultValue={DEFAULT_GRAPH[key] ?? 0}
      disabled={controlsLocked} onInteraction={() => setAnimating(null)} onChange={(value) => changeSetting(key, value)} />;
  function changeParameter(name: string, value: number) {
    setAnimating(null); setSettings((current) => ({ ...current, parameters: { ...current.parameters, [name]: value } }));
    setExplanation(null); setSuccess(null);
  }
  function useExample(formula: string) { changeSource(formula); analyze(formula); }
  function openSceneView(readInk: boolean) {
    editVersion.current++;
    setAnimating(null); setBusy((current) => current === "ocr" ? null : current);
    if (model) setResumedCamera({ mode: resolveGraphView(model, settings), camera });
    onScene(source, readInk, needsOcrConfirm);
  }
  function enableCoefficientControls() {
    if (!coefficientExploration || controlsLocked) return;
    const confirmationRequired = needsOcrConfirm;
    useExample(coefficientExploration.model.expression);
    setSettings(coefficientExploration.settings);
    setParameterDefaults({ ...coefficientExploration.settings.parameters });
    setNeedsOcrConfirm(confirmationRequired);
    setSuccess("Đã bật chỉnh hệ số, giữ nguyên hình ban đầu. Kéo thanh hoặc nhập số để khám phá.");
    requestAnimationFrame(() => parameterControls.current?.scrollIntoView({ block: "nearest" }));
  }
  function drawNow() {
    if (!source.trim() || busy === "ai" || busy === "save" || viewing) return;
    setAnimating(null);
    if (formulaRows.length > 1) { openSceneView(false); return; }
    if (graphReady) setGraphReset((value) => value + 1);
    else analyze();
  }
  function insertFormula(prefix: string, suffix = "", placeholder = "") {
    const input = formulaInput.current; if (!input) return;
    const result = insertMathSnippet(source, input.selectionStart, input.selectionEnd, prefix, suffix, placeholder);
    if (!result) { setError("Công thức quá dài (tối đa 500 ký tự)."); return; }
    changeSource(result.text);
    requestAnimationFrame(() => {
      if (!input.isConnected) return;
      input.focus();
      input.setSelectionRange(result.selectionStart, result.selectionEnd);
    });
  }

  const recommendation = model ? recommendGraph(model) : null;
  const previewStrokes = viewing?.source_strokes ?? (isSnapshotCopy ? [] : selectedStrokes);
  const spatial = model ? isSpatialView(resolveGraphView(model, settings)) : false;
  const formulaLocked = busy === "ai" || busy === "save";
  const coefficientExploration = useMemo(() => model && graphReady ? createCoefficientExploration(model, settings) : null, [model, graphReady, settings]);
  const xEquation = model && graphReady ? analyzeXPolynomialEquation(model, settings.parameters) : null;
  const hasMultiple = inkRows.regions.length > 1 || formulaRows.length > 1;
  const inkPreview = previewStrokes.length > 0 ? <div className={styles.singleInk}><OcrInkPreview strokes={previewStrokes} /></div> : null;
  return <aside hidden={!active} className={`${styles.panel} ${styles.singlePanel} ${expanded ? styles.singleExpanded : ""}`} aria-label="Math View — khám phá công thức">
    <header className={styles.singleHeader}>
      <div className={`${styles.row} ${styles.studioBrand}`}><span className={styles.studioBrandIcon}><Orbit size={23} /></span><div><h2>Math View <span>2D / 3D</span></h2><p>Viết công thức. Khám phá hình dạng.</p></div></div>
      <div className={styles.singleHeaderActions}>
        <button type="button" className={styles.button} onClick={() => openSceneView(selectedStrokes.length > 0 && !graphReady && formulaRows.length < 2)}>Nhiều biểu thức</button>
        <button type="button" className={styles.button} aria-label={expanded ? "Thu gọn Math View" : "Mở rộng Math View"} aria-pressed={expanded} title={expanded ? "Thu gọn" : "Mở rộng"} onClick={() => setExpanded(!expanded)}>{expanded ? <Minimize2 size={17} /> : <Maximize2 size={17} />}</button>
        <button className={styles.close} type="button" aria-label="Đóng Math View" onClick={onClose}><X size={18} /></button>
      </div>
    </header>
    <div className={styles.singleLayout}>
      <section className={styles.singleEditor} aria-label="Công thức và tùy chỉnh">
        {hasMultiple ? <section className={`${styles.equationCard} ${styles.multiFormulaCard}`} aria-label="Vẽ nhiều phương trình">
          <strong>{inkRows.regions.length > 1 ? `Đã chọn ${inkRows.regions.length} dòng viết tay` : `${formulaRows.length} công thức đang nhập`}</strong>
          <p>Vẽ chung trên hệ trục Oxy để xem các đường và giao điểm.</p>
          {inkRows.regions.length > 1 ? <details className={styles.multiInkPreview}><summary>Xem nét viết của từng dòng</summary>{inkRows.regions.map((row,index)=><div key={row.id}><strong>Dòng {index+1}</strong><OcrInkPreview strokes={row.strokes}/></div>)}</details> : null}
          <button type="button" className={styles.button} disabled={formulaLocked} onClick={() => openSceneView(inkRows.regions.length > 1 && formulaRows.length < 2)}>Vẽ các phương trình cùng nhau</button>
          {inkRows.regions.length > 1 ? <p>Mỗi dòng được nhận dạng riêng. Em có thể sửa từng công thức trước khi lưu.</p> : null}
          {inkRows.regions.length > 1 ? <button type="button" className={styles.singleTextButton} disabled={!!busy} onClick={() => { setReadSingleInk(true); setRun((value) => value + 1); }}>Đây là một công thức nhiều tầng? Thử đọc chung</button> : null}
        </section> : null}
        <form onSubmit={(event) => { event.preventDefault(); drawNow(); }}>
          <div className={styles.formulaHeading}><label className={styles.singleLabel} htmlFor="canvas-formula">Công thức của em</label><PencilLine size={14} /></div>
          <textarea ref={formulaInput} id="canvas-formula" className={`${styles.input} ${styles.formulaEditor}`} rows={2} value={source} maxLength={500} disabled={formulaLocked}
            placeholder="z = a*x² + b*y²" autoComplete="off" spellCheck={false} aria-invalid={!!error && formulaDirty} aria-describedby="formula-input-help"
            onChange={(e) => changeSource(e.target.value)} onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault(); drawNow();
              }
            }} />
          <div className={`${styles.row} ${styles.formulaKeys}`} role="group" aria-label="Chèn ký hiệu toán học">
            {[{ label: "x²", prefix: "", suffix: "^2", placeholder: "x" }, { label: "y²", prefix: "", suffix: "^2", placeholder: "y" }, { label: "sin", prefix: "sin(", suffix: ")", placeholder: "x" }, { label: "cos", prefix: "cos(", suffix: ")", placeholder: "x" }, { label: "√", prefix: "sqrt(", suffix: ")", placeholder: "x" }, { label: "π", prefix: "pi", suffix: "", placeholder: "" }].map((key) => <button className={styles.button} key={key.label} type="button" disabled={formulaLocked} aria-label={`Chèn ${key.label}`} title="Chèn tại vị trí con trỏ hoặc bọc phần đang chọn" onMouseDown={(event) => event.preventDefault()} onClick={() => insertFormula(key.prefix, key.suffix, key.placeholder)}>{key.label}</button>)}
          </div>
          <div className={`${styles.row} ${styles.formulaStatusRow}`}><span id="formula-input-help" className={styles.formulaState}>{graphReady ? <><Check size={13} /> Đã cập nhật</> : "Tự cập nhật khi nhập"}</span><button className={`${styles.button} ${styles.formulaApply}`} type="submit" disabled={!source.trim() || formulaLocked || !!viewing} title={viewing ? "Tiếp tục khám phá để chỉnh bản lưu" : "Vẽ và đưa đồ thị về khung nhìn ban đầu"}>{graphReady ? "Vẽ lại" : "Vẽ ngay"} <ArrowUpRight size={13} /></button></div>
          {source.trim() ? <div className={styles.singleFormula}><OcrMathPreview latex={source} /></div> : null}
        </form>
        {xEquation ? <section className={styles.equationCard} aria-label="Phương trình một ẩn x">
          <strong>{xEquation.degree === 2 ? "Phương trình bậc hai theo x" : "Phương trình theo x"}</strong>
          <div className={styles.rootList}>{xEquation.solution === "FINITE" ? xEquation.roots.map((root) => <span key={root}>{describeEquationRoot(root)}</span>) : <span>{xEquation.solution === "ALL_REAL" ? "Mọi x thực đều thỏa mãn" : "Không có nghiệm thực"}</span>}</div>
          <p>Mỗi nghiệm được vẽ thành một đường thẳng đứng trên mặt phẳng Oxy.</p>
          <button type="button" className={styles.button} disabled={formulaLocked || xEquation.relatedFunction.length > 500} onClick={() => { const original = source; useExample(xEquation.relatedFunction); setEquationSource(original); }}>{xEquation.degree === 2 ? "Vẽ parabol tương ứng" : "Vẽ hàm y = vế trái − vế phải"}</button>
        </section> : null}
        {equationSource ? <div className={styles.equationCard}><p>Đang xem hàm tương ứng của <code>{equationSource}</code>.</p><button type="button" className={styles.button} disabled={formulaLocked} onClick={() => useExample(equationSource)}>← Quay lại phương trình</button></div> : null}
        {busy === "ocr" ? <p className={styles.singleHint} role="status">Đang đọc nét viết… Em vẫn có thể nhập công thức.</p> : null}
        {needsOcrConfirm ? <div className={styles.singleOcr}>
          <strong>Đọc đúng nét viết chưa?</strong>{inkPreview}
          <p>Sửa công thức phía trên nếu chưa đúng.</p>
          <button className={styles.primary} type="button" disabled={!graphReady || !!busy} onClick={() => setNeedsOcrConfirm(false)}>Đúng, dùng công thức này</button>
        </div> : previewStrokes.length > 0 ? <details className={styles.singleDetails}><summary>Đối chiếu nét viết · Trang {pageIndex + 1}</summary>{inkPreview}</details> : null}
        {selectedStrokes.length > 0 ? <button className={styles.singleTextButton} type="button" disabled={!!busy} onClick={() => { setViewing(null); setIsSnapshotCopy(false); setResumedCamera(null); setRun((n) => n + 1); }}>Nhận dạng lại nét viết</button> : null}
        {error ? <p role="alert" className={styles.error}>{error}</p> : null}
        {model ? <>
          {model.parameters.length === 0 && graphReady ? <section className={styles.equationCard} aria-label="Bật điều chỉnh hệ số">
            <strong>Điều chỉnh hệ số</strong>
            {coefficientExploration ? <><p>Công thức đang dùng số cố định. Bật tham số để chỉnh mà vẫn giữ hình ban đầu.</p>
              <OcrMathPreview latex={coefficientExploration.model.expression} />
              <p className={styles.coefficientValues}>{Object.entries(coefficientExploration.settings.parameters).map(([name, value]) => `${name} = ${Number(value.toPrecision(8))}`).join(" · ")}</p>
              <button className={styles.button} type="button" disabled={controlsLocked} onClick={enableCoefficientControls}>Bật chỉnh hệ số</button>
            </> : <p>Công thức chưa có tham số. Dùng a, b, c… thay cho hệ số muốn chỉnh, ví dụ <code>y=a*x^2+b*x+c</code>, hoặc chọn công thức mẫu bên dưới.</p>}
          </section> : null}
          {model.parameters.length > 0 ? <section ref={parameterControls} className={styles.singleParameters} aria-label="Tham số công thức"><div className={styles.parameterHeading}><h3>Điều chỉnh hệ số</h3><button type="button" aria-label="Đặt lại tất cả tham số" title="Khôi phục các hệ số lúc bắt đầu" disabled={controlsLocked} onClick={() => { setAnimating(null); setSettings((current) => ({ ...current, parameters: Object.fromEntries(model.parameters.map((name) => [name, parameterDefaults[name] ?? 1])) })); setExplanation(null); setSuccess(null); }}><RotateCcw size={14} /></button></div><div className={styles.sliders}>
        {model.parameters.map((p) => <div className={styles.parameterCard} key={p}>
          <GraphValueControl label={`Tham số ${p}`} value={settings.parameters[p] ?? 1} defaultValue={parameterDefaults[p] ?? 1} disabled={controlsLocked} onInteraction={() => setAnimating(null)} onChange={(value) => changeParameter(p, value)} />
          <button type="button" className={styles.animateButton} aria-label={`${animating === p ? "Dừng" : "Chạy"} tham số ${p}`} aria-pressed={animating === p} disabled={controlsLocked}
            onClick={() => { setAnimating(animating === p ? null : p); setExplanation(null); setSuccess(null); }}>{animating === p ? <><Pause size={12} /> Dừng</> : <><Play size={12} /> Tự chạy</>}</button></div>)}
          </div></section> : null}
          {["SLICE_2D", "LEVEL_SLICE_2D"].includes(resolveGraphView(model, settings)) ? <div className={styles.singleParameters}>{slider("Vị trí mặt cắt y₀", "slice_y")}</div> : null}
          <div className={styles.domainControl}>{slider("Miền hiển thị ±", "domain", 1, 10, 0.5)}</div>
          {model.kind === "explicit" ? <details className={styles.singleDetails}><summary>Dịch chuyển và biến đổi</summary><div className={styles.sliders}>
        {model.kind === "explicit" ? <>{slider("Tỉ lệ độ cao s", "scale")}{slider("Dịch đứng v", "offset")}{slider("Dịch theo x: h", "shift_x")}
          {model.dimension === "3D" ? slider("Dịch theo y: k", "shift_y") : null}</> : null}
          </div></details> : null}
          <details className={styles.singleDetails}><summary>Ghi chú và giải thích AI</summary>
            {!viewing ? <><label>Ghi chú khám phá<textarea className={styles.note} value={note} maxLength={1000} placeholder="Em quan sát được điều gì?" onChange={(e) => setNote(e.target.value)} /></label>
              <button type="button" className={styles.button} disabled={!!busy || !graphReady || needsOcrConfirm} onClick={explain}>{busy === "ai" ? "AI đang giải thích…" : "Nhờ AI giải thích"}</button></> : viewing.note ? <p>{viewing.note}</p> : <p className={styles.singleHint}>Bản lưu này chưa có ghi chú.</p>}
            {explanation ? <div className={styles.explanation}><strong>AI giải thích · {explanation.provider}</strong><p>{explanation.text}</p></div> : null}
          </details>
        </> : null}
        <details className={styles.singleDetails}><summary>Thử một công thức mẫu</summary><p className={styles.singleHint}>Chọn mẫu sẽ thay công thức đang nhập.</p><div className={styles.singleExamples}>
          {GRAPH_EXAMPLES.map((example) => <button type="button" className={styles.button} key={example.formula} disabled={formulaLocked} onClick={() => useExample(example.formula)}>{example.label}<code>{example.formula}</code></button>)}
        </div></details>
        <details className={styles.singleDetails}><summary>Cách nhập công thức</summary><p>Dùng x, y, z cho tọa độ; a, b, r… cho hệ số. Ví dụ <code>z=a*x^2+b*y^2</code>.</p><p>Muốn xem giao điểm: chọn Nhiều biểu thức, mỗi dòng một phương trình. Có thể dán nhiều dòng hoặc dùng dấu chấm phẩy.</p><p>Hỗ trợ sin(x), cos(x), sqrt(x), abs(x), log(x), phân số và số mũ. Nhấn Enter để vẽ ngay.</p></details>
        <details className={styles.singleDetails}><summary>Đã lưu trong bài học ({snapshots.length})</summary>
      {listError ? <p className={styles.error}>Chưa tải được bản lưu. Hãy đóng rồi mở lại Math Canvas để thử lại.</p> : null}
      {!snapshots.length && !listError ? <p className={styles.muted}>Chưa có bản trực quan hóa được lưu.</p> : null}
      {snapshots.map((snapshot) => <button type="button" className={styles.saved} key={snapshot.id} disabled={!!busy} onClick={() => {
        editVersion.current++; setAnimating(null); setNeedsOcrConfirm(false); setIsSnapshotCopy(false); setResumedCamera(null); setViewing(snapshot); setSource(snapshot.source_latex || snapshot.expression); setPlottedSource(snapshot.source_latex || snapshot.expression); setModel(parseMathExpression(snapshot.expression));
        setGraphVisible(true);
        setSettings(snapshot.settings); setParameterDefaults({ ...snapshot.settings.parameters }); setCamera(snapshot.camera); setExplanation(snapshot.explanation); setError(null); setSuccess(null);
      }}>{snapshot.expression}<small>{describeGraphView(parseMathExpression(snapshot.expression), snapshot.settings)} · Trang {snapshot.page_index + 1} · {new Date(snapshot.created_at).toLocaleString("vi-VN")}</small></button>)}
        </details>
      </section>
      <section className={styles.singlePlot} aria-label="Đồ thị công thức">
        <div className={styles.singlePlotHeading}><strong>Đồ thị</strong><div className={styles.singleViewTabs} role="group" aria-label="Chọn chế độ xem đồ thị">
          <button type="button" disabled={!graphReady || formulaLocked} aria-pressed={!!model && !spatial} onClick={() => chooseView("2D")}><ChartNoAxesCombined size={16} />{model?.dimension === "3D" ? "2D · Mặt cắt" : "2D"}</button>
          <button type="button" disabled={!graphReady || formulaLocked} aria-pressed={!!model && spatial} onClick={() => chooseView("3D")}><Box size={16} />3D</button>
        </div></div>
        {model?.kind === "explicit" && model.dimension === "2D" && graphVisible ? <div className={styles.singleSurfaceAction}>
          <div><span className={styles.singleSurfaceIcon}><Layers3 size={18}/></span><div><strong>{resolveGraphView(model,settings) === "EXTRUDED_3D" ? "Đang xem bề mặt kéo dài" : "Khám phá dưới dạng bề mặt"}</strong><p>Giữ y = F(x), kéo dài theo trục z.</p></div></div>
          <button type="button" className={styles.button} disabled={formulaLocked || !graphReady} aria-pressed={resolveGraphView(model,settings) === "EXTRUDED_3D"} onClick={() => chooseView(resolveGraphView(model,settings) === "EXTRUDED_3D" ? "3D" : "EXTRUDED")}>
            {resolveGraphView(model,settings) === "EXTRUDED_3D" ? <><ChartNoAxesCombined size={15}/> Về đường cong 3D</> : <><Layers3 size={15}/> Tạo bề mặt kéo dài</>}
          </button>
        </div> : null}
        {model && graphVisible ? <>
          <p className={styles.singleViewDescription} role="status">{xEquation ? `Tập nghiệm theo x · ${spatial ? "Đặt trên mặt phẳng Oxy tại z = 0" : "Các đường x = nghiệm"}` : describeGraphView(model, settings)}</p>
          {formulaDirty ? <div className={styles.pendingFormula} role="status">{error ? "Công thức mới chưa hợp lệ." : "Đang nhập công thức mới…"} Hình bên dưới vẫn là <code>{model.expression}</code>.</div> : null}
          {active ? <div className={styles.singleViewport}><GraphView key={`${viewing?.id ?? model.expression}:${resolveGraphView(model, settings)}:${graphReset}`} model={model} settings={settings}
            initialCamera={viewing && resolveGraphView(model, viewing.settings) === resolveGraphView(model, settings) ? viewing.camera
              : resumedCamera?.mode === resolveGraphView(model, settings) ? resumedCamera.camera : undefined} onCameraChange={setCamera} /></div> : null}
          <details className={styles.singleHelp}><summary>Vì sao công thức này được gợi ý xem {model.dimension}?</summary><p>{recommendation?.reason}</p>
            <p>{model.kind === "implicit" ? "Hình được lấy mẫu gần đúng trong miền đang chọn." : model.dimension === "2D" ? "Chuyển sang 3D để xoay cùng đường cong tại z = 0. Công thức không đổi." : "Chọn 2D để xem một mặt cắt của bề mặt."}</p>
          </details>
        </> : <div className={styles.singleEmpty}><span className={styles.emptyOrbit}><Orbit size={38} strokeWidth={1.3} /></span><span className={styles.emptyEyebrow}>KHÁM PHÁ BẰNG HÌNH ẢNH</span><h3>{busy === "ocr" ? "Đang đọc nét viết của em" : hasMultiple ? "Vẽ chung để thấy giao điểm" : "Một công thức. Một góc nhìn mới."}</h3><p>{busy === "ocr" ? "Em có thể nhập hoặc sửa công thức ở bên trái." : hasMultiple ? "Mỗi phương trình sẽ nằm trên một dòng riêng và có màu riêng trên hệ trục Oxy." : "Nhập công thức ở bên trái hoặc bắt đầu từ một hình quen thuộc."}</p>
          {hasMultiple ? <button type="button" className={styles.primary} disabled={formulaLocked} onClick={() => openSceneView(inkRows.regions.length > 1 && formulaRows.length < 2)}>Mở bảng để xem giao điểm</button> : busy !== "ocr" ? <div className={styles.starterGallery}>{GRAPH_EXAMPLES.slice(0, 4).map((example) => <button type="button" key={example.formula} disabled={formulaLocked} onClick={() => useExample(example.formula)}><example.icon size={22} strokeWidth={1.5} /><strong>{example.label}</strong><span>{example.hint}</span><code>{example.formula}</code><ArrowUpRight size={14} className={styles.galleryArrow} /></button>)}</div> : null}
        </div>}
      </section>
    </div>
    <footer className={styles.singleFooter}>
      <div aria-live="polite">{success ? <span className={styles.singleSaved}>{success}</span> : <span>{viewing ? "Đang xem bản đã lưu." : formulaDirty && model ? "Hoàn tất công thức mới trước khi lưu." : needsOcrConfirm ? "Xác nhận công thức nhận dạng trước khi lưu." : "Lưu đồ thị để xem lại cùng bài làm."}</span>}</div>
      {viewing ? <button type="button" className={styles.primary} disabled={!!busy} onClick={continueExploration}>Tiếp tục khám phá</button>
        : <button type="button" className={styles.primary} disabled={!graphReady || !!busy || needsOcrConfirm} onClick={save}>{busy === "save" ? "Đang lưu…" : "Lưu vào bài học"}</button>}
    </footer>
  </aside>;
}
