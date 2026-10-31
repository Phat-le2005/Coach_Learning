'use client';

import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import type { InkStroke, StepKind, SolutionAttemptRead } from '@/lib/api/contracts';
import { STEP_KINDS } from '@/lib/api/contracts';
import { ApiNetworkError, ApiResponseError, type ApiClient } from '@/lib/api/client';
import { generateUuid } from '../utils/ink-math';
import { mergePageOcrRegions, splitPageOcrRegion } from '../utils/page-ocr';
import type { PageOcrRegion } from '../utils/page-ocr';
import { recognizeHandwrittenMath } from '../utils/handwritten-ocr';
import {
  createOcrReviewDraft, applyOcrToDraft, editOcrReviewDraft,
  selectOcrDraftKind, approveOcrDraft, skipOcrDraft,
  mergeOcrReviewDrafts, splitOcrReviewDraft, reorderOcrReviewDrafts,
  canApproveOcrDraft,
  type OcrReviewDraft,
} from '../utils/ocr-review-draft';
import { toConfirmedLatex, insertCorrectionKey, CORRECTION_KEYS } from '../utils/ocr-correction';
import { renderOcrLatexHtml } from '../utils/ocr-math-preview';
import { OcrInkPreview } from './OcrInkPreview';
import { OcrMathPreview } from './OcrMathPreview';
import { SequentialBatchManager, type BatchJournal } from '../utils/batch-manager';
import { IndexedDbBatchJournal, BrowserBatchLock } from '../utils/batch-journal';
import {
  createBatchApi,
  buildApprovedIntents,
  canStartBatchReview,
  syncRowsFromJournal,
} from '../utils/ocr-batch-adapter';
import styles from '../MathWorkspace.module.css';

type ReviewStatus = 'pending' | 'recognizing' | 'ready' | 'manual' | 'approved' | 'saved' | 'skipped';

interface ReviewRow {
  region: PageOcrRegion;
  status: ReviewStatus;
  draft: OcrReviewDraft;
  touched: boolean;
  actionId: string;
  error: string | null;
  retryOnly: boolean;
  serverStepId?: string | null;
}

interface PageOcrReviewModalProps {
  pageIndex: number;
  regions: PageOcrRegion[];
  pageStrokes: InkStroke[];
  onClose: () => void;
  onConfirmStep: (stepType: StepKind, latex: string | null, explanation: string, actionId: string) => Promise<void>;
  attemptId?: string;
  accessToken?: string;
  apiClient?: ApiClient;
  onBatchComplete?: (freshAttempt: SolutionAttemptRead) => void;
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

function newRow(region: PageOcrRegion, pageIndex: number): ReviewRow {
  return {
    region, status: 'pending',
    draft: createOcrReviewDraft({
      localId: generateUuid(),
      pageIndex,
      regionIds: [region.id],
      strokeIds: region.strokes.map((stroke) => stroke.id),
    }),
    touched: false, actionId: generateUuid(), error: null, retryOnly: false,
  };
}

export function PageOcrReviewModal({
  pageIndex,
  regions,
  pageStrokes,
  onClose,
  onConfirmStep,
  attemptId,
  accessToken,
  apiClient,
  onBatchComplete,
}: PageOcrReviewModalProps) {
  const [rows, setRows] = useState<ReviewRow[]>(() => regions.map((region) => newRow(region, pageIndex)));
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [processing, setProcessing] = useState(true);
  const [saving, setSaving] = useState(false);
  const [batchSaving, setBatchSaving] = useState(false);
  const [batchProgress, setBatchProgress] = useState<{ current: number; total: number; message: string } | null>(null);
  const [pausedJournal, setPausedJournal] = useState<BatchJournal | null>(null);
  const [cutPercent, setCutPercent] = useState(50);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const activeRunRef = useRef<{ cancelled: boolean } | null>(null);
  const row = rows[selectedIndex];
  const savedCount = rows.filter((item) => item.status === 'saved').length;
  const approvedCount = rows.filter((item) => item.status === 'approved').length;
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
              : { ...candidate, status: 'ready', draft: applyOcrToDraft(candidate.draft, result.latex) }
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
          : { ...item, status: 'ready', draft: applyOcrToDraft(item.draft, result.latex) }
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
    setRows((current) => [...current.slice(0, selectedIndex), newRow(merged, pageIndex), ...current.slice(selectedIndex + 2)]);
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
    setRows((current) => [...current.slice(0, selectedIndex), newRow(divided[selectedIndex], pageIndex),
      newRow(divided[selectedIndex + 1], pageIndex), ...current.slice(selectedIndex + 1)]);
    setReviewError('Đã tách vùng. Em có thể nhận diện lại từng vùng.');
  };

