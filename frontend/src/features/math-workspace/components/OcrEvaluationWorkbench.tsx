"use client";
import { generateUuid } from "../utils/ink-math";
import { useEffect, useMemo, useRef, useState } from "react";
import { annotationCoverage, assertNoSplitLeakage, convertVectorSource, generatePages, hashValue, importInkML, inkHash, LAYOUT_FAMILIES, nativePage, setUnitMembership, trustedUnits, validateAnnotation, validateEvaluationPage,
  type Annotation, type EvaluationPage, type GenerateConfig, type GtUnit, type Kind, type RawVectorSource } from "../utils/ocr-evaluation-data";
import { benchmarkPages, EVALUATION_PROFILES, summarizeBenchmark, type BenchmarkResult, type EvaluationProfile } from "../utils/ocr-evaluation-benchmark";
import { diagnoseMathScope, fingerprintMathScope } from "../utils/ocr-model-diagnostics";
import { csvRows, lassoIds } from "../utils/ocr-v2-experimental";
import { constructScopeCandidates } from "../utils/ocr-v2-scope-candidates";
import { renderTransform } from "../utils/ocr-v2-experimental";
import { readEvaluationWorkspace, saveEvaluationWorkspace, getRecognitionCache, putRecognitionCache, readEvaluationTransfer } from "../utils/ocr-evaluation-storage";
import { computeBounds } from "../utils/structured-transcription-ir";
import { OcrMathPreview } from "./OcrMathPreview";
import styles from "./OcrEvaluationWorkbench.module.css";

type Workspace = { schemaVersion: "ocr-evaluation-workspace/1"; pages: EvaluationPage[]; results: BenchmarkResult[]; selectedId: string; savedAt: string };
type Index = { codeSignature: string; archive: unknown; counts: Record<string, number>; records: RawVectorSource[]; native: { id: string; capture: { strokes: EvaluationPage["source"]["strokes"]; pageIndex: number }; checksum: string; origin: string }[]; rejected: unknown[]; recognizerVocabulary?: string[]; recognizerVocabularySha256?: string };
const saveFile = (name: string, value: unknown, mime = "application/json") => { const blob = new Blob([typeof value === "string" ? value : JSON.stringify(value, null, 2)], { type: mime }); const url = URL.createObjectURL(blob), link = document.createElement("a"); link.href = url; link.download = name; link.click(); setTimeout(() => URL.revokeObjectURL(url), 2000); };
const display = (n: unknown) => typeof n === "number" ? Number.isInteger(n) ? n : n.toFixed(3) : n === null || n === undefined ? "NOT_MEASURED" : String(n);
const hasStoredModelExposure = (page: EvaluationPage) => Boolean(page.provenance.importedModelEvidence || (Array.isArray(page.provenance.evaluationExposures) && page.provenance.evaluationExposures.length));
function invalidate(annotation: Annotation, id?: string): Annotation {
  const next = structuredClone(annotation); next.status = "DRAFT"; next.origin = "HUMAN"; delete next.confirmedAt;
  if (annotation.origin !== "HUMAN") next.units.forEach(u => { u.confirmed = false; });
  if (id) { const changed = new Set([id]); let again = true; while (again) { again = false; next.units.forEach(u => { if (!changed.has(u.id) && u.childIds.some(id => changed.has(id))) { changed.add(u.id); again = true; } }); } next.units.forEach(u => { if (changed.has(u.id)) u.confirmed = false; }); }
  return next;
}

