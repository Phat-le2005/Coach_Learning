'use client';

import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import type { InkStroke, StepKind } from '@/lib/api/contracts';
import { STEP_KINDS } from '@/lib/api/contracts';
import { ApiNetworkError, ApiResponseError } from '@/lib/api/client';
import { generateUuid } from '../utils/ink-math';
import { mergePageOcrRegions, splitPageOcrRegion } from '../utils/page-ocr';
import type { PageOcrRegion } from '../utils/page-ocr';
import { recognizeHandwrittenMath } from '../utils/handwritten-ocr';
import { toConfirmedLatex, insertCorrectionKey, CORRECTION_KEYS } from '../utils/ocr-correction';
import { renderOcrLatexHtml } from '../utils/ocr-math-preview';
import { OcrInkPreview } from './OcrInkPreview';
import { OcrMathPreview } from './OcrMathPreview';
import styles from '../MathWorkspace.module.css';

type ReviewStatus = 'pending' | 'recognizing' | 'ready' | 'manual' | 'saved' | 'skipped';

interface ReviewRow {
  region: PageOcrRegion;
  status: ReviewStatus;
  latex: string;
  explanation: string;
  stepType: StepKind;
  touched: boolean;
  actionId: string;
  error: string | null;
  retryOnly: boolean;
}

interface PageOcrReviewModalProps {
  pageIndex: number;
  regions: PageOcrRegion[];
  pageStrokes: InkStroke[];
  onClose: () => void;
  onConfirmStep: (stepType: StepKind, latex: string | null, explanation: string, actionId: string) => Promise<void>;
}

const STEP_LABELS: Record<StepKind, string> = {
  ASSUMPTION: 'Giả thiết / điều kiện',
  DERIVATIVE_CALCULATION: 'Tính đạo hàm',
  ROOT_FINDING: 'Tìm nghiệm',
  SIGN_TABLE: 'Bảng xét dấu',
  VARIATION_TABLE: 'Bảng biến thiên',
  CONCLUSION: 'Kết luận',
  EXPLANATION: 'Diễn giải',
  CUSTOM: 'Bước tự do',
};

function newRow(region: PageOcrRegion): ReviewRow {
  return { region, status: 'pending', latex: '', explanation: '', stepType: 'EXPLANATION',
    touched: false, actionId: generateUuid(), error: null, retryOnly: false };
}

