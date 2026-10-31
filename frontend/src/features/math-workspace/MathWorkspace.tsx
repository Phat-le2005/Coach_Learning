"use client";

import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import { Sparkles } from "lucide-react";
import { ApiResponseError, ApiNetworkError } from "@/lib/api/client";
import { createBrowserMathApiClient } from "@/lib/api/browser-math";
import type {
  DrawingTool,
  InkDocumentRead,
  InkPageRead,
  InkStroke,
  PaperGrid,
  ProblemRead,
  SolutionAttemptRead,
  SyncStatus,
} from "./types";
import { MAX_PAGES, A4_WIDTH } from "./types";
import { generateUuid } from "./utils/ink-math";
import { mathInkStorage } from "./storage/indexeddb";
import { ensureLatestInkSaved } from "./utils/ocr-sync";
import { getOcrPenStrokes } from "./utils/ocr-ink";
import { segmentPageInk } from "./utils/page-ocr";
import type { PageOcrRegion } from "./utils/page-ocr";
import { canSafelyRebaseInkDraft, restoreDirtyPageDrafts } from "./utils/draft-recovery";
import { WorkspaceToolbar } from "./components/WorkspaceToolbar";
import { PaperUploadPanel } from "./components/PaperUploadPanel";
import { PageNavigator } from "./components/PageNavigator";
import { ProblemPane } from "./components/ProblemPane";
import { MathCanvas } from "./components/MathCanvas";
import { SyncStatusBadge } from "./components/SyncStatusBadge";
import { PageOcrReviewModal } from "./components/PageOcrReviewModal";
import { VariationTableModal } from "./components/VariationTableModal";
import { AIReviewWorkspace } from "./components/ai-review/AIReviewWorkspace";
import type { AIReviewRead, AIReviewAvailabilityRead, StepKind, VariationTablePayload } from "@/lib/api/contracts";
import { SequentialBatchManager, type BatchJournal } from "./utils/batch-manager";
import { IndexedDbBatchJournal, BrowserBatchLock } from "./utils/batch-journal";
import { createBatchApi } from "./utils/ocr-batch-adapter";
import styles from "./MathWorkspace.module.css";

const MathCanvasPanel = dynamic(() => import("@/features/math-canvas/MathCanvasPanel").then((module) => module.MathCanvasPanel), {
  ssr: false,
  loading: () => <p role="status">Đang mở Math View…</p>,
});

interface PageMemory {
  strokes: InkStroke[];
  past: InkStroke[][];
  future: InkStroke[][];
  isDirty: boolean;
}

interface MathWorkspaceProps {
  attemptId: string;
  initialProblem?: ProblemRead | null;
  initialAttempt?: SolutionAttemptRead | null;
  initialDocument?: InkDocumentRead | null;
  initialPage?: InkPageRead | null;
}

