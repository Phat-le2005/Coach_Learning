"use client";

import React, { useState, useEffect, useRef, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Sparkles, Smartphone } from "lucide-react";
import { ApiResponseError, ApiNetworkError } from "@/lib/api/client";
import { getCsrfToken } from "@/lib/auth/browser";
import { createBrowserMathApiClient } from "@/lib/api/browser-math";
import type { ClassroomNavData } from "@/lib/classroom-assignments/launch";
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
import { canSafelyRebaseInkDraft, restoreDirtyPageDrafts } from "./utils/draft-recovery";
import { getExamMissingQuestions } from "./utils/exam-submission";
import { WorkspaceToolbar } from "./components/WorkspaceToolbar";
import { PaperUploadPanel } from "./components/PaperUploadPanel";
import { PageNavigator } from "./components/PageNavigator";
import { ProblemPane } from "./components/ProblemPane";
import { MathCanvas } from "./components/MathCanvas";
import { SyncStatusBadge } from "./components/SyncStatusBadge";
import { PageOcrV2ReviewModal } from "./components/PageOcrV2ReviewModal";
import { VariationTableModal } from "./components/VariationTableModal";
import { AIReviewWorkspace } from "./components/ai-review/AIReviewWorkspace";
import { STEP_KINDS, type AIReviewRead, type AIReviewAvailabilityRead, type StepKind, type VariationTablePayload } from "@/lib/api/contracts";
import { SequentialBatchManager, type BatchJournal } from "./utils/batch-manager";
import { IndexedDbBatchJournal, BrowserBatchLock } from "./utils/batch-journal";
import { createBatchApi } from "./utils/ocr-batch-adapter";
import { withSafeBatchSubmission } from "./utils/solution-submit-guard";
import styles from "./MathWorkspace.module.css";
import { useLiveInk } from "./live/useLiveInk";
import { DeviceConnection } from "./live/DeviceConnection";
import type { LiveSnapshot } from "./live/protocol";
import { deviceRequest, type DevicePairing } from "./live/device-client";

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
  initialPageIndex?: number;
  initialLiveRequested?: boolean;
  initialWritingMode?: boolean;
  classroomNav?: ClassroomNavData | null;
}

