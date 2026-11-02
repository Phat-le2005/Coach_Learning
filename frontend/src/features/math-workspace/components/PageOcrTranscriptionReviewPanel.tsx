"use client";

import { useMemo, useState } from "react";
import type { InkStroke } from "@/lib/api/contracts";
import type { PageOcrRegion } from "../utils/page-ocr";
import type { StructureKind } from "../utils/structural-candidate-engine";
import {
  buildStructuredTranscriptionIR, applyOcrToContentUnit, editContentUnit,
  approveContentUnit, editContainerRelation, confirmTranscriptionReadingOrder,
  setSiblingReadingOrder, getOrderedReviewUnits, getRootContentUnits,
  projectTranscriptionToLegacySteps, validateSolutionTranscriptionIR,
  type SolutionTranscriptionIR, type ContentUnitKind,
} from "../utils/structured-transcription-ir";
import { proposeIntegralExpressionUnits } from "../utils/expression-reconstruction";
import { detectStructuralCandidates } from "../utils/structural-candidate-engine";
import { recognizeHandwrittenMath } from "../utils/handwritten-ocr";
import { renderOcrLatexHtml } from "../utils/ocr-math-preview";
import { OcrInkPreview } from "./OcrInkPreview";
import styles from "../MathWorkspace.module.css";

interface Props {
  pageIndex: number;
  pageStrokes: InkStroke[];
  regions: PageOcrRegion[];
  attemptId?: string;
  sourceRevision?: number;
}

/** Source changes create a new review session; late OCR cannot update another page. */
export function PageOcrTranscriptionReviewPanel(props: Props) {
  const initial = useMemo(() => {
    try {
      return { ir: buildStructuredTranscriptionIR({ pageIndex: props.pageIndex, strokes: props.pageStrokes,
        regions: props.regions, attemptId: props.attemptId, sourceRevision: props.sourceRevision,
        integralUnits: proposeIntegralExpressionUnits(props.pageStrokes),
        structuralCandidates: detectStructuralCandidates(props.pageStrokes) }), error: null };
    } catch (error) {
      return { ir: null, error: error instanceof Error ? error.message : String(error) };
    }
  }, [props.pageIndex, props.pageStrokes, props.regions, props.attemptId, props.sourceRevision]);
  if (!initial.ir) return <p role="alert">Không thể tạo bản chép: {initial.error}</p>;
  return <ReviewSession key={JSON.stringify([props.pageIndex, props.pageStrokes, props.regions, props.attemptId, props.sourceRevision])} initialIr={initial.ir} />;
}

