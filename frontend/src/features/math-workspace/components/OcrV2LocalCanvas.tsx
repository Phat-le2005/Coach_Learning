"use client";
import { useMemo, useState } from "react";
import { MathCanvas } from "./MathCanvas";
import { OcrV2ExperimentalPanel } from "./OcrV2ExperimentalPanel";
import { validateOcrEvalCapture } from "../utils/ocr-eval-replay";
import { validateLabSource, type LabSource } from "../utils/ocr-v2-experimental";
import type { DrawingTool, InkStroke } from "../types";
import { hashValue, nativePage } from "../utils/ocr-evaluation-data";
import { storeEvaluationTransfer } from "../utils/ocr-evaluation-storage";
import { VietnameseHtrProbePanel } from "./VietnameseHtrProbePanel";
import { generateUuid } from "../utils/ink-math";

/** Actual shared MathCanvas component, local page state; deliberately no persistence client. */
export function OcrV2LocalCanvas() {
  const [pages, setPages] = useState<{ strokes: InkStroke[]; revision: number }[]>([{ strokes: [], revision: 1 }]);
  const [page, setPage] = useState(0), [tool, setTool] = useState<DrawingTool>("pen"), [error, setError] = useState("");
  const [sourceKind, setSourceKind] = useState<LabSource["sourceKind"]>("LIVE_INK"), [split, setSplit] = useState<"DEV" | "HOLDOUT">("DEV"), [writer, setWriter] = useState("");
  const current = pages[page];
  const source = useMemo<LabSource>(() => ({ pageIndex: page, sourceRevision: current.revision, sourceKind, datasetSplit: split, consent: false, writerId: writer || undefined, strokes: current.strokes }), [page, current, sourceKind, split, writer]);
  const changeInk = (strokes: InkStroke[]) => { setPages(previous => previous.map((p, i) => i === page ? { strokes, revision: p.revision + 1 } : p)); setSourceKind("LIVE_INK"); };
  async function importCapture(file: File) {
    try {
      if (file.size > 20_000_000) throw new Error("CAPTURE_TOO_LARGE_20MB");
      const value = JSON.parse(await file.text());
      // A lab export may contain raw tensors/history. Import only its active ink;
      // never promote archived predictions/corrections to a new source or GT.
      const capture = value.schemaVersion === "ocr-v2-experimental/1" && value.source
        ? { pageIndex: value.source.pageIndex, strokes: value.source.strokes }
        : validateOcrEvalCapture(value);
      validateLabSource({ ...source, pageIndex: capture.pageIndex, strokes: capture.strokes });
      setPages(previous => { const next = [...previous]; while (next.length <= capture.pageIndex) next.push({ strokes: [], revision: 1 }); next[capture.pageIndex] = { strokes: structuredClone(capture.strokes), revision: next[capture.pageIndex].revision + 1 }; return next; });
      setPage(capture.pageIndex); setSourceKind("IMPORTED_CAPTURE"); setError("");
    } catch (e) { setError(String(e)); }
  }
  return <main style={{ padding: 16, background: "#f3f6f8", color: "#183149" }}>
    <h1>MathCanvas · OCR V2 local lab</h1>
    <p><a href="/ocr-v2-lab/evaluation" target="_blank" rel="noopener">Dataset / Annotation / Oracle Benchmark</a> · <button data-testid="eval-transfer" onClick={() => { const tab = window.open("about:blank", "_blank"); if (!tab) { setError("Cho phép mở tab mới để chuyển sang annotation; canvas hiện tại vẫn được giữ."); return; } tab.opener = null; void (async () => {
      try { const id = `native-${(await hashValue(current.strokes)).slice(0, 16)}`, p = await nativePage(current.strokes, id, `MathCanvas trang ${page + 1}`, { origin: "LIVE_LAB_TRANSFER; no OCR labels imported" }, current.revision, page);
        p.split = split; p.source.datasetSplit = split; p.provenance.writerId = writer || "NOT_AVAILABLE";
        if (sourceKind === "SYNTHETIC_INK") p.sourceKind = "BROWSER_REPLAY";
        const transfer = generateUuid(); await storeEvaluationTransfer(transfer, p); tab.location.href = `/ocr-v2-lab/evaluation?transfer=${transfer}`;
      } catch (e) { tab.close(); setError(String(e)); }
    })(); }}>Gán nhãn / đánh giá trang đang viết</button></p>
    <p>Viết trực tiếp bằng MathCanvas thật. Trang này chỉ giữ nét trong bộ nhớ trình duyệt, không lưu database. Xuất trước khi đóng tab.</p>
    <VietnameseHtrProbePanel />
    <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 12 }}>
      {["pen", "highlighter", "eraser"].map(t => <button key={t} aria-pressed={tool === t} onClick={() => setTool(t as DrawingTool)}>{t === "pen" ? "Bút" : t === "eraser" ? "Tẩy" : "Dạ quang"}</button>)}
      <button onClick={() => changeInk(current.strokes.slice(0, -1))}>Bỏ nét cuối</button>
      <button onClick={() => { setPages(p => [...p, { strokes: [], revision: 1 }]); setPage(pages.length); setSourceKind("LIVE_INK"); }} disabled={pages.length >= 30}>Thêm trang local</button>
      <label>Trang <select aria-label="Trang lab" value={page} onChange={e => setPage(Number(e.target.value))}>{pages.map((_, i) => <option key={i} value={i}>{i + 1}</option>)}</select></label>
      <label>Import capture <input aria-label="Import capture V2" type="file" accept=".json" onChange={e => e.target.files?.[0] && void importCapture(e.target.files[0])} /></label>
      <label>Nguồn <select aria-label="Nguồn nét V2" value={sourceKind} onChange={e => setSourceKind(e.target.value as LabSource["sourceKind"])}>{["LIVE_INK", "HANDOFF_CAPTURE", "IMPORTED_CAPTURE", "SYNTHETIC_INK"].map(k => <option key={k}>{k}</option>)}</select></label>
      <label>Tập <select aria-label="Dataset split V2" value={split} onChange={e => setSplit(e.target.value as typeof split)}><option>DEV</option><option>HOLDOUT</option></select></label>
      <label>Mã người viết (tùy chọn) <input value={writer} onChange={e => setWriter(e.target.value)} maxLength={60} /></label>
    </div>
    {error && <p role="alert">{error}</p>}
    <div style={{ display: "grid", gridTemplateColumns: "minmax(300px, 794px) minmax(500px, 1fr)", gap: 18, alignItems: "start", overflowX: "auto" }}>
      <div style={{ maxHeight: "85vh", overflow: "auto", background: "white" }} data-testid="v2-live-canvas"><MathCanvas strokes={current.strokes} onStrokesChange={changeInk} currentTool={tool} penColor="#101010" penWidth={2} highlighterWidth={16} paperGrid="plain" zoomLevel={1} /></div>
      <OcrV2ExperimentalPanel source={source} />
    </div>
  </main>;
}