/** Standalone QA workflow. All annotations/results stay in IndexedDB or user exports. */
export function OcrEvaluationWorkbench() {
  const [pages, setPages] = useState<EvaluationPage[]>([]), [results, setResults] = useState<BenchmarkResult[]>([]), [selectedId, setSelectedId] = useState("");
  const [index, setIndex] = useState<Index | null>(null), [ready, setReady] = useState(false), [busy, setBusy] = useState(false), [message, setMessage] = useState("Nạp nguồn hoặc import capture để bắt đầu."), [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState("Đang mở bộ nhớ local…"), [picked, setPicked] = useState<string[]>([]), [unitId, setUnitId] = useState(""), [kind, setKind] = useState<Kind>("MATH");
  const [zoom, setZoom] = useState(1), [lasso, setLasso] = useState(false), [polygon, setPolygon] = useState<{ x: number; y: number; pressure: number }[]>([]), [childIds, setChildIds] = useState<string[]>([]), [relation, setRelation] = useState<NonNullable<GtUnit["relation"]>>("UNKNOWN");
  const [reviewer, setReviewer] = useState(""), [humanDeclaration, setHumanDeclaration] = useState(false), [overlay, setOverlay] = useState("GT"), [caseSplit, setCaseSplit] = useState("ALL"), [caseKind, setCaseKind] = useState("ALL");
  const [gen, setGen] = useState<GenerateConfig>({ seed: 20261104, count: 16, split: "DEV", family: "CYCLE", expressions: 3, gapPx: 24, rotationDegrees: 2, thickness: 1 });
  const [profiles, setProfiles] = useState<EvaluationProfile[]>(["GEOMETRY", "LAYOUT", "HYBRID", "ORACLE"]), [maxCases, setMaxCases] = useState(2), [inferenceLimit, setInferenceLimit] = useState(12), [recognize, setRecognize] = useState(true), [batchSelection, setBatchSelection] = useState<string[]>([]);
  const cancel = useRef(false), fileLock = useRef(false), pathRef = useRef<typeof polygon>([]), svgRef = useRef<SVGSVGElement>(null), history = useRef<Record<string, { undo: Annotation[]; redo: Annotation[] }>>({}), [, renderHistory] = useState(0);
  const mayPersist = useRef(true);
  const savedVersion = useRef<string | undefined>(undefined), saveQueue = useRef<Promise<void>>(Promise.resolve());
  const page = pages.find(p => p.id === selectedId), unit = page?.annotation.units.find(u => u.id === unitId);
  const latest = results.at(-1), arms = latest?.arms.filter(a => a.pageId === selectedId) ?? [], shownArm = arms.find(a => a.profile === overlay);
  const filtered = useMemo(() => pages.filter(p => (caseSplit === "ALL" || p.split === caseSplit) && (caseKind === "ALL" || p.sourceKind === caseKind)), [pages, caseSplit, caseKind]);
  const summary = latest ? summarizeBenchmark(latest.arms) : [];
  useEffect(() => { let live = true; void (async () => {
    try {
      const saved = await readEvaluationWorkspace<Workspace>(); let restored = saved?.schemaVersion === "ocr-evaluation-workspace/1" ? saved.pages : [];
      savedVersion.current = saved?.savedAt;
      restored = await Promise.all(restored.map(validateEvaluationPage));
      const transfer = sessionStorage.getItem("ocr-evaluation-transfer"); if (transfer) { const p = await validateEvaluationPage(JSON.parse(transfer)); if (!restored.some(old => old.id === p.id && old.sourceChecksum === p.sourceChecksum)) restored.push(p); sessionStorage.removeItem("ocr-evaluation-transfer"); if (live) setSelectedId(p.id); }
      const transferId = new URLSearchParams(location.search).get("transfer");
      if (transferId && /^[a-f0-9-]{36}$/.test(transferId)) { const value = await readEvaluationTransfer<EvaluationPage>(transferId); if (value) { const p = await validateEvaluationPage(value); if (!restored.some(old => old.id === p.id && old.sourceChecksum === p.sourceChecksum)) restored.push(p); if (live) setSelectedId(p.id); } }
      assertNoSplitLeakage(restored);
      if (live) { setPages(restored); setResults(saved?.results ?? []); setSelectedId(id => id || saved?.selectedId || restored[0]?.id || ""); setSaveStatus("Đã khôi phục IndexedDB local"); }
    } catch (e) { mayPersist.current = false; if (live) { setError(`Khôi phục thất bại: ${String(e)}. Dữ liệu cũ không bị xóa; autosave tạm khóa để bảo vệ bản cũ.`); setSaveStatus("BLOCKED_STORAGE; hãy xuất JSON"); } }
    finally { if (live) setReady(true); }
  })(); return () => { live = false; }; }, []);
  useEffect(() => {
    if (!ready || !mayPersist.current) return; setSaveStatus("Đang lưu local…"); const timer = setTimeout(() => {
      const value = { schemaVersion: "ocr-evaluation-workspace/1", pages, results, selectedId, savedAt: new Date().toISOString() } satisfies Workspace;
      saveQueue.current = saveQueue.current.then(async () => { if (!mayPersist.current) return; await saveEvaluationWorkspace(value, savedVersion.current); savedVersion.current = value.savedAt; setSaveStatus("Đã lưu IndexedDB trên máy"); }).catch(e => { mayPersist.current = false; setSaveStatus("BLOCKED_STORAGE; xuất JSON trước khi đóng tab"); setError(String(e)); });
    }, 350); return () => clearTimeout(timer);
  }, [pages, results, selectedId, ready]);
  useEffect(() => { const warn = (e: BeforeUnloadEvent) => { if (!saveStatus.startsWith("Đã")) { e.preventDefault(); e.returnValue = ""; } }; window.addEventListener("beforeunload", warn); return () => window.removeEventListener("beforeunload", warn); }, [saveStatus]);
  useEffect(() => { setPicked([]); setUnitId(""); setChildIds([]); setHumanDeclaration(false); }, [selectedId]);
  function addPages(incoming: EvaluationPage[]) {
    const next = [...pages];
    incoming.forEach((p, i) => {
      const sameInk = next.filter(o => o.sourceChecksum === p.sourceChecksum);
      const exposure = [...new Set([p, ...sameInk].flatMap(o => Array.isArray(o.provenance.evaluationExposures) ? o.provenance.evaluationExposures : []).map(x => JSON.stringify(x)))].map(x => JSON.parse(x));
      const importedModelEvidence = [p, ...sameInk].some(o => Boolean(o.provenance.importedModelEvidence));
      p = { ...p, provenance: { ...p.provenance, ...(exposure.length ? { evaluationExposures: exposure.slice(-100) } : {}), ...(importedModelEvidence ? { importedModelEvidence: true } : {}) } };
      incoming[i] = p;
      const existing = next.find(o => o.id === p.id && o.sourceChecksum === p.sourceChecksum);
      if (existing && JSON.stringify(existing.annotation) === JSON.stringify(p.annotation)) {
        next[next.indexOf(existing)] = { ...existing, provenance: { ...existing.provenance, ...p.provenance } }; return;
      }
      // An imported GT version must not silently disappear or overwrite local confirmed edits.
      if (existing) p = { ...p, id: `${p.id}-import-${generateUuid().slice(0, 8)}`, title: `${p.title} [import version]` };
      else if (next.some(o => o.id === p.id)) p = { ...p, id: `${p.id}-${p.sourceChecksum.slice(0, 8)}` };
      incoming[i] = p; next.push(p);
    });
    assertNoSplitLeakage(next); setPages(next); if (!selectedId && incoming.length) setSelectedId(incoming[0].id);
  }
  function update(annotation: Annotation) {
    if (!page || busy) return; validateAnnotation({ ...page, annotation }); const h = history.current[page.id] ??= { undo: [], redo: [] }; h.undo.push(structuredClone(page.annotation)); h.undo = h.undo.slice(-40); h.redo = [];
    setPages(old => old.map(p => p.id === page.id ? { ...p, annotation } : p)); renderHistory(n => n + 1);
  }
  function guarded(action: () => void) { try { action(); setError(""); } catch (e) { setError(String(e)); } }
  async function loadIndex() {
    if (busy) return; setBusy(true); setError("");
    try {
      const response = await fetch("/api/ocr-v2-lab/evaluation", { cache: "no-store" }), data = await response.json(); if (!response.ok) throw Error(data.message ?? response.statusText); setIndex(data);
      const loaded: EvaluationPage[] = [], rejected: string[] = [];
      for (const raw of (data as Index).records) { try { loaded.push(await convertVectorSource(raw, true)); } catch (e) { rejected.push(`${raw.id}: ${String(e)}`); } }
      for (const n of (data as Index).native) loaded.push(await nativePage(n.capture.strokes, n.id, `${n.id} · ${n.capture.strokes.length} nét`, { originalFile: n.origin, originalFileChecksum: n.checksum, groundTruth: "NONE; ignores all model outputs/corrections", importedModelEvidence: true, exposureNote: "Previously used diagnostic captures; not unseen native holdout" }, 1, n.capture.pageIndex));
      addPages(loaded); setMessage(`Đã nạp ${loaded.length} mẫu; excerpt có ${Object.values((data as Index).counts).reduce((a, b) => a + b, 0)} InkML. Symbols/synthetic không dùng làm nguồn ghép người thật. Bị loại: ${rejected.length}.`); if (rejected.length) setError(rejected.slice(0, 4).join("\n"));
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function importFile(file: File) {
    if (busy || fileLock.current) return; fileLock.current = true; setBusy(true); setError("");
    try {
      if (file.size > 150_000_000) throw Error("IMPORT_LIMIT_150MB"); const text = await file.text(); let incoming: EvaluationPage[] = [];
      if (/\.inkml$/i.test(file.name)) incoming = [await importInkML(text, file.name)];
      else {
        const data = JSON.parse(text);
        if (data.schemaVersion === "ocr-evaluation-workspace/1") { if (!Array.isArray(data.pages) || data.pages.length > 1000) throw Error("WORKSPACE_PAGE_LIMIT_1000"); incoming = await Promise.all(data.pages.map(validateEvaluationPage)); setResults(old => [...old, ...(data.results ?? [])]); }
        else if (data.schemaVersion === "ocr-evaluation/1") incoming = [await validateEvaluationPage(data)];
        else {
          const src = data.source?.strokes ? data.source : data.strokes ? data : null; if (!src) throw Error("NO_VECTOR_INK; screenshot is not a capture");
          const id = `native-${(await hashValue(src.strokes)).slice(0, 16)}`;
          incoming = [await nativePage(src.strokes, id, file.name, { filename: file.name, originalFileChecksum: await hashValue(text), importedPredictions: "IGNORED; labels not copied from OCR", importedModelEvidence: Array.isArray(data.recognition) && data.recognition.length > 0 }, src.sourceRevision ?? 1, src.pageIndex ?? 0)];
          incoming[0].provenance.writerId = src.writerId ?? "NOT_AVAILABLE";
          if (src.datasetSplit === "DEV" || src.datasetSplit === "HOLDOUT") { incoming[0].split = src.datasetSplit; incoming[0].source.datasetSplit = src.datasetSplit; }
        }
      }
      addPages(incoming); setSelectedId(incoming[0]?.id ?? ""); setMessage(`Import ${incoming.length} mẫu. Nhãn đã xác nhận chỉ được giữ khi source checksum/hierarchy hợp lệ.`);
    } catch (e) { setError(String(e)); } finally { fileLock.current = false; setBusy(false); }
  }
  function newUnit() {
    if (!page || !picked.length) return;
    const next = invalidate(page.annotation), id = `gt-${generateUuid()}`;
    next.units.push({ id, kind, strokeIds: [...picked], transcript: null, readingOrder: Math.max(-1, ...next.units.map(u => u.readingOrder)) + 1, childIds: [], confirmed: false });
    const fixed = setUnitMembership({ ...page, annotation: next }, id, picked); update(fixed); setUnitId(id); setPicked([]);
  }
  function editUnit(patch: Partial<GtUnit>) { if (!page || !unit) return; const next = invalidate(page.annotation, unit.id); next.units = next.units.map(u => u.id === unit.id ? { ...u, ...patch, confirmed: false } : u); update(next); }
  function confirmUnit() {
    if (!page || !unit || !humanDeclaration || !reviewer.trim()) throw Error("Cần tên người gán nhãn và xác nhận đã đối chiếu nét gốc");
    if (unit.childIds.some(id => !page.annotation.units.find(u => u.id === id)?.confirmed)) throw Error("Xác nhận các đơn vị con trước");
    const next = invalidate(page.annotation); next.reviewer = reviewer.trim(); next.assisted ||= hasStoredModelExposure(page) || results.some(r => r.arms.some(a => a.pageId === page.id));
    next.units = next.units.map(u => u.id === unit.id ? { ...u, confirmed: true, humanConfirmation: { reviewer: reviewer.trim(), at: new Date().toISOString(), assisted: next.assisted } } : u); update(next);
  }
  function confirmAll() {
    if (!page || !humanDeclaration || !reviewer.trim()) throw Error("Cần xác nhận đối chiếu và tên người gán nhãn");
    const next = { ...page.annotation, status: "HUMAN_CONFIRMED" as const, origin: "HUMAN" as const, reviewer: reviewer.trim(), confirmedAt: new Date().toISOString(), assisted: page.annotation.assisted || hasStoredModelExposure(page) || results.some(r => r.arms.some(a => a.pageId === page.id)) };
    next.units = next.units.map(u => u.confirmed ? { ...u, humanConfirmation: { reviewer: reviewer.trim(), at: next.confirmedAt, assisted: next.assisted } } : u);
    const confirmed: Annotation = page.softwareTestOnly ? { ...next, status: "SOFTWARE_SIMULATED", origin: "SOFTWARE_TEST" } : next;
    validateAnnotation({ ...page, annotation: confirmed }, true); update(confirmed); setMessage("Đã xác nhận GT (test automation được gắn SOFTWARE_SIMULATED). Benchmark không sửa nhãn; sửa child hủy xác nhận phụ thuộc.");
  }
  function createRelation() {
    if (!page || childIds.length < 2) throw Error("Chọn ít nhất hai đơn vị con");
    const next = invalidate(page.annotation), children = next.units.filter(u => childIds.includes(u.id));
    if (children.length !== childIds.length || next.units.some(u => u.childIds.some(id => childIds.includes(id)))) throw Error("Chỉ chọn các root units để tạo cấu trúc");
    const id = `structure-${generateUuid()}`;
    next.units.push({ id, kind: "STRUCTURE", relation, childIds: [...childIds], strokeIds: [...new Set([...children.flatMap(u => u.strokeIds), ...picked])], transcript: null, readingOrder: Math.min(...children.map(u => u.readingOrder)), confirmed: false });
    update(next); setUnitId(id); setPicked([]); setChildIds([]);
  }
  function mergeUnits() {
    if (!page || childIds.length < 2) throw Error("Chọn ít nhất hai atomic root units");
    const selected = page.annotation.units.filter(u => childIds.includes(u.id)).sort((a, b) => a.readingOrder - b.readingOrder);
    if (selected.some(u => u.kind === "STRUCTURE") || page.annotation.units.some(u => u.childIds.some(id => childIds.includes(id)))) throw Error("Gộp các atomic root units; sửa quan hệ parent trước nếu cần");
    const next = invalidate(page.annotation), id = `merged-${generateUuid()}`;
    next.units = next.units.filter(u => !childIds.includes(u.id)); next.units.push({ id, kind: selected.every(u => u.kind === selected[0].kind) ? selected[0].kind : "UNKNOWN", strokeIds: [...new Set(selected.flatMap(u => u.strokeIds))], transcript: selected.map(u => u.transcript ?? "").join("\n"), childIds: [], readingOrder: selected[0].readingOrder, confirmed: false });
    update(next); setUnitId(id); setChildIds([]);
  }
  function moveUnit(direction: number) {
    if (!page || !unit) return; const parent = page.annotation.units.find(u => u.childIds.includes(unit.id));
    const siblings = page.annotation.units.filter(u => parent ? parent.childIds.includes(u.id) : !page.annotation.units.some(p => p.childIds.includes(u.id))).sort((a, b) => a.readingOrder - b.readingOrder);
    const i = siblings.findIndex(u => u.id === unit.id), target = i + direction; if (target < 0 || target >= siblings.length) return;
    [siblings[i], siblings[target]] = [siblings[target], siblings[i]]; const next = invalidate(page.annotation); next.units = next.units.map(u => siblings.some(s => s.id === u.id) ? { ...u, readingOrder: siblings.findIndex(s => s.id === u.id) } : u); update(next);
  }
  async function runBenchmark() {
    if (busy || !page) return; setBusy(true); setError(""); cancel.current = false;
    try {
      // Dev hot reload can change constructor code after the source pool was loaded.
      // Refresh the working-tree signature before every run rather than reuse a stale cache namespace.
      const response = await fetch("/api/ocr-v2-lab/evaluation", { cache: "no-store" });
      const descriptor = await response.json(); if (!response.ok || !descriptor.codeSignature) throw Error("Dataset/code descriptor unavailable; prepare sources first");
      const selected = batchSelection.length ? pages.filter(p => batchSelection.includes(p.id)) : [page];
      const result = await benchmarkPages(structuredClone(selected), { profiles, maxCases, inferenceLimit, recognitionEnabled: recognize, codeSignature: descriptor.codeSignature, vocabulary: descriptor.recognizerVocabulary, vocabularySha256: descriptor.recognizerVocabularySha256 }, {
        detect: async png => { const r = await fetch("/api/ocr-v2-lab", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ model: "LAYOUT_M", png }), signal: AbortSignal.timeout(90000) }); const p = await r.json(); return { ...p, status: p.status ?? `HTTP_${r.status}`, regions: p.regions ?? [], model: "LAYOUT_M" }; },
        recognize: diagnoseMathScope, fingerprint: fingerprintMathScope, cacheGet: getRecognitionCache, cachePut: putRecognitionCache, progress: setMessage, cancelled: () => cancel.current,
      });
      // Exposure survives a GT-only export/reimport too; original confirmed labels stay unchanged.
      setPages(old => old.map(p => result.arms.some(a => a.pageId === p.id) ? { ...p, provenance: { ...p.provenance, evaluationExposures: [...(Array.isArray(p.provenance.evaluationExposures) ? p.provenance.evaluationExposures : []), { at: result.completedAt, profiles: result.config.profiles, recognitionRequested: result.config.recognitionEnabled, codeSignature: result.config.codeSignature }].slice(-100) } } : p));
      setResults(old => [...old, result]); setMessage(`${result.arms.length} arms · ${result.actualInferenceCalls} inference thực · ${result.cacheHits} cache hits theo tensor/model/config; nhãn không thay đổi.`);
    } catch (e) { setError(String(e)); } finally { setBusy(false); }
  }
  async function generate() { if (busy) return; setBusy(true); setError(""); try { const generated = await generatePages(pages, gen); addPages(generated); setBatchSelection(generated.map(p => p.id)); setSelectedId(generated[0].id); setMessage(`Đã tạo ${generated.length} trang ${gen.split}; membership xác định bởi phép ghép, không phải trang native.`); } catch (e) { setError(String(e)); } finally { setBusy(false); } }
  function point(e: React.PointerEvent<SVGSVGElement>) { const p = e.currentTarget.createSVGPoint(); p.x = e.clientX; p.y = e.clientY; const matrix = e.currentTarget.getScreenCTM(); if (!matrix) throw Error("SVG_MATRIX_UNAVAILABLE"); const v = p.matrixTransform(matrix.inverse()); return { x: v.x / 794, y: v.y / 1123, pressure: .5 }; }
  function exportOverlay(format: "svg" | "png") {
    if (!svgRef.current || !page) return; const svg = svgRef.current.cloneNode(true) as SVGSVGElement; svg.setAttribute("xmlns", "http://www.w3.org/2000/svg"); svg.setAttribute("width", "794"); svg.setAttribute("height", "1123"); const text = new XMLSerializer().serializeToString(svg);
    if (format === "svg") return saveFile(`${page.id}-${overlay}.svg`, text, "image/svg+xml");
    const image = new Image(); image.onload = () => { const canvas = document.createElement("canvas"); canvas.width = 794; canvas.height = 1123; canvas.getContext("2d")!.drawImage(image, 0, 0); canvas.toBlob(blob => { if (blob) { const url = URL.createObjectURL(blob), a = document.createElement("a"); a.href = url; a.download = `${page.id}-${overlay}.png`; a.click(); setTimeout(() => URL.revokeObjectURL(url), 2000); } }); }; image.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(text)}`;
  }
  const highlighted = picked.length ? picked : unit?.strokeIds ?? [], overlayUnits = overlay === "GT" ? page?.annotation.units ?? [] : shownArm?.scopes ?? [];
  return <main className={styles.main} data-testid="ocr-evaluation" aria-busy={busy}>
    <h1>OCR V2 · Dataset, Annotation & Evaluation</h1><p><a href="/ocr-v2-lab">← Viết MathCanvas</a> · Local/dev only · không lưu lời giải, không gọi Evaluator, không cloud inference.</p>
    <p>Import → khoanh nét → nhập bản chép đúng theo nét → xác nhận GT → benchmark → xem lỗi → export. Nhãn nguồn, nhãn ghép và nhãn người dùng được báo cáo riêng.</p>
    <p role="status" data-testid="eval-progress">{message}</p><p data-testid="eval-save-status">{saveStatus}</p>{error && <pre role="alert">{error}</pre>}
    <section className={styles.controls}>
      <button disabled={busy || !ready} onClick={() => void loadIndex()} data-testid="eval-load-sources">Nạp nguồn MathWriting + captures local</button>
      <label>Import capture / bundle / InkML / GT workspace <input data-testid="eval-import" type="file" accept=".json,.inkml" disabled={busy || !ready} onChange={e => e.target.files?.[0] && void importFile(e.target.files[0])} /></label>
      <button disabled={!ready || busy || !pages.length} onClick={() => saveFile("ocr-evaluation-workspace.json", { schemaVersion: "ocr-evaluation-workspace/1", pages, results, selectedId, savedAt: new Date().toISOString() } satisfies Workspace)}>Xuất dataset + annotation + kết quả</button>
      {page && <button disabled={busy} data-testid="eval-export-gt" onClick={() => saveFile("ocr-evaluation-ground-truth.json", page)}>Xuất GT của trang</button>}
    </section>
    <section><h2>Dataset overview</h2><p data-testid="eval-dataset-count">{pages.length} mẫu · native {pages.filter(p => p.sourceKind === "NATIVE_MATHCANVAS").length} · external {pages.filter(p => p.sourceKind.startsWith("EXTERNAL")).length} · composed {pages.filter(p => p.sourceKind === "SYNTHETIC_COMPOSED_REAL_INK").length} · DEV {pages.filter(p => p.split === "DEV").length} · HOLDOUT {pages.filter(p => p.split === "HOLDOUT").length} · nguồn {pages.filter(p => p.annotation.status === "SOURCE_AUTHORITATIVE").length} · ghép {pages.filter(p => p.annotation.status === "GENERATED_DETERMINISTIC").length} · người xác nhận {pages.filter(p => p.annotation.status === "HUMAN_CONFIRMED").length} · test mô phỏng {pages.filter(p => p.annotation.status === "SOFTWARE_SIMULATED").length} · draft {pages.filter(p => p.annotation.status === "DRAFT").length}</p>
      <p>MathWriting: CC BY-NC-SA 4.0, chỉ dùng phù hợp điều kiện phi thương mại; metadata nguồn/attribution giữ trong export. Không có writer IDs công khai. <a href="https://github.com/google-research/google-research/tree/master/mathwriting" target="_blank" rel="noreferrer">Nguồn chính thức</a></p>
      <label>Tập <select aria-label="Evaluation split filter" value={caseSplit} onChange={e => setCaseSplit(e.target.value)}>{["ALL", "DEV", "HOLDOUT"].map(x => <option key={x}>{x}</option>)}</select></label>
      <label>Nguồn <select aria-label="Evaluation kind filter" value={caseKind} onChange={e => setCaseKind(e.target.value)}>{["ALL", "NATIVE_MATHCANVAS", "EXTERNAL_HUMAN_INK", "EXTERNAL_SYNTHETIC_INK", "SYNTHETIC_COMPOSED_REAL_INK", "BROWSER_REPLAY"].map(x => <option key={x}>{x}</option>)}</select></label>
      <label>Chọn case <select data-testid="eval-case" value={selectedId} disabled={busy} onChange={e => setSelectedId(e.target.value)}><option value="">Chọn…</option>{filtered.map(p => <option key={p.id} value={p.id}>{p.title.slice(0, 85)} · {p.sourceKind} · {p.split} · {p.annotation.status}</option>)}</select></label>
      <button disabled={busy} onClick={() => setBatchSelection(filtered.map(p => p.id))}>Đưa các case đang lọc vào batch</button><button onClick={() => setBatchSelection([])} disabled={busy}>Chỉ case đang xem</button><p>Batch đã chọn: {batchSelection.length || (page ? 1 : 0)}.</p>
    </section>
    <details><summary>Sinh batch từ nét người thật có nhãn (10–20 smoke, 100–300 pilot)</summary><div className={styles.controls}>
      <label>Seed <input aria-label="Generator seed" type="number" value={gen.seed} onChange={e => setGen({ ...gen, seed: Number(e.target.value) })} /></label>
      <label>Số trang <input aria-label="Generator count" type="number" min={1} max={300} value={gen.count} onChange={e => setGen({ ...gen, count: Number(e.target.value) })} /></label>
      <label>Biểu thức/trang <input aria-label="Generator expressions" type="number" min={1} max={6} value={gen.expressions} onChange={e => setGen({ ...gen, expressions: Number(e.target.value) })} /></label>
      <label>Layout <select aria-label="Generator layout" value={gen.family} onChange={e => setGen({ ...gen, family: e.target.value as GenerateConfig["family"] })}>{["CYCLE", ...LAYOUT_FAMILIES].map(x => <option key={x}>{x}</option>)}</select></label>
      <label>Tập <select aria-label="Generator split" value={gen.split} onChange={e => setGen({ ...gen, split: e.target.value as "DEV" | "HOLDOUT" })}><option>DEV</option><option>HOLDOUT</option></select></label>
      <label>Khoảng cách px <input aria-label="Generator gap" type="number" min={4} max={100} value={gen.gapPx} onChange={e => setGen({ ...gen, gapPx: Number(e.target.value) })} /></label>
      <label>Góc tối đa ° <input aria-label="Generator rotation" type="number" min={0} max={5} value={gen.rotationDegrees} onChange={e => setGen({ ...gen, rotationDegrees: Number(e.target.value) })} /></label>
      <label>Độ dày × <input aria-label="Generator thickness" type="number" min={.5} max={2} step={.1} value={gen.thickness} onChange={e => setGen({ ...gen, thickness: Number(e.target.value) })} /></label>
      <label><input type="checkbox" checked={!!gen.writerSplit} onChange={e => setGen({ ...gen, writerSplit: e.target.checked })} />Split theo writer (BLOCKED nếu thiếu ID)</label>
      <button disabled={busy || !pages.length} data-testid="eval-generate" onClick={() => void generate()}>Tạo batch có GT xác định</button>
    </div><p>A4 794×1123; chuyển đổi affine có inverse. ALIGNED căn trái bbox, không giả vờ có nhãn vị trí dấu bằng. SYSTEM_DEFINED là quan hệ được bộ sinh định nghĩa tường minh; không thêm nét ngoặc giả. Source expression và mọi biến thể luôn ở cùng split.</p></details>
    {page && <section><h2>Annotation / per-case investigation</h2><p>{page.title} · {page.source.strokes.length} nét · {page.sourceKind} · {page.split} · annotation {page.annotation.status}/{page.annotation.origin} · coverage {annotationCoverage(page).covered}/{annotationCoverage(page).total} · Oracle units hợp lệ {trustedUnits(page).length}</p>
      <label>Tên sample <input aria-label="Evaluation sample title" value={page.title} disabled={busy} onChange={e => setPages(old => old.map(p => p.id === page.id ? { ...p, title: e.target.value } : p))} /></label>
      {page.split === "HOLDOUT" && <p role="note">HOLDOUT: không tinh chỉnh thuật toán từ những kết quả này rồi tiếp tục coi tập là độc lập.</p>}{page.softwareTestOnly && <p role="note">SOFTWARE WORKFLOW TEST ONLY — không coi thao tác browser automation là xác nhận của người viết thật.</p>}
      {(page.sourceKind === "NATIVE_MATHCANVAS" || page.sourceKind === "BROWSER_REPLAY") && <label>Tập của capture (khóa sau benchmark) <select aria-label="Native dataset split" value={page.split} disabled={busy || hasStoredModelExposure(page) || results.some(r => r.arms.some(a => a.pageId === page.id))} onChange={e => guarded(() => { const split = e.target.value as "DEV" | "HOLDOUT", next = pages.map(p => p.id === page.id ? { ...p, split, source: { ...p.source, datasetSplit: split } } : p); assertNoSplitLeakage(next); setPages(next); })}><option>DEV</option><option>HOLDOUT</option></select></label>}
      <div className={styles.columns}>
        <div><div className={styles.controls}><button aria-pressed={lasso} onClick={() => setLasso(!lasso)} disabled={busy}>Khoanh nét GT</button><button onClick={() => setPicked(page.source.strokes.filter(s => s.tool === "PEN").map(s => s.id))} disabled={busy}>Chọn toàn bộ nét</button><button onClick={() => setPicked([])}>Bỏ chọn</button><label>Zoom <input aria-label="Annotation zoom" type="range" min={.5} max={2.5} step={.1} value={zoom} onChange={e => setZoom(Number(e.target.value))} /></label></div>
          <label>Overlay <select data-testid="eval-overlay" value={overlay} onChange={e => setOverlay(e.target.value)}>{["GT", ...EVALUATION_PROFILES, "RAW_LAYOUT"].map(x => <option key={x}>{x}</option>)}</select></label>
          <div className={styles.scroll}><svg ref={svgRef} data-testid="eval-ink" viewBox="0 0 794 1123" style={{ width: 540 * zoom, minWidth: 540 * zoom, background: "white", touchAction: "none" }}
            onPointerDown={e => { if (!lasso || busy) return; e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId); pathRef.current = [point(e)]; setPolygon(pathRef.current); }}
            onPointerMove={e => { if (lasso && e.currentTarget.hasPointerCapture(e.pointerId)) { pathRef.current.push(point(e)); setPolygon([...pathRef.current]); } }}
            onPointerUp={e => { if (!lasso || !e.currentTarget.hasPointerCapture(e.pointerId)) return; e.currentTarget.releasePointerCapture(e.pointerId); setPicked(lassoIds(page.source, pathRef.current)); pathRef.current = []; setPolygon([]); }}>
            <rect width={794} height={1123} fill="white" pointerEvents="none" />
            {page.source.strokes.filter(s => s.tool === "PEN").map((s, i) => <g key={s.id} data-testid="eval-stroke" data-stroke-id={s.id} role="button" tabIndex={0} pointerEvents="bounding-box" aria-label={`GT nét ${i + 1}`} aria-pressed={picked.includes(s.id)} onClick={() => { if (!lasso && !busy) setPicked(p => p.includes(s.id) ? p.filter(id => id !== s.id) : [...p, s.id]); }}
              onKeyDown={e => { if (!busy && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); setPicked(p => p.includes(s.id) ? p.filter(id => id !== s.id) : [...p, s.id]); } }}>
              {s.points.length === 1 ? <circle cx={s.points[0].x * 794} cy={s.points[0].y * 1123} r={Math.max(2, s.width)} fill={highlighted.includes(s.id) ? "#d34d17" : "#151515"} /> : <polyline points={s.points.map(p => `${p.x * 794},${p.y * 1123}`).join(" ")} fill="none" stroke={highlighted.includes(s.id) ? "#d34d17" : "#151515"} strokeWidth={s.width} strokeLinecap="round" strokeLinejoin="round" />}
            </g>)}
            {overlayUnits.map((u, i) => { const b = computeBounds(page.source.strokes.filter(s => u.strokeIds.includes(s.id))); return <g key={u.id} pointerEvents="none"><rect x={b.left * 794} y={b.top * 1123} width={Math.max(1, (b.right - b.left) * 794)} height={Math.max(1, (b.bottom - b.top) * 1123)} fill="none" stroke={overlay === "GT" ? "#00986e" : "#225cb8"} strokeDasharray={u.kind === "STRUCTURE" ? "5 3" : undefined} /><text x={b.left * 794} y={b.top * 1123 - 3} fontSize={12} fill="#007958">{i + 1} {u.kind}</text></g>; })}
            {overlay === "RAW_LAYOUT" && arms.find(a => a.perception)?.perception?.regions.map(r => <g key={r.id} pointerEvents="none"><rect x={r.box[0] - 16} y={r.box[1] - 16} width={r.box[2] - r.box[0]} height={r.box[3] - r.box[1]} fill="none" stroke="#a722a0" /><text x={r.box[0] - 16} y={r.box[1] - 18} fontSize={12}>{r.label} {r.score?.toFixed(3)}</text></g>)}
            {polygon.length > 1 && <polygon points={polygon.map(p => `${p.x * 794},${p.y * 1123}`).join(" ")} fill="#48a2e533" stroke="#2474bb" />}
          </svg></div><p data-testid="eval-picked">Đã chọn {picked.length} nét; nguyên bản không thay đổi.</p>
          <div className={styles.controls}><button onClick={() => exportOverlay("svg")}>Xuất overlay SVG</button><button onClick={() => exportOverlay("png")}>Xuất overlay PNG</button></div>
        </div>
        <div><div className={styles.controls}><label>Loại đơn vị mới <select aria-label="GT new kind" value={kind} onChange={e => setKind(e.target.value as Kind)}>{["MATH", "TEXT", "UNKNOWN"].map(x => <option key={x}>{x}</option>)}</select></label><button disabled={busy || !picked.length} data-testid="eval-add-unit" onClick={() => guarded(newUnit)}>Tạo đơn vị GT từ nét đã chọn</button>
          <button disabled={busy || !history.current[page.id]?.undo.length} onClick={() => { const h = history.current[page.id]; h.redo.push(page.annotation); const a = h.undo.pop()!; setPages(old => old.map(p => p.id === page.id ? { ...p, annotation: a } : p)); renderHistory(n => n + 1); }}>Undo annotation</button><button disabled={busy || !history.current[page.id]?.redo.length} onClick={() => { const h = history.current[page.id]; h.undo.push(page.annotation); const a = h.redo.pop()!; setPages(old => old.map(p => p.id === page.id ? { ...p, annotation: a } : p)); renderHistory(n => n + 1); }}>Redo annotation</button></div>
          <nav>{page.annotation.units.map(u => <div key={u.id}><input type="checkbox" aria-label={`GT child ${u.id}`} checked={childIds.includes(u.id)} onChange={e => setChildIds(ids => e.target.checked ? [...ids, u.id] : ids.filter(id => id !== u.id))} /><button aria-current={unitId === u.id ? "true" : undefined} onClick={() => { setUnitId(u.id); setPicked([]); }}>{u.readingOrder + 1}. {u.kind} · {u.strokeIds.length} nét · {u.confirmed ? "CONFIRMED" : "DRAFT"}</button></div>)}</nav>
          {unit && <div data-testid="eval-unit-editor"><p>{unit.id}</p>{unit.kind !== "STRUCTURE" ? <><label>Loại <select aria-label="GT unit kind" disabled={busy} value={unit.kind} onChange={e => guarded(() => editUnit({ kind: e.target.value as Kind }))}>{["MATH", "TEXT", "UNKNOWN"].map(x => <option key={x}>{x}</option>)}</select></label><label>{unit.kind === "TEXT" ? "Nguyên văn tiếng Việt" : "LaTeX theo nét gốc"}<textarea data-testid="eval-transcript" disabled={busy} value={unit.transcript ?? ""} onChange={e => guarded(() => editUnit({ transcript: e.target.value }))} /></label>{unit.kind === "MATH" && <OcrMathPreview latex={unit.transcript ?? ""} />}<button disabled={busy || !picked.length} onClick={() => guarded(() => update(setUnitMembership(page, unit.id, picked)))}>Thay membership bằng nét đã chọn (tách/gán lại)</button></> : <label>Quan hệ <select value={unit.relation} disabled={busy} onChange={e => guarded(() => editUnit({ relation: e.target.value as GtUnit["relation"] }))}>{["SYSTEM", "ALTERNATIVES", "INDEPENDENT", "UNKNOWN"].map(x => <option key={x}>{x}</option>)}</select></label>}
            <button disabled={busy} onClick={() => guarded(() => moveUnit(-1))}>Lên</button><button disabled={busy} onClick={() => guarded(() => moveUnit(1))}>Xuống</button>
            <button disabled={busy || !humanDeclaration || !reviewer.trim()} data-testid="eval-confirm-unit" onClick={() => guarded(confirmUnit)}>Xác nhận đơn vị này</button>
            <button disabled={busy} onClick={() => guarded(() => { const next = invalidate(page.annotation); next.units = next.units.filter(u => u.id !== unit.id); next.units.forEach(u => { u.childIds = u.childIds.filter(id => id !== unit.id); u.confirmed = false; }); update(next); setUnitId(""); })}>Xóa đơn vị (giữ ink)</button></div>}
          <button disabled={busy || childIds.length < 2} onClick={() => guarded(mergeUnits)}>Gộp atomic units đã chọn (giữ bản chép ở trạng thái draft)</button>
          <label>Quan hệ mới <select aria-label="GT relation" value={relation} onChange={e => setRelation(e.target.value as typeof relation)}>{["UNKNOWN", "SYSTEM", "ALTERNATIVES", "INDEPENDENT"].map(x => <option key={x}>{x}</option>)}</select></label><button disabled={busy || childIds.length < 2} onClick={() => guarded(createRelation)}>Tạo container từ các đơn vị đã chọn + nét khung đang khoanh</button>
          <label>Người xác nhận (mã/tên tùy chọn riêng tư) <input aria-label="GT reviewer" value={reviewer} onChange={e => setReviewer(e.target.value)} /></label><label><input data-testid="eval-human-declaration" type="checkbox" checked={humanDeclaration} onChange={e => setHumanDeclaration(e.target.checked)} />Tôi đã đối chiếu membership và bản chép với nét gốc; không lấy prediction làm nhãn.</label>
          <button disabled={busy || !humanDeclaration || !reviewer.trim()} data-testid="eval-confirm-page" onClick={() => guarded(confirmAll)}>Xác nhận GT toàn trang (đủ nét, từng unit đã xác nhận)</button>
          <button disabled={busy} onClick={() => guarded(() => { const proposals = constructScopeCandidates(page.source, { status: "GEOMETRY_ASSISTANCE_ONLY", model: "NONE", regions: [] }, renderTransform(), "GEOMETRY");
            if (page.annotation.units.length) throw Error("Giữ annotation hiện có: chọn/gán nét để chỉnh; không tự ghi đè bằng proposal");
            const a = invalidate(page.annotation); a.assisted = true; a.origin = "MACHINE_PROPOSAL"; a.units = proposals.scopes.map((s, i) => ({ id: `proposal-${s.id}`, kind: s.kind === "MIXED" ? "UNKNOWN" : s.kind, strokeIds: s.strokeIds, readingOrder: i, transcript: null, childIds: [], confirmed: false })); update(a);
          })}>Gợi ý geometry (chưa xác nhận, không điền transcript)</button>
          <p>Benchmark không sửa GT. Sửa một child hủy xác nhận parent. Proposal không phải Oracle. HUMAN_CONFIRMED là xác nhận do người dùng khai báo, không phải chữ ký định danh; assistance/exposure được lưu riêng.</p>
          <details><summary>GT / provenance / membership</summary><pre>{JSON.stringify({ sourceChecksum: page.sourceChecksum, provenance: page.provenance, annotation: page.annotation }, null, 2)}</pre></details>
        </div>
      </div>
    </section>}
    <section><h2>Oracle vs Automatic benchmark</h2><div className={styles.controls}>{EVALUATION_PROFILES.map(p => <label key={p}><input type="checkbox" aria-label={`Benchmark ${p}`} disabled={busy} checked={profiles.includes(p)} onChange={e => setProfiles(old => e.target.checked ? [...old, p] : old.filter(v => v !== p))} />{p}</label>)}
      <label>Max cases <input aria-label="Benchmark max cases" type="number" min={1} max={300} value={maxCases} onChange={e => setMaxCases(Number(e.target.value))} /></label><label><input aria-label="Benchmark recognition enabled" type="checkbox" checked={recognize} disabled={busy} onChange={e => setRecognize(e.target.checked)} />Chạy CoMER thật</label><label>Giới hạn inference <input aria-label="Benchmark inference limit" type="number" min={0} max={500} value={inferenceLimit} onChange={e => setInferenceLimit(Number(e.target.value))} /></label>
      <button data-testid="eval-run" disabled={busy || !page || !profiles.length} onClick={() => void runBenchmark()}>Chạy benchmark</button><button disabled={!busy} onClick={() => { cancel.current = true; setMessage("Dừng sau inference hiện tại; annotation vẫn được giữ."); }}>Dừng có kiểm soát</button></div>
      <p>Cache kiểm tensor/mask/model/config/code hash; cache hit không tính inference mới. Oracle dùng GT confirmed/source/generated, không dùng auto candidate. V3 BLOCKED_UNSUPPORTED_RUNTIME; HTR tiếng Việt NOT_MEASURED/manual. Geometry không gọi detector. HYBRID_NO_TYPE bỏ nhãn detector; NO_RECONCILIATION giữ ownership box gốc, chỉ giữ type geometry khi membership trùng hoàn toàn.</p>
      {latest && <><div className={styles.table}><table data-testid="eval-summary"><thead><tr>{["Cohort / profile", "Cases", "GT", "Prec", "Recall", "IoU", "Exact scope", "Pair F1", "Order", "Raw exact", "CER", "Split", "Merge", "Calls", "Cache"].map(x => <th key={x}>{x}</th>)}</tr></thead><tbody>{summary.map(r => <tr key={r.cohort}><td>{r.cohort}</td>{[r.cases, r.fullyLabeledCases, r.scopePrecision, r.scopeRecall, r.meanIoU, r.exactMembership, r.pairwiseF1, r.readingOrderAccuracy, r.rawExpressionExact, r.canonicalTokenCER, r.falseSplits, r.falseMerges, r.inferenceCalls, r.cacheHits].map((v, i) => <td key={i}>{display(v)}</td>)}</tr>)}</tbody></table></div>
        <p>Chỉ GT hoàn chỉnh vào trung bình scope; recognition-only chỉ khi membership khớp chính xác. Native/external/composed, DEV/HOLDOUT và loại nhãn luôn tách cohort. Không có một accuracy gộp tất cả.</p>
        <button data-testid="eval-export-results" onClick={() => { saveFile("ocr-evaluation-results.json", latest); saveFile("ocr-evaluation-summary.csv", csvRows(summary as unknown as Record<string, unknown>[]), "text/csv"); saveFile("ocr-evaluation-report.md", `# OCR evaluation\n\n${latest.normalization}\n\nNo pooled native/synthetic accuracy.\n\n${JSON.stringify(summary, null, 2)}`, "text/markdown"); }}>Xuất kết quả JSON + CSV + report</button>
        {arms.map(a => <details key={a.profile}><summary>{a.profile}: scope {a.metrics.status} · lỗi {a.failures.length} · {Math.round(a.timings.totalMs)}ms</summary>
          <table><thead><tr><th>Scope</th><th>Kind</th><th>Nét</th><th>Trạng thái</th><th>Raw trước repair</th><th>Selected</th><th>Cache</th></tr></thead><tbody>{a.scopes.map(s => <tr key={s.id} onClick={() => { setOverlay(a.profile); setPicked(s.strokeIds); }}><td>{s.id}</td><td>{s.kind}</td><td>{s.strokeIds.length}</td><td>{s.status}</td><td>{s.diagnostic?.status === "COMPLETED" ? s.diagnostic.rawLatex : "NOT_AVAILABLE"}</td><td>{s.diagnostic?.status === "COMPLETED" ? s.diagnostic.selectedLatex : "NOT_AVAILABLE"}</td><td>{s.cacheHit ? "REUSE_VERIFIED_TENSOR" : s.actualInferenceCalls ?? "UNKNOWN_AFTER_ERROR"}</td></tr>)}</tbody></table>
          <pre>{JSON.stringify({ metrics: a.metrics, recognition: a.recognition, failures: a.failures, timings: a.timings, rawRegions: a.perception?.regions, routes: a.scopes.map(s => ({ id: s.id, strokeIds: s.strokeIds, reasons: s.reasons, error: s.error })) }, null, 2)}</pre>
        </details>)}
      </>}
    </section>
  </main>;
}
