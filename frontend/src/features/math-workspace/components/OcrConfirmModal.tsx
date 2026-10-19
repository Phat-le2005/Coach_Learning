"use client";

import React, { useState, useEffect } from "react";
import { Sparkles, Check, X, AlertCircle, Loader2 } from "lucide-react";
import type { OCRRecognizeResponse, StepKind } from "@/lib/api/contracts";
import type { InkStroke } from "@/lib/api/contracts";
import { STEP_KINDS } from "@/lib/api/contracts";
import styles from "../MathWorkspace.module.css";
import { getOcrConfidenceDisplay } from "../utils/ocr-confidence";
import { OcrInkPreview } from "./OcrInkPreview";
import { OcrMathPreview } from "./OcrMathPreview";

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
  isSubmitting: boolean;
  onConfirmStep: (stepType: StepKind, latex: string, explanation: string) => Promise<void>;
  onRequestAlternatives: () => Promise<string[]>;
  sourceStrokes: InkStroke[];
  errorMessage?: string | null;
}

export function OcrConfirmModal({
  isOpen,
  onClose,
  ocrData,
  isSubmitting,
  onConfirmStep,
  onRequestAlternatives,
  sourceStrokes,
  errorMessage,
}: OcrConfirmModalProps) {
  const [latex, setLatex] = useState("");
  const [stepType, setStepType] = useState<StepKind>("EXPLANATION");
  const [explanation, setExplanation] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [alternatives, setAlternatives] = useState<string[]>([]);
  const [loadingAlternatives, setLoadingAlternatives] = useState(false);
  const [alternativesRequested, setAlternativesRequested] = useState(false);

  useEffect(() => {
    if (ocrData) {
      setLatex(ocrData.latex || "");
      setStepType(ocrData.suggested_step_type || "EXPLANATION");
      setExplanation(ocrData.explanation_text || "");
      setLocalError(null);
      setAlternatives([]);
      setAlternativesRequested(false);
    }
  }, [ocrData]);

  if (!isOpen || !ocrData) {
    return null;
  }

  const confidenceDisplay = getOcrConfidenceDisplay(ocrData.confidence);
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
    setLocalError(null);
    try {
      await onConfirmStep(stepType, latex.trim(), explanation.trim());
    } catch (err: unknown) {
      if (err instanceof Error) {
        setLocalError(err.message);
      } else {
        setLocalError("Không thể tạo bước giải. Vui lòng thử lại.");
      }
    }
  };

  const handleRequestAlternatives = async () => {
    if (loadingAlternatives || alternativesRequested || isSubmitting) return;
    setLoadingAlternatives(true);
    setLocalError(null);
    try {
      const candidates = await onRequestAlternatives();
      setAlternatives([...new Set(candidates.filter((candidate) => candidate.trim() && candidate !== ocrData.latex))].slice(0, 2));
      setAlternativesRequested(true);
    } catch {
      setLocalError("Chưa lấy được cách đọc khác. Bạn vẫn có thể sửa công thức bằng tay hoặc thử lại.");
    } finally {
      setLoadingAlternatives(false);
    }
  };

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="ocr-modal-title">
      <div className={styles.modalContainer}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div className={styles.modalTitle}>
            <Sparkles className={styles.sparkleIcon} size={20} />
            <span id="ocr-modal-title">Xác nhận nhận diện nét vẽ (OCR)</span>
            <span className={`${styles.confidenceBadge} ${confidenceClass}`}>
              {confidenceDisplay.label}
            </span>
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

          <OcrInkPreview strokes={sourceStrokes} />

          {(errorMessage || localError) && (
            <div className={styles.errorAlert} role="alert">
              <AlertCircle size={16} />
              <span>{errorMessage || localError}</span>
            </div>
          )}

          {/* Detected symbols chip list */}
          {ocrData.detected_symbols && ocrData.detected_symbols.length > 0 && (
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
            <span className={styles.formLabel}>Chọn cách đọc gần đúng nhất rồi sửa nếu cần:</span>
            <div className={styles.ocrCandidates}>
              {[ocrData.latex, ...alternatives].map((candidate, index) => (
                <button
                  key={`${index}-${candidate}`}
                  type="button"
                  className={`${styles.ocrCandidate} ${latex === candidate ? styles.ocrCandidateSelected : ""}`}
                  aria-pressed={latex === candidate}
                  onClick={() => setLatex(candidate)}
                  disabled={isSubmitting}
                >
                  <span className={styles.ocrCandidateLabel}>{index === 0 ? "Gợi ý ban đầu" : `Cách đọc khác ${index}`}</span>
                  <span className={styles.ocrCandidateFormula}><OcrMathPreview latex={candidate} /></span>
                </button>
              ))}
            </div>
            {!alternativesRequested && (
              <button type="button" className={styles.ocrRetryButton} onClick={handleRequestAlternatives} disabled={loadingAlternatives || isSubmitting}>
                {loadingAlternatives ? "Đang thử cách đọc khác..." : "Thử cách đọc khác"}
              </button>
            )}
            {alternativesRequested && alternatives.length === 0 && <span className={styles.emptyPreviewText}>Không tìm thấy gợi ý khác; hãy sửa bằng tay nếu cần.</span>}
          </div>

          {/* LaTeX formula input */}
          <div className={styles.formGroup}>
            <label htmlFor="ocr-latex-input" className={styles.formLabel}>
              Công thức LaTeX (có thể chỉnh sửa):
            </label>
            <textarea
              id="ocr-latex-input"
              className={`${styles.formInput} ${styles.latexTextarea}`}
              rows={2}
              value={latex}
              onChange={(e) => setLatex(e.target.value)}
              placeholder="Nhập hoặc sửa công thức LaTeX..."
              disabled={isSubmitting}
              required
            />
          </div>

          {/* Live Math Preview */}
          <div className={styles.formGroup}>
            <span className={styles.formLabel}>Xem trước công thức:</span>
            <div className={styles.mathPreviewBox}>
              <OcrMathPreview latex={latex} />
            </div>
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
              disabled={isSubmitting || !latex.trim()}
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
