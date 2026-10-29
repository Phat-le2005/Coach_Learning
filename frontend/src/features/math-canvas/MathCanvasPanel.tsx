"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { InkStroke } from "@/lib/api/contracts";
import { OcrInkPreview } from "@/features/math-workspace/components/OcrInkPreview";
import { recognizeHandwrittenMath } from "@/features/math-workspace/utils/handwritten-ocr";
import { generateUuid } from "@/features/math-workspace/utils/ink-math";
import { canvasRequest, type CanvasExplanation, type CanvasSnapshot } from "./api";
import { DEFAULT_GRAPH, defaultCamera, parseMathExpression, type MathExpression, type GraphSettings, type GraphCamera, type NumericGraphSetting } from "./expression";
import { describeGraphView, isSpatialView, recommendGraph, resolveGraphView, type GraphRenderMode } from "./presentation";
import { createExplorationDraft } from "./exploration";
import { GraphScenePanel } from "./GraphScenePanel";
import styles from "./MathCanvas.module.css";

const GraphView = dynamic(() => import("./GraphView").then((module) => module.GraphView), {
  ssr: false,
  loading: () => <p className={styles.muted} role="status">Đang mở khung nhìn công thức…</p>,
});

interface Props { attemptId: string; pageIndex: number; selectedStrokes: InkStroke[]; initialFormula?: string; ensureInkSaved: () => Promise<void>; onClose: () => void }
export function MathCanvasPanel({ attemptId, pageIndex, selectedStrokes, initialFormula = "", ensureInkSaved, onClose }: Props) {
  const [mode,setMode]=useState<"scene"|"single">("scene");
  const [single,setSingle]=useState<{snapshot?:CanvasSnapshot;formula?:string}|null>(null);
  const props={attemptId,pageIndex,selectedStrokes,initialFormula,ensureInkSaved,onClose};
  return <>
    <GraphScenePanel {...props} active={mode==="scene"} onSingle={(snapshot,formula)=>{setSingle({snapshot,formula});setMode("single");}}/>
    {single?<SingleFormulaPanel key={single.snapshot?.id??single.formula??"single"} {...props} initialFormula={single.formula??initialFormula} selectedStrokes={single.formula?[]:selectedStrokes} initialSnapshot={single.snapshot} active={mode==="single"} onScene={()=>setMode("scene")}/>:null}
  </>;
}