export function MathWorkspace({
  attemptId,
  initialProblem = null,
  initialAttempt = null,
  initialDocument = null,
  initialPage = null,
}: MathWorkspaceProps) {
  // The BFF reads the HttpOnly cookie. No bearer token is passed to this client component.
  const accessToken = "";
  // Problem & Attempt
  const [problem, setProblem] = useState<ProblemRead | null>(initialProblem);
  const [attempt, setAttempt] = useState<SolutionAttemptRead | null>(initialAttempt);

  // Layout & View
  const [isProblemPaneCollapsed, setIsProblemPaneCollapsed] = useState(false);
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const [graphOpen, setGraphOpen] = useState(false);
  const [graphSelection, setGraphSelection] = useState<{ page: number; strokes: InkStroke[]; formula?: string }>({ page: 0, strokes: [] });

  // Document & Multi-page
  const [documentRevision, setDocumentRevision] = useState(
    initialDocument?.document_revision ?? 0,
  );
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [pageCount, setPageCount] = useState(
    Math.max(1, ...(initialDocument?.pages.map((page) => page.page_index + 1) ?? [])),
  );

  // Pages state memory
  const [pagesMap, setPagesMap] = useState<Map<number, PageMemory>>(() => {
    const map = new Map<number, PageMemory>();
    const initialStrokes = initialPage?.strokes ?? [];
    map.set(0, {
      strokes: initialStrokes,
      past: [],
      future: [],
      isDirty: false,
    });
    return map;
  });

  // Tools & Attributes
  const [currentTool, setCurrentTool] = useState<DrawingTool>("pen");
  const [penColor, setPenColor] = useState("#0f172a");
  const [penWidth, setPenWidth] = useState(2);
  const [highlighterWidth, setHighlighterWidth] = useState(18);
  const [paperGrid, setPaperGrid] = useState<PaperGrid>("grid");
  const [paperMode, setPaperMode] = useState(false);

  // Sync state
  const [syncStatus, setSyncStatus] = useState<SyncStatus>("saved");
  const [syncErrorMessage, setSyncErrorMessage] = useState<string | undefined>();
  const [authExpired, setAuthExpired] = useState(false);

  // OCR recognition & confirmation state
  const [isRecognizingOCR, setIsRecognizingOCR] = useState(false);
  const [pageOcrReview, setPageOcrReview] = useState<{
    pageIndex: number; regions: PageOcrRegion[]; pageStrokes: InkStroke[];
  } | null>(null);
  const [ocrError, setOcrError] = useState<string | null>(null);
  const [variationTableEditor, setVariationTableEditor] = useState<{ stepId?: string; initial?: VariationTablePayload } | null>(null);

  // PR3-C: Batch recovery state
  const [pendingBatch, setPendingBatch] = useState<BatchJournal | null>(null);
  const [batchResuming, setBatchResuming] = useState(false);
  const [recoveryMessage, setRecoveryMessage] = useState<string | null>(null);

  const [aiReview, setAIReview] = useState<AIReviewRead | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      const raw = window.sessionStorage.getItem(`edums_ai_review_${attemptId}`);
      return raw ? JSON.parse(raw) as AIReviewRead : null;
    } catch {
      return null;
    }
  });
  const [aiReviewAvailability, setAIReviewAvailability] = useState<AIReviewAvailabilityRead | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isReviewing, setIsReviewing] = useState(false);
  const [isReviewWorkspaceOpen, setIsReviewWorkspaceOpen] = useState(false);
  const [instantReviewOpen, setInstantReviewOpen] = useState(false);
  const [gradingError, setGradingError] = useState<string | null>(null);
  const submitActionRef = useRef<{ revision: number; actionId: string } | null>(null);
  // Debounce save timer ref
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const revisionRef = useRef(initialDocument?.document_revision ?? 0);
  const latestStrokesRef = useRef<Map<number, InkStroke[]>>(
    new Map([[0, initialPage?.strokes ?? []]]),
  );
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const pendingDeleteRef = useRef<{ stepId: string; revision: number; actionId: string } | null>(null);
  const locallyEditedPagesRef = useRef(new Set<number>());
  const recoveredDraftRevisionsRef = useRef(new Map<number, number>());
  const transientPageIndexesRef = useRef(new Set<number>());
  const unverifiedPageIndexesRef = useRef(new Set<number>(initialPage ? [] : [0]));

  const apiClient = useRef(createBrowserMathApiClient()).current;

  const pagesRecord = useMemo(() => {
    const rec: Record<number, InkStroke[]> = {};
    for (const [idx, page] of pagesMap.entries()) {
      rec[idx] = page.strokes;
    }
    return rec;
  }, [pagesMap]);

  // Current active page memory
  const currentPageMemory: PageMemory = pagesMap.get(currentPageIndex) ?? {
    strokes: [],
    past: [],
    future: [],
    isDirty: false,
  };

  useEffect(() => {
    let active = true;
    apiClient.getMathAIReviewAvailability(accessToken, attemptId)
      .then((value) => {
        if (active) {
          setAIReviewAvailability(value);
          if (value.cached_review) {
            setAIReview(value.cached_review);
            try {
              window.sessionStorage.setItem(`edums_ai_review_${attemptId}`, JSON.stringify(value.cached_review));
            } catch {}
          }
        }
      })
      .catch(() => { if (active) setAIReviewAvailability(null); });
    return () => { active = false; };
  }, [apiClient, accessToken, attemptId]);

  // 1. Initial data fetch if not passed via props
  useEffect(() => {
    if (!problem && attemptId) {
      apiClient
        .getMathAttemptProblem(accessToken, attemptId)
        .then(setProblem)
        .catch(() => {});
    }

    if (!attempt && attemptId) {
      apiClient
        .getMathAttempt(accessToken, attemptId)
        .then(setAttempt)
        .catch(() => {});
    }

    if (!initialDocument && attemptId) {
      apiClient
        .getMathInkDocument(accessToken, attemptId)
        .then((doc) => {
          revisionRef.current = Math.max(revisionRef.current, doc.document_revision);
          setDocumentRevision((revision) => Math.max(revision, doc.document_revision));
          if (doc.pages.length > 0) {
            setPageCount((count) => Math.max(count, ...doc.pages.map((page) => page.page_index + 1)));
          }
        })
        .catch(() => {});
    }
  }, [attemptId, accessToken, problem, attempt, initialDocument, apiClient]);

  // SSR may have failed to read page 0 during an expired session. Never treat
  // that blank fallback as an authoritative page or overwrite existing ink.
  useEffect(() => {
    if (initialPage || !attemptId) return;
    let active = true;
    void apiClient.getMathInkPage(accessToken, attemptId, 0).then((page) => {
      if (!active) return;
      revisionRef.current = Math.max(revisionRef.current, page.document_revision);
      setDocumentRevision((revision) => Math.max(revision, page.document_revision));
      if (locallyEditedPagesRef.current.has(0) || recoveredDraftRevisionsRef.current.has(0)) return;
      setPagesMap((current) => {
        if (current.get(0)?.isDirty) return current;
        const next = new Map(current);
        next.set(0, { strokes: page.strokes, past: [], future: [], isDirty: false });
        latestStrokesRef.current.set(0, page.strokes);
        unverifiedPageIndexesRef.current.delete(0);
        return next;
      });
    }).catch((err: unknown) => {
      if (!active || locallyEditedPagesRef.current.has(0) || recoveredDraftRevisionsRef.current.has(0)) return;
      // Keep the page unverified. Any later save must compare server ink first.
      setAuthExpired(err instanceof ApiResponseError && err.status === 401);
      setSyncStatus(err instanceof ApiNetworkError ? "offline" : "error");
      setSyncErrorMessage("Không thể tải nét viết từ máy chủ. Bấm Thử lại sau khi kết nối hoặc đăng nhập lại.");
    });
    return () => { active = false; };
  }, [attemptId, accessToken, apiClient, initialPage]);

  // Recover local ink that never reached the server (for example after an expired session).
  useEffect(() => {
    let active = true;
    void mathInkStorage.listDirtyPages(attemptId).then((drafts) => {
      if (!active || drafts.length === 0) return;
      const candidates = restoreDirtyPageDrafts(new Map(), drafts, locallyEditedPagesRef.current, MAX_PAGES).restored;
      if (candidates.length === 0) return;
      for (const draft of candidates) {
        latestStrokesRef.current.set(draft.pageIndex, draft.strokes);
        recoveredDraftRevisionsRef.current.set(draft.pageIndex, draft.documentRevision);
      }
      setPagesMap((current) =>
        restoreDirtyPageDrafts(current, candidates, locallyEditedPagesRef.current, MAX_PAGES).pages,
      );
      setPageCount((count) => Math.max(count, ...candidates.map((draft) => draft.pageIndex + 1)));
      setCurrentPageIndex(candidates[0].pageIndex);
      setSyncStatus("error");
      setSyncErrorMessage("Đã khôi phục nét viết chưa đồng bộ. Bấm Thử lại để lưu lên máy chủ.");
    }).catch(() => {
      // Keep the server copy visible; IndexedDB may be disabled by browser policy.
    });
    return () => { active = false; };
  }, [attemptId]);

  // PR3-C: Recover unfinished batch journal from previous tab session or reload (F5 recovery)
  const checkPendingBatch = useCallback(async () => {
    if (typeof window === "undefined" || !attemptId) return;
    try {
      const store = new IndexedDbBatchJournal();
      const journal = await store.load(attemptId);
      if (journal && journal.state !== "COMPLETE" && journal.state !== "ABANDONED") {
        setPendingBatch(journal);
      } else {
        setPendingBatch(null);
      }
    } catch (err: unknown) {
      setRecoveryMessage(err instanceof Error ? err.message : "Lỗi đọc dữ liệu đợt lưu từ bộ nhớ trình duyệt.");
    }
  }, [attemptId]);

  useEffect(() => {
    void checkPendingBatch();
  }, [checkPendingBatch]);

  const handleResumePendingBatch = async () => {
    if (batchResuming || !attemptId || !accessToken || !apiClient) return;
    setBatchResuming(true);
    setRecoveryMessage("Đang đối soát và lưu tiếp các bước giải...");
    try {
      const batchApi = createBatchApi(apiClient, accessToken);
      const store = new IndexedDbBatchJournal();
      const lock = new BrowserBatchLock();
      const manager = new SequentialBatchManager(batchApi, store, lock);
      const res = await manager.resume(attemptId);
      if (res.status === "COMPLETE") {
        setAttempt(res.attempt);
        setPendingBatch(null);
        setRecoveryMessage(null);
      } else if (res.status === "PAUSED") {
        setPendingBatch(res.journal);
        const committed = res.journal.entries.filter((e) => e.state === "COMMITTED").length;
        setRecoveryMessage(`Tạm dừng: ${res.journal.message} (${committed}/${res.journal.entries.length} bước đã lưu).`);
      } else {
        setRecoveryMessage("Không thể lấy quyền thao tác độc quyền (Web Lock). Tab khác đang thao tác.");
      }
    } catch (err: unknown) {
      setRecoveryMessage(err instanceof Error ? err.message : "Lỗi khi phục hồi đợt lưu.");
    } finally {
      setBatchResuming(false);
    }
  };

  const handleAbandonPendingBatch = async () => {
    if (batchResuming || !attemptId || !accessToken || !apiClient) return;
    if (!window.confirm("Hủy bỏ đợt lưu các bước lỗi này? Các bước đã lưu trên máy chủ vẫn được giữ nguyên.")) return;
    setBatchResuming(true);
    try {
      const batchApi = createBatchApi(apiClient, accessToken);
      const store = new IndexedDbBatchJournal();
      const lock = new BrowserBatchLock();
      const manager = new SequentialBatchManager(batchApi, store, lock);
      await manager.abandonRejected(attemptId);
      setPendingBatch(null);
      setRecoveryMessage(null);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Không thể hủy bỏ đợt lưu.");
    } finally {
      setBatchResuming(false);
    }
  };

  // 2. Perform server save
  const flushSavePage = useCallback(
    (pageIdx: number, strokesToSave: InkStroke[]): Promise<boolean> => {
      const operation = async (): Promise<boolean> => {
        if (latestStrokesRef.current.get(pageIdx) !== strokesToSave) return false;
        setSyncStatus("saving");
        setSyncErrorMessage(undefined);
        try {
          let revision = revisionRef.current;
          let checkServerPage = unverifiedPageIndexesRef.current.has(pageIdx)
            || (recoveredDraftRevisionsRef.current.get(pageIdx) !== undefined
              && recoveredDraftRevisionsRef.current.get(pageIdx) !== revision);
          for (let saveAttempt = 0; saveAttempt < 2; saveAttempt++) {
            if (checkServerPage) {
              const serverPage = await apiClient.getMathInkPage(accessToken, attemptId, pageIdx);
              if (latestStrokesRef.current.get(pageIdx) !== strokesToSave) {
                setSyncStatus("unsaved");
                return false;
              }
              if (!canSafelyRebaseInkDraft(strokesToSave, serverPage.strokes)) {
                setSyncStatus("conflict");
                setSyncErrorMessage("Trang trên máy chủ đã thay đổi khác bản nháp. Nét viết của bạn vẫn được giữ trên thiết bị.");
                return false;
              }
              revision = serverPage.document_revision;
              revisionRef.current = revision;
              setDocumentRevision(revision);
            }
            if (latestStrokesRef.current.get(pageIdx) !== strokesToSave) {
              setSyncStatus("unsaved");
              return false;
            }
            const clientActionId = generateUuid();
            let localDraftWritten = false;
            try {
              await mathInkStorage.savePageDraft(
                attemptId, pageIdx, strokesToSave, revision, clientActionId, true,
              );
              localDraftWritten = true;
            } catch {
              // A failed browser cache must not prevent an authoritative server save.
            }
            if (latestStrokesRef.current.get(pageIdx) !== strokesToSave) {
              setSyncStatus("unsaved");
              return false;
            }
            try {
              const response = await apiClient.saveMathInkPage(
                accessToken, attemptId, pageIdx,
                {
                  expected_document_revision: revision,
                  client_action_id: clientActionId,
                  strokes: strokesToSave,
                },
              );
              revisionRef.current = response.document_revision;
              recoveredDraftRevisionsRef.current.delete(pageIdx);
              unverifiedPageIndexesRef.current.delete(pageIdx);
              transientPageIndexesRef.current.delete(pageIdx);
              setDocumentRevision(response.document_revision);
              const matched = localDraftWritten
                ? await mathInkStorage.markPageClean(
                  attemptId, pageIdx, response.document_revision, clientActionId,
                ).catch(() => false)
                : true;
              if (!matched || latestStrokesRef.current.get(pageIdx) !== strokesToSave) {
                setSyncStatus("unsaved");
                return false;
              }
              setPagesMap((prev) => {
                const updated = new Map(prev);
                const page = updated.get(pageIdx);
                if (page?.strokes === strokesToSave) {
                  updated.set(pageIdx, { ...page, isDirty: false });
                }
                return updated;
              });
              setAuthExpired(false);
              setSyncStatus("saved");
              return true;
            } catch (err: unknown) {
              if (err instanceof ApiResponseError && err.code === "INK_REVISION_CONFLICT" && saveAttempt === 0) {
                checkServerPage = true;
                continue;
              }
              throw err;
            }
          }
          return false;
        } catch (err: unknown) {
          if (err instanceof ApiResponseError && err.code === "INK_REVISION_CONFLICT") {
            setSyncStatus("conflict");
            setSyncErrorMessage("Máy chủ lại thay đổi khi đang lưu. Bản nháp được giữ lại; hãy thử lại.");
          } else if (err instanceof ApiResponseError) {
            const expired = err.status === 401 || err.code === "INVALID_TOKEN";
            setAuthExpired(expired);
            setSyncStatus("error");
            setSyncErrorMessage(expired
              ? "Phiên đăng nhập đã hết hạn. Giữ trang này mở, đăng nhập lại ở tab khác rồi bấm Thử lại."
              : err.message);
          } else if (err instanceof ApiNetworkError) {
            setSyncStatus("offline");
          } else {
            setSyncStatus("error");
            setSyncErrorMessage("Không thể lưu trang. Vui lòng thử lại.");
          }
          return false;
        }
      };
      const pending = saveQueueRef.current.then(operation);
      saveQueueRef.current = pending.then(() => undefined, () => undefined);
      return pending;
    },
    [attemptId, accessToken, apiClient],
  );

  const handleRetrySync = useCallback(async () => {
    if (!unverifiedPageIndexesRef.current.has(currentPageIndex) || currentPageMemory.isDirty) {
      await flushSavePage(currentPageIndex, currentPageMemory.strokes);
      return;
    }
    const visibleStrokes = latestStrokesRef.current.get(currentPageIndex);
    setSyncStatus("saving");
    try {
      const page = await apiClient.getMathInkPage(accessToken, attemptId, currentPageIndex);
      if (latestStrokesRef.current.get(currentPageIndex) !== visibleStrokes) {
        setSyncStatus("unsaved");
        return;
      }
      revisionRef.current = Math.max(revisionRef.current, page.document_revision);
      setDocumentRevision((revision) => Math.max(revision, page.document_revision));
      latestStrokesRef.current.set(currentPageIndex, page.strokes);
      unverifiedPageIndexesRef.current.delete(currentPageIndex);
      setPagesMap((current) => {
        if (current.get(currentPageIndex)?.isDirty) return current;
        const next = new Map(current);
        next.set(currentPageIndex, { strokes: page.strokes, past: [], future: [], isDirty: false });
        return next;
      });
      setAuthExpired(false);
      setSyncErrorMessage(undefined);
      setSyncStatus("saved");
    } catch (err: unknown) {
      setAuthExpired(err instanceof ApiResponseError && err.status === 401);
      setSyncStatus(err instanceof ApiNetworkError ? "offline" : "error");
      setSyncErrorMessage("Không thể tải nét viết từ máy chủ. Nét viết trên trang hiện tại được giữ nguyên.");
    }
  }, [accessToken, apiClient, attemptId, currentPageIndex, currentPageMemory, flushSavePage]);

  // Persist the page before reviewing it; recognition only suggests step content.
  const handleTriggerOCR = useCallback(async () => {
    const penStrokes = getOcrPenStrokes(currentPageMemory.strokes);
    if (penStrokes.length === 0 || pageOcrReview) return;
    setOcrError(null);
    setIsRecognizingOCR(true);
    try {
      if (currentPageMemory.isDirty) {
        if (saveTimeoutRef.current) {
          clearTimeout(saveTimeoutRef.current);
          saveTimeoutRef.current = null;
        }
        const saved = await ensureLatestInkSaved(true, () =>
          flushSavePage(currentPageIndex, currentPageMemory.strokes),
        );
        if (!saved) {
          setOcrError(authExpired
            ? "Phiên đăng nhập đã hết hạn. Giữ trang này mở, đăng nhập lại ở tab khác rồi thử lại."
            : "Chưa thể lưu nét viết lên máy chủ. Hãy thử lưu lại trước khi trích xuất trang.");
          return;
        }
      }
      const regions = segmentPageInk(penStrokes);
      if (!regions.length) return;
      setPageOcrReview({ pageIndex: currentPageIndex, regions, pageStrokes: currentPageMemory.strokes });
    } catch (error: unknown) {
      setOcrError(error instanceof ApiResponseError && error.status === 401
        ? "Phiên đăng nhập đã hết hạn. Đăng nhập lại để lưu nét viết."
        : "Không thể lưu nét viết lên máy chủ. Hãy kiểm tra kết nối rồi thử lại.");
    } finally {
      setIsRecognizingOCR(false);
    }
  }, [currentPageMemory.strokes, currentPageMemory.isDirty, currentPageIndex,
    flushSavePage, authExpired, pageOcrReview]);

  const handleConfirmStep = useCallback(
    async (stepType: StepKind, latex: string | null, explanation: string, actionId: string) => {
      if (pendingDeleteRef.current) {
        throw new Error("Một thao tác xóa bước chưa nhận được kết quả. Hãy thử xóa lại hoặc tải lại bài giải trước khi thêm bước mới.");
      }
      const updatedAttempt = await apiClient.createMathStep(accessToken, attemptId, {
        expected_attempt_revision: attempt?.current_revision ?? 1,
        client_action_id: actionId,
        step_type: stepType,
        content_latex: latex,
        explanation_text: explanation || null,
      });
      setAttempt(updatedAttempt);
    },
    [attempt?.current_revision, apiClient, accessToken, attemptId],
  );

  const handleSaveVariationTable = useCallback(async (payload: VariationTablePayload, actionId: string) => {
    if (!attempt || !["DRAFT", "IN_PROGRESS"].includes(attempt.status)) {
      throw new Error("Bài giải đã nộp nên không thể sửa bảng.");
    }
    if (pendingDeleteRef.current) {
      throw new Error("Hãy hoàn tất thao tác xóa bước trước khi lưu bảng.");
    }
    const mutation = {
      expected_attempt_revision: attempt.current_revision,
      client_action_id: actionId,
      step_type: "VARIATION_TABLE" as const,
      content_latex: null,
      explanation_text: null,
      artifact: { artifact_type: "VARIATION_TABLE", payload },
    };
    const updated = variationTableEditor?.stepId
      ? await apiClient.updateMathStep(accessToken, attemptId, variationTableEditor.stepId, mutation)
      : await apiClient.createMathStep(accessToken, attemptId, mutation);
    setAttempt(updated);
  }, [attempt, variationTableEditor, apiClient, accessToken, attemptId]);

  const handleDeleteStep = useCallback(async (stepId: string) => {
    if (!attempt || !["DRAFT", "IN_PROGRESS"].includes(attempt.status)) {
      throw new Error("Bài giải này không còn cho phép xóa bước.");
    }
    let revision = attempt.current_revision;
    const previous = pendingDeleteRef.current;
    if (previous && previous.stepId !== stepId) {
      // Resolve an ambiguous previous delete before starting a different one.
      const latest = await apiClient.getMathAttempt(accessToken, attemptId);
      setAttempt(latest);
      pendingDeleteRef.current = null;
      revision = latest.current_revision;
    }
    const pending = pendingDeleteRef.current ?? { stepId, revision, actionId: generateUuid() };
    pendingDeleteRef.current = pending;
    try {
      const updated = await apiClient.deleteMathStep(accessToken, attemptId, stepId, {
        expected_attempt_revision: pending.revision,
        client_action_id: pending.actionId,
      });
      setAttempt(updated);
      pendingDeleteRef.current = null;
    } catch (error: unknown) {
      if (error instanceof ApiNetworkError || (error instanceof ApiResponseError && error.status >= 500)) {
        // A replay with this exact key and revision is safe even if the first response was lost.
        throw error;
      }
      pendingDeleteRef.current = null;
      if (error instanceof ApiResponseError && (error.status === 404 || error.status === 409)) {
        const latest = await apiClient.getMathAttempt(accessToken, attemptId);
        setAttempt(latest);
        if (!latest.steps?.some((step) => step.id === stepId)) return;
      }
      throw error;
    }
  }, [attempt, apiClient, accessToken, attemptId]);

  const executeAIReview = useCallback(async (targetAttempt: SolutionAttemptRead) => {
    if (isReviewing || targetAttempt.status !== "SUBMITTED") return;
    setInstantReviewOpen(false);
    setIsReviewWorkspaceOpen(true);
    setIsReviewing(true);
    setGradingError(null);
    try {
      const result = await apiClient.reviewMathAttempt(accessToken, attemptId);
      if (result.attempt_id !== attemptId || result.step_grades.length !== targetAttempt.steps?.length) {
        throw new Error("Phản hồi AI không khớp bài làm đã nộp.");
      }
      setAIReview(result);
      try {
        window.sessionStorage.setItem(`edums_ai_review_${attemptId}`, JSON.stringify(result));
      } catch {}
    } catch (error: unknown) {
      const code = error instanceof ApiResponseError ? error.code : "";
      const message = code === "GRADING_ANSWER_REQUIRED"
        ? "Câu hỏi này chưa có đáp án được duyệt; hiện chưa thể chấm bằng AI."
        : code === "REAL_AI_PROVIDER_REQUIRED" || code === "AI_CONFIGURATION_ERROR"
          ? "Gemini chưa được cấu hình trên máy chủ. Hãy liên hệ người quản trị."
          : code === "AI_RATE_LIMIT_EXCEEDED"
            ? "Đã hết lượt Gemini hiện tại. Hãy thử lại sau."
            : error instanceof ApiResponseError && error.status === 401
              ? "Phiên đăng nhập đã hết hạn. Hãy đăng nhập lại rồi thử tiếp."
              : error instanceof ApiResponseError ? error.message
                : error instanceof Error ? error.message : "Chưa thể nhận xét bài giải. Hãy thử lại.";
      setGradingError(message);
    } finally {
      setIsReviewing(false);
    }
  }, [isReviewing, apiClient, accessToken, attemptId]);

  const handleAIReview = useCallback(async () => {
    if (!attempt) return;
    await executeAIReview(attempt);
  }, [attempt, executeAIReview]);

  const handleOpenReviewWorkspace = useCallback(() => {
    if (aiReview) {
      setInstantReviewOpen(false);
      setIsReviewWorkspaceOpen(true);
    } else if (attempt) {
      void executeAIReview(attempt);
    }
  }, [aiReview, attempt, executeAIReview]);

  const handleSubmitSolution = useCallback(async (autoReview = true) => {
    if (!attempt || isSubmitting || !["DRAFT", "IN_PROGRESS"].includes(attempt.status)) return;
    setIsSubmitting(true);
    setGradingError(null);
    let successfullySubmitted: SolutionAttemptRead | null = null;
    try {
      if (pendingDeleteRef.current || pageOcrReview) throw new Error("Hãy hoàn tất thao tác sửa bước và xác nhận OCR trước khi nộp.");
      if (!attempt.steps?.length) throw new Error("Hãy xác nhận ít nhất một bước giải trước khi nộp.");
      if (syncStatus === "conflict" || syncStatus === "offline" || authExpired) {
        throw new Error("Nét viết chưa đồng bộ. Hãy lưu lại trước khi nộp bài.");
      }
      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
      await saveQueueRef.current;
      for (const [pageIndex, page] of pagesMap) {
        if (page.isDirty && !await flushSavePage(pageIndex, page.strokes)) {
          throw new Error("Không thể lưu toàn bộ trang viết. Hãy thử lại trước khi nộp.");
        }
      }
      const dirty = await mathInkStorage.listDirtyPages(attemptId).catch(() => []);
      if (dirty.length) throw new Error("Vẫn còn trang viết chưa đồng bộ. Hãy thử lưu lại.");
      const pending = submitActionRef.current ?? { revision: attempt.current_revision, actionId: generateUuid() };
      submitActionRef.current = pending;
      const submitted = await apiClient.submitMathAttempt(accessToken, attemptId, {
        expected_attempt_revision: pending.revision, client_action_id: pending.actionId,
      });
      setAttempt(submitted);
      successfullySubmitted = submitted;
      submitActionRef.current = null;
    } catch (error: unknown) {
      if (error instanceof ApiResponseError && (error.status === 401 || error.status === 409)) {
        const latest = await apiClient.getMathAttempt(accessToken, attemptId).catch(() => null);
        if (latest) {
          setAttempt(latest);
          if (latest.status === "SUBMITTED") {
            submitActionRef.current = null;
            successfullySubmitted = latest;
          }
        }
      }
      if (!successfullySubmitted) {
        setGradingError(error instanceof ApiResponseError ? error.message
          : error instanceof Error ? error.message : "Không thể nộp bài. Hãy thử lại.");
      }
    } finally {
      setIsSubmitting(false);
    }

    if (autoReview && successfullySubmitted && problem?.question_type === "OPEN_RESPONSE") {
      void executeAIReview(successfullySubmitted);
    }
  }, [attempt, isSubmitting, pageOcrReview, syncStatus, authExpired, pagesMap,
    flushSavePage, attemptId, apiClient, accessToken, problem?.question_type, executeAIReview]);
  // Keep stroke persistence separate from history updates. Undo/redo must not
  // append another history entry or erase the redo stack.
  const queueInkSave = useCallback((pageIndex: number, newStrokes: InkStroke[]) => {
    locallyEditedPagesRef.current.add(pageIndex);
    latestStrokesRef.current.set(pageIndex, newStrokes);
    setSyncStatus("unsaved");

    // Save draft immediately to IndexedDB
    void mathInkStorage.savePageDraft(
      attemptId,
      pageIndex,
      newStrokes,
      recoveredDraftRevisionsRef.current.get(pageIndex) ?? documentRevision,
      generateUuid(),
      true,
    ).catch(() => {
      setSyncStatus("error");
      setSyncErrorMessage("Không lưu được bản nháp trên thiết bị. Giữ trang này mở và thử lưu lên máy chủ.");
    });

    // Debounce network save (1.5s)
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveTimeoutRef.current = setTimeout(() => {
      flushSavePage(pageIndex, newStrokes);
    }, 1500);
  }, [attemptId, documentRevision, flushSavePage]);

  // 3. Handle strokes update with Undo stack & autosave debounce
  const handleStrokesChange = useCallback(
    (newStrokes: InkStroke[]) => {
      queueInkSave(currentPageIndex, newStrokes);
      setPagesMap((prev) => {
        const updated = new Map(prev);
        const current = updated.get(currentPageIndex) ?? {
          strokes: [],
          past: [],
          future: [],
          isDirty: false,
        };

        const newPast = [...current.past, current.strokes];
        if (newPast.length > 30) newPast.shift(); // Bound history

        updated.set(currentPageIndex, {
          strokes: newStrokes,
          past: newPast,
          future: [],
          isDirty: true,
        });
        return updated;
      });
    },
    [currentPageIndex, queueInkSave],
  );

  // 4. Undo / Redo
  const handleUndo = useCallback(() => {
    if (currentPageMemory.past.length === 0) return;

    const newPast = [...currentPageMemory.past];
    const previousStrokes = newPast.pop()!;
    const newFuture = [currentPageMemory.strokes, ...currentPageMemory.future];

    setPagesMap((prev) => {
      const updated = new Map(prev);
      updated.set(currentPageIndex, {
        strokes: previousStrokes,
        past: newPast,
        future: newFuture,
        isDirty: true,
      });
      return updated;
    });

    queueInkSave(currentPageIndex, previousStrokes);
  }, [currentPageMemory, currentPageIndex, queueInkSave]);

  const handleRedo = useCallback(() => {
    if (currentPageMemory.future.length === 0) return;

    const newFuture = [...currentPageMemory.future];
    const nextStrokes = newFuture.shift()!;
    const newPast = [...currentPageMemory.past, currentPageMemory.strokes];

    setPagesMap((prev) => {
      const updated = new Map(prev);
      updated.set(currentPageIndex, {
        strokes: nextStrokes,
        past: newPast,
        future: newFuture,
        isDirty: true,
      });
      return updated;
    });

    queueInkSave(currentPageIndex, nextStrokes);
  }, [currentPageMemory, currentPageIndex, queueInkSave]);

  const handleClearPage = useCallback(() => {
    if (currentPageMemory.strokes.length === 0) return;
    if (window.confirm("Bạn có chắc chắn muốn xóa toàn bộ nét vẽ trên trang này không?")) {
      handleStrokesChange([]);
    }
  }, [currentPageMemory.strokes, handleStrokesChange]);

  // 5. Switching Pages
  const handleSelectPage = useCallback(
    async (targetIndex: number) => {
      if (targetIndex === currentPageIndex || targetIndex < 0 || targetIndex >= pageCount) {
        return;
      }

      // Do not navigate away from ink that the server has not accepted.
      const pageStrokesAtStart = latestStrokesRef.current.get(currentPageIndex);
      if (currentPageMemory.isDirty) {
        if (saveTimeoutRef.current) {
          clearTimeout(saveTimeoutRef.current);
          saveTimeoutRef.current = null;
        }
        if (!await flushSavePage(currentPageIndex, currentPageMemory.strokes)) return;
      }

      // Load target page data if not present in memory
      if (!pagesMap.has(targetIndex)) {
        // Check IndexedDB draft first
        const offlineDraft = await mathInkStorage.getPageDraft(attemptId, targetIndex).catch(() => null);
        if (offlineDraft?.isDirty) {
          recoveredDraftRevisionsRef.current.set(targetIndex, offlineDraft.documentRevision);
          latestStrokesRef.current.set(targetIndex, offlineDraft.strokes);
          setSyncStatus("error");
          setSyncErrorMessage("Đã khôi phục bản nháp chưa đồng bộ. Bấm Thử lại để lưu lên máy chủ.");
          setPagesMap((prev) => {
            const updated = new Map(prev);
            updated.set(targetIndex, {
              strokes: offlineDraft.strokes,
              past: [],
              future: [],
              isDirty: offlineDraft.isDirty,
            });
            return updated;
          });
        } else {
          // Clean browser cache can be stale; load the authoritative server page.
          try {
            const pageData = await apiClient.getMathInkPage(
              accessToken,
              attemptId,
              targetIndex,
            );
            latestStrokesRef.current.set(targetIndex, pageData.strokes);
            setPagesMap((prev) => {
              const updated = new Map(prev);
              updated.set(targetIndex, {
                strokes: pageData.strokes,
                past: [],
                future: [],
                isDirty: false,
              });
              return updated;
            });
          } catch (err: unknown) {
            setSyncStatus(err instanceof ApiNetworkError ? "offline" : "error");
            setSyncErrorMessage("Không thể tải trang từ máy chủ. Trang hiện tại và nét vẽ được giữ nguyên.");
            return;
          }
        }
      }

      if (latestStrokesRef.current.get(currentPageIndex) !== pageStrokesAtStart) return;
      setCurrentPageIndex(targetIndex);
    },
    [
      currentPageIndex,
      pageCount,
      currentPageMemory,
      flushSavePage,
      pagesMap,
      attemptId,
      accessToken,
      apiClient,
    ],
  );

  const handleAddPage = useCallback(async () => {
    if (pageCount >= MAX_PAGES) return;
    const pageStrokesAtStart = latestStrokesRef.current.get(currentPageIndex);
    if (currentPageMemory.isDirty) {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
        saveTimeoutRef.current = null;
      }
      if (!await flushSavePage(currentPageIndex, currentPageMemory.strokes)) return;
    }
    if (latestStrokesRef.current.get(currentPageIndex) !== pageStrokesAtStart) return;
    const newIndex = pageCount;
    transientPageIndexesRef.current.add(newIndex);
    setPageCount((c) => c + 1);
    latestStrokesRef.current.set(newIndex, []);
    setPagesMap((prev) => {
      const updated = new Map(prev);
      updated.set(newIndex, {
        strokes: [],
        past: [],
        future: [],
        isDirty: false,
      });
      return updated;
    });
    setCurrentPageIndex(newIndex);
  }, [pageCount, currentPageIndex, currentPageMemory, flushSavePage]);

  // The backend has no delete/reindex API. Only a new, empty trailing page can
  // be removed locally; renumbering persisted pages would corrupt server ink.
  const canDeleteCurrentPage = pageCount > 1
    && currentPageIndex === pageCount - 1
    && transientPageIndexesRef.current.has(currentPageIndex)
    && currentPageMemory.strokes.length === 0
    && !currentPageMemory.isDirty;
  const handleDeleteCurrentPage = useCallback(() => {
    if (!canDeleteCurrentPage) return;
    transientPageIndexesRef.current.delete(currentPageIndex);
    latestStrokesRef.current.delete(currentPageIndex);
    setPagesMap((prev) => {
      const updated = new Map(prev);
      updated.delete(currentPageIndex);
      return updated;
    });
    setPageCount((count) => count - 1);
    setCurrentPageIndex(currentPageIndex - 1);
  }, [canDeleteCurrentPage, currentPageIndex]);

  // Exporting a local copy is a deliberate escape hatch for true divergent edits.
  const handleExportDraft = useCallback(() => {
    const payload = {
      attempt_id: attemptId,
      page_index: currentPageIndex,
      exported_at: new Date().toISOString(),
      strokes: currentPageMemory.strokes,
    };
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload)], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `edums-ink-${attemptId}-page-${currentPageIndex + 1}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  }, [attemptId, currentPageIndex, currentPageMemory.strokes]);

  // 6. Conflict Resolution
  const handleResolveConflict = useCallback(async () => {
    const visibleDraft = latestStrokesRef.current.get(currentPageIndex);
    if (!window.confirm("Thao tác này BỎ bản nháp hiện tại và tải trang từ máy chủ. Hãy bấm Sao lưu bản nháp trước khi tiếp tục. Bạn có chắc chắn không?")) return;
    try {
      const pageData = await apiClient.getMathInkPage(
        accessToken,
        attemptId,
        currentPageIndex,
      );

      if (latestStrokesRef.current.get(currentPageIndex) !== visibleDraft) {
        setSyncErrorMessage("Nét viết đã thay đổi trong lúc tải. Bản nháp vẫn được giữ.");
        return;
      }
      await mathInkStorage.savePageDraft(
        attemptId, currentPageIndex, pageData.strokes, pageData.document_revision, generateUuid(), false,
      );
      revisionRef.current = pageData.document_revision;
      setDocumentRevision(pageData.document_revision);
      recoveredDraftRevisionsRef.current.delete(currentPageIndex);
      latestStrokesRef.current.set(currentPageIndex, pageData.strokes);
      setPagesMap((prev) => {
        const updated = new Map(prev);
        updated.set(currentPageIndex, {
          strokes: pageData.strokes,
          past: [],
          future: [],
          isDirty: false,
        });
        return updated;
      });

      setSyncStatus("saved");
      setSyncErrorMessage(undefined);
    } catch {
      setSyncErrorMessage("Không thể tải bản mới nhất từ máy chủ.");
    }
  }, [apiClient, accessToken, attemptId, currentPageIndex]);

  // 7. Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement
        || e.target instanceof HTMLSelectElement
        || (e.target instanceof HTMLElement && e.target.closest('[role="dialog"]'))) {
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        if (e.shiftKey) {
          e.preventDefault();
          handleRedo();
        } else {
          e.preventDefault();
          handleUndo();
        }
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "y") {
        e.preventDefault();
        handleRedo();
      } else if (e.key.toLowerCase() === "p") {
        setCurrentTool("pen");
      } else if (e.key.toLowerCase() === "h") {
        setCurrentTool("highlighter");
      } else if (e.key.toLowerCase() === "e") {
        setCurrentTool("eraser");
      } else if (e.key === "[") {
        if (currentPageIndex > 0) handleSelectPage(currentPageIndex - 1);
      } else if (e.key === "]") {
        if (currentPageIndex < pageCount - 1) handleSelectPage(currentPageIndex + 1);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleUndo, handleRedo, handleSelectPage, currentPageIndex, pageCount]);

  return (
    <div className={styles.workspaceContainer}>
      {/* Top Header Bar */}
      <header className={styles.topHeader}>
        <div className={styles.headerLeft}>
          <h1 className={styles.headerTitle}>Không gian giải bài Toán</h1>
          <SyncStatusBadge
            status={syncStatus}
            errorMessage={syncErrorMessage}
            authExpired={authExpired}
            onRetry={handleRetrySync}
            onResolveConflict={handleResolveConflict}
            onExportDraft={handleExportDraft}
          />
          {attempt && !problem?.is_read_only ? (
            <button
              type="button"
              className={styles.headerGradeButton}
              onClick={() => {
                if (attempt.status === "SUBMITTED") {
                  if (aiReview) {
                    handleOpenReviewWorkspace();
                  } else {
                    void handleAIReview();
                  }
                } else {
                  void handleSubmitSolution();
                }
              }}
              disabled={isSubmitting || isReviewing || (attempt.status !== "SUBMITTED" && !attempt.steps?.length)}
              title={attempt.status === "SUBMITTED" ? "Chấm bài bằng AI" : "Nộp bài và chấm tự động bằng AI"}
            >
              <Sparkles size={14} />
              <span>
                {isSubmitting
                  ? "Đang nộp bài..."
                  : isReviewing
                    ? "Đang chấm bằng Gemini..."
                    : attempt.status === "SUBMITTED"
                      ? aiReview
                        ? "Xem lại điểm AI"
                        : "Chấm bài bằng AI"
                      : "Nộp & Chấm bài"}
              </span>
            </button>
          ) : null}
        </div>

        <PageNavigator
          currentPageIndex={currentPageIndex}
          pageCount={pageCount}
          onSelectPage={handleSelectPage}
          onAddPage={handleAddPage}
          onDeleteCurrentPage={handleDeleteCurrentPage}
          canDeleteCurrentPage={canDeleteCurrentPage}
          isReadOnly={problem?.is_read_only}
        />
      </header>

      {/* PR3-C: Unfinished Batch Recovery Banner */}
      {pendingBatch ? (
        <div className={styles.batchRecoveryBanner} role="alert">
          <div className={styles.batchRecoveryInfo}>
            <strong>Phát hiện đợt lưu bước giải chưa hoàn tất</strong>
            <p>
              {pendingBatch.entries.filter((e) => e.state === "COMMITTED").length}/{pendingBatch.entries.length} bước đã được xác nhận trên máy chủ.
              {pendingBatch.message ? ` (Trạng thái: ${pendingBatch.message})` : ""}
              {recoveryMessage ? ` — ${recoveryMessage}` : ""}
            </p>
          </div>
          <div className={styles.batchRecoveryActions}>
            <button
              type="button"
              className={styles.buttonPrimary}
              onClick={() => void handleResumePendingBatch()}
              disabled={batchResuming}
            >
              {batchResuming ? "Đang xử lý..." : "Lưu tiếp (Resume)"}
            </button>
            {pendingBatch.entries.some((e) => e.state === "REJECTED") &&
            !pendingBatch.entries.some((e) => e.state === "SENDING" || e.state === "UNKNOWN" || e.errorCode === "ACTION_KEY_REUSED" || e.errorCode === "CONTENT_MISMATCH") ? (
              <button
                type="button"
                className={styles.buttonSecondary}
                onClick={() => void handleAbandonPendingBatch()}
                disabled={batchResuming}
              >
                Hủy đợt lưu
              </button>
            ) : null}
          </div>
        </div>
      ) : null}

      {/* Floating or Top Toolbar */}
      <WorkspaceToolbar
        currentTool={currentTool}
        onSelectTool={setCurrentTool}
        penColor={penColor}
        onSelectPenColor={setPenColor}
        penWidth={penWidth}
        onSelectPenWidth={setPenWidth}
        highlighterWidth={highlighterWidth}
        onSelectHighlighterWidth={setHighlighterWidth}
        paperGrid={paperGrid}
        onSelectPaperGrid={setPaperGrid}
        canUndo={!problem?.is_read_only && currentPageMemory.past.length > 0}
        onUndo={handleUndo}
        canRedo={!problem?.is_read_only && currentPageMemory.future.length > 0}
        onRedo={handleRedo}
        onClearPage={handleClearPage}
        zoomLevel={zoomLevel}
        onZoomIn={() => setZoomLevel((z) => Math.min(2.0, z + 0.1))}
        onZoomOut={() => setZoomLevel((z) => Math.max(0.6, z - 0.1))}
        onResetZoom={() => setZoomLevel(1.0)}
        onTriggerOCR={paperMode || attempt?.status === "SUBMITTED" || problem?.is_read_only ? undefined : handleTriggerOCR}
        onOpenVariationTable={attempt && ["DRAFT", "IN_PROGRESS"].includes(attempt.status) && !pageOcrReview && !problem?.is_read_only
          ? () => setVariationTableEditor({}) : undefined}
        onTogglePaper={() => setPaperMode((current) => !current)}
        paperMode={paperMode}
        isRecognizingOCR={isRecognizingOCR}
        strokeCount={getOcrPenStrokes(currentPageMemory.strokes).length}
        isReadOnly={problem?.is_read_only}
        onOpenGraph={() => { setGraphSelection({ page: currentPageIndex, strokes: [] }); setGraphOpen(true); }}
      />

      {ocrError && !pageOcrReview ? (
        <div className={styles.ocrErrorBanner} role="alert">
          <span>{ocrError}</span>
          <button type="button" onClick={() => setOcrError(null)}>
            Đóng
          </button>
        </div>
      ) : null}

      {/* Main 2-Column Split Workspace */}
      <main className={styles.mainLayout}>
        {/* Left Column: Problem (35%) */}
        <ProblemPane
          problem={problem}
          attempt={attempt}
          isCollapsed={isProblemPaneCollapsed}
          onToggleCollapse={() => setIsProblemPaneCollapsed((c) => !c)}
          onVisualizeFormula={(formula) => { setGraphSelection({ page: currentPageIndex, strokes: [], formula }); setGraphOpen(true); }}
          onDeleteStep={handleDeleteStep}
          onEditVariationTable={(stepId, initial) => setVariationTableEditor({ stepId, initial })}
          onSubmitSolution={handleSubmitSolution}
          onAIReview={handleAIReview}
          onOpenReviewWorkspace={handleOpenReviewWorkspace}
          aiReview={aiReview}
          aiReviewAvailability={aiReviewAvailability}
          gradingError={gradingError}
          isSubmitting={isSubmitting}
          isReviewing={isReviewing}
        />

        {/* Right Column: A4 Writing Canvas (65% or expanded) */}
        <section
          className={`${styles.canvasPane} ${isProblemPaneCollapsed ? styles.canvasPaneExpanded : ""}`}
          aria-label="Không gian giấy A4 viết tay"
        >
          {paperMode ? (
            <PaperUploadPanel
              attemptId={attemptId}
              accessToken={accessToken}
              apiClient={apiClient}
              isReadOnly={Boolean(problem?.is_read_only || attempt?.status === "SUBMITTED")}
              onConfirmStep={(content, actionId) =>
                handleConfirmStep("EXPLANATION", content.latex, content.explanation, actionId)
              }
              onSubmitSolution={handleSubmitSolution}
              isSubmitting={isSubmitting}
              isReviewing={isReviewing}
              hasConfirmedSteps={Boolean(attempt?.steps && attempt.steps.length > 0)}
            />
          ) : (
            <MathCanvas
              strokes={currentPageMemory.strokes}
              onStrokesChange={handleStrokesChange}
              currentTool={currentTool}
              penColor={penColor}
              penWidth={penWidth}
              highlighterWidth={highlighterWidth}
              paperGrid={paperGrid}
              zoomLevel={zoomLevel}
              isReadOnly={attempt?.status === "SUBMITTED" || problem?.is_read_only}
              selectedStrokeIds={
                graphSelection.page === currentPageIndex
                  ? graphSelection.strokes.map((stroke) => stroke.id)
                  : []
              }
              onLassoSelect={(strokes) => {
                setGraphSelection({ page: currentPageIndex, strokes });
                setGraphOpen(true);
              }}
            />
          )}
        </section>
      </main>

      {variationTableEditor ? (
        <VariationTableModal initial={variationTableEditor.initial} onSave={handleSaveVariationTable}
          onClose={() => setVariationTableEditor(null)} />
      ) : null}

      {graphOpen ? <MathCanvasPanel
        key={`${attemptId}:${currentPageIndex}:${graphSelection.formula ?? ""}:${graphSelection.page === currentPageIndex ? graphSelection.strokes.map((s) => s.id).join(",") : ""}`}
        attemptId={attemptId} pageIndex={currentPageIndex}
        selectedStrokes={graphSelection.page === currentPageIndex ? graphSelection.strokes : []}
        initialFormula={graphSelection.page === currentPageIndex ? graphSelection.formula : undefined}
        ensureInkSaved={async () => {
          if (authExpired || syncStatus === "conflict" || syncStatus === "offline") throw new Error("Hãy đồng bộ nét viết trước khi lưu đồ thị.");
          await saveQueueRef.current;
          if (currentPageMemory.isDirty) {
            const saved = await flushSavePage(currentPageIndex, latestStrokesRef.current.get(currentPageIndex) ?? currentPageMemory.strokes);
            if (!saved) throw new Error("Nét viết chưa được lưu lên máy chủ. Hãy đồng bộ rồi thử lại.");
          }
          await saveQueueRef.current;
        }}
        onClose={() => setGraphOpen(false)} /> : null}

      {pageOcrReview ? (
        <PageOcrReviewModal
          pageIndex={pageOcrReview.pageIndex}
          regions={pageOcrReview.regions}
          pageStrokes={pageOcrReview.pageStrokes}
          onClose={() => {
            setPageOcrReview(null);
            void checkPendingBatch();
          }}
          onConfirmStep={handleConfirmStep}
          attemptId={attemptId}
          accessToken={accessToken}
          apiClient={apiClient}
          onBatchComplete={(fresh) => {
            setAttempt(fresh);
            setPendingBatch(null);
          }}
          onBatchUpdate={(journal) => {
            setPendingBatch(journal);
          }}
        />
      ) : null}

      {isReviewWorkspaceOpen ? (
        <AIReviewWorkspace
          attemptId={attemptId}
          accessToken={accessToken}
          apiClient={apiClient}
          problem={problem}
          attempt={attempt}
          aiReview={aiReview}
          isRequesting={isReviewing}
          errorMessage={gradingError}
          pages={pagesRecord}
          currentPageIndex={currentPageIndex}
          instantOpen={instantReviewOpen}
          onRetryReview={() => void handleAIReview()}
          onClose={() => setIsReviewWorkspaceOpen(false)}
        />
      ) : null}
    </div>
  );
}