  // Logical step composition is separate from geometric segmentation.
  // Combining drafts never silently creates a valid mathematical step.
  const mergeNextLogicalStep = () => {
    const next = rows[selectedIndex + 1];
    if (!row || !next || processing || saving || row.retryOnly || next.retryOnly
      || ['saved', 'skipped', 'pending', 'recognizing'].includes(row.status)
      || ['saved', 'skipped', 'pending', 'recognizing'].includes(next.status)) return;
    const mergedRegion = mergePageOcrRegions(rows.map((item) => item.region), selectedIndex, pageStrokes)[selectedIndex];
    const mergedDraft = mergeOcrReviewDrafts(row.draft, next.draft, generateUuid());
    setRows((current) => [
      ...current.slice(0, selectedIndex),
      { ...newRow(mergedRegion, pageIndex), draft: mergedDraft, status: 'manual', touched: true },
      ...current.slice(selectedIndex + 2),
    ]);
    setReviewError('Đã ghép hai bước tạm thời. Nội dung chưa được xác nhận: hãy sửa LaTeX và chọn lại loại bước trước khi lưu.');
  };

  // Split at an explicit student-selected cursor position, never by guessing a math boundary.
  const splitLogicalStep = () => {
    if (!row || processing || saving || row.retryOnly || ['saved', 'skipped', 'pending', 'recognizing'].includes(row.status)) return;
    if (row.draft.explanationText.trim()) {
      setReviewError('Bước đang có lời giải thích. Hãy xử lý phần giải thích trước khi tách thành hai bước.');
      return;
    }
    const text = row.draft.contentLatex;
    const cut = textareaRef.current?.selectionStart ?? -1;
    if (cut <= 0 || cut >= text.length || !text.slice(0, cut).trim() || !text.slice(cut).trim()) {
      setReviewError('Hãy đặt con trỏ trong ô LaTeX tại ranh giới của hai bước rồi chọn Tách bước.');
      return;
    }
    const [first, second] = splitOcrReviewDraft(
      row.draft,
      { localId: generateUuid(), contentLatex: text.slice(0, cut).trim() },
      { localId: generateUuid(), contentLatex: text.slice(cut).trim() },
    );
    const firstRegion = { ...row.region, id: first.localId };
    const secondRegion = { ...row.region, id: second.localId };
    setRows((current) => [
      ...current.slice(0, selectedIndex),
      { ...newRow(firstRegion, pageIndex), draft: first, status: 'manual', touched: true },
      { ...newRow(secondRegion, pageIndex), draft: second, status: 'manual', touched: true },
      ...current.slice(selectedIndex + 1),
    ]);
    setReviewError('Hai bước tạm thời cùng tham chiếu nét gốc. Hãy kiểm tra LaTeX và loại của từng bước trước khi lưu.');
  };

  const moveLogicalStep = (offset: -1 | 1) => {
    const target = selectedIndex + offset;
    if (!row || processing || saving || target < 0 || target >= rows.length
      || ['saved', 'skipped', 'pending', 'recognizing'].includes(row.status)
      || ['saved', 'skipped', 'pending', 'recognizing'].includes(rows[target].status)
      || row.retryOnly || rows[target].retryOnly) return;
    const orderedDrafts = reorderOcrReviewDrafts(rows.map((item) => item.draft), selectedIndex, target);
    const byId = new Map(rows.map((item) => [item.draft.localId, item] as const));
    setRows(orderedDrafts.map((draft) => byId.get(draft.localId)!));
    setSelectedIndex(target);
    setReviewError(null);
  };