export function MathWorkspace({
  attemptId,
  initialProblem = null,
  initialAttempt = null,
  initialDocument = null,
  initialPage = null,
  initialPageIndex = 0,
  initialLiveRequested = false,
  initialWritingMode = false,
  classroomNav = null,
}: MathWorkspaceProps) {
  // The BFF reads the HttpOnly cookie. No bearer token is passed to this client component.
  const accessToken = "";
  // Problem & Attempt
  const [problem, setProblem] = useState<ProblemRead | null>(initialProblem);
  const [attempt, setAttempt] = useState<SolutionAttemptRead | null>(initialAttempt);

  // Layout & View
  const [isProblemPaneCollapsed, setIsProblemPaneCollapsed] = useState(initialWritingMode);
  const [writingMode, setWritingMode] = useState(initialWritingMode);
  const [liveEnabled, setLiveEnabled] = useState(false);
  const [pairingOpen, setPairingOpen] = useState(false);
  const [liveStarting, setLiveStarting] = useState(false);
  const [draftRecoveryReady, setDraftRecoveryReady] = useState(false);
  const [canvasDrawing, setCanvasDrawing] = useState(false);
  const [devicePairing, setDevicePairing] = useState<DevicePairing | null>(null);
  const writingLayoutRef = useRef({collapsed: false, zoom: 1, paper: false});
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const [graphOpen, setGraphOpen] = useState(false);
  const [graphSelection, setGraphSelection] = useState<{ page: number; strokes: InkStroke[]; formula?: string }>({ page: 0, strokes: [] });

  const isClassroomExam = classroomNav?.deliveryMode === "EXAM";
  const [examSubmitted, setExamSubmitted] = useState(
    classroomNav?.assignmentStatus === "SUBMITTED" || classroomNav?.assignmentStatus === "GRADED"
  );
  const [examSubmitOpen, setExamSubmitOpen] = useState(false);
  const [isSubmittingExam, setIsSubmittingExam] = useState(false);
  const [examSubmitError, setExamSubmitError] = useState<string | null>(null);

  const router = useRouter();
  const [switchingQuestion, setSwitchingQuestion] = useState(false);

  const handleSwitchQuestion = useCallback(
    async (targetIndex: number) => {
      if (!classroomNav || targetIndex === classroomNav.currentIndex || switchingQuestion) return;
      const targetQ = classroomNav.questions[targetIndex];
      if (targetQ?.attemptId) {
        router.push(`/student/attempts/${targetQ.attemptId}`);
        return;
      }

      setSwitchingQuestion(true);
      try {
        const csrfToken = await getCsrfToken().catch(() => "");
        const res = await fetch(
          `/api/student/assignments/${classroomNav.studentAssignmentId}/launch`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
            },
            body: JSON.stringify({ index: targetIndex }),
          }
        );
        if (res.ok) {
          const data = await res.json();
          if (data.attemptId) {
            router.push(`/student/attempts/${data.attemptId}`);
            return;
          }
        }
      } catch {
        // Fallback
      } finally {
        setSwitchingQuestion(false);
      }
    },
    [classroomNav, switchingQuestion, router]
  );



  const nextProblemLabel = useMemo(() => {
    if (classroomNav) {
      if (classroomNav.currentIndex < classroomNav.totalQuestions - 1) {
        return `Làm câu tiếp theo (Câu ${classroomNav.currentIndex + 2}) →`;
      }
      return "Hoàn thành bài tập lớp →";
    }
    return "Luyện tập bài tiếp theo →";
  }, [classroomNav]);

  const [advancingPractice, setAdvancingPractice] = useState(false);

  const handleNextProblem = useCallback(async () => {
    if (switchingQuestion || advancingPractice) return;

    if (classroomNav) {
      if (classroomNav.currentIndex < classroomNav.totalQuestions - 1) {
        void handleSwitchQuestion(classroomNav.currentIndex + 1);
      } else {
        router.push(`/student/assignments/${classroomNav.studentAssignmentId}`);
      }
      return;
    }

    // Practice mode
    setAdvancingPractice(true);
    try {
      const csrfToken = await getCsrfToken().catch(() => "");
      const res = await fetch("/api/student/practice/next", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
        },
        body: JSON.stringify({
          subjectId: problem?.subject_id,
          practiceSessionId: attempt?.practice_session_id,
        }),
      });
      if (res.ok) {
        const data = await res.json();
        if (data.attemptId) {
          router.push(`/student/attempts/${data.attemptId}`);
          return;
        }
      }
      router.push("/student/practice");
    } catch {
      router.push("/student/practice");
    } finally {
      setAdvancingPractice(false);
    }
  }, [classroomNav, switchingQuestion, advancingPractice, handleSwitchQuestion, router, problem?.subject_id, attempt?.practice_session_id]);

  // Document & Multi-page
  const [documentRevision, setDocumentRevision] = useState(
    initialDocument?.document_revision ?? 0,
  );
  const [currentPageIndex, setCurrentPageIndex] = useState(initialPageIndex);
  const [pageCount, setPageCount] = useState(
    Math.max(1, ...(initialDocument?.pages.map((page) => page.page_index + 1) ?? [])),
  );

  // Pages state memory
  const [pagesMap, setPagesMap] = useState<Map<number, PageMemory>>(() => {
    const map = new Map<number, PageMemory>();
    const initialStrokes = initialPage?.strokes ?? [];
    map.set(initialPageIndex, {
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
    pageIndex: number; pageStrokes: InkStroke[]; sourceRevision: number;
  } | null>(null);
  const [ocrError, setOcrError] = useState<string | null>(null);
  const [variationTableEditor, setVariationTableEditor] = useState<{ stepId?: string; initial?: VariationTablePayload } | null>(null);

  // PR3-C: Batch recovery state
  const [pendingBatch, setPendingBatch] = useState<BatchJournal | null>(null);
  const [batchJournalLoadError, setBatchJournalLoadError] = useState<string | null>(null);
  const [batchJournalReady, setBatchJournalReady] = useState(false);
  const [batchResuming, setBatchResuming] = useState(false);
  const [recoveryMessage, setRecoveryMessage] = useState<string | null>(null);

  // A final score must come from the server, never from editable browser storage.
  const [aiReview, setAIReview] = useState<AIReviewRead | null>(null);
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
    new Map([[initialPageIndex, initialPage?.strokes ?? []]]),
  );
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const pendingDeleteRef = useRef<{ stepId: string; revision: number; actionId: string } | null>(null);
  const locallyEditedPagesRef = useRef(new Set<number>());
  const recoveredDraftRevisionsRef = useRef(new Map<number, number>());
  const transientPageIndexesRef = useRef(new Set<number>());
  const unverifiedPageIndexesRef = useRef(new Set<number>(initialPage ? [] : [initialPageIndex]));

  const apiClient = useRef(createBrowserMathApiClient()).current;
  const receiveLiveSnapshot = useCallback((snapshot: LiveSnapshot, pending: boolean) => {
    revisionRef.current = Math.max(revisionRef.current, snapshot.document_revision);
    setDocumentRevision(revisionRef.current);
    latestStrokesRef.current.set(snapshot.page_index, snapshot.strokes);
    unverifiedPageIndexesRef.current.delete(snapshot.page_index);
    setPagesMap(current => {
      const next = new Map(current);
      // Live undo history is operation-based; never restore a remote page snapshot.
      next.set(snapshot.page_index, { strokes: snapshot.strokes, past: [], future: [], isDirty: pending });
      return next;
    });
    setPageCount(count => Math.max(count, snapshot.page_index + 1));
  }, []);
  const live = useLiveInk({ attemptId, pageIndex: currentPageIndex, enabled: liveEnabled, onSnapshot: receiveLiveSnapshot,
    onPageAvailable: index => setPageCount(count => Math.max(count, index + 1)) });
  const liveRef = useRef(live); liveRef.current = live;
  const liveEnabledRef = useRef(liveEnabled); liveEnabledRef.current = liveEnabled;
  useEffect(() => {
    if (!liveEnabled) return;
    const url = new URL(window.location.href);
    url.searchParams.set("page", String(currentPageIndex));
    url.searchParams.set("writing", writingMode ? "1" : "0");
    window.history.replaceState(null, "", url);
  }, [currentPageIndex, liveEnabled, writingMode]);
  useEffect(() => {
    if (!liveEnabled) return;
    setSyncStatus(live.pendingCount ? "unsaved" : live.drafts.length ? "saving" : live.status === "connected" ? "saved"
      : live.status === "offline" ? "offline" : live.status === "error" ? "error" : "saving");
    setSyncErrorMessage(live.error || undefined);
  }, [liveEnabled, live.pendingCount, live.status, live.error, live.drafts.length]);

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
    void apiClient.getMathInkPage(accessToken, attemptId, initialPageIndex).then((page) => {
      if (!active) return;
      revisionRef.current = Math.max(revisionRef.current, page.document_revision);
      setDocumentRevision((revision) => Math.max(revision, page.document_revision));
      if (liveEnabledRef.current || locallyEditedPagesRef.current.has(initialPageIndex) || recoveredDraftRevisionsRef.current.has(initialPageIndex)) return;
      setPagesMap((current) => {
        if (current.get(initialPageIndex)?.isDirty) return current;
        const next = new Map(current);
        next.set(initialPageIndex, { strokes: page.strokes, past: [], future: [], isDirty: false });
        latestStrokesRef.current.set(initialPageIndex, page.strokes);
        unverifiedPageIndexesRef.current.delete(initialPageIndex);
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
  }, [attemptId, accessToken, apiClient, initialPage, initialPageIndex]);

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
    }).finally(() => { if (active) setDraftRecoveryReady(true); });
    return () => { active = false; };
  }, [attemptId]);

  // PR3-C: Recover unfinished batch journal from previous tab session or reload (F5 recovery)
  const checkPendingBatch = useCallback(async () => {
    if (typeof window === "undefined" || !attemptId) return;
    try {
      const store = new IndexedDbBatchJournal();
      const journal = await store.load(attemptId);
      setBatchJournalLoadError(null);
      if (journal && journal.state !== "COMPLETE" && journal.state !== "ABANDONED") {
        setPendingBatch(journal);
      } else {
        setPendingBatch(null);
        setRecoveryMessage(null);
      }
    } catch (err: unknown) {
      const code = err instanceof Error ? err.message : "BATCH_JOURNAL_READ_FAILED";
      setPendingBatch(null);
      setBatchJournalLoadError(code);
      setRecoveryMessage(`Lỗi đọc dữ liệu đợt lưu từ bộ nhớ trình duyệt (${code}). Đã tạm khóa tạo bước mới để bảo toàn dữ liệu máy chủ.`);
    } finally { setBatchJournalReady(true); }
  }, [attemptId]);

  useEffect(() => {
    void checkPendingBatch();
  }, [checkPendingBatch]);

  const handleSyncAuthoritativeAttempt = async () => {
    if (batchResuming || !attemptId || !apiClient) return;
    setBatchResuming(true);
    try {
      const fresh = await apiClient.getMathAttempt(accessToken, attemptId);
      setAttempt(fresh);
      await checkPendingBatch();
    } catch (err: unknown) {
      setRecoveryMessage(err instanceof Error ? err.message : "Không thể tải lại trạng thái bài giải từ máy chủ.");
    } finally {
      setBatchResuming(false);
    }
  };

  const handleResumePendingBatch = async () => {
    if (batchResuming || !attemptId || !apiClient) return;
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
        setBatchJournalLoadError(null);
        setRecoveryMessage(null);
      } else if (res.status === "PAUSED") {
        setPendingBatch(res.journal);
        const committed = res.journal.entries.filter((e) => e.state === "COMMITTED").length;
        if (committed > 0) {
          try {
            const fresh = await apiClient.getMathAttempt(accessToken, attemptId);
            setAttempt(fresh);
          } catch {
            // Keep current attempt state if offline
          }
        }
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
    if (batchResuming || !attemptId || !apiClient) return;
    if (!window.confirm("Hủy bỏ đợt lưu các bước lỗi này? Các bước đã lưu trên máy chủ vẫn được giữ nguyên.")) return;
    setBatchResuming(true);
    try {
      const batchApi = createBatchApi(apiClient, accessToken);
      const store = new IndexedDbBatchJournal();
      const lock = new BrowserBatchLock();
      const manager = new SequentialBatchManager(batchApi, store, lock);
      const abandoned = await manager.abandonRejected(attemptId);
      if (!abandoned) {
        setRecoveryMessage("Không thể lấy quyền thao tác độc quyền (Web Lock). Tab khác đang thao tác.");
        return;
      }
      const freshAttempt = await apiClient.getMathAttempt(accessToken, attemptId);
      setAttempt(freshAttempt);
      setPendingBatch(null);
      setBatchJournalLoadError(null);
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
      if (liveEnabledRef.current) return liveRef.current.flush();
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

  const startLive = useCallback(async (showPairing = true) => {
    if (liveEnabledRef.current) { setPairingOpen(showPairing); return; }
    if (!draftRecoveryReady || liveStarting || canvasDrawing) return;
    setLiveStarting(true);
    try {
      if (saveTimeoutRef.current) { clearTimeout(saveTimeoutRef.current); saveTimeoutRef.current = null; }
      // Barrier: no legacy PUT may still be in flight when live snapshots begin.
      await saveQueueRef.current;
      for (const [idx, page] of pagesMap) {
        if (page.isDirty && !await flushSavePage(idx, page.strokes)) return;
      }
      if (unverifiedPageIndexesRef.current.has(currentPageIndex)) {
        const page = await apiClient.getMathInkPage(accessToken, attemptId, currentPageIndex);
        receiveLiveSnapshot(page, false);
      }
      setLiveEnabled(true); setPairingOpen(showPairing);
      const url = new URL(window.location.href); url.searchParams.set("live", "1");
      window.history.replaceState(null, "", url);
    } catch (error) {
      setSyncErrorMessage(error instanceof Error ? error.message : "Không bật được kết nối.");
    } finally { setLiveStarting(false); }
  }, [draftRecoveryReady, liveStarting, canvasDrawing, pagesMap, flushSavePage, currentPageIndex, apiClient, attemptId, receiveLiveSnapshot]);
  const autoLiveStarted = useRef(false);
  useEffect(() => {
    if (!initialLiveRequested || !draftRecoveryReady || autoLiveStarted.current) return;
    autoLiveStarted.current = true;
    void startLive(false);
  }, [initialLiveRequested, draftRecoveryReady, startLive]);

  const stopLive = async () => {
    if (canvasDrawing) { setSyncErrorMessage("Nhả bút trước khi ngắt kết nối."); return; }
    if (liveEnabledRef.current && live.pendingCount > 0) {

      if (!await live.flush()) { setSyncErrorMessage("Chưa nhận xác nhận lưu. Giữ kết nối hoặc xuất bản nháp trước khi rời trang."); return; }

    }
    if (devicePairing && !["REVOKED", "EXPIRED"].includes(devicePairing.status)) {
      try {
        await deviceRequest(`/api/v2/math-solutions/attempts/${attemptId}/ink/pairings/${devicePairing.id}/revoke`, {});
        setDevicePairing({...devicePairing, status: "REVOKED", code: undefined});
      } catch (failure) {
        if (![404, 410].includes((failure as {status?: number}).status ?? 0)) {
          setSyncErrorMessage("Chưa ngắt được thiết bị. Kiểm tra mạng rồi thử lại."); return;
        }
      }
    }
    setLiveEnabled(false); setPairingOpen(false);
    const url = new URL(window.location.href); url.searchParams.delete("live");
    window.history.replaceState(null, "", url);
    setSyncStatus("saved"); setSyncErrorMessage(undefined);
  };

  const handleRetrySync = useCallback(async () => {
    if (liveEnabledRef.current) { await liveRef.current.retry(); return; }
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
    const capturedStrokes = currentPageMemory.strokes;
    const penStrokes = getOcrPenStrokes(capturedStrokes);
    if (!batchJournalReady) { setOcrError("Đang kiểm tra nhật ký lưu trước. Hãy thử lại sau khi hoàn tất."); return; }
    if (pendingBatch || batchJournalLoadError) {
      setOcrError(
        batchJournalLoadError
          ? `Không thể trích xuất bước mới: nhật ký đợt lưu trong trình duyệt bị hỏng hoặc không đọc được (${batchJournalLoadError}).`
          : "Đợt lưu trước chưa hoàn tất. Hãy phục hồi hoặc hủy đợt lưu an toàn trước khi trích xuất bước mới."
      );
      return;
    }
    if (penStrokes.length === 0 || pageOcrReview || authExpired || syncStatus === "conflict") return;
    setOcrError(null);
    setIsRecognizingOCR(true);
    try {
      if (attempt && ["SUBMITTED", "EVALUATED"].includes(attempt.status)) {
        try {
          const reopened = await apiClient.reopenMathAttempt(accessToken, attemptId);
          setAttempt(reopened);
        } catch (reopenErr) {
          console.warn("Could not reopen attempt for OCR:", reopenErr);
        }
      }
      if (liveEnabledRef.current) {
        // Live Ink persists with operation ACKs; a legacy full-page PUT here
        // could overwrite another device's committed strokes.
        if (!await liveRef.current.flush()) {
          setOcrError("Nét viết trực tiếp chưa được máy chủ xác nhận. Hãy đồng bộ rồi thử lại.");
          return;
        }
      } else if (currentPageMemory.isDirty) {
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
      await saveQueueRef.current;
      if (latestStrokesRef.current.get(currentPageIndex) !== capturedStrokes
          && (!liveEnabledRef.current || JSON.stringify(latestStrokesRef.current.get(currentPageIndex)) !== JSON.stringify(capturedStrokes))) {
        setOcrError("Nét viết đã thay đổi khi đồng bộ. Hãy trích xuất lại trang mới nhất."); return;
      }
      setPageOcrReview({ pageIndex: currentPageIndex, pageStrokes: structuredClone(capturedStrokes), sourceRevision: Math.max(1, revisionRef.current) });
    } catch (error: unknown) {
      setOcrError(error instanceof ApiResponseError && error.status === 401
        ? "Phiên đăng nhập đã hết hạn. Đăng nhập lại để lưu nét viết."
        : "Không thể lưu nét viết lên máy chủ. Hãy kiểm tra kết nối rồi thử lại.");
    } finally {
      setIsRecognizingOCR(false);
    }
  }, [currentPageMemory.strokes, currentPageMemory.isDirty, currentPageIndex,
    flushSavePage, authExpired, syncStatus, pageOcrReview, pendingBatch, batchJournalLoadError, batchJournalReady]);

  const handleConfirmStep = useCallback(
    async (stepType: StepKind, latex: string | null, explanation: string, actionId: string) => {
      if (pendingBatch || batchJournalLoadError) {
        throw new Error("Đợt lưu hàng loạt chưa hoàn tất hoặc nhật ký trình duyệt đang lỗi; hãy xử lý trước khi lưu bước riêng.");
      }
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
    [attempt?.current_revision, apiClient, accessToken, attemptId, pendingBatch, batchJournalLoadError],
  );

  const handleSaveVariationTable = useCallback(async (payload: VariationTablePayload, actionId: string) => {
    if (pendingBatch || batchJournalLoadError) {
      throw new Error("Đợt lưu hàng loạt chưa hoàn tất hoặc nhật ký trình duyệt đang lỗi; hãy phục hồi trước khi sửa bài giải.");
    }
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
  }, [attempt, variationTableEditor, apiClient, accessToken, attemptId, pendingBatch, batchJournalLoadError]);

  const handleDeleteStep = useCallback(async (stepId: string) => {
    if (pendingBatch || batchJournalLoadError) {
      throw new Error("Đợt lưu hàng loạt chưa hoàn tất hoặc nhật ký trình duyệt đang lỗi; hãy phục hồi trước khi xóa bước.");
    }
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
  }, [attempt, apiClient, accessToken, attemptId, pendingBatch]);

  const executeAIReview = useCallback(async (targetAttempt: SolutionAttemptRead) => {
    if (isReviewing || !["SUBMITTED", "EVALUATED"].includes(targetAttempt.status)) return;
    setInstantReviewOpen(false);
    setIsReviewWorkspaceOpen(true);
    setIsReviewing(true);
    setGradingError(null);
    try {
      const result = await apiClient.reviewMathAttempt(accessToken, attemptId);
      if (result.attempt_id !== attemptId ||
          (!result.is_final && result.step_grades.length !== targetAttempt.steps?.length)) {
        throw new Error("Phản hồi AI không khớp bài làm đã nộp.");
      }
      setAIReview(result);
      if (result.is_final) {
        const refreshed = await apiClient.getMathAttempt(accessToken, attemptId).catch(() => null);
        if (refreshed) setAttempt(refreshed);
        router.refresh();
      }
    } catch (error: unknown) {
      const code = error instanceof ApiResponseError ? error.code : "";
      const message = code === "GRADING_ASSIGNMENT_NOT_SUBMITTED"
        ? "Hãy nộp toàn bộ bài giáo viên giao trước khi kiểm tra lời giải này."
        : code === "GRADING_ANSWER_REQUIRED"
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
  }, [isReviewing, apiClient, accessToken, attemptId, router]);


  const handleReopenAttempt = useCallback(async () => {
    if (!attempt || attempt.status !== "SUBMITTED") return;
    try {
      const reopened = await apiClient.reopenMathAttempt(accessToken, attemptId);
      setAttempt(reopened);
      setGradingError(null);
    } catch (err: unknown) {
      setGradingError(err instanceof Error ? err.message : "Chưa thể mở lại bài làm.");
    }
  }, [attempt, attemptId, accessToken, apiClient]);

  const handleAIReview = useCallback(async () => {
    if (!attempt) return;
    await executeAIReview(attempt);
  }, [attempt, executeAIReview]);

  const handleOpenReviewWorkspace = useCallback(() => {
    if (aiReview) {
      setInstantReviewOpen(true);
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
      if (pendingBatch || batchJournalLoadError || batchResuming) throw new Error("Chưa thể nộp bài: đợt lưu OCR đang chờ phục hồi hoặc nhật ký lưu không đọc được. Hãy xử lý trạng thái phục hồi trước.");
      if (pendingDeleteRef.current || pageOcrReview) throw new Error("Hãy hoàn tất thao tác sửa bước và xác nhận OCR trước khi nộp.");
      if (syncStatus === "conflict" || syncStatus === "offline" || authExpired) {
        throw new Error("Nét viết chưa đồng bộ. Hãy lưu lại trước khi nộp bài.");
      }
      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
      await saveQueueRef.current;
      if (liveEnabledRef.current && !await liveRef.current.flush()) {
        throw new Error("Nét viết trực tiếp chưa được xác nhận lưu. Không thể nộp bài.");
      }
      for (const [pageIndex, page] of pagesMap) {
        // The active live page was already persisted via operations above.
        // Never submit a stale full-page PUT over another device's ink.
        if (liveEnabledRef.current && pageIndex === currentPageIndex) continue;
        if (page.isDirty && !await flushSavePage(pageIndex, page.strokes)) {
          throw new Error("Không thể lưu toàn bộ trang viết. Hãy thử lại trước khi nộp.");
        }
      }
      const dirty = await mathInkStorage.listDirtyPages(attemptId).catch(() => []);
      if (dirty.length) throw new Error("Vẫn còn trang viết chưa đồng bộ. Hãy thử lưu lại.");

      // Auto-extract handwriting from canvas via Gemini OCR if needed
      let currentAttempt = attempt;
      const allPenStrokes = currentPageMemory.strokes.filter((s) => s.tool === "PEN" && s.points.length > 0);
      if (allPenStrokes.length > 0) {
        try {
          const ocrRes = await apiClient.recognizeMathInk(accessToken ?? "", attemptId, {
            page_index: currentPageIndex,
            stroke_ids: allPenStrokes.map((s) => s.id),
            strokes: allPenStrokes,
          });
          const recognizedLatex = ocrRes.latex ? ocrRes.latex.trim() : "";
          if (recognizedLatex) {
            const cleanOcr = recognizedLatex.replace(/[\s\$\\]/g, "");
            const matchesExisting = cleanOcr.length > 0 && (currentAttempt.steps ?? []).some((step) => {
              const cleanStep = (step.content_latex ?? "").replace(/[\s\$\\]/g, "");
              return cleanStep && (cleanStep.includes(cleanOcr) || cleanOcr.includes(cleanStep));
            });

            if (!matchesExisting) {
              const suggestedKind = ocrRes.suggested_step_type && STEP_KINDS.includes(ocrRes.suggested_step_type as StepKind)
                ? (ocrRes.suggested_step_type as StepKind)
                : "CUSTOM";

              if (currentAttempt.steps?.length === 1) {
                const stepId = currentAttempt.steps[0]!.id;
                const updated = await apiClient.updateMathStep(accessToken, attemptId, stepId, {
                  expected_attempt_revision: currentAttempt.current_revision,
                  client_action_id: generateUuid(),
                  step_type: suggestedKind,
                  content_latex: recognizedLatex,
                  explanation_text: null,
                });
                currentAttempt = updated;
                setAttempt(updated);
              } else {
                const updated = await apiClient.createMathStep(accessToken, attemptId, {
                  expected_attempt_revision: currentAttempt.current_revision,
                  client_action_id: generateUuid(),
                  step_type: suggestedKind,
                  content_latex: recognizedLatex,
                  explanation_text: null,
                });
                currentAttempt = updated;
                setAttempt(updated);
              }
            }
          }
        } catch (ocrErr: unknown) {
          console.warn("Auto Gemini OCR failed during submit, continuing with existing steps if any:", ocrErr);
        }
      }

      if (!currentAttempt.steps?.length) {
        throw new Error("Hãy viết bài giải trên giấy hoặc xác nhận ít nhất một bước giải trước khi nộp.");
      }

      // Read IndexedDB while holding the exact Web Lock used by the batch engine.
      // Do NOT allocate an idempotency key before the safety gate: a blocked
      // submission must not retain a stale attempt revision for a later retry.
      const submitted = await withSafeBatchSubmission(
        attemptId, new IndexedDbBatchJournal(), new BrowserBatchLock(),
        () => {
          const pending = submitActionRef.current ?? { revision: currentAttempt.current_revision, actionId: generateUuid() };
          submitActionRef.current = pending;
          return apiClient.submitMathAttempt(accessToken, attemptId, {
            expected_attempt_revision: pending.revision, client_action_id: pending.actionId,
          });
        },
      );
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
          } else if (error.status === 409 && submitActionRef.current
            && latest.current_revision !== submitActionRef.current.revision) {
            // Server authoritatively rejected this revision; a later manual
            // retry must use the refreshed revision and a new action ID.
            // Do not regenerate the key on timeout/unknown commit outcomes.
            submitActionRef.current = null;
          }
        }
      }
      if (!successfullySubmitted) {
        const code = error instanceof Error ? error.message : "";
        if (code === "BATCH_PENDING_RECOVERY_REQUIRED" || code === "BATCH_JOURNAL_CORRUPT"
          || code === "BATCH_INDEXEDDB_UNAVAILABLE" || code === "BATCH_SUBMIT_LOCK_UNAVAILABLE") {
          void checkPendingBatch();
        }
        const message = code === "BATCH_PENDING_RECOVERY_REQUIRED"
          ? "Có đợt lưu OCR chưa hoàn tất. Hãy phục hồi hoặc xử lý đợt lưu trước khi nộp bài."
          : code === "BATCH_SUBMIT_LOCK_UNAVAILABLE"
            ? "Một tab khác đang xử lý bước giải. Hãy đợi hoàn tất và thử nộp lại."
            : code === "BATCH_JOURNAL_CORRUPT" || code === "BATCH_INDEXEDDB_UNAVAILABLE"
              ? "Không thể xác minh nhật ký lưu OCR trong trình duyệt. Nộp bài đã bị chặn để bảo vệ dữ liệu."
              : error instanceof ApiResponseError ? error.message
                : error instanceof Error ? error.message : "Không thể nộp bài. Hãy thử lại.";
        setGradingError(message);
      }
    } finally {
      setIsSubmitting(false);
    }

    const availability = successfullySubmitted && problem?.question_type === "OPEN_RESPONSE"
      ? await apiClient.getMathAIReviewAvailability(accessToken, attemptId).catch(() => null)
      : null;
    if (availability) setAIReviewAvailability(availability);
    if (autoReview && successfullySubmitted && problem?.question_type === "OPEN_RESPONSE"
        && availability?.available !== false) {
      void executeAIReview(successfullySubmitted);
    }
  }, [attempt, isSubmitting, pageOcrReview, syncStatus, authExpired, pagesMap,
    flushSavePage, attemptId, apiClient, accessToken, problem?.question_type, executeAIReview,
    pendingBatch, batchJournalLoadError, batchResuming, checkPendingBatch, currentPageIndex]);
  // Keep stroke persistence separate from history updates. Undo/redo must not
  // append another history entry or erase the redo stack.
  const queueInkSave = useCallback((pageIndex: number, newStrokes: InkStroke[]) => {
    if (liveEnabledRef.current) {
      // Only the operation-based handler may edit ink during live mode.
      // Never let legacy snapshot autosave overwrite concurrent remote strokes.
      throw new Error("Legacy ink saving is disabled while Live Ink is active.");
    }
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
    (newStrokes: InkStroke[], observedStrokes?: InkStroke[]) => {
      if (liveEnabledRef.current) {
        liveRef.current.change(newStrokes, observedStrokes ?? currentPageMemory.strokes);
        return;
      }
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
    [currentPageIndex, queueInkSave, currentPageMemory.strokes],
  );

  // 4. Undo / Redo
  const handleUndo = useCallback(() => {
    if (liveEnabledRef.current) { liveRef.current.undo(); return; }
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
    if (liveEnabledRef.current) { liveRef.current.redo(); return; }
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
      handleStrokesChange([], currentPageMemory.strokes);
    }
  }, [currentPageMemory.strokes, handleStrokesChange]);

  // 5. Switching Pages
  const handleSelectPage = useCallback(
    async (targetIndex: number) => {
      if (canvasDrawing || liveStarting) return;
      if (targetIndex === currentPageIndex || targetIndex < 0 || targetIndex >= pageCount) {
        return;
      }
      if (liveEnabledRef.current && !await liveRef.current.flush()) return;

      // Do not navigate away from ink that the server has not accepted.
      const pageStrokesAtStart = latestStrokesRef.current.get(currentPageIndex);
      if (!liveEnabledRef.current && currentPageMemory.isDirty) {
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
      canvasDrawing, liveStarting,
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
    if (canvasDrawing || liveStarting) return;
    if (liveEnabledRef.current && !await liveRef.current.flush()) return;
    if (pageCount >= MAX_PAGES) return;
    const pageStrokesAtStart = latestStrokesRef.current.get(currentPageIndex);
    if (!liveEnabledRef.current && currentPageMemory.isDirty) {
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
  }, [pageCount, currentPageIndex, currentPageMemory, flushSavePage, canvasDrawing, liveStarting]);

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
    if (liveEnabledRef.current) { await liveRef.current.retry(); return; }
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

  const handlePrepareSubmission = useCallback(() => {
    if (paperMode) return;
    void handleTriggerOCR();
  }, [paperMode, handleTriggerOCR]);

  const handleSubmitExam = useCallback(async () => {
    if (!classroomNav || !isClassroomExam || examSubmitted || isSubmittingExam) return;
    setExamSubmitError(null);
    setIsSubmittingExam(true);
    try {
      if (pendingBatch || batchJournalLoadError || batchResuming || pageOcrReview || pendingDeleteRef.current) {
        throw new Error("Hãy hoàn tất xác nhận và đồng bộ các bước giải trước khi nộp bài kiểm tra.");
      }
      if (authExpired || syncStatus === "offline" || syncStatus === "conflict") {
        throw new Error("Bài làm chưa đồng bộ hoặc phiên đăng nhập đã hết hạn. Hãy lưu lại trước khi nộp.");
      }
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
        saveTimeoutRef.current = null;
      }
      await saveQueueRef.current;
      if (liveEnabledRef.current && !await liveRef.current.flush()) {
        throw new Error("Nét viết từ thiết bị chưa lưu xong. Hãy đồng bộ rồi nộp lại.");
      }
      for (const [index, page] of pagesMap) {
        if (liveEnabledRef.current && index === currentPageIndex) continue;
        if (page.isDirty && !await flushSavePage(index, page.strokes)) {
          throw new Error("Chưa lưu xong trang viết hiện tại. Hãy thử lại.");
        }
      }
      if ((await mathInkStorage.listDirtyPages(attemptId)).length) {
        throw new Error("Vẫn còn trang viết chưa đồng bộ. Hãy lưu lại trước khi nộp.");
      }

      // 1. Auto-submit active attempt if it has steps and is in DRAFT / IN_PROGRESS
      if (attempt && ["DRAFT", "IN_PROGRESS"].includes(attempt.status) && (attempt.steps?.length ?? 0) > 0) {
        await apiClient.submitMathAttempt(accessToken, attemptId, { expected_attempt_revision: revisionRef.current, client_action_id: generateUuid() });
        setAttempt((prev) => prev ? { ...prev, status: "SUBMITTED" } : prev);
      }

      // 2. Prepare submission answers: for questions that do NOT have submitted steps, provide placeholder
      // Questions with submitted step attempts MUST NOT have text answers submitted to avoid ASSIGNMENT_ANSWER_SOURCE_CONFLICT.
      const answers: Array<{
        question_id?: string | null;
        teacher_material_item_id?: string | null;
        student_answer: string;
      }> = [];

      for (const q of classroomNav.questions) {
        const isCurrent = q.attemptId === attemptId;
        const hasSubmittedSteps = isCurrent
          ? ((attempt?.steps?.length ?? 0) > 0)
          : (q.stepCount > 0 || q.status === "SUBMITTED" || q.status === "EVALUATED");

        if (!hasSubmittedSteps) {
          const fallbackAnswer = (q.studentAnswer && q.studentAnswer.trim().length > 0)
            ? q.studentAnswer.trim()
            : "(Chưa làm)";
          if (q.sourceKind === "CANONICAL" || q.questionId) {
            answers.push({
              question_id: q.questionId || q.problemId,
              student_answer: fallbackAnswer,
            });
          } else {
            answers.push({
              teacher_material_item_id: q.teacherMaterialItemId || q.problemId,
              student_answer: fallbackAnswer,
            });
          }
        }
      }

      const csrfToken = await getCsrfToken().catch(() => "");
      const res = await fetch(`/api/student/assignments/${classroomNav.studentAssignmentId}/submit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
        },
        body: JSON.stringify({ answers }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null);
        if (body?.error?.code === "ASSIGNMENT_ALREADY_SUBMITTED") {
          const check = await fetch(`/api/student/assignments/${classroomNav.studentAssignmentId}`, { cache: "no-store" });
          const current = check.ok ? await check.json().catch(() => null) : null;
          if (current?.status === "SUBMITTED" || current?.status === "GRADED") {
            setExamSubmitted(true);
            setAttempt((row) => row ? { ...row, status: "SUBMITTED" } : row);
            setExamSubmitOpen(false);
            router.refresh();
            return;
          }
        }
        throw new Error(body?.error?.message ?? "Không thể nộp bài kiểm tra. Hãy thử lại.");
      }
      setExamSubmitted(true);
      setAttempt((current) => current ? { ...current, status: "SUBMITTED" } : current);
      setExamSubmitOpen(false);
      router.refresh();
    } catch (error) {
      setExamSubmitError(error instanceof Error ? error.message : "Không thể nộp bài kiểm tra.");
    } finally {
      setIsSubmittingExam(false);
    }
  }, [classroomNav, isClassroomExam, examSubmitted, isSubmittingExam, pendingBatch,
    batchJournalLoadError, batchResuming, pageOcrReview, authExpired, syncStatus,
    attemptId, attempt, accessToken, apiClient, pagesMap, currentPageIndex, flushSavePage, router]);

  const handleExamSwitchQuestion = useCallback(async (targetIndex: number) => {
    if (!isClassroomExam) {
      await handleSwitchQuestion(targetIndex);
      return;
    }
    setExamSubmitError(null);
    try {
      if (pendingBatch || batchJournalLoadError || batchResuming || pageOcrReview || pendingDeleteRef.current) {
        throw new Error("Hãy xác nhận và lưu xong bước giải hiện tại trước khi chuyển câu.");
      }
      if (authExpired || syncStatus === "offline" || syncStatus === "conflict") {
        throw new Error("Nét viết chưa đồng bộ. Hãy lưu lại trước khi chuyển câu.");
      }
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
        saveTimeoutRef.current = null;
      }
      await saveQueueRef.current;
      if (liveEnabledRef.current && !await liveRef.current.flush()) {
        throw new Error("Thiết bị viết chưa đồng bộ xong. Hãy thử lại.");
      }
      for (const [index, page] of pagesMap) {
        if (liveEnabledRef.current && index === currentPageIndex) continue;
        if (page.isDirty && !await flushSavePage(index, page.strokes)) {
          throw new Error("Chưa lưu được trang viết. Hãy thử lại.");
        }
      }
      if ((await mathInkStorage.listDirtyPages(attemptId)).length) {
        throw new Error("Còn trang viết chưa đồng bộ. Hãy lưu lại trước khi chuyển câu.");
      }
      await handleSwitchQuestion(targetIndex);
    } catch (error) {
      setExamSubmitError(error instanceof Error ? error.message : "Không thể chuyển câu.");
    }
  }, [isClassroomExam, handleSwitchQuestion, pendingBatch, batchJournalLoadError,
    batchResuming, pageOcrReview, authExpired, syncStatus, pagesMap,
    currentPageIndex, flushSavePage, attemptId]);

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

  const isReadOnlyAttempt = Boolean(
    examSubmitted ||
    problem?.is_read_only ||
    (attempt && ["SUBMITTED", "EVALUATED", "ABANDONED"].includes(attempt.status))
  );

  const currentHasSteps = Boolean(attempt?.steps && attempt.steps.length > 0);
  const examMissingQuestions = useMemo(() => {
    return getExamMissingQuestions(
      classroomNav?.questions ?? [],
      attemptId,
      attempt?.status,
      currentHasSteps
    );
  }, [classroomNav?.questions, attemptId, attempt?.status, currentHasSteps]);
  const toggleWritingMode = () => {
    if (canvasDrawing) return;
    if (writingMode) {
      setWritingMode(false);
      setIsProblemPaneCollapsed(writingLayoutRef.current.collapsed);
      setZoomLevel(writingLayoutRef.current.zoom); setPaperMode(writingLayoutRef.current.paper);
    } else {
      writingLayoutRef.current = {collapsed: isProblemPaneCollapsed, zoom: zoomLevel, paper: paperMode};
      setWritingMode(true); setIsProblemPaneCollapsed(true); setZoomLevel(1); setPaperMode(false);
    }
  };

  return (
    <div className={`${styles.workspaceContainer} ${writingMode ? styles.mobileWriting : ""}`}>
      {/* Classroom Assignment Top Bar */}
      {classroomNav && (
        <div className={styles.classroomBar} role="navigation" aria-label="Điều hướng bài tập lớp">
          <div className={styles.classroomLeft}>
            <Link href="/student/attempts?tab=classroom" className={styles.classroomBackLink}>
              ← Bài tập lớp
            </Link>
            <span
              className={`${styles.classroomModeBadge} ${
                classroomNav.deliveryMode === "EXAM"
                  ? styles.classroomModeBadgeExam
                  : styles.classroomModeBadgePractice
              }`}
            >
              {classroomNav.deliveryMode === "EXAM" ? "Kiểm tra" : "Luyện tập"}
            </span>
            <span className={styles.classroomTitle} title={classroomNav.title}>
              {classroomNav.title}
            </span>
          </div>

          <div className={styles.classroomCenter}>
            {classroomNav.questions.map((q) => {
              const isCurrent = q.isCurrent;
              const isCompleted =
                (q.attemptId === attemptId && (attempt?.status === "SUBMITTED" || attempt?.status === "EVALUATED" || (attempt?.steps?.length ?? 0) > 0)) ||
                (q.status === "SUBMITTED" || q.status === "EVALUATED" || (q.stepCount ?? 0) > 0) ||
                Boolean(q.hasAnswer || (q.studentAnswer && q.studentAnswer.trim().length > 0));
              let pillClass = styles.qNavPill;
              if (isCurrent) pillClass += ` ${styles.qNavPillActive}`;
              else if (isCompleted) pillClass += ` ${styles.qNavPillCompleted}`;

              return (
                <button
                  key={q.index}
                  type="button"
                  className={pillClass}
                  onClick={() => void handleExamSwitchQuestion(q.index)}
                  disabled={switchingQuestion}
                  title={`Chuyển sang Câu ${q.index + 1}`}
                >
                  {q.index + 1}
                </button>
              );
            })}
          </div>

          <div className={styles.classroomRight}>
            <button
              type="button"
              className={styles.navStepBtn}
              disabled={classroomNav.currentIndex === 0 || switchingQuestion}
              onClick={() => void handleExamSwitchQuestion(classroomNav.currentIndex - 1)}
            >
              ← Câu trước
            </button>
            <button
              type="button"
              className={styles.navStepBtn}
              disabled={
                classroomNav.currentIndex >= classroomNav.totalQuestions - 1 || switchingQuestion
              }
              onClick={() => void handleExamSwitchQuestion(classroomNav.currentIndex + 1)}
            >
              {switchingQuestion ? "Đang chuyển..." : "Câu tiếp theo →"}
            </button>
            {isClassroomExam && !examSubmitted ? (
              <button
                type="button"
                className={styles.navStepBtnPrimary}
                onClick={() => { setExamSubmitError(null); setExamSubmitOpen(true); }}
              >
                Nộp bài kiểm tra
              </button>
            ) : isClassroomExam ? (
              <span className={styles.examSubmittedLabel}>Đã nộp toàn bài</span>
            ) : null}
          </div>
        </div>
      )}

      {isClassroomExam && examSubmitted ? (
        <div className={styles.examStatusBanner} role="status">
          {classroomNav?.assignmentStatus === "GRADED" && classroomNav.assignmentScore !== null
            ? `Bài kiểm tra đã được chấm: ${classroomNav.assignmentScore}/10 điểm.`
            : "Đã nộp toàn bộ bài kiểm tra. Câu có thể kiểm chứng được chấm theo đáp án; câu còn lại chờ giáo viên duyệt."}
        </div>
      ) : null}
      {isClassroomExam && examSubmitError && !examSubmitOpen ? (
        <div className={styles.ocrErrorBanner} role="alert">{examSubmitError}</div>
      ) : null}

      {/* Top Header Bar */}
      <header className={styles.topHeader}>
        <div className={styles.headerLeft}>
          <h1 className={styles.headerTitle}>Không gian giải bài Toán</h1>
          <button
            type="button"
            className={styles.buttonSecondary}
            disabled={liveStarting || canvasDrawing || !draftRecoveryReady}
            onClick={() => void startLive()}
            title="Quét mã QR để kết nối điện thoại hoặc iPad làm bảng viết"
          >
            <Smartphone size={15} />
            {liveStarting ? "Đang kết nối…" : liveEnabled ? "Thiết bị viết (Đang kết nối)" : "Kết nối thiết bị viết"}
          </button>
          <button type="button" className={styles.buttonSecondary} disabled={canvasDrawing} onClick={toggleWritingMode}>
            {writingMode ? "Về MathWorkspace" : "Chế độ viết cảm ứng"}
          </button>
          {liveEnabled ? <span className={styles.liveConnectionStatus} role="status" data-live-status={live.status} data-pending={live.pendingCount}>
            <span/>{live.pendingCount ? "Đang lưu nét viết…" : live.drafts.length ? "Thiết bị khác đang viết…" : live.status === "connected" ? live.devices > 1 ? "Đã kết nối thiết bị viết" : "Sẵn sàng kết nối thiết bị" : live.status === "offline" ? "Mất mạng · Đang giữ nét viết" : "Đang kết nối lại…"}
          </span> : null}
          {liveEnabled && !writingMode ? <button type="button" className={styles.liveDisconnectButton} onClick={() => void stopLive()}>Dừng đồng bộ</button> : null}
          <SyncStatusBadge
            status={syncStatus}
            errorMessage={syncErrorMessage}
            authExpired={authExpired}
            onRetry={handleRetrySync}
            onResolveConflict={handleResolveConflict}
            onExportDraft={handleExportDraft}
          />
          {isClassroomExam && !examSubmitted && attempt?.status === "SUBMITTED" ? (
            <button type="button" className={styles.buttonSecondary} onClick={() => void handleReopenAttempt()}>
              Sửa câu này
            </button>
          ) : null}
          {isClassroomExam && !examSubmitted && attempt && ["DRAFT", "IN_PROGRESS"].includes(attempt.status) ? (
            <button type="button" className={styles.headerGradeButton}
              onClick={() => attempt.steps?.length ? void handleSubmitSolution(false) : handlePrepareSubmission()}
              disabled={isSubmitting || batchResuming || Boolean(pendingBatch || batchJournalLoadError)}>
              {isSubmitting ? "Đang xác nhận..." : attempt.steps?.length ? "Xác nhận câu" : "Chuẩn bị bước giải"}
            </button>
          ) : null}
          {!isClassroomExam && !writingMode && attempt && (!problem?.is_read_only || ["SUBMITTED", "EVALUATED"].includes(attempt.status)) ? (
            <button
              type="button"
              className={styles.headerGradeButton}
              onClick={() => {
                if (["SUBMITTED", "EVALUATED"].includes(attempt.status)) {
                  if (aiReview) {
                    handleOpenReviewWorkspace();
                  } else {
                    void handleAIReview();
                  }
                } else {
                  void handleSubmitSolution();
                }
              }}
              disabled={isSubmitting || isReviewing || batchResuming || Boolean(pendingBatch || batchJournalLoadError) || (!isReadOnlyAttempt && !attempt.steps?.length)}
              title={isReadOnlyAttempt ? "Xem kết quả kiểm tra bài làm" : "Nộp bài và kiểm tra các bước giải"}
            >
              <Sparkles size={14} />
              <span>
                {isSubmitting
                  ? "Đang nộp bài..."
                  : isReviewing
                    ? "Đang kiểm tra bài..."
                    : isReadOnlyAttempt
                      ? aiReview
                        ? "Xem kết quả"
                        : "Kiểm tra bài làm"
                      : "Nộp bài & kiểm tra"}
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
          isReadOnly={isReadOnlyAttempt}
        />
      </header>
      {pairingOpen ? (
        <DeviceConnection
          attemptId={attemptId}
          page={currentPageIndex}
          pairing={devicePairing}
          onPairingChange={setDevicePairing}
          onClose={() => {
            setPairingOpen(false);
            if (!devicePairing || devicePairing.status !== "ACTIVE") {
              void stopLive();
            }
          }}
        />
      ) : null}

      {/* PR3-C: Unfinished Batch Recovery Banner & Corrupted Journal Fail-Closed Banner */}
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
      ) : batchJournalLoadError ? (
        <div className={styles.batchRecoveryBanner} role="alert">
          <div className={styles.batchRecoveryInfo}>
            <strong>Phát hiện dữ liệu lịch sử lưu hàng loạt bị hỏng ({batchJournalLoadError})</strong>
            <p>
              {recoveryMessage ?? `Lỗi đọc dữ liệu đợt lưu (${batchJournalLoadError}).`} Dữ liệu gốc trong trình duyệt và các bước giải trên máy chủ vẫn được giữ nguyên.
            </p>
          </div>
          <div className={styles.batchRecoveryActions}>
            <button
              type="button"
              className={styles.buttonSecondary}
              onClick={() => void handleSyncAuthoritativeAttempt()}
              disabled={batchResuming}
            >
              {batchResuming ? "Đang đối soát..." : "Đối soát máy chủ"}
            </button>
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
        canUndo={!isReadOnlyAttempt && (liveEnabled ? live.canUndo : currentPageMemory.past.length > 0)}
        onUndo={handleUndo}
        canRedo={!isReadOnlyAttempt && (liveEnabled ? live.canRedo : currentPageMemory.future.length > 0)}
        onRedo={handleRedo}
        onClearPage={handleClearPage}
        zoomLevel={zoomLevel}
        onZoomIn={() => setZoomLevel((z) => Math.min(2.0, z + 0.1))}
        onZoomOut={() => setZoomLevel((z) => Math.max(0.6, z - 0.1))}
        onResetZoom={() => setZoomLevel(1.0)}
        onTriggerOCR={paperMode ? undefined : handleTriggerOCR}
        ocrBlocked={!batchJournalReady || Boolean(pendingBatch || batchJournalLoadError || batchResuming || pageOcrReview)
          || (liveEnabled && (!live.ready || live.pendingCount > 0 || live.drafts.length > 0))}
        onOpenVariationTable={attempt && ["DRAFT", "IN_PROGRESS"].includes(attempt.status) && !pageOcrReview && !isReadOnlyAttempt
          ? () => setVariationTableEditor({}) : undefined}
        onTogglePaper={() => setPaperMode((current) => !current)}
        paperMode={paperMode}
        isRecognizingOCR={isRecognizingOCR}
        strokeCount={getOcrPenStrokes(currentPageMemory.strokes).length}
        isReadOnly={isReadOnlyAttempt}
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
        {!writingMode ? <ProblemPane
          problem={problem}
          attempt={attempt}
          isCollapsed={isProblemPaneCollapsed}
          onToggleCollapse={() => setIsProblemPaneCollapsed((c) => !c)}
          onVisualizeFormula={(formula) => { setGraphSelection({ page: currentPageIndex, strokes: [], formula }); setGraphOpen(true); }}
          onDeleteStep={handleDeleteStep}
          onEditVariationTable={(stepId, initial) => setVariationTableEditor({ stepId, initial })}
          onSubmitSolution={handleSubmitSolution}
          onConfirmExamQuestion={() => handleSubmitSolution(false)}
          onPrepareSubmission={handlePrepareSubmission}
          onReopenAttempt={handleReopenAttempt}
          onAIReview={handleAIReview}
          onOpenReviewWorkspace={handleOpenReviewWorkspace}
          aiReview={aiReview}
          aiReviewAvailability={aiReviewAvailability}
          gradingError={gradingError}
          isSubmitting={isSubmitting}
          isReviewing={isReviewing}
          submissionBlocked={Boolean(pendingBatch || batchJournalLoadError || batchResuming)}
          examMode={isClassroomExam && !examSubmitted}
        /> : null}

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
              isReadOnly={isReadOnlyAttempt}
              onConfirmStep={(content, actionId) =>
                handleConfirmStep("EXPLANATION", content.latex, content.explanation, actionId)
              }
              onSubmitSolution={handleSubmitSolution}
              isSubmitting={isSubmitting}
              isReviewing={isReviewing}
              submissionBlocked={Boolean(pendingBatch || batchJournalLoadError || batchResuming)}
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
              isReadOnly={isReadOnlyAttempt || liveStarting}
              remoteDrafts={liveEnabled ? live.drafts : []}
              onLiveStroke={liveEnabled ? live.stream : undefined}
              responsive={writingMode}
              onDrawingStateChange={setCanvasDrawing}
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
          if (liveEnabledRef.current) {
            if (!await liveRef.current.flush()) {
              throw new Error("Nét viết trực tiếp chưa được xác nhận lưu. Hãy đồng bộ rồi thử lại.");
            }
          } else if (currentPageMemory.isDirty) {
            const saved = await flushSavePage(currentPageIndex, latestStrokesRef.current.get(currentPageIndex) ?? currentPageMemory.strokes);
            if (!saved) throw new Error("Nét viết chưa được lưu lên máy chủ. Hãy đồng bộ rồi thử lại.");
          }
          await saveQueueRef.current;
        }}
        onClose={() => setGraphOpen(false)} /> : null}

      {pageOcrReview ? (
        <PageOcrV2ReviewModal
          pageIndex={pageOcrReview.pageIndex}
          source={{ pageIndex: pageOcrReview.pageIndex, sourceRevision: pageOcrReview.sourceRevision, sourceKind: "INK", strokes: pageOcrReview.pageStrokes }}
          blockedByBatch={Boolean(pendingBatch || batchJournalLoadError)}
          isSourceCurrent={() => !authExpired && documentRevision === pageOcrReview.sourceRevision && currentPageIndex === pageOcrReview.pageIndex && JSON.stringify(latestStrokesRef.current.get(pageOcrReview.pageIndex)) === JSON.stringify(pageOcrReview.pageStrokes)}
          beforeSave={async () => {
            if (authExpired || syncStatus !== "saved" || revisionRef.current !== pageOcrReview.sourceRevision || JSON.stringify(latestStrokesRef.current.get(pageOcrReview.pageIndex)) !== JSON.stringify(pageOcrReview.pageStrokes)) throw Error("SOURCE_CHANGED_OR_UNSYNCED; hãy đồng bộ và trích xuất lại");
            const fresh = await apiClient.getMathInkPage(accessToken, attemptId, pageOcrReview.pageIndex);
            if (fresh.document_revision !== pageOcrReview.sourceRevision || JSON.stringify(fresh.strokes) !== JSON.stringify(pageOcrReview.pageStrokes)) throw Error("SERVER_INK_REVISION_CHANGED; snapshot cũ được giữ, hãy đối chiếu lại");
          }}
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

      {examSubmitOpen && classroomNav ? (
        <div className={styles.modalOverlay} role="presentation">
          <div className={styles.examSubmitDialog} role="dialog" aria-modal="true" aria-labelledby="exam-submit-title">
            <h2 id="exam-submit-title">Nộp toàn bộ bài kiểm tra?</h2>
            <div className={styles.examSubmitStats}>
              <span>
                Đã hoàn thành <strong>{classroomNav.totalQuestions - examMissingQuestions.length}/{classroomNav.totalQuestions}</strong> câu
              </span>
            </div>
            {examMissingQuestions.length > 0 ? (
              <div className={styles.examWarningBox} role="alert">
                <p className={styles.examWarningTitle}>
                  ⚠️ Còn {examMissingQuestions.length} câu chưa làm (Câu {examMissingQuestions.map((q) => q.index + 1).join(", ")}).
                </p>
                <p className={styles.examWarningSub}>
                  Các câu để trống sẽ được tính 0 điểm. Em có chắc chắn muốn nộp bài ngay bây giờ không?
                </p>
              </div>
            ) : (
              <p className={styles.examAllDoneNotice}>
                ✓ Em đã hoàn thành tất cả {classroomNav.totalQuestions} câu. Sau khi nộp, bài thi sẽ được chuyển sang giáo viên để chấm điểm.
              </p>
            )}
            {examSubmitError ? <p className={styles.examIncomplete} role="alert">{examSubmitError}</p> : null}
            <div className={styles.examDialogActions}>
              {examMissingQuestions.length > 0 ? (
                <button
                  type="button"
                  className={styles.navStepBtn}
                  onClick={() => {
                    setExamSubmitOpen(false);
                    void handleExamSwitchQuestion(examMissingQuestions[0]!.index);
                  }}
                >
                  Đi tới câu {examMissingQuestions[0]!.index + 1}
                </button>
              ) : null}
              <button
                type="button"
                className={styles.navStepBtn}
                disabled={isSubmittingExam}
                onClick={() => setExamSubmitOpen(false)}
              >
                Tiếp tục làm bài
              </button>
              <button
                type="button"
                className={styles.navStepBtnPrimary}
                disabled={isSubmittingExam}
                onClick={() => void handleSubmitExam()}
              >
                {isSubmittingExam ? "Đang nộp toàn bài..." : "Xác nhận nộp bài"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {isReviewWorkspaceOpen && !isClassroomExam ? (
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

          onNextProblem={handleNextProblem}

          nextProblemLabel={nextProblemLabel}

          isNextLoading={switchingQuestion || advancingPractice}

        />
      ) : null}
    </div>
  );
}
