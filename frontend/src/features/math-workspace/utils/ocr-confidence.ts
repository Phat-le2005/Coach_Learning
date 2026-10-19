/**
 * Local OCR providers return confidence=0 when no calibrated score exists.
 * That means "unknown", NOT "this recognition is 0% correct".
 */
export interface OcrConfidenceDisplay {
  label: string;
  known: boolean;
  percent: number | null;
}

export function getOcrConfidenceDisplay(confidence: number): OcrConfidenceDisplay {
  if (!Number.isFinite(confidence) || confidence <= 0) {
    return { label: "Chưa có điểm tin cậy", known: false, percent: null };
  }
  const percentage = Math.round(Math.min(1, confidence) * 100);
  return { label: `${percentage}% tin cậy (tham khảo)`, known: true, percent: percentage };
}
