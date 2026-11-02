"use client";

import { useMemo, useState } from "react";
import type { InkStroke } from "@/lib/api/contracts";
import type { PageOcrRegion } from "../utils/page-ocr";
import { buildOcrShadowQaReport } from "../utils/ocr-shadow-qa";
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

  return (
    <section aria-label="Đối chiếu cấu trúc OCR QA" className={styles.pageReviewNotice}
      data-testid="ocr-shadow-qa-panel">
      <h3>Đối chiếu cấu trúc — chỉ QA</h3>
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
      <p>Chưa có ground truth: không thể coi các nhóm này là cấu trúc đúng của bài viết.</p>
    </section>
  );
}
