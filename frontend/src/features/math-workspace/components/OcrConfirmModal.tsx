"use client";

import React, { useState, useEffect, useRef } from "react";
import { Sparkles, Check, X, AlertCircle, Loader2 } from "lucide-react";
import type { OCRRecognizeResponse, StepKind } from "@/lib/api/contracts";
import type { InkStroke } from "@/lib/api/contracts";
import { STEP_KINDS } from "@/lib/api/contracts";
import styles from "../MathWorkspace.module.css";
import { getOcrConfidenceDisplay } from "../utils/ocr-confidence";
import { OcrInkPreview } from "./OcrInkPreview";
import { OcrMathPreview } from "./OcrMathPreview";
import { renderOcrLatexHtml } from "../utils/ocr-math-preview";
import { CORRECTION_KEYS, insertCorrectionKey, toConfirmedLatex } from "../utils/ocr-correction";

const STEP_KIND_LABELS: Record<StepKind, string> = {
  DERIVATIVE_CALCULATION: "Tính đạo hàm (Derivative Calculation)",
  ROOT_FINDING: "Tìm nghiệm phương trình (Root Finding)",
  SIGN_TABLE: "Bảng xét dấu (Sign Table)",
  VARIATION_TABLE: "Bảng biến thiên (Variation Table)",
  CONCLUSION: "Kết luận (Conclusion)",
  EXPLANATION: "Diễn giải / Lập luận (Explanation)",
  ASSUMPTION: "Giả thiết / ĐK xác định (Assumption)",
  CUSTOM: "Bước giải tự do (Custom Step)",
};

interface OcrConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  ocrData: OCRRecognizeResponse | null;
  manualMode?: boolean;
  isSubmitting: boolean;
  onConfirmStep: (stepType: StepKind, latex: string, explanation: string) => Promise<void>;
  sourceStrokes: InkStroke[];
  errorMessage?: string | null;
}

