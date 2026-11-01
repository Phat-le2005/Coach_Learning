"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import type { ApiClient, PaperAttachmentRead, PaperOcrRead } from "@/lib/api/client";
import { API_PATHS, ApiResponseError } from "@/lib/api/client";
import { generateUuid } from "../utils/ink-math";
import { PaperOcrReview } from "./PaperOcrReview";
import type { ConfirmedPaperStepContent } from "../utils/paper-ocr-step";
import styles from "../MathWorkspace.module.css";

interface Props {
  attemptId: string;
  accessToken: string;
  apiClient: ApiClient;
  isReadOnly: boolean;
  onConfirmStep: (content: ConfirmedPaperStepContent, actionId: string) => Promise<void>;
  onSubmitSolution?: () => Promise<void>;
  isSubmitting?: boolean;
  isReviewing?: boolean;
  submissionBlocked?: boolean;
  hasConfirmedSteps?: boolean;
}

const MAX_BYTES = 10 * 1024 * 1024;
const MIME_TYPES = new Set(["image/png", "image/jpeg", "application/pdf"]);

export function PaperUploadPanel({
  attemptId,
  accessToken,
  apiClient,
  isReadOnly,
  onConfirmStep,
  onSubmitSolution,
  isSubmitting,
  isReviewing,
  submissionBlocked,
  hasConfirmedSteps,
}: Props) {
  const [files, setFiles] = useState<PaperAttachmentRead[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [stepText, setStepText] = useState("");
  const [savingStep, setSavingStep] = useState(false);
  const [recognizing, setRecognizing] = useState(false);
  const [ocrResult, setOcrResult] = useState<PaperOcrRead | null>(null);
  const [ocrNonce, setOcrNonce] = useState(0);
  const [savedOcrPaperIds, setSavedOcrPaperIds] = useState<Set<string>>(() => new Set());
  const [activeOcrIndex, setActiveOcrIndex] = useState<number | null>(0);
  const [showBbox, setShowBbox] = useState(true);
  const actionId = useRef(generateUuid());
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    apiClient.listMathPaper(accessToken, attemptId).then((list) => {
      if (!active) return;
      setFiles(list);
      setSelectedId((current) => current && list.some((item) => item.id === current) ? current : list[0]?.id ?? null);
    }).catch(() => { if (active) setError("Chưa tải được bài viết giấy. Hãy thử lại sau."); });
    return () => { active = false; };
  }, [apiClient, accessToken, attemptId]);

  const selected = files.find((item) => item.id === selectedId) ?? null;
  const recognize = async () => {
    if (!selected || busy || recognizing || isReadOnly || savedOcrPaperIds.has(selected.id)) return;
    setRecognizing(true);
    setError(null);
    try {
      const result = await apiClient.recognizeMathPaper(accessToken, attemptId, selected.id);
      if (result.paper_id !== selected.id || result.file_sha256 !== selected.sha256) {
        throw new Error("Kết quả nhận diện không khớp ảnh gốc. Hãy thử lại.");
      }
      setOcrResult(result);
      setActiveOcrIndex(0);
      setShowBbox(true);
      setOcrNonce((current) => current + 1);
    } catch (cause) {
      const code = cause instanceof ApiResponseError ? cause.code : "";
      setError(code === "PAPER_OCR_NOT_CONFIGURED"
        ? "Máy chủ chưa cấu hình Gemini để đọc bài chụp. Em vẫn có thể nhập bước ở dưới."
        : code === "PAPER_OCR_RATE_LIMITED"
          ? "Gemini đang hết lượt nhận diện. Hãy thử lại sau hoặc nhập bước ở dưới."
          : code === "PAPER_OCR_INVALID"
            ? "Kết quả nhận diện không đủ tin cậy để hiển thị. Hãy thử ảnh rõ hơn hoặc nhập bước ở dưới."
            : cause instanceof ApiResponseError && cause.status === 401
              ? "Phiên đăng nhập đã hết hạn. Đăng nhập lại rồi thử tiếp."
              : cause instanceof ApiResponseError ? cause.message : cause instanceof Error ? cause.message
                : "Chưa trích xuất được bài chụp. Hãy thử lại hoặc nhập bước ở dưới.");
    } finally { setRecognizing(false); }
  };
  const upload = async (file: File | undefined) => {
    if (!file || busy || isReadOnly) return;
    if (!MIME_TYPES.has(file.type) || file.size === 0 || file.size > MAX_BYTES) {
      setError("Chọn ảnh PNG/JPEG hoặc PDF tối đa 10 MB.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const uploaded = await apiClient.uploadMathPaper(accessToken, attemptId, file);
      setFiles((current) => current.some((item) => item.id === uploaded.id) ? current : [...current, uploaded]);
      setSelectedId(uploaded.id);
    } catch (cause) {
      setError(cause instanceof ApiResponseError ? cause.message : "Không thể tải bài lên máy chủ. Hãy thử lại.");
    } finally {
      setBusy(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  };

  const remove = async (id: string) => {
    if (busy || isReadOnly || !window.confirm("Xóa tệp bài viết giấy này khỏi bài làm?")) return;
    setBusy(true);
    setError(null);
    try {
      await apiClient.deleteMathPaper(accessToken, attemptId, id);
      setFiles((current) => current.filter((item) => item.id !== id));
      if (selectedId === id) setSelectedId(files.find((item) => item.id !== id)?.id ?? null);
      if (ocrResult?.paper_id === id) setOcrResult(null);
    } catch (cause) {
      setError(cause instanceof ApiResponseError ? cause.message : "Không thể xóa tệp. Hãy thử lại.");
    } finally { setBusy(false); }
  };

  const saveStep = async () => {
    const text = stepText.trim();
    if (savingStep || isReadOnly || !text) return;
    setSavingStep(true);
    setError(null);
    try {
      await onConfirmStep({ latex: null, explanation: text }, actionId.current);
      setStepText("");
      actionId.current = generateUuid();
    } catch (cause) {
      setError(cause instanceof ApiResponseError ? cause.message : "Chưa lưu được bước giải. Giữ nguyên nội dung và thử lại.");
    } finally { setSavingStep(false); }
  };

  return <div className={styles.paperUploadPanel}>
    <header>
      <h2>Bài viết trên giấy</h2>
      <p>Tải ảnh chụp hoặc PDF bài làm. Tệp được giữ riêng trong lượt giải này, kể cả khi em tải lại trang.</p>
    </header>
    {!isReadOnly ? <label className={styles.paperUploadLabel}>
      <span>{busy ? "Đang tải lên..." : "Chọn ảnh hoặc PDF"}</span>
      <input ref={fileInput} type="file" accept="image/png,image/jpeg,application/pdf,.png,.jpg,.jpeg,.pdf"
        disabled={busy} onChange={(event) => void upload(event.currentTarget.files?.[0])} />
    </label> : null}
    <p className={styles.paperNote}>PNG/JPEG/PDF, tối đa 10 MB mỗi tệp và 10 tệp mỗi bài.</p>
    {error ? <p role="alert" className={styles.paperError}>{error}</p> : null}
    {files.length ? <>
      <div className={styles.paperFileList} aria-label="Tệp bài viết đã tải lên">
        {files.map((item) => <div key={item.id}>
          <button type="button" className={item.id === selectedId ? styles.paperFileActive : ""}
            onClick={() => setSelectedId(item.id)}>{item.file_name}</button>
          {!isReadOnly ? <button type="button" onClick={() => void remove(item.id)} disabled={busy}
            aria-label={`Xóa tệp ${item.file_name}`}>Xóa</button> : null}
        </div>)}
      </div>
      {selected ? <div className={styles.paperPreview}>
        {selected.content_type === "application/pdf" ?
          <a href={API_PATHS.mathPaperFile(attemptId, selected.id)} target="_blank" rel="noopener noreferrer">Mở bản PDF đã lưu</a>
          : <div className={styles.paperImageWrapper}>
              <img src={API_PATHS.mathPaperFile(attemptId, selected.id)} alt={`Bài viết trên giấy: ${selected.file_name}`} className={styles.paperImage} />
              {showBbox && ocrResult?.paper_id === selected.id ? (
                <svg className={styles.paperOverlaySvg} viewBox="0 0 1000 1000" preserveAspectRatio="none" aria-label="Vùng nhận diện công thức toán">
                  {ocrResult.suggestions.map((s, idx) => {
                    if (!s.box_2d) return null;
                    const [ymin, xmin, ymax, xmax] = s.box_2d;
                    const isActive = activeOcrIndex === idx;
                    const width = Math.max(12, xmax - xmin);
                    const height = Math.max(12, ymax - ymin);
                    return (
                      <g key={idx} className={`${styles.bboxGroup} ${isActive ? styles.bboxGroupActive : ""}`} onClick={() => setActiveOcrIndex(idx)}>
                        <rect x={xmin} y={ymin} width={width} height={height} rx={8} className={styles.bboxRect} />
                        <g transform={`translate(${xmin}, ${Math.max(24, ymin - 8)})`} className={styles.bboxBadge}>
                          <rect x={0} y={-22} width={s.kind === "TABLE" ? 95 : 68} height={22} rx={4} className={styles.bboxBadgeBg} />
                          <text x={6} y={-7} className={styles.bboxBadgeText}>
                            {s.kind === "TABLE" ? "Bảng B.1" : `Bước ${idx + 1}`}
                          </text>
                        </g>
                      </g>
                    );
                  })}
                </svg>
              ) : null}
            </div>}
      </div> : null}
      {selected && ocrResult?.paper_id === selected.id && selected.content_type !== "application/pdf" ? (
        <div className={styles.paperBboxToolbar}>
          <span className={styles.paperBboxHint}>
            📍 Bấm vào khung viền màu xanh trên ảnh hoặc bấm từng bước ở dưới để đối chiếu công thức với chữ viết tay.
          </span>
          <button type="button" className={`${styles.paperBboxToggleBtn} ${showBbox ? styles.paperBboxToggleBtnActive : ""}`} onClick={() => setShowBbox((prev) => !prev)}>
            {showBbox ? "Ẩn khung nhận diện" : `Hiện khung nhận diện (${ocrResult.suggestions.filter((s) => !!s.box_2d).length} vùng)`}
          </button>
        </div>
      ) : null}
      {selected && !isReadOnly ? <div className={styles.paperOcrControls}>
        <button type="button" onClick={() => void recognize()} disabled={busy || recognizing || savedOcrPaperIds.has(selected.id)}>
          {recognizing ? "Đang trích xuất bài chụp..." : savedOcrPaperIds.has(selected.id)
            ? "Đã lưu bước từ OCR" : "Trích xuất OCR từ bài chụp"}
        </button>
        <p>Ảnh/PDF được gửi tới Gemini để gợi ý từng bước. Kết quả có thể sai, nhất là bảng biến thiên và ký hiệu viết tay. Em phải đối chiếu và xác nhận trước khi nộp.</p>
      </div> : null}
      {selected && ocrResult?.paper_id === selected.id && !isReadOnly ?
        <PaperOcrReview key={`${selected.id}:${ocrResult.file_sha256}:${ocrNonce}`} result={ocrResult}
          onConfirmStep={onConfirmStep} onStepSaved={() => setSavedOcrPaperIds((current) => new Set(current).add(selected.id))}
          activeStepIndex={activeOcrIndex} onSelectStepIndex={setActiveOcrIndex} /> : null}
      {!isReadOnly ? <div className={styles.paperStepEntry}>
        <h3>Thêm bước chưa được OCR đọc rõ</h3>
        <p>Đối chiếu bài giấy rồi nhập bước còn thiếu. AI chỉ nhận xét các bước em đã xác nhận với đáp án tham chiếu; ảnh gốc không tự trở thành điểm số.</p>
        <label htmlFor="paper-step-text">Một bước giải từ bài viết</label>
        <textarea id="paper-step-text" value={stepText} onChange={(event) => setStepText(event.target.value)}
          rows={4} maxLength={4000} placeholder="Ví dụ: y' = x² - 2x - 3 = (x+1)(x-3)" />
        <button type="button" onClick={() => void saveStep()} disabled={!stepText.trim() || savingStep}>
          {savingStep ? "Đang lưu bước..." : "Xác nhận bước này"}
        </button>
      </div> : null}
      {hasConfirmedSteps && !isReadOnly && onSubmitSolution ? (
        <div className={styles.paperSubmitBanner}>
          <div className={styles.paperSubmitBannerText}>
            <h4>✨ Đã có các bước giải được xác nhận!</h4>
            <p>Em có thể bấm nộp bài để AI (Gemini) đối chiếu và chấm điểm từng bước giải ngay lập tức.</p>
          </div>
          <button
            type="button"
            className={styles.primaryGradeButton}
            onClick={() => void onSubmitSolution()}
            disabled={isSubmitting || isReviewing || submissionBlocked}
          >
            <Sparkles size={16} />
            {isSubmitting ? "Đang nộp bài..." : isReviewing ? "Đang chấm bằng Gemini..." : "Nộp & Chấm bài bằng AI"}
          </button>
        </div>
      ) : null}
    </> : <p role="status">Chưa có bài viết giấy được tải lên.</p>}
  </div>;
}
