"use client";

import { useMemo, useState } from "react";
import type { InkStroke } from "@/lib/api/contracts";
import type { PageOcrRegion } from "../utils/page-ocr";
import { buildOcrShadowQaReport } from "../utils/ocr-shadow-qa";
import { proposeIntegralExpressionUnits, type IntegralExpressionUnit } from "../utils/expression-reconstruction";
import { recognizeHandwrittenMath } from "../utils/handwritten-ocr";
import { renderOcrLatexHtml } from "../utils/ocr-math-preview";
import { OcrInkPreview } from "./OcrInkPreview";
import styles from "../MathWorkspace.module.css";

interface PageOcrShadowQaPanelProps {
  pageStrokes: InkStroke[];
  initialRegions: PageOcrRegion[];
}

/**
 * Development-only, non-authoritative inspection panel.
 *
 * It receives original ink and initial segmentation, NEVER review rows or
 * saving callbacks. Proposals cannot create/edit/approve/save a student step.
 */
export function PageOcrShadowQaPanel({
  pageStrokes,
  initialRegions,
}: PageOcrShadowQaPanelProps) {
  const report = useMemo(
    () => buildOcrShadowQaReport(pageStrokes, initialRegions),
    [pageStrokes, initialRegions],
  );
  const integralUnits = useMemo(
    () => proposeIntegralExpressionUnits(pageStrokes), [pageStrokes],
  );
  const [selectedCandidate, setSelectedCandidate] = useState(0);
  const selected = report.candidates[selectedCandidate];
  const penById = useMemo(
    () => new Map(pageStrokes.filter((stroke) => stroke.tool === "PEN")
      .map((stroke) => [stroke.id, stroke])),
    [pageStrokes],
  );
  const previewStrokes = selected
    ? selected.strokeIds.flatMap((id) => {
      const stroke = penById.get(id);
      return stroke ? [stroke] : [];
    })
    : [];

  const [ocrLoadingByUnit, setOcrLoadingByUnit] = useState<Record<string, boolean>>({});
  const [ocrResultByUnit, setOcrResultByUnit] = useState<Record<string, { latex: string; html: string | null; durationMs: number }>>({});
  const [ocrErrorByUnit, setOcrErrorByUnit] = useState<Record<string, string>>({});

  const handleRecognizeUnit = async (unit: IntegralExpressionUnit) => {
    const unitStrokes = unit.sourceStrokeIds.flatMap((id) => {
      const stroke = penById.get(id);
      return stroke ? [stroke] : [];
    });
    if (unitStrokes.length === 0) return;

    setOcrLoadingByUnit((prev) => ({ ...prev, [unit.id]: true }));
    setOcrErrorByUnit((prev) => {
      const next = { ...prev };
      delete next[unit.id];
      return next;
    });

    const t0 = performance.now();
    try {
      const response = await recognizeHandwrittenMath(unitStrokes);
      const durationMs = performance.now() - t0;
      const html = renderOcrLatexHtml(response.latex);
      setOcrResultByUnit((prev) => ({
        ...prev,
        [unit.id]: { latex: response.latex, html, durationMs: Math.round(durationMs) },
      }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setOcrErrorByUnit((prev) => ({ ...prev, [unit.id]: msg }));
    } finally {
      setOcrLoadingByUnit((prev) => ({ ...prev, [unit.id]: false }));
    }
  };

  return (
    <section aria-label="Đối chiếu cấu trúc OCR QA" className={styles.pageReviewNotice}
      data-testid="ocr-shadow-qa-panel">
      <h3>Đối chiếu cấu trúc — chỉ QA</h3>
      <p><a href="/ocr-diagnostics" target="_blank" rel="noopener noreferrer">Mở chẩn đoán OCR A/B từ file capture</a></p>
      <p>
        Đây là đề xuất chỉ đọc từ các nét ban đầu, không phải kết quả OCR đã duyệt.
        Các vùng phía dưới vẫn sử dụng segmentation hiện tại; bảng này không gộp,
        tách, tạo hoặc lưu bước giải.
      </p>
      <p>
        Nét bút: {report.sourcePenStrokeCount} · Phân vùng ban đầu: {report.baselineRegionCount}
        {" · "}Nhóm đề xuất: {report.structuralCandidateCount}
      </p>
      <p>
        Nét thiếu ở baseline: {report.baselineMissingStrokeIds.length}
        {" · "}Nét lặp ở baseline: {report.baselineDuplicateStrokeIds.length}
        {" · "}Nét thiếu ở đề xuất: {report.shadowMissingStrokeIds.length}
        {" · "}Nét lặp ở đề xuất: {report.shadowDuplicateStrokeIds.length}
        {" · "}Nét lạ: {report.shadowUnknownStrokeIds.length}
      </p>
      {report.candidates.length === 0 ? (
        <p>Chưa có nét bút để đề xuất cấu trúc.</p>
      ) : (
        <>
          <div role="group" aria-label="Các nhóm cấu trúc đề xuất"
            style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBlock: "0.75rem" }}>
            {report.candidates.map((candidate, index) => (
              <button type="button" key={candidate.id + ":" + index}
                className={styles.buttonSecondary}
                aria-pressed={selectedCandidate === index}
                onClick={() => setSelectedCandidate(index)}>
                {index + 1}. {candidate.kind} · {candidate.strokeIds.length} nét
              </button>
            ))}
          </div>
          {selected ? (
            <div aria-live="polite" data-testid="ocr-shadow-selected">
              <p><strong>Nhóm {selectedCandidate + 1}: {selected.kind}</strong>
                {" · "}{selected.children.length} cấu trúc con
              </p>
              <p>
                Vùng baseline liên quan:{" "}
                {selected.overlappingBaselineRegions.length === 0
                  ? "không có"
                  : selected.overlappingBaselineRegions
                    .map((item) => `vùng ${item.index + 1} (${item.strokeCount} nét)`)
                    .join(", ")}
              </p>
              {selected.children.length > 0 ? (
                <ul>
                  {selected.children.map((child) => (
                    <li key={child.id}>{child.kind} · {child.strokeIds.length} nét</li>
                  ))}
                </ul>
              ) : null}
              {selected.reasons.length > 0 ? (
                <p>Heuristic: {selected.reasons.join("; ")}</p>
              ) : null}
              <OcrInkPreview strokes={previewStrokes} />
            </div>
          ) : null}
        </>
      )}
      <div style={{ marginTop: "0.75rem", borderTop: "1px solid #b7cfbf", paddingTop: "0.5rem" }}>
        <h4>Đề xuất ghép biểu thức (Core OCR V2 — thử nghiệm)</h4>
        {integralUnits.length === 0 ? (
          <p>Chưa có đề xuất tích phân đủ bằng chứng hình học.</p>
        ) : integralUnits.map((unit) => (
          <div key={unit.id} data-testid="ocr-integral-expression-proposal">
            <p><strong>INTEGRAL · {unit.sourceStrokeIds.length} nét</strong>
              {" · "}cận trên: {unit.upperLimitStrokeIds.length}
              {" · "}cận dưới: {unit.lowerLimitStrokeIds.length}
              {" · "}biểu thức: {unit.bodyStrokeIds.length}
            </p>
            <OcrInkPreview strokes={unit.sourceStrokeIds.flatMap((id) => {
              const stroke = penById.get(id);
              return stroke ? [stroke] : [];
            })} />
            <div style={{ marginBlock: "0.5rem" }}>
              <button
                type="button"
                className={styles.buttonSecondary}
                data-testid="btn-recognize-integral-expression"
                disabled={ocrLoadingByUnit[unit.id]}
                onClick={() => handleRecognizeUnit(unit)}
              >
                {ocrLoadingByUnit[unit.id] ? "Đang nhận diện toàn bộ biểu thức..." : "Thử OCR toàn bộ biểu thức"}
              </button>
            </div>
            {ocrResultByUnit[unit.id] ? (
              <div
                data-testid="integral-expression-ocr-result"
                style={{
                  background: "#ffffff",
                  border: "1px solid #16a34a",
                  borderRadius: "6px",
                  padding: "8px 12px",
                  marginBlock: "0.5rem",
                }}
              >
                <p style={{ margin: "0 0 4px 0", color: "#16a34a", fontWeight: "bold" }}>
                  Kết quả nhận diện toàn bộ biểu thức ({ocrResultByUnit[unit.id].durationMs}ms):
                </p>
                <p style={{ margin: "0 0 6px 0" }}>
                  <code data-testid="integral-ocr-latex" style={{ background: "#f1f5f9", padding: "2px 6px", borderRadius: "4px" }}>
                    {ocrResultByUnit[unit.id].latex}
                  </code>
                </p>
                {ocrResultByUnit[unit.id].html ? (
                  <div
                    data-testid="integral-ocr-preview"
                    style={{ padding: "4px", fontSize: "1.1rem" }}
                    dangerouslySetInnerHTML={{ __html: ocrResultByUnit[unit.id].html! }}
                  />
                ) : null}
              </div>
            ) : null}
            {ocrErrorByUnit[unit.id] ? (
              <p style={{ color: "#dc2626", margin: "4px 0" }}>
                Không thể nhận diện: {ocrErrorByUnit[unit.id]}
              </p>
            ) : null}
            <p style={{ fontSize: "12px", color: "#64748b" }}>Chỉ là đề xuất thử nghiệm trong Shadow QA; không thay đổi các bước giải đã lưu.</p>
          </div>
        ))}
      </div>
      <p>Chưa có ground truth: không thể coi các nhóm này là cấu trúc đúng của bài viết.</p>
    </section>
  );
}
