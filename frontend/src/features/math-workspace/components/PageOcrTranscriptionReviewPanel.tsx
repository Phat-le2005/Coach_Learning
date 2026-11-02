"use client";

import { useMemo, useState } from "react";
import type { InkStroke } from "@/lib/api/contracts";
import type { PageOcrRegion } from "../utils/page-ocr";
import {
  buildStructuredTranscriptionIR,
  applyOcrToContentUnit,
  editContentUnit,
  approveContentUnit,
  projectTranscriptionToLegacySteps,
  type SolutionTranscriptionIR,
  type ContentUnit,
  type LegacyStepProjection,
} from "../utils/structured-transcription-ir";
import { proposeIntegralExpressionUnits } from "../utils/expression-reconstruction";
import { detectStructuralCandidates } from "../utils/structural-candidate-engine";
import { recognizeHandwrittenMath } from "../utils/handwritten-ocr";
import { renderOcrLatexHtml } from "../utils/ocr-math-preview";
import { OcrInkPreview } from "./OcrInkPreview";
import styles from "../MathWorkspace.module.css";

interface PageOcrTranscriptionReviewPanelProps {
  pageIndex: number;
  pageStrokes: InkStroke[];
  regions: PageOcrRegion[];
}

/**
 * Stage D: Structured Transcription IR Review Panel (Feature-flagged / QA Mode).
 * Allows students/reviewers to verify and correct unified ContentUnits across multiple regions
 * without being forced to choose an evaluator StepKind.
 *
 * Provides a clean projection preview into Phát's legacy evaluator step format.
 */