function ReviewSession({ initialIr }: { initialIr: SolutionTranscriptionIR }) {
  const [ir, setIr] = useState(initialIr);
  const [selectedId, setSelectedId] = useState(getRootContentUnits(initialIr.contentUnits)[0]?.id ?? "");
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [showProjection, setShowProjection] = useState(false);
  const [recognizing, setRecognizing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rows = getOrderedReviewUnits(ir.contentUnits);
  const roots = getRootContentUnits(ir.contentUnits);
  const selected = ir.contentUnits.find((u) => u.id === selectedId);
  const sourceById = new Map(ir.sourceSnapshot.strokes.map((s) => [s.id, s]));
  const selectedStrokes = selected?.sourceStrokeIds.map((id) => sourceById.get(id)!) ?? [];
  const content = selected?.approvedContent ?? selected?.rawRecognition ?? "";
  const preview = selected?.kind === "MATH" ? renderOcrLatexHtml(content) : null;
  const projection = projectTranscriptionToLegacySteps(ir);
  const run = (change: (previous: SolutionTranscriptionIR) => SolutionTranscriptionIR) => {
    try { setIr(change(ir)); setError(null); } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  };
  const recognize = async () => {
    if (!selected || selected.role !== "ATOMIC" || selected.kind !== "MATH") return;
    const id = selected.id;
    setRecognizing(true); setError(null);
    try {
      const result = await recognizeHandwrittenMath(selectedStrokes);
      // Functional update preserves corrections made while inference is running.
      setIr((previous) => applyOcrToContentUnit(previous, id, result.latex));
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setRecognizing(false); }
  };
  const move = (id: string, parentId: string | null, direction: number) => {
    const ids = rows.filter((r) => r.parentId === parentId).map((r) => r.unit.id);
    const from = ids.indexOf(id), to = from + direction;
    if (to < 0 || to >= ids.length) return;
    [ids[from], ids[to]] = [ids[to], ids[from]];
    run((previous) => setSiblingReadingOrder(previous, parentId, ids));
  };
  const exportIr = () => {
    try {
      validateSolutionTranscriptionIR(ir, initialIr.sourceSnapshot.strokes);
      const url = URL.createObjectURL(new Blob([JSON.stringify(ir, null, 2)], { type: "application/json" }));
      const a = document.createElement("a"); a.href = url; a.download = `transcription-page-${ir.pageIndex + 1}.json`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  };

  return <section className={styles.pageReviewNotice} aria-label="Xem lại bản chép có cấu trúc (IR)" data-testid="ocr-transcription-review-panel">
    <h3>Bản chép trang {ir.pageIndex + 1}</h3>
    <p role="status" data-testid="transcription-status">
      {ir.approvedUnitCount}/{ir.contentUnits.length} đơn vị đã xác nhận · {roots.length} đơn vị cấp đầu · {ir.reviewStatus}
    </p>
    <p>Đối chiếu nét viết, sửa bản chép và xác nhận từng nội dung. Mở cấu trúc để xem từng phần con.</p>
    <p>Thứ tự đọc: {ir.readingOrderStatus}. {ir.readingOrderStatus !== "CONFIRMED" ? "Kiểm tra danh sách và dùng nút lên/xuống nếu cần." : "Đã đối chiếu thứ tự."}</p>
    {ir.readingOrderWarnings.length > 0 && <p role="note">Bố cục có thể nhập nhằng hoặc có hai cột; cần đối chiếu thứ tự đọc.</p>}
    <button type="button" className={styles.buttonSecondary} onClick={() => run(confirmTranscriptionReadingOrder)}>
      Xác nhận thứ tự đọc đang hiển thị
    </button>
    <div role="group" aria-label="Danh sách đơn vị nội dung">
      {rows.filter((row) => {
        let parent = row.parentId;
        while (parent) {
          if (!expanded.has(parent)) return false;
          parent = rows.find((r) => r.unit.id === parent)?.parentId ?? null;
        }
        return true;
      }).map(({ unit, depth, parentId }) => <div key={unit.id} style={{ marginLeft: depth * 20, marginBlock: 6 }}>
        {unit.role === "CONTAINER" && <button type="button" aria-label={`Mở cấu trúc ${unit.id}`} aria-expanded={expanded.has(unit.id)}
          onClick={() => setExpanded((old) => { const next = new Set(old); if (next.has(unit.id)) next.delete(unit.id); else next.add(unit.id); return next; })}>
          {expanded.has(unit.id) ? "−" : "+"}
        </button>}
        <button type="button" className={styles.buttonSecondary} data-testid="transcription-unit-nav" data-unit-id={unit.id}
          aria-pressed={selectedId === unit.id} onClick={() => setSelectedId(unit.id)}>
          {unit.readingOrder + 1}. {unit.kind}{unit.structureKind ? ` — ${unit.structureKind}` : ""} · {unit.reviewStatus} · {unit.sourceStrokeIds.length} nét
        </button>{" "}
        <button type="button" aria-label={`Đưa ${unit.id} lên`} disabled={unit.readingOrder === 0} onClick={() => move(unit.id, parentId, -1)}>↑</button>
        <button type="button" aria-label={`Đưa ${unit.id} xuống`} disabled={unit.readingOrder === rows.filter((r) => r.parentId === parentId).length - 1}
          onClick={() => move(unit.id, parentId, 1)}>↓</button>
      </div>)}
    </div>
    {error && <p role="alert">{error}</p>}
    {selected && <div data-testid="selected-transcription-unit" style={{ background: "white", padding: 10 }}>
      <strong>{selected.kind} {selected.structureKind} · {selected.reviewStatus}{selected.role === "ATOMIC" ? ` · ${selected.recognitionStatus}` : ""}</strong>
      <div style={{ maxWidth: 320 }}><OcrInkPreview strokes={selectedStrokes} /></div>
      {selected.role === "CONTAINER" ? <>
        <label>Quan hệ cấu trúc{" "}<select aria-label="Quan hệ cấu trúc" value={selected.structureKind ?? "UNKNOWN"}
          onChange={(e) => run((previous) => editContainerRelation(previous, selected.id, e.target.value as StructureKind))}>
          {["SYSTEM", "ALTERNATIVES", "FRACTION", "INDEPENDENT", "UNKNOWN"].map((kind) => <option key={kind}>{kind}</option>)}
        </select></label>
        <p>Đối chiếu quan hệ và từng phần con trước khi xác nhận. Cấu trúc không cần chuỗi LaTeX riêng.</p>
        <p>{selected.childIds.filter((id) => ir.contentUnits.find((u) => u.id === id)?.reviewStatus === "APPROVED").length}/{selected.childIds.length} phần con đã xác nhận</p>
      </> : <>
        <label>Loại nội dung{" "}<select aria-label="Loại nội dung" value={selected.kind} disabled={recognizing}
          onChange={(e) => run((previous) => editContentUnit(previous, selected.id, { kind: e.target.value as ContentUnitKind }))}>
          {["MATH", "TEXT", "UNKNOWN"].map((kind) => <option key={kind}>{kind}</option>)}
        </select></label>
        {selected.kind === "MATH" ? <button type="button" className={styles.buttonSecondary} data-testid="btn-recognize-unit-comer"
          disabled={recognizing} onClick={recognize}>{recognizing ? "Đang nhận diện bằng CoMER..." : "Nhận diện nội dung bằng CoMER"}</button>
          : <p>{selected.kind}: nhập bản chép thủ công hoặc giữ UNRESOLVED. CoMER chỉ hỗ trợ công thức toán.</p>}
        <p>CoMER nhận diện thô: <code data-testid="raw-recognition">{selected.rawRecognition ?? "UNRESOLVED"}</code></p>
        <label>Bản chép nội dung:
          <textarea aria-label="Bản chép nội dung" rows={3} style={{ width: "100%" }} value={content}
            onChange={(e) => run((previous) => editContentUnit(previous, selected.id, { content: e.target.value }))} />
        </label>
        <p>{selected.isManuallyCorrected ? "MANUAL_CORRECTION — Đã sửa tay" : "Chưa sửa tay"}</p>
        {preview && <div data-testid="transcription-katex" dangerouslySetInnerHTML={{ __html: preview }} />}
      </>}
      <button type="button" className={styles.buttonSecondary} disabled={recognizing} onClick={() => run((previous) => approveContentUnit(previous, selected.id))}>
        {selected.role === "CONTAINER" ? "Xác nhận cấu trúc này" : "Xác nhận bản chép này"}
      </button>
    </div>}
    <button type="button" className={styles.buttonSecondary} onClick={exportIr}>Tải bản chép IR về máy</button>{" "}
    <button type="button" className={styles.buttonSecondary} onClick={() => setShowProjection((old) => !old)}>
      {showProjection ? "Ẩn xem trước chuyển đổi bước chấm" : "Xem trước chuyển đổi bước chấm"}
    </button>
    {showProjection && <div data-testid="legacy-projection-preview">
      <strong>BLOCKED — Chỉ xem trước; chưa có payload để gửi.</strong>
      <p>Module G cần xác định ranh giới bước chấm và StepKind. Không tự chuyển mỗi đơn vị thành một bước chấm.</p>
      <ul>{projection.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
      {projection.candidateUnits.map((u) => <p key={u.id}>{u.kind} {u.structureKind} · {u.reviewStatus}: {u.approvedContent ?? u.rawRecognition ?? u.recognitionStatus}</p>)}
    </div>}
  </section>;
}
