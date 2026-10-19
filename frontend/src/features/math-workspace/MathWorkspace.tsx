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
    Math.max(1, initialDocument?.pages?.length ?? 1),
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

  // OCR recognition & confirmation state
  const [isRecognizingOCR, setIsRecognizingOCR] = useState(false);
  const [ocrModalOpen, setOcrModalOpen] = useState(false);
  const [ocrData, setOcrData] = useState<OCRRecognizeResponse | null>(null);
  const [ocrSourcePageIndex, setOcrSourcePageIndex] = useState<number | null>(null);
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
          revisionRef.current = doc.document_revision;
          setDocumentRevision(doc.document_revision);
          if (doc.pages.length > 0) {
            setPageCount(doc.pages.length);
          }
        })
        .catch(() => {});
    }
  }, [attemptId, accessToken, problem, attempt, initialDocument, apiClient]);

  // 2. Perform server save
  const flushSavePage = useCallback(
    (pageIdx: number, strokesToSave: InkStroke[]): Promise<boolean> => {
      const operation = async (): Promise<boolean> => {
        if (latestStrokesRef.current.get(pageIdx) !== strokesToSave) return false;
        setSyncStatus("saving");
        setSyncErrorMessage(undefined);
        const clientActionId = generateUuid();
        const revision = revisionRef.current;
        try {
          await mathInkStorage.savePageDraft(
            attemptId, pageIdx, strokesToSave, revision, clientActionId, true,
          );
          const response = await apiClient.saveMathInkPage(
            accessToken, attemptId, pageIdx,
            {
              expected_document_revision: revision,
              client_action_id: clientActionId,
              strokes: strokesToSave,
            },
          );
          revisionRef.current = response.document_revision;
          setDocumentRevision(response.document_revision);
          const matched = await mathInkStorage.markPageClean(
            attemptId, pageIdx, response.document_revision, clientActionId,
          );
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
          setSyncStatus("saved");
          return true;
        } catch (err: unknown) {
          if (err instanceof ApiResponseError && err.status === 409) {
            setSyncStatus("conflict");
            setSyncErrorMessage("Phiên bản trên máy chủ đã thay đổi.");
          } else if (err instanceof ApiResponseError) {
            setSyncStatus("error");
            setSyncErrorMessage(err.message);
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
          setOcrError("Không thể nhận diện vì nét vẽ chưa được lưu lên máy chủ. Vui lòng lưu lại trước khi thử OCR.");
          return;
        }
      }

      // 2. Call OCR recognition
      const resp = await apiClient.recognizeMathInk(accessToken, attemptId, {
        page_index: currentPageIndex,
        stroke_ids: penStrokes.map((stroke) => stroke.id),
      });

      setOcrData(resp);
      setOcrSourcePageIndex(currentPageIndex);
      setOcrSourceStrokes(penStrokes);
      setOcrModalOpen(true);
    } catch (err: unknown) {
      if (err instanceof ApiResponseError) {
        setOcrError(err.message);
      } else if (err instanceof ApiNetworkError) {
        setOcrError("Không thể kết nối đến máy chủ nhận diện. Vui lòng kiểm tra mạng.");
      } else {
        setOcrError("Lỗi nhận diện nét vẽ. Vui lòng thử lại.");
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
  ]);

  const handleRequestOcrAlternatives = useCallback(async (): Promise<string[]> => {
    if (ocrSourcePageIndex === null || ocrSourceStrokes.length === 0) {
      throw new Error("No original pen strokes available for OCR retry.");
    }
    const response = await apiClient.recognizeMathInk(accessToken, attemptId, {
      page_index: ocrSourcePageIndex,
      stroke_ids: ocrSourceStrokes.map((stroke) => stroke.id),
      include_alternatives: true,
    });
    return [response.latex, ...response.alternative_latex];
  }, [ocrSourcePageIndex, ocrSourceStrokes, apiClient, accessToken, attemptId]);

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
        setOcrSourcePageIndex(null);
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

  // 3. Handle strokes update with Undo stack & autosave debounce
  const handleStrokesChange = useCallback(
    (newStrokes: InkStroke[]) => {
      latestStrokesRef.current.set(currentPageIndex, newStrokes);
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

      setSyncStatus("unsaved");

      // Save draft immediately to IndexedDB
      mathInkStorage.savePageDraft(
        attemptId,
        currentPageIndex,
        newStrokes,
        documentRevision,
        generateUuid(),
        true,
      );

      // Debounce network save (1.5s)
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
      saveTimeoutRef.current = setTimeout(() => {
        flushSavePage(currentPageIndex, newStrokes);
      }, 1500);
    },
    [currentPageIndex, attemptId, documentRevision, flushSavePage],
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

    handleStrokesChange(previousStrokes);
  }, [currentPageMemory, currentPageIndex, handleStrokesChange]);

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

    handleStrokesChange(nextStrokes);
  }, [currentPageMemory, currentPageIndex, handleStrokesChange]);

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

      // If current page is dirty, flush save before leaving
      if (currentPageMemory.isDirty) {
        if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
        flushSavePage(currentPageIndex, currentPageMemory.strokes);
      }

      // Load target page data if not present in memory
      if (!pagesMap.has(targetIndex)) {
        // Check IndexedDB draft first
        const offlineDraft = await mathInkStorage.getPageDraft(attemptId, targetIndex);
        if (offlineDraft) {
          latestStrokesRef.current.set(targetIndex, offlineDraft.strokes);
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
          // Fetch from server
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
          } catch {
            // New empty page
            setPagesMap((prev) => {
              const updated = new Map(prev);
              updated.set(targetIndex, {
                strokes: [],
                past: [],
                future: [],
                isDirty: false,
              });
              return updated;
            });
          }
        }
      }

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

  const handleAddPage = useCallback(() => {
    if (pageCount >= MAX_PAGES) return;
    const newIndex = pageCount;
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
  }, [pageCount]);

  const handleDeleteCurrentPage = useCallback(() => {
    if (pageCount <= 1) return;
    if (!window.confirm(`Bạn có chắc muốn xóa trang ${currentPageIndex + 1}?`)) return;

    setPagesMap((prev) => {
      const updated = new Map<number, PageMemory>();
      let newIdx = 0;
      for (let i = 0; i < pageCount; i++) {
        if (i !== currentPageIndex) {
          const mem = prev.get(i) ?? { strokes: [], past: [], future: [], isDirty: false };
          updated.set(newIdx, mem);
          newIdx++;
        }
      }
      return updated;
    });

    setPageCount((c) => c - 1);
    setCurrentPageIndex((i) => Math.max(0, i - 1));
  }, [pageCount, currentPageIndex]);

  // 6. Conflict Resolution
  const handleResolveConflict = useCallback(async () => {
    try {
      const doc = await apiClient.getMathInkDocument(accessToken, attemptId);
      revisionRef.current = doc.document_revision;
      setDocumentRevision(doc.document_revision);
      const pageData = await apiClient.getMathInkPage(
        accessToken,
        attemptId,
        currentPageIndex,
      );

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
            onRetry={() => flushSavePage(currentPageIndex, currentPageMemory.strokes)}
            onResolveConflict={handleResolveConflict}
          />
        </div>

        <PageNavigator
          currentPageIndex={currentPageIndex}
          pageCount={pageCount}
          onSelectPage={handleSelectPage}
          onAddPage={handleAddPage}
          onDeleteCurrentPage={handleDeleteCurrentPage}
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
        onClose={() => setOcrModalOpen(false)}
        ocrData={ocrData}
        isSubmitting={isSubmittingStep}
        onConfirmStep={handleConfirmStep}
        onRequestAlternatives={handleRequestOcrAlternatives}
        sourceStrokes={ocrSourceStrokes}
        errorMessage={ocrError}
      />
    </div>
  );
}