export function PageOcrTranscriptionReviewPanel({
  pageIndex,
  pageStrokes,
  regions,
}: PageOcrTranscriptionReviewPanelProps) {
  const penById = useMemo(
    () => new Map(pageStrokes.filter((s) => s.tool === "PEN").map((s) => [s.id, s])),
    [pageStrokes],
  );

  // Initialize initial IR
  const initialIr = useMemo(() => {
    const integralUnits = proposeIntegralExpressionUnits(pageStrokes);
    const structuralCandidates = detectStructuralCandidates(pageStrokes);
    return buildStructuredTranscriptionIR({
      pageIndex,
      strokes: pageStrokes,
      regions,
      integralUnits,
      structuralCandidates,
    });
  }, [pageIndex, pageStrokes, regions]);

  const [ir, setIr] = useState<SolutionTranscriptionIR>(initialIr);
  const [selectedUnitId, setSelectedUnitId] = useState<string>(
    initialIr.contentUnits[0]?.id ?? "",
  );
  const [showProjection, setShowProjection] = useState(false);
  const [recognizingUnit, setRecognizingUnit] = useState(false);
  const [recognitionError, setRecognitionError] = useState<string | null>(null);

  const topUnits = useMemo(
    () => ir.contentUnits.filter((u) => !u.id.startsWith("sub-")),
    [ir.contentUnits],
  );

  const selectedUnit = useMemo(
    () => ir.contentUnits.find((u) => u.id === selectedUnitId) ?? topUnits[0],
    [ir.contentUnits, selectedUnitId, topUnits],
  );

  const selectedStrokes = useMemo(() => {
    if (!selectedUnit) return [];
    return selectedUnit.sourceStrokeIds.flatMap((id) => {
      const s = penById.get(id);
      return s ? [s] : [];
    });
  }, [selectedUnit, penById]);

  const handleRecognizeUnitWithComer = async () => {
    if (!selectedUnit || selectedStrokes.length === 0) return;
    if (selectedUnit.kind !== "MATH" && selectedUnit.kind !== "STRUCTURE") {
      return;
    }
    setRecognizingUnit(true);
    setRecognitionError(null);
    try {
      const resp = await recognizeHandwrittenMath(selectedStrokes);
      setIr((prev) => applyOcrToContentUnit(prev, selectedUnit.id, resp.latex));
    } catch (err: unknown) {
      setRecognitionError(err instanceof Error ? err.message : String(err));
    } finally {
      setRecognizingUnit(false);
    }
  };

  // Evaluator projection preview
  const projection: LegacyStepProjection = useMemo(
    () => projectTranscriptionToLegacySteps(ir),
    [ir],
  );

  const handleEditContent = (content: string) => {
    if (!selectedUnit) return;
    setIr((prev) => editContentUnit(prev, selectedUnit.id, { content }));
  };

  const handleApprove = () => {
    if (!selectedUnit) return;
    try {
      setIr((prev) => approveContentUnit(prev, selectedUnit.id));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <section
      aria-label="Xem lại bản chép có cấu trúc (IR)"
      className={styles.pageReviewNotice}
      data-testid="ocr-transcription-review-panel"
      style={{
        background: "#f0fdf4",
        border: "1px solid #86efac",
        borderRadius: "8px",
        marginBlock: "0.5rem",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h3 style={{ margin: 0, color: "#166534" }}>
          Bản chép có cấu trúc (Structured Transcription IR v1.0)
        </h3>
        <span style={{ fontSize: "12px", color: "#15803d", fontWeight: "bold" }}>
          {ir.approvedUnitCount}/{topUnits.length} đơn vị đã xác nhận · Trạng thái:{" "}
          {ir.reviewStatus === "APPROVED" ? "ĐÃ HOÀN TẤT" : "CẦN KIỂM TRA"}
        </span>
      </div>

      <p style={{ fontSize: "12px", color: "#374151", margin: "4px 0 8px 0" }}>
        Chế độ xem xét theo biểu thức (Expression Units). Em có thể kiểm tra nội dung chép lại,
        chỉnh sửa nếu OCR đọc sai, rồi bấm xác nhận mà không cần chọn bước giải đánh giá.
      </p>

      {/* Content Units Navigation List */}
      <div
        role="group"
        aria-label="Danh sách đơn vị nội dung"
        style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginBlock: "6px" }}
      >
        {topUnits.map((u, idx) => {
          const isSelected = selectedUnit?.id === u.id;
          const isApproved = u.reviewStatus === "APPROVED";
          return (
            <button
              type="button"
              key={u.id}
              className={styles.buttonSecondary}
              style={{
                background: isSelected ? "#bbf7d0" : isApproved ? "#dcfce7" : "#ffffff",
                borderColor: isSelected ? "#15803d" : isApproved ? "#86efac" : "#cbd5e1",
                fontWeight: isSelected ? "bold" : "normal",
                fontSize: "12px",
              }}
              onClick={() => setSelectedUnitId(u.id)}
            >
              #{idx + 1}. {u.kind} ({u.sourceStrokeIds.length} nét)
              {isApproved ? " ✓" : ""}
            </button>
          );
        })}
      </div>

      {/* Selected Unit Review and Correction Workspace */}
      {selectedUnit ? (
        <div
          data-testid="selected-transcription-unit"
          style={{
            background: "#ffffff",
            border: "1px solid #cbd5e1",
            borderRadius: "6px",
            padding: "10px",
            marginTop: "8px",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <strong>
              Đơn vị #{selectedUnit.readingOrder + 1} ({selectedUnit.kind}) ·{" "}
              {selectedUnit.sourceStrokeIds.length} nét bút
            </strong>
            <span
              style={{
                fontSize: "11px",
                fontWeight: "bold",
                padding: "2px 6px",
                borderRadius: "4px",
                background: selectedUnit.reviewStatus === "APPROVED" ? "#dcfce7" : "#fef3c7",
                color: selectedUnit.reviewStatus === "APPROVED" ? "#166534" : "#92400e",
              }}
            >
              {selectedUnit.reviewStatus === "APPROVED" ? "ĐÃ XÁC NHẬN" : "CẦN KIỂM TRA"}
            </span>
          </div>

          <p style={{ fontSize: "11px", color: "#64748b", margin: "2px 0 6px 0" }}>
            Thuộc các vùng ban đầu: {selectedUnit.sourceRegionIds.join(", ") || "tự do"} ·{" "}
            {selectedUnit.isManuallyCorrected ? "Đã sửa tay" : "Chưa sửa"}
          </p>

          <div style={{ display: "flex", gap: "12px", alignItems: "flex-start" }}>
            {/* Visual ink preview */}
            <div style={{ flex: 1, minWidth: "180px", maxWidth: "260px" }}>
              <OcrInkPreview strokes={selectedStrokes} />
            </div>

            {/* Editable Content */}
            <div style={{ flex: 2, display: "flex", flexDirection: "column", gap: "6px" }}>
              {(selectedUnit.kind === "MATH" || selectedUnit.kind === "STRUCTURE") ? (
                <div style={{ marginBlock: "2px" }}>
                  <button
                    type="button"
                    className={styles.buttonSecondary}
                    data-testid="btn-recognize-unit-comer"
                    disabled={recognizingUnit}
                    onClick={handleRecognizeUnitWithComer}
                  >
                    {recognizingUnit ? "Đang nhận diện bằng CoMER..." : "Nhận diện nội dung bằng CoMER"}
                  </button>
                  {recognitionError ? (
                    <span style={{ color: "#dc2626", fontSize: "11px", marginLeft: "8px" }}>
                      Lỗi: {recognitionError}
                    </span>
                  ) : null}
                </div>
              ) : selectedUnit.kind === "TEXT" ? (
                <p style={{ fontSize: "11px", color: "#64748b", margin: "2px 0" }}>
                  Đơn vị nội dung chữ (TEXT): nhập hoặc chỉnh sửa nội dung bên dưới.
                </p>
              ) : (
                <p style={{ fontSize: "11px", color: "#b45309", margin: "2px 0" }}>
                  Đơn vị UNKNOWN: kiểm tra lại nét và nhập nội dung thủ công.
                </p>
              )}

              {selectedUnit.rawRecognition ? (
                <div style={{ fontSize: "11px", color: "#475569", margin: "1px 0 3px 0" }}>
                  CoMER nhận diện thô: <code style={{ background: "#f1f5f9", padding: "1px 4px" }}>{selectedUnit.rawRecognition}</code>
                </div>
              ) : null}

              <label style={{ fontSize: "12px", fontWeight: "bold" }}>
                Bản chép nội dung:
              </label>
              <textarea
                rows={2}
                style={{
                  width: "100%",
                  fontFamily: "monospace",
                  fontSize: "13px",
                  padding: "6px",
                  border: "1px solid #cbd5e1",
                  borderRadius: "4px",
                }}
                value={selectedUnit.approvedContent ?? selectedUnit.rawRecognition ?? ""}
                placeholder="Nhập nội dung chép đúng những gì em viết..."
                onChange={(e) => handleEditContent(e.target.value)}
              />

              {/* KaTeX preview if valid */}
              {renderOcrLatexHtml(selectedUnit.approvedContent ?? selectedUnit.rawRecognition ?? "") ? (
                <div
                  style={{
                    padding: "6px",
                    background: "#f8fafc",
                    border: "1px solid #e2e8f0",
                    borderRadius: "4px",
                  }}
                  dangerouslySetInnerHTML={{
                    __html: renderOcrLatexHtml(selectedUnit.approvedContent ?? selectedUnit.rawRecognition ?? "")!,
                  }}
                />
              ) : null}

              <div style={{ marginTop: "4px", display: "flex", gap: "8px" }}>
                <button
                  type="button"
                  className={styles.buttonSecondary}
                  style={{ background: "#15803d", color: "#ffffff", border: "none" }}
                  onClick={handleApprove}
                >
                  Xác nhận bản chép này
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}

      {/* Projection Preview Toggle for Phát's Evaluator (Module G) */}
      <div style={{ marginTop: "10px", borderTop: "1px dashed #86efac", paddingTop: "8px" }}>
        <button
          type="button"
          className={styles.buttonSecondary}
          onClick={() => setShowProjection((prev) => !prev)}
        >
          {showProjection
            ? "Ẩn xem trước chuyển đổi bước chấm (Module G)"
            : "Xem trước chuyển đổi bước chấm sang Evaluator (Module G)"}
        </button>

        {showProjection ? (
          <div
            data-testid="legacy-projection-preview"
            style={{
              marginTop: "8px",
              padding: "10px",
              background: "#ffffff",
              border: "1px solid #cbd5e1",
              borderRadius: "6px",
              fontSize: "12px",
            }}
          >
            <p style={{ margin: "0 0 6px 0", fontWeight: "bold" }}>
              Ánh xạ chuyển đổi sang {projection.projectedStepCount} bước giải:
            </p>
            {projection.warnings.length > 0 ? (
              <ul style={{ margin: "4px 0 8px 16px", color: "#b45309" }}>
                {projection.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            ) : null}
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {projection.steps.map((st) => (
                <div
                  key={st.targetStepOrder}
                  style={{ padding: "6px", background: "#f8fafc", borderRadius: "4px" }}
                >
                  <strong>Bước {st.targetStepOrder}:</strong> [{st.step_type}]{" "}
                  {st.content_latex ? <code>{st.content_latex}</code> : st.explanation_text}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
