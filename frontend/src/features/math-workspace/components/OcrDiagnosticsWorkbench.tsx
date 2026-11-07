"use client";

import { useRef, useState } from "react";
import type { OcrEvalCaptureV1 } from "../utils/ocr-eval-capture";
import { validateOcrEvalCapture, type OcrGroundTruthV1 } from "../utils/ocr-eval-replay";
import { annotationTemplate, evaluateCapture, validateRecognitionAnnotation, type AutoProfile } from "../utils/ocr-scope-diagnostics";
import { diagnoseMathScope, sha256 } from "../utils/ocr-model-diagnostics";
import { recognizeHandwrittenMath } from "../utils/handwritten-ocr";
import { computeBounds } from "../utils/structured-transcription-ir";

function download(name: string, value: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const a = document.createElement("a"); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
type Evaluation = Awaited<ReturnType<typeof evaluateCapture>>;

/** Local files only. No student session, backend client, evaluator or batch journal. */
export function OcrDiagnosticsWorkbench() {
  const [capture, setCapture] = useState<OcrEvalCaptureV1 | null>(null);
  const [captureHash, setCaptureHash] = useState("");
  const [annotation, setAnnotation] = useState<OcrGroundTruthV1 | null>(null);
  const [annotationHash, setAnnotationHash] = useState<string | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [latex, setLatex] = useState("");
  const [kind, setKind] = useState<"MATH" | "TEXT" | "UNKNOWN" | "STRUCTURE">("MATH");
  const [humanConfirmed, setHumanConfirmed] = useState(false);
  const [e2, setE2] = useState(false);
  const [profile, setProfile] = useState("both");
  const [result, setResult] = useState<Evaluation | null>(null);
  const [resultAnnotationHash, setResultAnnotationHash] = useState<string | null>(null);
  const [legacyParity, setLegacyParity] = useState<unknown[]>([]);
  const [busy, setBusy] = useState(false);
  const fileTask = useRef(false);
  const [hasSeenOcr, setHasSeenOcr] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bounds = computeBounds(capture?.strokes.filter((s) => s.tool === "PEN") ?? []);
  const viewBox = `${bounds.left * 794 - 30} ${bounds.top * 1123 - 30} ${Math.max(60, (bounds.right - bounds.left) * 794 + 60)} ${Math.max(60, (bounds.bottom - bounds.top) * 1123 + 60)}`;
  const locked = busy || hasSeenOcr || annotation?.annotationStatus === "HUMAN_VERIFIED";
  const loadCapture = async (file: File) => {
    if (busy || fileTask.current) return;
    fileTask.current = true; setBusy(true);
    try {
      const bytes = await file.arrayBuffer(); const parsed = validateOcrEvalCapture(JSON.parse(new TextDecoder().decode(bytes)));
      const hash = await sha256(bytes); setCapture(parsed); setCaptureHash(hash); setAnnotation(annotationTemplate(hash, file.name));
      setAnnotationHash(null); setResult(null); setLegacyParity([]); setHasSeenOcr(false); setSelected([]); setHumanConfirmed(false); setError(null);
    } catch (err) { setError(String(err)); }
    finally { fileTask.current = false; setBusy(false); }
  };
  const loadAnnotation = async (file: File) => {
    if (!capture || busy || fileTask.current) return;
    fileTask.current = true; setBusy(true);
    try {
      const bytes = await file.arrayBuffer();
      const validated = validateRecognitionAnnotation(JSON.parse(new TextDecoder().decode(bytes)), capture, captureHash);
      const hash = await sha256(bytes);
      setAnnotation(validated); setAnnotationHash(hash); setError(null);
    } catch (err) { setError(String(err)); }
    finally { fileTask.current = false; setBusy(false); }
  };
  const addGroup = () => {
    if (!capture || !annotation || locked) return;
    try {
      const nextId = Math.max(0, ...annotation.expectedGroups.map((g) => Number(g.groupId.match(/^group-(\d+)$/)?.[1] ?? 0))) + 1;
      const next = { ...annotation, expectedGroups: [...annotation.expectedGroups, { groupId: `group-${nextId}`,
        strokeIds: [...selected], contentKind: kind, latex: kind === "MATH" ? latex : null, text: kind === "TEXT" ? latex : null }] };
      setAnnotation(validateRecognitionAnnotation(next, capture, captureHash)); setAnnotationHash(null); setSelected([]); setLatex(""); setError(null);
    } catch (err) { setError(String(err)); }
  };
  const saveAnnotation = async (verified: boolean) => {
    if (!capture || !annotation || busy || fileTask.current) return;
    fileTask.current = true; setBusy(true);
    try {
      const next = validateRecognitionAnnotation({ ...annotation, annotationStatus: verified ? "HUMAN_VERIFIED" : "DRAFT" }, capture, captureHash);
      const hash = await sha256(new TextEncoder().encode(JSON.stringify(next, null, 2)));
      setAnnotation(next); setAnnotationHash(hash); download("ocr-annotation.json", next); setError(null);
    } catch (err) { setError(String(err)); }
    finally { fileTask.current = false; setBusy(false); }
  };
  const run = async () => {
    if (!capture || busy || fileTask.current) return;
    setBusy(true); setHasSeenOcr(true); setError(null); setResult(null); setLegacyParity([]);
    try {
      const profiles: AutoProfile[] = profile === "both" ? ["LEGACY_REGIONS", "IR_ATOMIC"] : [profile as AutoProfile];
      const evaluated = await evaluateCapture({ capture, captureSha256: captureHash, annotation, profiles, e2, recognize: diagnoseMathScope });
      setResult(evaluated); setResultAnnotationHash(annotationHash);
    } catch (err) { setError(String(err)); } finally { setBusy(false); }
  };
  const checkLegacy = async () => {
    if (!capture || !result) return;
    setBusy(true);
    try {
      const parity = [];
      for (const run of result.runs) if (run.diagnostic.status === "COMPLETED") {
        const d = run.diagnostic;
        let legacy: string | null = null;
        try { legacy = (await recognizeHandwrittenMath(capture.strokes.filter((s) => run.scope.strokeIds.includes(s.id)))).latex; } catch { /* original wrapper abstention */ }
        parity.push({ id: run.scope.id, profile: run.scope.profile, legacyLatex: legacy, diagnosticAcceptedLatex: d.frontendAcceptedLatex, equal: legacy === d.frontendAcceptedLatex });
      }
      setLegacyParity(parity);
    } catch (err) { setError(String(err)); } finally { setBusy(false); }
  };
  return <main data-testid="ocr-diagnostics-workbench" aria-busy={busy} data-capture-sha256={captureHash} data-annotation-sha256={annotationHash ?? "NONE"}
    style={{ maxWidth: 1100, margin: "24px auto", padding: 20, color: "#17392d", background: "white" }}>
    <h1>OCR Diagnostics — QA local</h1>
    <p>Import nét đã xuất từ MathCanvas. Chọn nét và ghi nhãn độc lập trước khi xem OCR. File chỉ được đọc trong trình duyệt.</p>
    <label>Capture JSON <input aria-label="Capture JSON" type="file" accept=".json" disabled={busy} onChange={(e) => e.target.files?.[0] && void loadCapture(e.target.files[0])} /></label>
    {error && <p role="alert">{error}</p>}
    {capture && annotation && <>
      <p>{capture.strokes.length} nét · SHA-256: <code>{captureHash}</code></p>
      <label>Annotation JSON <input aria-label="Annotation JSON" type="file" accept=".json" disabled={busy || hasSeenOcr} onChange={(e) => e.target.files?.[0] && void loadAnnotation(e.target.files[0])} /></label>
      <p>Annotation: {annotation.annotationStatus}. Sau khi xem OCR, bộ chọn nhãn bị khóa để tránh lấy prediction làm ground truth.</p>
      <svg viewBox={viewBox} role="group" aria-label="Chọn nét chuẩn" style={{ width: 450, maxWidth: "100%", height: 420, border: "1px solid #777" }}>
        {capture.strokes.filter((s) => s.tool === "PEN" && s.points.length).map((s, index) => <g key={s.id}
            data-testid="annotation-stroke" data-stroke-id={s.id} tabIndex={locked ? -1 : 0} role="button" aria-label={`Chọn nét ${index + 1}`} aria-pressed={selected.includes(s.id)}
            onClick={() => !locked && setSelected((ids) => ids.includes(s.id) ? ids.filter((id) => id !== s.id) : [...ids, s.id])}
            onKeyDown={(e) => { if (!locked && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); setSelected((ids) => ids.includes(s.id) ? ids.filter((id) => id !== s.id) : [...ids, s.id]); } }}>
          {s.points.length === 1 ? <circle cx={s.points[0].x * 794} cy={s.points[0].y * 1123} r={Math.max(3, s.width)} fill={selected.includes(s.id) ? "#d43f13" : "#17392d"} /> :
            <polyline fill="none" stroke={selected.includes(s.id) ? "#d43f13" : "#17392d"} strokeWidth={Math.max(5, s.width * 2)} strokeLinecap="round" strokeLinejoin="round"
              points={s.points.map((p) => `${p.x * 794},${p.y * 1123}`).join(" ")} />}
          {s.points[0] && <text x={s.points[0].x * 794} y={s.points[0].y * 1123 - 5} fontSize={12} pointerEvents="none">{index + 1}</text>}
        </g>)}
      </svg>
      <p>Đã chọn {selected.length} nét.</p>
      <label>Loại nội dung <select aria-label="Loại nhãn" disabled={locked} value={kind} onChange={(e) => setKind(e.target.value as typeof kind)}>
        {["MATH", "TEXT", "UNKNOWN", "STRUCTURE"].map((k) => <option key={k}>{k}</option>)}</select></label>{" "}
      <label>{kind === "TEXT" ? "Bản chép chữ độc lập" : "Nhãn LaTeX độc lập"} <input aria-label="Nhãn LaTeX độc lập" disabled={locked} value={latex} onChange={(e) => setLatex(e.target.value)} /></label>{" "}
      <button type="button" disabled={locked || !selected.length} onClick={addGroup}>Thêm nhóm nhãn</button>
      <ul>{annotation.expectedGroups.map((g) => <li key={g.groupId}>{g.groupId} · {g.contentKind} · {g.strokeIds.length} nét · <code>{g.latex ?? g.text ?? "UNLABELED"}</code>{" "}
        <button type="button" disabled={locked} onClick={() => { setAnnotation({ ...annotation, expectedGroups: annotation.expectedGroups.filter((v) => v.groupId !== g.groupId) }); setAnnotationHash(null); }}>Bỏ nhóm {g.groupId}</button></li>)}</ul>
      <button type="button" disabled={busy} onClick={() => void saveAnnotation(false)}>Tải annotation draft</button>{" "}
      <label><input type="checkbox" disabled={locked} checked={humanConfirmed} onChange={(e) => setHumanConfirmed(e.target.checked)} />Tôi đã đối chiếu nhãn với nét gốc, độc lập với OCR</label>{" "}
      <button type="button" disabled={locked || !humanConfirmed || !annotation.expectedGroups.length} onClick={() => void saveAnnotation(true)}>Xác nhận và tải nhãn chuẩn</button>
      <hr />
      <label>Baseline A <select aria-label="Auto profile" disabled={busy} value={profile} onChange={(e) => setProfile(e.target.value)}>
        <option value="both">Cả hai profile, báo cáo riêng</option><option>LEGACY_REGIONS</option><option>IR_ATOMIC</option></select></label>{" "}
      <label><input aria-label="E2 width variants" type="checkbox" disabled={busy} checked={e2} onChange={(e) => setE2(e.target.checked)} />E2: width ×0.75 và ×1.25, chỉ trên oracle có nhãn</label>{" "}
      <button type="button" data-testid="run-diagnostics" disabled={busy} onClick={() => void run()}>{busy ? "Đang chạy..." : "Chạy A/B diagnostics"}</button>
    </>}
    {result && <section data-testid="diagnostics-results">
      <h2>{result.status}</h2>
      <p>{result.summary.completedInferences}/{result.summary.inferenceCalls} inference hoàn tất. Oracle có nhãn: {result.summary.labeledMathScopes}.</p>
      <p>Beam score không phải calibrated confidence. Kiểm tra cú pháp không chứng minh đúng bản chép hoặc đúng toán.</p>
      {result.runs.map((r, i) => <details key={i}><summary>{r.scope.source} / {r.scope.profile} / {r.scope.id} · {r.diagnostic.status}</summary>
        <pre style={{ whiteSpace: "pre-wrap" }}>{JSON.stringify({ scope: r.scope, diagnostic: r.diagnostic.status === "COMPLETED" ? { ...r.diagnostic,
          preprocessing: { ...r.diagnostic.preprocessing, previewPng: "see image below" } } : r.diagnostic }, null, 2)}</pre>
        {r.diagnostic.status === "COMPLETED" && <img src={r.diagnostic.preprocessing.previewPng} alt="Tensor thực được đưa vào encoder" style={{ maxWidth: "100%", imageRendering: "pixelated" }} />}
      </details>)}
      <button type="button" disabled={busy} data-testid="export-diagnostics" onClick={() => download("ocr-diagnostics.json", { ...result, annotationSha256: resultAnnotationHash, legacyParity })}>Tải kết quả diagnostics</button>{" "}
      <button type="button" disabled={busy} data-testid="check-legacy-parity" onClick={() => void checkLegacy()}>Đối chiếu wrapper legacy cùng scope</button>
      <pre data-testid="legacy-parity">{JSON.stringify(legacyParity, null, 2)}</pre>
    </section>}
  </main>;
}
