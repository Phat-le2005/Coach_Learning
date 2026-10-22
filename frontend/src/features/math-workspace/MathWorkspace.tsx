"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
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
import { recognizeHandwrittenMath } from "./utils/handwritten-ocr";
import { canSafelyRebaseInkDraft, restoreDirtyPageDrafts } from "./utils/draft-recovery";
import { WorkspaceToolbar } from "./components/WorkspaceToolbar";
import { PageNavigator } from "./components/PageNavigator";
import { ProblemPane } from "./components/ProblemPane";
import { MathCanvas } from "./components/MathCanvas";
import { SyncStatusBadge } from "./components/SyncStatusBadge";
import { OcrConfirmModal } from "./components/OcrConfirmModal";
import type { OCRRecognizeResponse, StepKind } from "@/lib/api/contracts";
import styles from "./MathWorkspace.module.css";

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

  // Sync state
  const [syncStatus, setSyncStatus] = useState<SyncStatus>("saved");
  const [syncErrorMessage, setSyncErrorMessage] = useState<string | undefined>();
  const [authExpired, setAuthExpired] = useState(false);

  // OCR recognition & confirmation state
  const [isRecognizingOCR, setIsRecognizingOCR] = useState(false);
  const [ocrModalOpen, setOcrModalOpen] = useState(false);
  const [ocrData, setOcrData] = useState<OCRRecognizeResponse | null>(null);
  const [ocrManualMode, setOcrManualMode] = useState(false);
  const [ocrSourceStrokes, setOcrSourceStrokes] = useState<InkStroke[]>([]);
  const [isSubmittingStep, setIsSubmittingStep] = useState(false);
  const [ocrError, setOcrError] = useState<string | null>(null);

  // Debounce save timer ref
  const saveTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const revisionRef = useRef(initialDocument?.document_revision ?? 0);
  const latestStrokesRef = useRef<Map<number, InkStroke[]>>(
    new Map([[0, initialPage?.strokes ?? []]]),
  );
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const locallyEditedPagesRef = useRef(new Set<number>());
  const recoveredDraftRevisionsRef = useRef(new Map<number, number>());
  const transientPageIndexesRef = useRef(new Set<number>());
  const unverifiedPageIndexesRef = useRef(new Set<number>(initialPage ? [] : [0]));

  const apiClient = useRef(createBrowserMathApiClient()).current;

  // Current active page memory
  const currentPageMemory: PageMemory = pagesMap.get(currentPageIndex) ?? {
    strokes: [],
    past: [],
    future: [],
    isDirty: false,
  };

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

  // OCR Recognition Workflow (Human-in-the-loop Invariant)
  const handleTriggerOCR = useCallback(async () => {
    const penStrokes = getOcrPenStrokes(currentPageMemory.strokes);
    if (penStrokes.length === 0) {
      return;
    }

    setOcrError(null);
    setIsRecognizingOCR(true);

    try {
      // 1. If currently dirty, flush to server first so recognition has latest strokes
      if (currentPageMemory.isDirty) {
        if (saveTimeoutRef.current) {
          clearTimeout(saveTimeoutRef.current);
          saveTimeoutRef.current = null;
        }
        const saved = await ensureLatestInkSaved(true, () =>
          flushSavePage(currentPageIndex, currentPageMemory.strokes),
        );
        if (!saved) {
          setOcrError(
            authExpired
              ? "Phiên đăng nhập đã hết hạn. Giữ trang này mở, mở tab khác đăng nhập lại rồi bấm Thử lại để lưu nét vẽ."
              : "Không thể nhận diện vì nét vẽ chưa được lưu lên máy chủ. Vui lòng lưu lại trước khi thử OCR."
          );
          return;
        }
      }

      // CoMER reads saved pen geometry only, without exercise-text hints.
      const resp = await recognizeHandwrittenMath(penStrokes);

      setOcrData(resp);
      setOcrManualMode(false);
      setOcrSourceStrokes(penStrokes);
      setOcrModalOpen(true);
    } catch (err: unknown) {
      if (err instanceof ApiResponseError || err instanceof ApiNetworkError) {
        setOcrError(
          err instanceof ApiResponseError && (err.status === 401 || err.code === "INVALID_TOKEN")
            ? "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại để lưu nét viết."
            : "Không thể lưu nét viết lên máy chủ. Vui lòng kiểm tra kết nối rồi thử lại.",
        );
      } else {
        setOcrData(null);
        setOcrManualMode(true);
        setOcrSourceStrokes(penStrokes);
        setOcrModalOpen(true);
        setOcrError(
          err instanceof Error && err.message === "OCR_NOT_RECOGNIZED"
            ? "Model chưa đọc được nét viết này. Em có thể nhập công thức theo nét viết gốc."
            : "Không tải được model nhận diện trên trình duyệt. Em vẫn có thể nhập công thức theo nét viết gốc.",
        );
      }
    } finally {
      setIsRecognizingOCR(false);
    }
  }, [
    currentPageMemory.strokes,
    currentPageMemory.isDirty,
    currentPageIndex,
    flushSavePage,
    apiClient,
    accessToken,
    attemptId,
    authExpired,
  ]);

  const handleConfirmStep = useCallback(
    async (stepType: StepKind, latex: string, explanation: string) => {
      setIsSubmittingStep(true);
      setOcrError(null);

      try {
        const expectedRev = attempt?.current_revision ?? 1;
        const updatedAttempt = await apiClient.createMathStep(accessToken, attemptId, {
          expected_attempt_revision: expectedRev,
          client_action_id: generateUuid(),
          step_type: stepType,
          content_latex: latex,
          explanation_text: explanation || null,
        });

        setAttempt(updatedAttempt);
        setOcrModalOpen(false);
        setOcrData(null);
        setOcrManualMode(false);
        setOcrSourceStrokes([]);
      } catch (err: unknown) {
        if (err instanceof ApiResponseError) {
          setOcrError(err.message);
          throw err;
        } else if (err instanceof ApiNetworkError) {
          const msg = "Không thể lưu bước giải: mất kết nối mạng.";
          setOcrError(msg);
          throw new Error(msg);
        } else {
          const msg = "Không thể lưu bước giải.";
          setOcrError(msg);
          throw new Error(msg);
        }
      } finally {
        setIsSubmittingStep(false);
      }
    },
    [attempt?.current_revision, apiClient, accessToken, attemptId],
  );

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
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
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
        </div>

        <PageNavigator
          currentPageIndex={currentPageIndex}
          pageCount={pageCount}
          onSelectPage={handleSelectPage}
          onAddPage={handleAddPage}
          onDeleteCurrentPage={handleDeleteCurrentPage}
          canDeleteCurrentPage={canDeleteCurrentPage}
        />
      </header>

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
        canUndo={currentPageMemory.past.length > 0}
        onUndo={handleUndo}
        canRedo={currentPageMemory.future.length > 0}
        onRedo={handleRedo}
        onClearPage={handleClearPage}
        zoomLevel={zoomLevel}
        onZoomIn={() => setZoomLevel((z) => Math.min(2.0, z + 0.1))}
        onZoomOut={() => setZoomLevel((z) => Math.max(0.6, z - 0.1))}
        onResetZoom={() => setZoomLevel(1.0)}
        onTriggerOCR={handleTriggerOCR}
        isRecognizingOCR={isRecognizingOCR}
        strokeCount={getOcrPenStrokes(currentPageMemory.strokes).length}
      />

      {ocrError && !ocrModalOpen ? (
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
        />

        {/* Right Column: A4 Writing Canvas (65% or expanded) */}
        <section
          className={`${styles.canvasPane} ${isProblemPaneCollapsed ? styles.canvasPaneExpanded : ""}`}
          aria-label="Không gian giấy A4 viết tay"
        >
          <MathCanvas
            strokes={currentPageMemory.strokes}
            onStrokesChange={handleStrokesChange}
            currentTool={currentTool}
            penColor={penColor}
            penWidth={penWidth}
            highlighterWidth={highlighterWidth}
            paperGrid={paperGrid}
            zoomLevel={zoomLevel}
            isReadOnly={attempt?.status === "SUBMITTED"}
          />
        </section>
      </main>

      {/* OCR Confirmation Dialog (Human-in-the-loop Invariant) */}
      <OcrConfirmModal
        isOpen={ocrModalOpen}
        onClose={() => { setOcrModalOpen(false); setOcrManualMode(false); }}
        manualMode={ocrManualMode}
        ocrData={ocrData}
        isSubmitting={isSubmittingStep}
        onConfirmStep={handleConfirmStep}
        sourceStrokes={ocrSourceStrokes}
        errorMessage={ocrError}
      />
    </div>
  );
}