export function PageOcrReviewModal({ pageIndex, regions, pageStrokes, onClose, onConfirmStep }: PageOcrReviewModalProps) {
  const [rows, setRows] = useState<ReviewRow[]>(() => regions.map(newRow));
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [processing, setProcessing] = useState(true);
  const [saving, setSaving] = useState(false);
  const [cutPercent, setCutPercent] = useState(50);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const activeRunRef = useRef<{ cancelled: boolean } | null>(null);
  const row = rows[selectedIndex];
  const savedCount = rows.filter((item) => item.status === 'saved').length;
  const earlierUnreviewed = rows.slice(0, selectedIndex).some((item) => item.status !== 'saved' && item.status !== 'skipped');

  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    dialogRef.current?.querySelector<HTMLButtonElement>('button')?.focus();
    return () => previousFocus?.focus();
  }, []);

  useEffect(() => {
    const run = { cancelled: false };
    activeRunRef.current = run;
    async function recognizePage() {
      for (const item of regions) {
        if (run.cancelled) break;
        setRows((current) => current.map((candidate) => candidate.region.id === item.id
          ? { ...candidate, status: 'recognizing' } : candidate));
        try {
          const result = await recognizeHandwrittenMath(item.strokes);
          if (run.cancelled) break;
          setRows((current) => current.map((candidate) => candidate.region.id === item.id
            ? candidate.touched
              ? { ...candidate, status: 'manual' }
              : { ...candidate, status: 'ready', latex: result.latex, stepType: result.suggested_step_type }
            : candidate));
        } catch (error: unknown) {
          if (run.cancelled) break;
          const unavailable = !(error instanceof Error && error.message === 'OCR_NOT_RECOGNIZED');
          setRows((current) => current.map((candidate) => candidate.region.id === item.id
            ? { ...candidate, status: 'manual', error: unavailable ? 'Model chưa tải được. Em có thể nhập bước giải bằng tay.' : null }
            : candidate));
          if (unavailable) {
            setRows((current) => current.map((candidate) => candidate.status === 'pending'
              ? { ...candidate, status: 'manual', error: 'Model chưa tải được. Em có thể nhập bước giải bằng tay.' }
              : candidate));
            break;
          }
        }
      }
      if (!run.cancelled) setProcessing(false);
    }
    void recognizePage();
    return () => { run.cancelled = true; };
  }, [regions]);

  const changeRow = (changes: Partial<ReviewRow>) => {
    setRows((current) => current.map((item, index) => index === selectedIndex ? { ...item, ...changes } : item));
    setReviewError(null);
  };

  const stopRecognition = () => {
    if (activeRunRef.current) activeRunRef.current.cancelled = true;
    setProcessing(false);
    setRows((current) => current.map((item) => item.status === 'pending' || item.status === 'recognizing'
      ? { ...item, status: 'manual', error: 'Chưa nhận diện vùng này. Em có thể thử lại hoặc tự nhập.' }
      : item));
  };

  const retryRecognition = async () => {
    if (!row || processing || saving || row.status === 'saved') return;
    const id = row.region.id;
    changeRow({ status: 'recognizing', error: null, touched: false });
    try {
      const result = await recognizeHandwrittenMath(row.region.strokes);
      setRows((current) => current.map((item) => item.region.id === id && item.status === 'recognizing'
        ? item.touched
          ? { ...item, status: 'manual' }
          : { ...item, status: 'ready', latex: result.latex, stepType: result.suggested_step_type }
        : item));
    } catch (error: unknown) {
      setRows((current) => current.map((item) => item.region.id === id
        ? { ...item, status: 'manual', error: error instanceof Error && error.message === 'OCR_NOT_RECOGNIZED'
          ? 'Model chưa đọc rõ vùng này. Em có thể nhập hoặc sửa bằng tay.' : 'Không tải được model. Em có thể nhập bằng tay.' }
        : item));
    }
  };

  const mergeNext = () => {
    if (!row || processing || saving || row.status === 'saved' || row.retryOnly
      || selectedIndex >= rows.length - 1 || rows[selectedIndex + 1].status === 'saved'
      || rows[selectedIndex + 1].retryOnly) return;
    const merged = mergePageOcrRegions(rows.map((item) => item.region), selectedIndex, pageStrokes)[selectedIndex];
    setRows((current) => [...current.slice(0, selectedIndex), newRow(merged), ...current.slice(selectedIndex + 2)]);
    setReviewError('Đã gộp hai vùng. Bấm Nhận diện lại hoặc nhập công thức cho vùng mới.');
  };

  const splitHere = () => {
    if (!row || processing || saving || row.status === 'saved' || row.retryOnly) return;
    const cut = row.region.bounds.top + (row.region.bounds.bottom - row.region.bounds.top) * cutPercent / 100;
    const divided = splitPageOcrRegion(rows.map((item) => item.region), selectedIndex, cut);
    if (divided.length === rows.length) {
      setReviewError('Vị trí này chưa tách được nét viết. Hãy kéo vạch chia sang chỗ khác.');
      return;
    }
    setRows((current) => [...current.slice(0, selectedIndex), newRow(divided[selectedIndex]),
      newRow(divided[selectedIndex + 1]), ...current.slice(selectedIndex + 1)]);
    setReviewError('Đã tách vùng. Em có thể nhận diện lại từng vùng.');
  };

  const insertKey = (template: string) => {
    if (!row || row.retryOnly) return;
    const field = textareaRef.current;
    const result = insertCorrectionKey(row.latex, field?.selectionStart ?? row.latex.length,
      field?.selectionEnd ?? row.latex.length, template);
    changeRow({ latex: result.value, touched: true });
    window.requestAnimationFrame(() => {
      field?.focus();
      field?.setSelectionRange(result.selectionStart, result.selectionEnd);
    });
  };

  const saveStep = async () => {
    if (!row || saving || row.status === 'saved' || row.status === 'skipped') return;
    if (earlierUnreviewed) {
      setReviewError('Hãy xác nhận hoặc bỏ qua các vùng phía trên trước để giữ đúng thứ tự bài giải.');
      return;
    }
    const regionId = row.region.id;
    const latex = row.latex.trim() ? toConfirmedLatex(row.latex) : null;
    if ((row.latex.trim() && (!latex || !renderOcrLatexHtml(latex))) || (!latex && !row.explanation.trim())) {
      setReviewError('Hãy sửa công thức hợp lệ hoặc nhập lời giải thích trước khi lưu.');
      return;
    }
    setSaving(true);
    setReviewError(null);
    try {
      await onConfirmStep(row.stepType, latex, row.explanation.trim(), row.actionId);
      setRows((current) => current.map((item) => item.region.id === regionId
        ? { ...item, status: 'saved', error: null, retryOnly: false } : item));
      const next = rows.findIndex((item, index) => index > selectedIndex && item.status !== 'saved' && item.status !== 'skipped');
      if (next >= 0) setSelectedIndex(next);
    } catch (error: unknown) {
      const retryOnly = error instanceof ApiNetworkError
        || (error instanceof ApiResponseError && error.status >= 500);
      changeRow({ retryOnly });
      setReviewError(retryOnly
        ? 'Mất kết nối khi lưu. Giữ nguyên nội dung và bấm Lưu lại để kiểm tra kết quả, tránh tạo bước trùng.'
        : error instanceof ApiResponseError && error.status === 401
          ? 'Phiên đăng nhập đã hết hạn. Đăng nhập lại ở tab khác, rồi thử lưu bước này.'
          : error instanceof ApiResponseError && error.status === 409
            ? 'Bài giải đã thay đổi ở nơi khác. Giữ trang này và tải lại sau khi kiểm tra các bước đã lưu.'
        : error instanceof Error ? error.message : 'Không lưu được bước giải.');
    } finally {
      setSaving(false);
    }
  };

  const closeReview = () => {
    if (saving) return;
    if (rows.some((item) => (item.touched || item.retryOnly) && item.status !== 'saved' && item.status !== 'skipped')
      && !window.confirm('Các bước chưa lưu sẽ mất phần chỉnh sửa. Nét viết trên trang vẫn được giữ. Đóng phần trích xuất?')) return;
    if (activeRunRef.current) activeRunRef.current.cancelled = true;
    onClose();
  };

  const handleDialogKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      closeReview();
    }
    if (event.key !== 'Tab') return;
    const buttons = Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(
      'button:not(:disabled), textarea:not(:disabled), select:not(:disabled), input:not(:disabled)',
    ) ?? []);
    if (!buttons.length) return;
    const first = buttons[0];
    const last = buttons[buttons.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  return (
    <div ref={dialogRef} className={`${styles.modalOverlay} ${styles.pageReviewOverlay}`}
      role='dialog' aria-modal='true' aria-labelledby='page-ocr-title' onKeyDown={handleDialogKeyDown}>
      <div className={styles.pageReviewModal}>
        <header className={styles.pageReviewHeader}>
          <div>
            <h2 id='page-ocr-title'>Trích xuất trang {pageIndex + 1}</h2>
            <p>Hệ thống gợi ý các vùng nét viết. Em có thể gộp, tách, sửa và xác nhận từng bước.</p>
          </div>
          <button type='button' className={styles.buttonSecondary} onClick={closeReview} disabled={saving}>Đóng</button>
        </header>
        <div className={styles.pageReviewNotice}>
          OCR chỉ là gợi ý cho công thức viết tay, không tự chấm bài. Với bảng biến thiên, hãy dùng nút “Bảng biến thiên” trên thanh công cụ để điền vào ô và vẽ mũi tên tự động.
        </div>
        <div className={styles.pageReviewProgress} role='status' aria-live='polite'>
          <span>{savedCount}/{rows.length} vùng đã lưu thành bước giải</span>
          {processing ? (
            <button type='button' className={styles.buttonSecondary} onClick={stopRecognition}>
              Đang nhận diện {rows.filter((item) => item.status !== 'pending').length}/{rows.length} · Dừng
            </button>
          ) : null}
        </div>
        <div className={styles.pageReviewContent}>
          <nav className={styles.pageReviewList} aria-label='Các vùng nét viết trên trang'>
            {rows.map((item, index) => (
              <button
                type='button'
                key={item.region.id}
                className={index === selectedIndex ? styles.pageReviewRowActive : styles.pageReviewRow}
                onClick={() => { setSelectedIndex(index); setReviewError(null); setCutPercent(50); }}
                aria-current={index === selectedIndex ? 'step' : undefined}
                disabled={saving}
              >
                <strong>Vùng {index + 1}</strong>
                <span>{item.status === 'saved' ? 'Đã lưu' : item.status === 'skipped' ? 'Đã bỏ qua'
                  : item.status === 'recognizing' ? 'Đang nhận diện' : item.status === 'pending' ? 'Chờ nhận diện'
                    : item.status === 'manual' ? 'Cần tự kiểm tra' : 'Chờ xác nhận'}</span>
                <small>{item.region.strokes.length} nét viết</small>
              </button>
            ))}
          </nav>
          {row ? (
            <div className={styles.pageReviewEditor}>
              <div className={styles.pageReviewEditorTitle}>
                <h3>Vùng {selectedIndex + 1}</h3>
                <span>Trang {pageIndex + 1} · {row.region.strokes.length} nét</span>
              </div>
              <div className={styles.ocrComparison}>
                <OcrInkPreview strokes={row.region.strokes} />
                <div className={styles.ocrResultPreview}>
                  <span className={styles.formLabel}>Công thức sẽ lưu</span>
                  <div className={styles.mathPreviewBox}>
                    {row.stepType === 'VARIATION_TABLE' && row.explanation.trim()
                      ? <pre className={styles.variationTableStep}>{row.explanation}</pre>
                      : <OcrMathPreview latex={row.latex.trim() ? toConfirmedLatex(row.latex) ?? '' : ''} />}
                  </div>
                </div>
              </div>
              {row.error ? <p className={styles.pageReviewWarning} role='status'>{row.error}</p> : null}
              {earlierUnreviewed ? <p className={styles.pageReviewWarning}>Duyệt các vùng phía trên trước để lưu đúng thứ tự bài giải.</p> : null}
              {reviewError ? <p className={styles.ocrErrorBanner} role='alert'>{reviewError}</p> : null}
              <div className={styles.pageReviewActions}>
                <button type='button' className={styles.buttonSecondary} onClick={() => void retryRecognition()}
                  disabled={processing || saving || row.status === 'saved' || row.retryOnly}>Nhận diện lại vùng</button>
                <button type='button' className={styles.buttonSecondary} onClick={mergeNext}
                  disabled={processing || saving || row.status === 'saved' || row.retryOnly || selectedIndex >= rows.length - 1
                    || rows[selectedIndex + 1].status === 'saved' || rows[selectedIndex + 1].retryOnly}>Gộp với vùng sau</button>
              </div>
              <div className={styles.pageReviewSplit}>
                <label htmlFor='page-ocr-cut'>Vạch tách vùng: {cutPercent}% chiều cao vùng</label>
                <input id='page-ocr-cut' type='range' min='10' max='90' value={cutPercent}
                  onChange={(event) => setCutPercent(Number(event.target.value))}
                  disabled={processing || saving || row.status === 'saved' || row.retryOnly || row.region.strokes.length < 2} />
                <button type='button' className={styles.buttonSecondary} onClick={splitHere}
                  disabled={processing || saving || row.status === 'saved' || row.retryOnly || row.region.strokes.length < 2}>Tách tại vạch</button>
              </div>
              <label className={styles.formGroup}>
                <span className={styles.formLabel}>Sửa công thức của em</span>
                <textarea ref={textareaRef} className={styles.formInput} rows={3} value={row.latex}
                  onChange={(event) => changeRow({ latex: event.target.value, touched: true })}
                  placeholder='Ví dụ: y = x^2 + 2'
                  disabled={saving || row.status === 'saved' || row.retryOnly} />
              </label>
              <div className={styles.ocrCorrectionKeys} role='group' aria-label='Bàn phím toán'>
                {CORRECTION_KEYS.map((key) => (
                  <button type='button' key={key.label} className={styles.ocrCorrectionKey}
                    title={key.description} onClick={() => insertKey(key.insert)}
                    disabled={saving || row.status === 'saved' || row.retryOnly}>{key.label}</button>
                ))}
              </div>
              <label className={styles.formGroup}>
                <span className={styles.formLabel}>Loại bước giải</span>
                <select className={styles.formSelect} value={row.stepType}
                  onChange={(event) => changeRow({ stepType: event.target.value as StepKind, touched: true })}
                  disabled={saving || row.status === 'saved' || row.retryOnly}>
                  {STEP_KINDS.map((kind) => <option key={kind} value={kind}>{STEP_LABELS[kind]}</option>)}
                </select>
              </label>
              <label className={styles.formGroup}>
                <span className={styles.formLabel}>Lời giải thích (có thể dùng thay công thức)</span>
                <textarea className={styles.formInput} rows={2} value={row.explanation}
                  onChange={(event) => changeRow({ explanation: event.target.value, touched: true })}
                  placeholder='Ví dụ: Hàm số đồng biến trên khoảng...'
                  disabled={saving || row.status === 'saved' || row.retryOnly} />
              </label>
              <div className={styles.pageReviewFooter}>
                <button type='button' className={styles.buttonSecondary}
                  onClick={() => changeRow({ status: row.status === 'skipped' ? 'manual' : 'skipped' })}
                  disabled={saving || processing || row.status === 'saved' || row.retryOnly}>
                  {row.status === 'skipped' ? 'Xem lại vùng' : 'Bỏ qua vùng'}
                </button>
                <button type='button' className={styles.buttonPrimary} onClick={() => void saveStep()}
                  disabled={saving || earlierUnreviewed || row.status === 'saved' || row.status === 'skipped'}>
                  {saving ? 'Đang lưu...' : row.status === 'saved' ? 'Đã lưu' : row.retryOnly ? 'Lưu lại' : 'Xác nhận bước này'}
                </button>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
