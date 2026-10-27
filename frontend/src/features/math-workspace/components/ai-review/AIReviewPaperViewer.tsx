"use client";

import React, { useEffect, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  FileImage,
  PenTool,
  Sparkles,
} from "lucide-react";
import {
  API_PATHS,
  type ApiClient,
  type PaperAttachmentRead,
} from "@/lib/api/client";
import type { SolutionStepRead } from "@/lib/api/contracts";
import type { InkStroke } from "../../types";
import { MathCanvas } from "../MathCanvas";
import { OcrMathPreview } from "../OcrMathPreview";
import styles from "./AIReview.module.css";

interface AIReviewPaperViewerProps {
  attemptId: string;
  accessToken: string;
  apiClient: ApiClient;
  pages: Record<number, InkStroke[]>;
  initialPageIndex: number;
  activeStep: SolutionStepRead | undefined;
  activeStepIndex: number | null;
  isScanning?: boolean;
  isRevealing?: boolean;
}

const noopStrokesChange = () => {};

export function AIReviewPaperViewer({
  attemptId,
  accessToken,
  apiClient,
  pages,
  initialPageIndex,
  activeStep,
  activeStepIndex,
  isScanning = false,
  isRevealing = false,
}: AIReviewPaperViewerProps) {
  const pageIndices = Object.keys(pages)
    .map(Number)
    .filter((n) => !Number.isNaN(n))
    .sort((a, b) => a - b);
  const availablePages = pageIndices.length > 0 ? pageIndices : [0];
  const hasAnyInkStrokes = availablePages.some(
    (idx) => (pages[idx]?.length ?? 0) > 0,
  );

  const [currentPageIdx, setCurrentPageIdx] = useState<number>(
    availablePages.includes(initialPageIndex)
      ? initialPageIndex
      : (availablePages[0] ?? 0),
  );
  const [paperFiles, setPaperFiles] = useState<PaperAttachmentRead[]>([]);
  const [selectedPaperId, setSelectedPaperId] = useState<string | null>(null);
  const [viewerSource, setViewerSource] = useState<"canvas" | "paper">(
    "canvas",
  );
  const [zoomPercent, setZoomPercent] = useState<number>(100);

  useEffect(() => {
    let active = true;
    apiClient
      .listMathPaper(accessToken, attemptId)
      .then((list) => {
        if (!active) return;
        setPaperFiles(list);
        if (list.length > 0) {
          setSelectedPaperId(list[0]!.id);
          if (!hasAnyInkStrokes) {
            setViewerSource("paper");
          }
        }
      })
      .catch(() => {
        // Keep viewer functional on canvas even if paper listing fails
      });
    return () => {
      active = false;
    };
  }, [apiClient, accessToken, attemptId, hasAnyInkStrokes]);

  const selectedPaper =
    paperFiles.find((item) => item.id === selectedPaperId) ??
    paperFiles[0] ??
    null;

  const currentStrokes = pages[currentPageIdx] ?? [];
  const pagePos = availablePages.indexOf(currentPageIdx);
  const canPrevPage = pagePos > 0;
  const canNextPage = pagePos >= 0 && pagePos < availablePages.length - 1;

  const showLaserScanner = isScanning || isRevealing;

  return (
    <div className={styles.viewerColumn} aria-label="Bài viết của học sinh">
      <div className={styles.viewerToolbar}>
        <div className={styles.viewerModeSwitch}>
          <button
            type="button"
            onClick={() => setViewerSource("canvas")}
            className={`${styles.viewerModeBtn} ${
              viewerSource === "canvas" ? styles.viewerModeBtnActive : ""
            }`}
          >
            <PenTool
              size={13}
              style={{ marginRight: 5, verticalAlign: "middle" }}
            />
            Giấy viết số ({availablePages.length} trang)
          </button>
          {paperFiles.length > 0 && (
            <button
              type="button"
              onClick={() => setViewerSource("paper")}
              className={`${styles.viewerModeBtn} ${
                viewerSource === "paper" ? styles.viewerModeBtnActive : ""
              }`}
            >
              <FileImage
                size={13}
                style={{ marginRight: 5, verticalAlign: "middle" }}
              />
              Ảnh bài chụp ({paperFiles.length})
            </button>
          )}
        </div>

        <div className={styles.viewerNavControls}>
          {viewerSource === "canvas" && availablePages.length > 1 && (
            <>
              <button
                type="button"
                disabled={!canPrevPage}
                onClick={() => {
                  if (canPrevPage) {
                    setCurrentPageIdx(availablePages[pagePos - 1]!);
                  }
                }}
                className={styles.controlIconBtn}
                aria-label="Trang giấy trước"
              >
                <ChevronLeft size={14} />
              </button>
              <span className={styles.progressCountBadge}>
                Trang {currentPageIdx + 1} / {availablePages.length}
              </span>
              <button
                type="button"
                disabled={!canNextPage}
                onClick={() => {
                  if (canNextPage) {
                    setCurrentPageIdx(availablePages[pagePos + 1]!);
                  }
                }}
                className={styles.controlIconBtn}
                aria-label="Trang giấy tiếp"
              >
                <ChevronRight size={14} />
              </button>
            </>
          )}

          {viewerSource === "paper" && paperFiles.length > 1 && (
            <select
              value={selectedPaper?.id ?? ""}
              onChange={(e) => setSelectedPaperId(e.target.value)}
              className={styles.controlIconBtn}
              aria-label="Chọn tệp ảnh bài làm"
            >
              {paperFiles.map((file, i) => (
                <option key={file.id} value={file.id}>
                  Tệp {i + 1}: {file.file_name}
                </option>
              ))}
            </select>
          )}

          <button
            type="button"
            onClick={() => setZoomPercent((z) => Math.max(75, z - 25))}
            disabled={zoomPercent <= 75}
            className={styles.controlIconBtn}
            aria-label="Thu nhỏ bài viết"
            title="Thu nhỏ"
          >
            <ZoomOut size={14} />
          </button>
          <span className={styles.progressCountBadge}>{zoomPercent}%</span>
          <button
            type="button"
            onClick={() => setZoomPercent((z) => Math.min(200, z + 25))}
            disabled={zoomPercent >= 200}
            className={styles.controlIconBtn}
            aria-label="Phóng to bài viết"
            title="Phóng to"
          >
            <ZoomIn size={14} />
          </button>
          {zoomPercent !== 100 && (
            <button
              type="button"
              onClick={() => setZoomPercent(100)}
              className={styles.controlIconBtn}
              title="Đặt lại tỉ lệ 100%"
            >
              <RotateCcw size={13} />
            </button>
          )}
        </div>
      </div>

      {activeStepIndex !== null && (
        <div className={styles.viewerContextBar}>
          <div className={styles.viewerContextInfo}>
            <span className={styles.viewerContextStepTag}>
              Đang đối chiếu Bước {activeStepIndex}
            </span>
            {activeStep?.content_latex ? (
              <div className={styles.viewerContextFormula}>
                <OcrMathPreview latex={activeStep.content_latex} />
              </div>
            ) : activeStep?.explanation_text ? (
              <span className={styles.viewerContextFormula}>
                {activeStep.explanation_text}
              </span>
            ) : (
              <span className={styles.viewerContextHint}>
                Quan sát bài viết gốc để đối chiếu với nhận xét bên trái
              </span>
            )}
          </div>
          <span className={styles.viewerContextHint}>
            Chế độ chỉ đọc (Giữ nguyên bài viết gốc)
          </span>
        </div>
      )}

      <div className={styles.viewerCanvasStage}>
        <div
          className={`${styles.viewerStageInner} ${
            showLaserScanner ? styles.viewerStageInnerScanning : ""
          }`}
        >
          {showLaserScanner && (
            <div className={styles.paperScannerOverlay} aria-hidden="true">
              <div className={styles.laserBeamLine} />
              <div className={styles.scannerHudBadge}>
                <Sparkles size={14} />
                <span>
                  {isScanning
                    ? "AI Vision đang quét nét viết & cấu trúc lời giải..."
                    : activeStepIndex !== null
                      ? `Đang đối chiếu Bước ${activeStepIndex} trên bài viết...`
                      : "Đang trình chiếu kết quả từng bước..."}
                </span>
              </div>
            </div>
          )}

          {viewerSource === "canvas" ? (
            <MathCanvas
              strokes={currentStrokes}
              onStrokesChange={noopStrokesChange}
              currentTool="pen"
              penColor="#1e293b"
              penWidth={2.5}
              highlighterWidth={18}
              paperGrid="grid"
              zoomLevel={zoomPercent / 100}
              isReadOnly={true}
            />
          ) : selectedPaper ? (
            <div className={styles.paperImageScroll}>
              {selectedPaper.content_type === "application/pdf" ? (
                <iframe
                  title={selectedPaper.file_name}
                  src={API_PATHS.mathPaperFile(attemptId, selectedPaper.id)}
                  style={{
                    width: "100%",
                    minHeight: "520px",
                    border: "none",
                  }}
                />
              ) : (
                <div
                  className={styles.paperImageFrame}
                  style={{
                    transform: `scale(${zoomPercent / 100})`,
                  }}
                >
                  <img
                    src={API_PATHS.mathPaperFile(attemptId, selectedPaper.id)}
                    alt={`Bài viết tay: ${selectedPaper.file_name}`}
                  />
                </div>
              )}
            </div>
          ) : (
            <div className={styles.emptyViewerNotice}>
              Chưa có ảnh bài chụp cho lượt làm bài này. Bạn có thể chuyển sang tab Giấy viết số.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