  const insertKey = (template: string) => {
    if (!row || row.retryOnly) return;
    const field = textareaRef.current;
    const result = insertCorrectionKey(row.draft.contentLatex, field?.selectionStart ?? row.draft.contentLatex.length,
      field?.selectionEnd ?? row.draft.contentLatex.length, template);
    changeRow({ draft: editOcrReviewDraft(row.draft, { contentLatex: result.value }), touched: true });
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
    const selectedKind = row.draft.selectedStepKind;
    if (!selectedKind) {
      setReviewError('Chưa xác định được loại bước. Hãy chọn loại bước trước khi lưu.');
      return;
    }
    const latex = row.draft.contentLatex.trim() ? toConfirmedLatex(row.draft.contentLatex) : null;
    if ((row.draft.contentLatex.trim() && (!latex || !renderOcrLatexHtml(latex))) || (!latex && !row.draft.explanationText.trim())) {
      setReviewError('Hãy sửa công thức hợp lệ hoặc nhập lời giải thích trước khi lưu.');
      return;
    }
    // Approve the exact draft being submitted before any async mutation.
    // Never perform a potentially throwing validation inside setState after a server commit.
    const approvedDraft = approveOcrDraft(row.draft);
    setSaving(true);
    setReviewError(null);
    try {
      await onConfirmStep(selectedKind, latex, approvedDraft.explanationText.trim(), row.actionId);
      setRows((current) => current.map((item) => item.region.id === regionId
        ? { ...item, draft: approvedDraft, status: 'saved', error: null, retryOnly: false } : item));
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

  const approveCurrentDraft = () => {
    if (!row || row.status === 'saved' || row.status === 'skipped') return;
    if (!canApproveOcrDraft(row.draft)) {
      setReviewError('Chưa xác định được loại bước hoặc công thức đang để trống. Hãy chọn loại bước trước khi duyệt.');
      return;
    }
    const approved = approveOcrDraft(row.draft);
    changeRow({ draft: approved, status: 'approved', error: null });
    const next = rows.findIndex((item, index) => index > selectedIndex && item.status !== 'saved' && item.status !== 'skipped' && item.status !== 'approved');
    if (next >= 0) setSelectedIndex(next);
  };

  const unapproveCurrentDraft = () => {
    if (!row || row.status !== 'approved') return;
    changeRow({
      draft: { ...row.draft, reviewStatus: 'NEEDS_REVIEW' },
      status: 'manual',
      error: null,
    });
  };

  const saveBatchSteps = async () => {
    if (batchSaving || saving) return;
    const check = canStartBatchReview(rows);
    if (!check.canStart) {
      setReviewError(check.reason ?? 'Chưa thể lưu đợt bước giải.');
      return;
    }
    if (!attemptId || !accessToken || !apiClient) {
      setReviewError('Thiếu thông tin phiên làm bài để lưu hàng loạt.');
      return;
    }
    const intents = buildApprovedIntents(rows);
    if (intents.length === 0) {
      setReviewError('Chưa có bước nào được duyệt để lưu.');
      return;
    }

    setBatchSaving(true);
    setReviewError(null);
    setBatchProgress({
      current: 0,
      total: intents.length,
      message: `Đang khởi tạo đợt lưu ${intents.length} bước...`,
    });

    try {
      const batchApi = createBatchApi(apiClient, accessToken);
      const store = new IndexedDbBatchJournal();
      const lock = new BrowserBatchLock();
      const manager = new SequentialBatchManager(batchApi, store, lock);
      const batchId = generateUuid();

      const result = await manager.start(attemptId, batchId, intents);

      if (result.status === 'COMPLETE') {
        setRows((current) => syncRowsFromJournal(current, result.journal));
        setBatchProgress({
          current: intents.length,
          total: intents.length,
          message: `Đã lưu thành công tất cả ${intents.length} bước lên máy chủ!`,
        });
        setPausedJournal(null);
        onBatchComplete?.(result.attempt);
      } else if (result.status === 'PAUSED') {
        setRows((current) => syncRowsFromJournal(current, result.journal));
        setPausedJournal(result.journal);
        const committedCount = result.journal.entries.filter((e) => e.state === 'COMMITTED').length;
        setBatchProgress({
          current: committedCount,
          total: intents.length,
          message: `Đã lưu ${committedCount}/${intents.length} bước. Đợt lưu tạm dừng: ${result.journal.message}`,
        });
        setReviewError(
          `Đợt lưu tạm dừng (${committedCount}/${intents.length} bước đã lưu). ${result.journal.message}. Các bước đã lưu được giữ nguyên trên máy chủ. Em có thể bấm "Lưu tiếp đợt này" để tiếp tục.`
        );
      } else {
        setReviewError('Không thể lấy quyền thao tác độc quyền (Web Lock). Tab khác đang lưu bài giải.');
      }
    } catch (err: unknown) {
      setReviewError(err instanceof Error ? err.message : 'Không lưu được đợt bước giải.');
    } finally {
      setBatchSaving(false);
    }
  };

  const resumeBatchSteps = async () => {
    if (batchSaving || saving || !attemptId || !accessToken || !apiClient) return;
    setBatchSaving(true);
    setReviewError(null);
    setBatchProgress({
      current: 0,
      total: rows.length,
      message: 'Đang đối soát và lưu tiếp các bước...',
    });
    try {
      const batchApi = createBatchApi(apiClient, accessToken);
      const store = new IndexedDbBatchJournal();
      const lock = new BrowserBatchLock();
      const manager = new SequentialBatchManager(batchApi, store, lock);

      const result = await manager.resume(attemptId);
      if (result.status === 'COMPLETE') {
        setRows((current) => syncRowsFromJournal(current, result.journal));
        const total = result.journal.entries.length;
        setBatchProgress({
          current: total,
          total,
          message: `Đã lưu thành công tất cả ${total} bước!`,
        });
        setPausedJournal(null);
        onBatchComplete?.(result.attempt);
      } else if (result.status === 'PAUSED') {
        setRows((current) => syncRowsFromJournal(current, result.journal));
        setPausedJournal(result.journal);
        const total = result.journal.entries.length;
        const committed = result.journal.entries.filter((e) => e.state === 'COMMITTED').length;
        setBatchProgress({
          current: committed,
          total,
          message: `Đã lưu ${committed}/${total} bước. Tạm dừng: ${result.journal.message}`,
        });
        setReviewError(`Đợt lưu tạm dừng: ${result.journal.message}. Em có thể bấm "Lưu tiếp đợt này" để thử lại.`);
      } else {
        setReviewError('Không thể lấy khóa thao tác độc quyền. Tab khác đang thao tác.');
      }
    } catch (err: unknown) {
      setReviewError(err instanceof Error ? err.message : 'Lỗi khi lưu tiếp đợt.');
    } finally {
      setBatchSaving(false);
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
          <span>{savedCount}/{rows.length} vùng đã lưu · {approvedCount} bước đã duyệt</span>
          {processing ? (
            <button type='button' className={styles.buttonSecondary} onClick={stopRecognition}>
              Đang nhận diện {rows.filter((item) => item.status !== 'pending').length}/{rows.length} · Dừng
            </button>
          ) : null}
        </div>
        {batchProgress ? (
          <div className={styles.pageReviewBatchProgress} role='status'>
            {batchProgress.message}
          </div>
        ) : null}
        <div className={styles.pageReviewContent}>
          <nav className={styles.pageReviewList} aria-label='Các vùng nét viết trên trang'>
            {rows.map((item, index) => (
              <button
                type='button'
                key={item.draft.localId}
                className={
                  index === selectedIndex
                    ? styles.pageReviewRowActive
                    : item.status === 'approved'
                      ? styles.pageReviewRowApproved
                      : styles.pageReviewRow
                }
                onClick={() => { setSelectedIndex(index); setReviewError(null); setCutPercent(50); }}
                aria-current={index === selectedIndex ? 'step' : undefined}
                disabled={saving || batchSaving}
              >
                <strong>Vùng {index + 1}</strong>
                <span>{item.status === 'saved' ? 'Đã lưu' : item.status === 'skipped' ? 'Đã bỏ qua'
                  : item.status === 'approved' ? 'Đã duyệt'
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
                    {row.draft.selectedStepKind === 'VARIATION_TABLE' && row.draft.explanationText.trim()
                      ? <pre className={styles.variationTableStep}>{row.draft.explanationText}</pre>
                      : <OcrMathPreview latex={row.draft.contentLatex.trim() ? toConfirmedLatex(row.draft.contentLatex) ?? '' : ''} />}
                  </div>
                </div>
              </div>
              {row.error ? <p className={styles.pageReviewWarning} role='status'>{row.error}</p> : null}
              {earlierUnreviewed ? <p className={styles.pageReviewWarning}>Duyệt các vùng phía trên trước để lưu đúng thứ tự bài giải.</p> : null}
              {reviewError ? <p className={styles.ocrErrorBanner} role='alert'>{reviewError}</p> : null}
              <div className={styles.pageReviewActions}>
                {row.status === 'approved' ? (
                  <button type='button' className={styles.buttonSecondary} onClick={unapproveCurrentDraft}
                    disabled={saving || batchSaving}>Hủy duyệt bước này</button>
                ) : row.status !== 'saved' && row.status !== 'skipped' ? (
                  <button type='button' className={styles.buttonSecondary} onClick={approveCurrentDraft}
                    disabled={saving || batchSaving}>Duyệt bước này (Approve)</button>
                ) : null}
                <button type='button' className={styles.buttonSecondary} onClick={() => void retryRecognition()}
                  disabled={processing || saving || batchSaving || row.status === 'saved' || row.retryOnly}>Nhận diện lại vùng</button>
                <button type='button' className={styles.buttonSecondary} onClick={mergeNext}
                  disabled={processing || saving || batchSaving || row.status === 'saved' || row.retryOnly || selectedIndex >= rows.length - 1
                    || rows[selectedIndex + 1].status === 'saved' || rows[selectedIndex + 1].retryOnly}>Gộp vùng nét</button>
                <button type='button' className={styles.buttonSecondary} onClick={mergeNextLogicalStep}
                  disabled={processing || saving || batchSaving || row.retryOnly || ['saved', 'skipped', 'pending', 'recognizing'].includes(row.status)
                    || selectedIndex >= rows.length - 1 || rows[selectedIndex + 1].retryOnly
                    || ['saved', 'skipped', 'pending', 'recognizing'].includes(rows[selectedIndex + 1].status)}>
                  Gộp hai bước logic
                </button>
              </div>
              <div className={styles.pageReviewActions}>
                <button type='button' className={styles.buttonSecondary} onClick={splitLogicalStep}
                  disabled={processing || saving || batchSaving || row.retryOnly || ['saved', 'skipped', 'pending', 'recognizing'].includes(row.status)}>
                  Tách thành hai bước tại con trỏ
                </button>
                <button type='button' className={styles.buttonSecondary} onClick={() => moveLogicalStep(-1)}
                  disabled={processing || saving || batchSaving || selectedIndex === 0 || row.retryOnly
                    || ['saved', 'skipped', 'pending', 'recognizing'].includes(row.status)
                    || ['saved', 'skipped', 'pending', 'recognizing'].includes(rows[selectedIndex - 1]?.status)}>
                  Đưa lên
                </button>
                <button type='button' className={styles.buttonSecondary} onClick={() => moveLogicalStep(1)}
                  disabled={processing || saving || batchSaving || selectedIndex >= rows.length - 1 || row.retryOnly
                    || ['saved', 'skipped', 'pending', 'recognizing'].includes(row.status)
                    || ['saved', 'skipped', 'pending', 'recognizing'].includes(rows[selectedIndex + 1]?.status)}>
                  Đưa xuống
                </button>
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
                <textarea ref={textareaRef} className={styles.formInput} rows={3} value={row.draft.contentLatex}
                  onChange={(event) => changeRow({
                    draft: editOcrReviewDraft(row.draft, { contentLatex: event.target.value }),
                    touched: true,
                  })}
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
                <select className={styles.formSelect} value={row.draft.selectedStepKind ?? ''}
                  onChange={(event) => changeRow({
                    draft: selectOcrDraftKind(row.draft, event.target.value as StepKind),
                    touched: true,
                  })}
                  disabled={saving || row.status === 'saved' || row.retryOnly}>
                  <option value='' disabled>Chưa xác định — vui lòng chọn</option>
                  {STEP_KINDS.map((kind) => <option key={kind} value={kind}>{STEP_LABELS[kind]}</option>)}
                </select>
              </label>
              {row.draft.stepKindSource === 'UNRESOLVED' ? (
                <p className={styles.pageReviewWarning} role='status'>
                  Bộ phân loại chưa đủ căn cứ xác định loại bước. Em hãy chọn thủ công trước khi xác nhận.
                </p>
              ) : row.draft.stepKindSource === 'SUGGESTED' ? (
                <p className={styles.pageReviewWarning}>
                  Loại bước đang là gợi ý tự động; em có thể chọn lại nếu cần.
                </p>
              ) : null}
              <label className={styles.formGroup}>
                <span className={styles.formLabel}>Lời giải thích (có thể dùng thay công thức)</span>
                <textarea className={styles.formInput} rows={2} value={row.draft.explanationText}
                  onChange={(event) => changeRow({
                    draft: editOcrReviewDraft(row.draft, { explanationText: event.target.value }),
                    touched: true,
                  })}
                  placeholder='Ví dụ: Hàm số đồng biến trên khoảng...'
                  disabled={saving || row.status === 'saved' || row.retryOnly} />
              </label>
              <div className={styles.pageReviewFooter}>
                <button type='button' className={styles.buttonSecondary}
                  onClick={() => changeRow({
                    status: row.status === 'skipped' ? 'manual' : 'skipped',
                    draft: row.status === 'skipped'
                      ? { ...row.draft, reviewStatus: 'NEEDS_REVIEW' }
                      : skipOcrDraft(row.draft),
                  })}
                  disabled={saving || batchSaving || processing || row.status === 'saved' || row.retryOnly}>
                  {row.status === 'skipped' ? 'Xem lại vùng' : 'Bỏ qua vùng'}
                </button>
                <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                  <button type='button' className={styles.buttonSecondary} onClick={() => void saveStep()}
                    disabled={saving || batchSaving || earlierUnreviewed || row.status === 'saved' || row.status === 'skipped'}>
                    {saving ? 'Đang lưu...' : row.status === 'saved' ? 'Đã lưu' : row.retryOnly ? 'Lưu lại' : 'Lưu ngay bước này'}
                  </button>
                  {pausedJournal ? (
                    <button type='button' className={styles.buttonPrimary} onClick={() => void resumeBatchSteps()}
                      disabled={saving || batchSaving}>
                      {batchSaving ? 'Đang xử lý...' : 'Lưu tiếp đợt này (Resume)'}
                    </button>
                  ) : (
                    <button type='button' className={styles.buttonPrimary} onClick={() => void saveBatchSteps()}
                      disabled={saving || batchSaving || approvedCount === 0}>
                      {batchSaving ? 'Đang lưu đợt...' : `Lưu tất cả bước đã duyệt (${approvedCount})`}
                    </button>
                  )}
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