function SingleFormulaPanel({ attemptId, pageIndex, selectedStrokes, initialFormula = "", ensureInkSaved, onClose, initialSnapshot, active, onScene }: Props & {initialSnapshot?:CanvasSnapshot;active:boolean;onScene:()=>void}) {
  const [source, setSource] = useState(initialSnapshot?.source_latex||initialSnapshot?.expression||initialFormula);
  const [model, setModel] = useState<MathExpression | null>(()=>initialSnapshot?parseMathExpression(initialSnapshot.expression):null);
  const [graphVisible, setGraphVisible] = useState(!!initialSnapshot);
  const [settings, setSettings] = useState<GraphSettings>(initialSnapshot?.settings??{ ...DEFAULT_GRAPH });
  const [camera, setCamera] = useState<GraphCamera>(initialSnapshot?.camera??defaultCamera("3D"));
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
  const [animating, setAnimating] = useState<string | null>(null);
  const [needsOcrConfirm, setNeedsOcrConfirm] = useState(false);
  const editVersion = useRef(0);
  const analyzedSource = useRef<string | null>(null);
  const liveSettings = useRef(settings); liveSettings.current = settings;
  const pendingSave = useRef<{ signature: string; action: string } | null>(null);
  const endpoint = `attempts/${attemptId}`;

  useEffect(() => {
    if (!active) return;
    let live = true;
    canvasRequest<CanvasSnapshot[]>(`${endpoint}/snapshots`).then((rows) => { if (live) setSnapshots(rows.filter((row)=>!row.settings.scene)); })
      .catch(() => { if (live) setListError(true); });
    return () => { live = false; };
  }, [endpoint, active]);

  useEffect(() => {
    if (!selectedStrokes.length || viewing) return;
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
    if (!animating || busy || viewing) return;
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
  }, [animating, busy, viewing, model?.kind]);

  function changeSource(value: string) {
    setIsSnapshotCopy((copy) => copy || !!viewing); setResumedCamera(null);
    analyzedSource.current = null;
    setAnimating(null); setNeedsOcrConfirm(false);
    editVersion.current++; setSource(value); setModel(null); setGraphVisible(false); setExplanation(null); setViewing(null); setSuccess(null); setError(null);
    setBusy((current) => current === "ocr" ? null : current);
  }
  function analyze(value = source) {
    analyzedSource.current = value;
    try {
      const parsed = parseMathExpression(value);
      editVersion.current++;
      setBusy((current) => current === "ocr" ? null : current);
      setAnimating(null); setGraphVisible(true);
      setModel(parsed); setSettings({ ...DEFAULT_GRAPH, parameters: Object.fromEntries(parsed.parameters.map((p) => [p, 1])) });
      setCamera(defaultCamera(parsed.dimension)); setExplanation(null); setViewing(null); setError(null); setSuccess(null);
    } catch (err) { setModel(null); setGraphVisible(false); setError(err instanceof Error ? err.message : "Không thể phân tích công thức."); }
  }
  function changeSetting(key: NumericGraphSetting, value: number) {
    setSettings((current) => ({ ...current, [key]: value })); setExplanation(null); setSuccess(null);
  }
  function chooseView(viewMode: NonNullable<GraphSettings["view_mode"]>) {
    if (!model) return;
    const next = { ...settings, view_mode: viewMode };
    if (resolveGraphView(model, next) !== resolveGraphView(model, settings)) {
      setResumedCamera(null);
      setCamera(defaultCamera(isSpatialView(resolveGraphView(model, next)) ? "3D" : "2D"));
      if (!viewing) setExplanation(null);
    }
    setSettings(next); setGraphVisible(true); setError(null); setSuccess(null);
  }
  async function explain() {
    if (!model) return;
    setAnimating(null);
    setBusy("ai"); setError(null);
    try { setExplanation(await canvasRequest<CanvasExplanation>(`${endpoint}/explain`, { expression: model.expression, settings })); }
    catch (err) { setError(err instanceof Error ? err.message : "AI chưa sẵn sàng."); }
    finally { setBusy(null); }
  }
  async function save() {
    if (!model) return;
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
    setSource(draft.source); setSettings(draft.settings); setCamera(draft.camera); setNote(draft.note);
    setResumedCamera({ mode: resolveGraphView(model, settings), camera: draft.camera });
    setIsSnapshotCopy(true); setViewing(null); setNeedsOcrConfirm(false); setAnimating(null);
    setExplanation(null); setError(null); setSuccess("Đã mở một lượt khám phá mới. Kéo thanh tham số để tiếp tục quan sát.");
  }
  const slider = (label: string, key: NumericGraphSetting, min = -5, max = 5, step = 0.1) =>
    <label className={styles.slider} key={key}><span>{label}<strong>{(settings[key] ?? 0).toFixed(1)}</strong></span>
      <input type="range" aria-label={label} min={min} max={max} step={step} value={settings[key] ?? 0}
        disabled={!!busy || !!viewing} onChange={(e) => changeSetting(key, Number(e.target.value))} /></label>;

  const recommendation = model ? recommendGraph(model) : null;
  const previewStrokes = viewing?.source_strokes ?? (isSnapshotCopy ? [] : selectedStrokes);
  return <aside hidden={!active} className={styles.panel} aria-label="Math View 3D — khám phá công thức">
    <div className={styles.heading}><div><h2>Math View 3D</h2><span className={styles.badge}>Viết · Khoanh · Nhìn thấy toán học</span></div>
      <div className={styles.row}><button type="button" className={styles.button} onClick={()=>{setAnimating(null);if(model)setResumedCamera({mode:resolveGraphView(model,settings),camera});onScene();}}>Bảng nhiều biểu thức</button><button className={styles.close} type="button" aria-label="Đóng Math View" onClick={onClose}>×</button></div></div>
    <p className={styles.muted}>Quan sát hình dạng và sự biến đổi của công thức. Thử dự đoán trước khi kéo thanh tham số.</p>
    <p className={styles.muted}>{selectedStrokes.length ? `Đã chọn ${selectedStrokes.length} nét bút ở trang ${pageIndex + 1}. Đối chiếu công thức nhận dạng với nét viết.` : "Khoanh công thức trên bảng, chọn một bước đã xác nhận, hoặc nhập công thức bên dưới."}</p>
    {previewStrokes.length > 0 ? <OcrInkPreview strokes={previewStrokes} /> : null}
    <label htmlFor="canvas-formula">Công thức</label>
    <input id="canvas-formula" className={styles.input} value={source} maxLength={500} disabled={busy === "ai" || busy === "save"}
      placeholder="z = x² + y²" autoComplete="off" spellCheck={false} onChange={(e) => changeSource(e.target.value)} />
    <div className={styles.row}>
      <button className={styles.primary} type="button" disabled={!source.trim() || busy === "ai" || busy === "save"} onClick={() => { setNeedsOcrConfirm(false); if (!model) analyze(); }}>{needsOcrConfirm ? "Xác nhận công thức nhận dạng" : "Cập nhật hình"}</button>
      {selectedStrokes.length > 0 ? <button className={styles.button} type="button" disabled={!!busy} onClick={() => { setViewing(null); setIsSnapshotCopy(false); setResumedCamera(null); setRun((n) => n + 1); }}>Nhận dạng lại</button> : null}
      {busy === "ocr" ? <span role="status">Đang nhận dạng nét viết… Có thể nhập công thức trực tiếp.</span> : null}
    </div>
    <p className={styles.muted}>Tự nhận diện sau khi nhập · sin, cos, căn, phân số · Tham số a–w (trừ e).</p>
    {!model ? <div className={styles.row}><span className={styles.muted}>Thử khám phá:</span>{["y=a*sin(x)", "z=a*x²+b*y²", "x²+y²+z²=r²", "x+y+z=a", "x²+y²=r²"].map((example) =>
      <button type="button" className={styles.button} key={example} onClick={() => { changeSource(example); analyze(example); }}>{example}</button>)}</div> : null}
    {model ? <>
      <div className={styles.recommendation} role="status"><strong>{recommendation?.title}</strong><p>{recommendation?.reason}</p><code>{model.expression}</code></div>
      <div className={styles.row} role="group" aria-label="Chọn chế độ xem đồ thị">
        <button className={styles.button} type="button" disabled={busy === "save" || busy === "ai"}
          aria-pressed={graphVisible && !isSpatialView(resolveGraphView(model, settings))} onClick={() => chooseView("2D")}>{model.dimension === "3D" ? "View 2D · Mặt cắt" : "View 2D"}</button>
        <button className={styles.primary} type="button" disabled={busy === "save" || busy === "ai"}
          aria-pressed={graphVisible && isSpatialView(resolveGraphView(model, settings))} onClick={() => chooseView("3D")}>View 3D</button>
      </div>
      {model.dimension === "2D" && model.kind === "explicit" ? <details className={styles.muted}><summary>Mở rộng thành bề mặt</summary>
        <p>Giữ y = F(x) và cho z thay đổi tự do để tạo bề mặt kéo dài. Đây là một phép mở rộng được chọn riêng.</p>
        <button type="button" className={styles.button} disabled={busy === "save" || busy === "ai"} onClick={() => chooseView("EXTRUDED")}>Tạo bề mặt kéo dài</button>
      </details> : null}
      {graphVisible && active ? <>
      <p className={styles.muted} role="status">{describeGraphView(model, settings)}</p>
      <GraphView key={`${viewing?.id ?? model.expression}:${resolveGraphView(model, settings)}`} model={model} settings={settings}
        initialCamera={viewing && resolveGraphView(model, viewing.settings) === resolveGraphView(model, settings) ? viewing.camera
          : resumedCamera?.mode === resolveGraphView(model, settings) ? resumedCamera.camera : undefined} onCameraChange={setCamera} />
      <p className={styles.muted}>{model.kind === "implicit" ? "Hình là tập các điểm thỏa mãn phương trình. Đổi tham số để quan sát tập điểm thay đổi. Hình được lấy mẫu gần đúng trong miền đang chọn." : `Phép biến đổi: ${model.dimension === "3D" ? "Z = s·f(x−h, y−k) + v" : "Y = s·f(x−h) + v"}. Hệ số âm lật đồ thị qua mặt phẳng/trục ngang.`}</p>
      <div className={styles.sliders}>
        {model.parameters.map((p) => <div className={styles.slider} key={p}><label htmlFor={`graph-param-${p}`}><span>Tham số {p}<strong>{(settings.parameters[p] ?? 1).toFixed(2)}</strong></span></label>
          <input id={`graph-param-${p}`} type="range" aria-label={`Tham số ${p}`} min={-5} max={5} step={0.1} value={settings.parameters[p] ?? 1} disabled={!!busy || !!viewing}
            onChange={(e) => { setAnimating(null); setSettings((s) => ({ ...s, parameters: { ...s.parameters, [p]: Number(e.target.value) } })); setExplanation(null); setSuccess(null); }} />
          <button type="button" className={styles.animateButton} aria-label={`${animating === p ? "Dừng" : "Chạy"} tham số ${p}`} aria-pressed={animating === p} disabled={!!busy || !!viewing}
            onClick={() => { setAnimating(animating === p ? null : p); setExplanation(null); setSuccess(null); }}>{animating === p ? "Ⅱ Dừng" : "▷ Chạy tham số"}</button></div>)}
        {model.kind === "explicit" ? <>{slider("Tỉ lệ độ cao s", "scale")}{slider("Dịch đứng v", "offset")}{slider("Dịch theo x: h", "shift_x")}
          {model.dimension === "3D" ? slider("Dịch theo y: k", "shift_y") : null}</> : null}
        {slider("Miền hiển thị ±", "domain", 1, 10, 0.5)}
        {["SLICE_2D", "LEVEL_SLICE_2D"].includes(resolveGraphView(model, settings)) ? slider("Vị trí mặt cắt y₀", "slice_y") : null}
      </div>
      {explanation ? <div className={styles.explanation}><strong>AI giải thích · {explanation.provider}</strong><p>{explanation.text}</p></div> : null}
      {!viewing ? <>
        <label>Ghi chú khám phá<textarea className={styles.note} value={note} maxLength={1000} placeholder="Em quan sát điều gì khi thay đổi tham số?" onChange={(e) => setNote(e.target.value)} /></label>
        <div className={styles.row}><button type="button" className={styles.button} disabled={!!busy} onClick={explain}>{busy === "ai" ? "AI đang giải thích…" : "AI giải thích sự biến đổi"}</button>
          <button type="button" className={styles.primary} disabled={!!busy || needsOcrConfirm} onClick={save}>{busy === "save" ? "Đang lưu…" : "Lưu vào bài học"}</button></div>
        {needsOcrConfirm ? <p className={styles.muted}>Đối chiếu nét viết và bấm xác nhận công thức nhận dạng trước khi lưu.</p> : null}
      </> : <div className={styles.section}><p className={styles.muted}>Đang xem bản lưu của bài học. Tiếp tục khám phá để thử các giá trị tham số mới.</p>
        {viewing.note ? <p>{viewing.note}</p> : null}
        <button type="button" className={styles.primary} disabled={!!busy} onClick={continueExploration}>Tiếp tục khám phá</button></div>}
      </> : null}
    </> : null}
    {error ? <p role="alert" className={styles.error}>{error}</p> : null}
    {success ? <p role="status" className={styles.success}>{success}</p> : null}
    <div className={styles.section}><h3>Đã lưu trong bài học ({snapshots.length})</h3>
      {listError ? <p className={styles.error}>Chưa tải được bản lưu. Hãy đóng rồi mở lại Math Canvas để thử lại.</p> : null}
      {!snapshots.length && !listError ? <p className={styles.muted}>Chưa có bản trực quan hóa được lưu.</p> : null}
      {snapshots.map((snapshot) => <button type="button" className={styles.saved} key={snapshot.id} disabled={!!busy} onClick={() => {
        editVersion.current++; setAnimating(null); setNeedsOcrConfirm(false); setIsSnapshotCopy(false); setResumedCamera(null); setViewing(snapshot); setSource(snapshot.source_latex || snapshot.expression); setModel(parseMathExpression(snapshot.expression));
        setGraphVisible(true);
        setSettings(snapshot.settings); setCamera(snapshot.camera); setExplanation(snapshot.explanation); setError(null); setSuccess(null);
      }}>{snapshot.expression}<small>{describeGraphView(parseMathExpression(snapshot.expression), snapshot.settings)} · Trang {snapshot.page_index + 1} · {new Date(snapshot.created_at).toLocaleString("vi-VN")}</small></button>)}
    </div>
  </aside>;
}