export function OcrConfirmModal({
  isOpen,
  onClose,
  ocrData,
  manualMode = false,
  isSubmitting,
  onConfirmStep,
  sourceStrokes,
  errorMessage,
}: OcrConfirmModalProps) {
  const [latex, setLatex] = useState("");
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [stepType, setStepType] = useState<StepKind>("EXPLANATION");
  const [explanation, setExplanation] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    if (ocrData || manualMode) {
      setLatex(ocrData && renderOcrLatexHtml(ocrData.latex) ? ocrData.latex : "");
      setStepType(ocrData?.suggested_step_type || "EXPLANATION");
      setExplanation(ocrData?.explanation_text || "");
      setLocalError(null);
    }
  }, [ocrData, manualMode]);

  if (!isOpen || (!ocrData && !manualMode)) {
    return null;
  }

  const confidenceDisplay = getOcrConfidenceDisplay(ocrData?.confidence ?? 0);
  const initialSuggestionValid = ocrData !== null && renderOcrLatexHtml(ocrData.latex) !== null;
  const confirmedLatex = toConfirmedLatex(latex);
  const previewValid = confirmedLatex !== null && renderOcrLatexHtml(confirmedLatex) !== null;
  const reviewableCandidates = [
    ...(initialSuggestionValid && ocrData ? [{ value: ocrData.latex, label: "Gợi ý ban đầu" }] : []),
  ];
  const confidenceClass =
    confidenceDisplay.known && confidenceDisplay.percent !== null && confidenceDisplay.percent >= 90
      ? styles.confidenceHigh
      : confidenceDisplay.known && confidenceDisplay.percent !== null && confidenceDisplay.percent >= 75
      ? styles.confidenceMedium
      : styles.confidenceLow;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!latex.trim()) {
      setLocalError("Vui lòng nhập công thức toán học.");
      return;
    }
    if (!previewValid) {
      setLocalError("Công thức chưa hoàn chỉnh. Điền hết ô vuông và kiểm tra bản xem trước trước khi lưu.");
      return;
    }
    setLocalError(null);
    try {
      await onConfirmStep(stepType, confirmedLatex!, explanation.trim());
    } catch (err: unknown) {
      if (err instanceof Error) {
        setLocalError(err.message);
      } else {
        setLocalError("Không thể tạo bước giải. Vui lòng thử lại.");
      }
    }
  };

  const handleInsertKey = (template: string) => {
    const field = inputRef.current;
    const result = insertCorrectionKey(
      latex,
      field?.selectionStart ?? latex.length,
      field?.selectionEnd ?? latex.length,
      template,
    );
    setLatex(result.value);
    setLocalError(null);
    window.requestAnimationFrame(() => {
      field?.focus();
      field?.setSelectionRange(result.selectionStart, result.selectionEnd);
    });
  };

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="ocr-modal-title">
      <div className={styles.modalContainer}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div className={styles.modalTitle}>
            <Sparkles className={styles.sparkleIcon} size={20} />
            <span id="ocr-modal-title">Xác nhận nhận diện nét vẽ (OCR)</span>
            {ocrData && <span className={`${styles.confidenceBadge} ${confidenceClass}`}>
              {confidenceDisplay.label}
            </span>}
          </div>
          <button
            type="button"
            className={styles.modalCloseButton}
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Đóng hộp thoại"
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <form onSubmit={handleSubmit} className={styles.modalBody}>
          {/* Invariant Banner */}
          <div className={styles.invariantNotice}>
            <p>
              <strong>OCR chỉ là gợi ý.</strong> Đối chiếu nét viết với công thức bên dưới, sửa mọi ký hiệu sai rồi xác nhận. Nhận diện không tự chấm bài hoặc tạo bước giải.
            </p>
          </div>

          {(errorMessage || localError) && (
            <div className={styles.errorAlert} role="alert">
              <AlertCircle size={16} />
              <span>{errorMessage || localError}</span>
            </div>
          )}

          {/* Detected symbols chip list */}
          {ocrData?.detected_symbols && ocrData.detected_symbols.length > 0 && (
            <div className={styles.formGroup}>
              <span className={styles.formLabel}>Ký hiệu nhận diện được:</span>
              <div className={styles.symbolsList}>
                {ocrData.detected_symbols.map((sym, idx) => (
                  <span key={idx} className={styles.symbolChip}>
                    {sym}
                  </span>
                ))}
              </div>
            </div>
          )}

          <div className={styles.formGroup}>
            <span className={styles.formLabel}>Gợi ý OCR — chọn nếu gần đúng, rồi sửa ngay bên dưới:</span>
            <div className={styles.ocrCandidates}>
              {!initialSuggestionValid && (
                <p className={styles.emptyPreviewText} role="status">
                  OCR chưa đọc rõ nét viết này. Em có thể nhập lại bằng ô và bàn phím toán bên dưới.
                </p>
              )}
              {reviewableCandidates.map(({ value: candidate, label }, index) => (
                <button
                  key={`${index}-${candidate}`}
                  type="button"
                  className={`${styles.ocrCandidate} ${latex === candidate ? styles.ocrCandidateSelected : ""}`}
                  aria-pressed={latex === candidate}
                  onClick={() => setLatex(candidate)}
                  disabled={isSubmitting}
                >
                  <span className={styles.ocrCandidateLabel}>{label}</span>
                  <span className={styles.ocrCandidateFormula}><OcrMathPreview latex={candidate} /></span>
                </button>
              ))}
            </div>
          </div>

          <div className={styles.ocrComparison}>
            <OcrInkPreview strokes={sourceStrokes} />
            <div className={styles.ocrResultPreview}>
              <span className={styles.formLabel}>Công thức sẽ lưu — đối chiếu với nét viết:</span>
              <div className={styles.mathPreviewBox}>
                <OcrMathPreview latex={confirmedLatex ?? ""} />
              </div>
            </div>
          </div>

          {/* Student correction workspace */}
          <div className={styles.formGroup}>
            <div className={styles.ocrEditorHeading}>
              <label htmlFor="ocr-latex-input" className={styles.formLabel}>Sửa công thức của em</label>
              <button
                type="button"
                className={styles.ocrClearButton}
                onClick={() => {
                  setLatex("");
                  setLocalError(null);
                  window.requestAnimationFrame(() => inputRef.current?.focus());
                }}
                disabled={isSubmitting || !latex}
              >
                Xóa gợi ý, nhập lại
              </button>
            </div>
            <p id="ocr-edit-help" className={styles.ocrEditorHelp}>
              Gõ như trên giấy, ví dụ <code>y=x+2</code> hoặc <code>x^2</code>. Chạm vào vị trí cần sửa rồi bấm ký hiệu. Công thức LaTeX nâng cao vẫn dùng được.
            </p>
            <textarea
              id="ocr-latex-input"
              ref={inputRef}
              className={`${styles.formInput} ${styles.latexTextarea}`}
              rows={2}
              value={latex}
              onChange={(event) => { setLatex(event.target.value); setLocalError(null); }}
              placeholder="Ví dụ: y=x+2"
              aria-describedby="ocr-edit-help ocr-template-help"
              disabled={isSubmitting}
              required
            />
            <div className={styles.ocrCorrectionKeys} role="group" aria-label="Bàn phím toán để sửa công thức">
              {CORRECTION_KEYS.map((key) => (
                <button
                  key={key.label}
                  type="button"
                  className={styles.ocrCorrectionKey}
                  title={key.description}
                  aria-label={key.description}
                  onClick={() => handleInsertKey(key.insert)}
                  disabled={isSubmitting}
                >
                  {key.label}
                </button>
              ))}
            </div>
            <span id="ocr-template-help" className={styles.ocrEditorHelp}>Với căn, phân số và số mũ: thay từng ô □ bằng số hoặc biểu thức của em.</span>
            {latex.includes("□") && <span className={styles.ocrIncompleteHint} role="status">Còn ô □ chưa điền — chưa thể lưu bước giải.</span>}
          </div>

          {/* Step Kind Selection */}
          <div className={styles.formGroup}>
            <label htmlFor="ocr-step-type-select" className={styles.formLabel}>
              Phân loại bước giải:
            </label>
            <select
              id="ocr-step-type-select"
              className={styles.formSelect}
              value={stepType}
              onChange={(e) => setStepType(e.target.value as StepKind)}
              disabled={isSubmitting}
            >
              {STEP_KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {STEP_KIND_LABELS[kind]}
                </option>
              ))}
            </select>
          </div>

          {/* Explanation Text */}
          <div className={styles.formGroup}>
            <label htmlFor="ocr-explanation-input" className={styles.formLabel}>
              Diễn giải / Lời giải thích (tùy chọn):
            </label>
            <textarea
              id="ocr-explanation-input"
              className={styles.formInput}
              rows={2}
              value={explanation}
              onChange={(e) => setExplanation(e.target.value)}
              placeholder="Thêm diễn giải chi tiết cho bước giải này..."
              disabled={isSubmitting}
            />
          </div>

          {/* Footer Actions */}
          <div className={styles.modalFooter}>
            <button
              type="button"
              className={styles.buttonSecondary}
              onClick={onClose}
              disabled={isSubmitting}
            >
              Hủy bỏ
            </button>
            <button
              type="submit"
              className={styles.buttonPrimary}
              disabled={isSubmitting || !previewValid}
            >
              {isSubmitting ? (
                <>
                  <Loader2 className={styles.spinIcon} size={16} />
                  <span>Đang lưu...</span>
                </>
              ) : (
                <>
                  <Check size={16} />
                  <span>Xác nhận bước giải</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
