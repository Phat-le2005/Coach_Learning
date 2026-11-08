"use client";

import React from "react";
import {
  Pen,
  Highlighter,
  Eraser,
  Undo2,
  Redo2,
  Trash2,
  Grid3X3,
  AlignJustify,
  File,
  ZoomIn,
  ZoomOut,
  ChevronDown,
  SlidersHorizontal,
  Sparkles,
  Table2,
  Upload,
  Loader2,
  Lasso,
  Box,
} from "lucide-react";
import type { DrawingTool, PaperGrid } from "../types";
import {
  PEN_WIDTHS,
  HIGHLIGHTER_WIDTHS,
  WORKSPACE_COLORS,
} from "../types";
import styles from "../MathWorkspace.module.css";

interface WorkspaceToolbarProps {
  currentTool: DrawingTool;
  onSelectTool: (tool: DrawingTool) => void;
  penColor: string;
  onSelectPenColor: (color: string) => void;
  penWidth: number;
  onSelectPenWidth: (width: number) => void;
  highlighterWidth: number;
  onSelectHighlighterWidth: (width: number) => void;
  paperGrid: PaperGrid;
  onSelectPaperGrid: (grid: PaperGrid) => void;
  canUndo: boolean;
  onUndo: () => void;
  canRedo: boolean;
  onRedo: () => void;
  onClearPage: () => void;
  zoomLevel: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onResetZoom: () => void;
  onTriggerOCR?: () => void;
  ocrBlocked?: boolean;
  onOpenVariationTable?: () => void;
  onTogglePaper: () => void;
  paperMode: boolean;
  isRecognizingOCR?: boolean;
  strokeCount?: number;
  isReadOnly?: boolean;
  onOpenGraph?: () => void;
}

export function WorkspaceToolbar({
  currentTool,
  onSelectTool,
  penColor,
  onSelectPenColor,
  penWidth,
  onSelectPenWidth,
  highlighterWidth,
  onSelectHighlighterWidth,
  paperGrid,
  onSelectPaperGrid,
  canUndo,
  onUndo,
  canRedo,
  onRedo,
  onClearPage,
  zoomLevel,
  onZoomIn,
  onZoomOut,
  onResetZoom,
  onTriggerOCR,
  ocrBlocked,
  onOpenVariationTable,
  onTogglePaper,
  paperMode,
  isRecognizingOCR = false,
  strokeCount = 0,
  isReadOnly = false,
  onOpenGraph,
}: WorkspaceToolbarProps) {
  const toolsRef = React.useRef<HTMLDetailsElement>(null);
  const penRef = React.useRef<HTMLDetailsElement>(null);
  const closeTools = () => { if (toolsRef.current) toolsRef.current.open = false; };
  React.useEffect(() => {
    const panels = [toolsRef, penRef];
    const outside = (event: PointerEvent) => {
      for (const ref of panels) if (ref.current?.open && event.target instanceof Node && !ref.current.contains(event.target)) ref.current.open = false;
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      for (const ref of panels) if (ref.current?.open) {
        const containsFocus = ref.current.contains(document.activeElement);
        ref.current.open = false;
        if (containsFocus) ref.current.querySelector<HTMLElement>("summary")?.focus();
      }
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, []);
  return (
    <div className={styles.toolbar} role="group" aria-label="Thanh công cụ vẽ">
      <div className={styles.toolbarMain} role="group" aria-label="Bút và chỉnh sửa nét">
        {/* Group: Primary Tools */}
        <div className={styles.toolGroup}>
          <button
            type="button"
            className={`${styles.toolButton} ${currentTool === "pen" ? styles.active : ""}`}
            onClick={() => onSelectTool("pen")} aria-label="Bút"
            title="Bút viết (P)"
            aria-pressed={currentTool === "pen"}
          >
            <Pen size={18} />
            <span className={styles.toolLabel}>Bút</span>
          </button>

          <button
            type="button"
            className={`${styles.toolButton} ${currentTool === "highlighter" ? styles.active : ""}`}
            onClick={() => onSelectTool("highlighter")} aria-label="Dạ quang"
            title="Bút dạ quang (H)"
            aria-pressed={currentTool === "highlighter"}
          >
            <Highlighter size={18} />
            <span className={styles.toolLabel}>Dạ quang</span>
          </button>

          <button
            type="button"
            className={`${styles.toolButton} ${currentTool === "eraser" ? styles.active : ""}`}
            onClick={() => onSelectTool("eraser")} aria-label="Tẩy"
            title="Bút xóa nét (E)"
            aria-pressed={currentTool === "eraser"}
          >
            <Eraser size={18} />
            <span className={styles.toolLabel}>Tẩy</span>
          </button>
        </div>

        <div className={styles.divider} />

        {(currentTool === "pen" || currentTool === "highlighter") && <details ref={penRef} className={styles.penSettings}>
          <summary aria-label="Màu và độ dày bút"><SlidersHorizontal size={18} aria-hidden="true" /><span>Màu &amp; nét</span></summary>
          <div className={styles.penSettingsBody}>
        {/* Group: Pen / Highlighter Attributes */}
        {currentTool === "pen" && (
          <>
            {/* Colors */}
            <div className={styles.toolGroup}>
              {WORKSPACE_COLORS.map((c) => (
                <button
                  key={c.value}
                  type="button"
                  className={`${styles.colorSwatch} ${penColor === c.value ? styles.activeColor : ""}`}
                  style={{ backgroundColor: c.value }}
                  onClick={() => onSelectPenColor(c.value)}
                  title={c.name}
                  aria-label={`Màu ${c.name}`}
                />
              ))}
            </div>

            <div className={styles.divider} />

            {/* Widths */}
            <div className={styles.toolGroup}>
              {PEN_WIDTHS.map((w) => (
                <button
                  key={w}
                  type="button"
                  className={`${styles.widthButton} ${penWidth === w ? styles.active : ""}`}
                  onClick={() => onSelectPenWidth(w)}
                  title={`Độ dày ${w}px`} aria-label={`Độ dày ${w}px`} aria-pressed={penWidth === w}
                >
                  <span
                    className={styles.widthPreview}
                    style={{ width: Math.max(3, w * 1.5), height: Math.max(3, w * 1.5) }}
                  />
                </button>
              ))}
            </div>
          </>
        )}

        {currentTool === "highlighter" && (
          <div className={styles.toolGroup}>
            {HIGHLIGHTER_WIDTHS.map((w) => (
              <button
                key={w}
                type="button"
                className={`${styles.widthButton} ${highlighterWidth === w ? styles.active : ""}`}
                onClick={() => onSelectHighlighterWidth(w)}
                title={`Bút dạ ${w}px`} aria-label={`Bút dạ ${w}px`} aria-pressed={highlighterWidth === w}
              >
                <span
                  className={styles.highlighterPreview}
                  style={{ width: w / 2, height: 14 }}
                />
              </button>
            ))}
          </div>
        )}

        <div className={styles.divider} />

          </div>
        </details>}

        {/* Group: Undo / Redo / Clear */}
        <div className={styles.toolGroup}>
          <button
            type="button"
            className={styles.iconButton}
            onClick={onUndo}
            disabled={!canUndo}
            title="Hoàn tác (Ctrl+Z)"
          >
            <Undo2 size={17} />
          </button>
          <button
            type="button"
            className={styles.iconButton}
            onClick={onRedo}
            disabled={!canRedo}
            title="Làm lại (Ctrl+Y)"
          >
            <Redo2 size={17} />
          </button>

        </div>

        {/* Group: AI OCR Recognition */}
        {onTriggerOCR && (
          <>
            <div className={styles.divider} />
            <div className={styles.toolGroup}>
              <button
                type="button"
                className={styles.ocrButton}
                aria-label={isRecognizingOCR ? "Đang lưu trang..." : "Trích xuất trang"}
                onClick={onTriggerOCR}
                disabled={ocrBlocked || isRecognizingOCR || strokeCount === 0}
                title={
                  ocrBlocked
                    ? "Chờ đồng bộ nét viết hoặc hoàn tất bản chép đang mở"
                    : strokeCount === 0
                      ? "Vẽ công thức lên trang để nhận diện"
                      : "Nhận diện bản chép OCR V2 để em kiểm tra"
                }
              >
                {isRecognizingOCR ? (
                  <>
                    <Loader2 className={styles.spinIcon} size={15} />
                    <span>Đang lưu trang...</span>
                  </>
                ) : (
                  <>
                    <Sparkles size={15} />
                    <span className={styles.ocrFullLabel}>Trích xuất trang</span><span className={styles.ocrShortLabel}>Trích xuất</span>
                  </>
                )}
              </button>
            </div>
          </>
        )}

      </div>
      <details ref={toolsRef} className={styles.toolbarMore}>
        <summary>Công cụ toán &amp; giấy <ChevronDown size={16} aria-hidden="true" /></summary>
        <div className={styles.toolbarSecondary} role="group" aria-label="Nhận dạng, giấy và góc nhìn">
          <section className={styles.toolbarSection} aria-label="Công cụ toán">
            <h2>Công cụ toán</h2>
            <div className={styles.toolGroup}>
              <button type="button" className={`${styles.toolButton} ${currentTool === "lasso" ? styles.active : ""}`}
                onClick={() => { closeTools(); onSelectTool("lasso"); }} title="Khoanh vùng công thức để nhận dạng" aria-pressed={currentTool === "lasso"}>
                <Lasso size={18} /><span>Khoanh vùng</span>
              </button>
              {onOpenGraph && <button type="button" className={styles.toolButton} onClick={() => { closeTools(); onOpenGraph(); }} title="Khám phá công thức 2D/3D">
                <Box size={18} /><span>Math View</span>
              </button>}
              {onOpenVariationTable && <button type="button" className={styles.toolButton} onClick={() => { closeTools(); onOpenVariationTable(); }} title="Tạo bảng biến thiên bằng cách điền các ô">
                <Table2 size={17} aria-hidden="true" /><span>Bảng biến thiên</span>
              </button>}
            </div>
          </section>
          <section className={styles.toolbarSection} aria-label="Giấy viết">
            <h2>Giấy viết</h2>
            <div className={styles.toolGroup}>
              <button type="button" className={`${styles.iconButton} ${paperGrid === "grid" ? styles.active : ""}`} onClick={() => onSelectPaperGrid("grid")} title="Lưới ô vuông ca-rô" aria-label="Lưới ô vuông ca-rô" aria-pressed={paperGrid === "grid"}><Grid3X3 size={17} /></button>
              <button type="button" className={`${styles.iconButton} ${paperGrid === "lines" ? styles.active : ""}`} onClick={() => onSelectPaperGrid("lines")} title="Dòng kẻ ngang" aria-label="Dòng kẻ ngang" aria-pressed={paperGrid === "lines"}><AlignJustify size={17} /></button>
              <button type="button" className={`${styles.iconButton} ${paperGrid === "plain" ? styles.active : ""}`} onClick={() => onSelectPaperGrid("plain")} title="Giấy trơn không dòng kẻ" aria-label="Giấy trơn không dòng kẻ" aria-pressed={paperGrid === "plain"}><File size={17} /></button>
              <button type="button" className={`${styles.toolButton} ${paperMode ? styles.active : ""}`} onClick={() => { closeTools(); onTogglePaper(); }} aria-pressed={paperMode} title="Tải ảnh hoặc PDF bài viết trên giấy"><Upload size={17} aria-hidden="true" /><span>{paperMode ? "Về giấy số" : "Tải bài giấy"}</span></button>
            </div>
          </section>
          <div className={styles.toolbarViewRow}>
            <div className={styles.toolGroup} aria-label="Phóng to và thu nhỏ">
              <button type="button" className={styles.iconButton} onClick={onZoomOut} disabled={zoomLevel <= 0.6} title="Thu nhỏ" aria-label="Thu nhỏ"><ZoomOut size={16} /></button>
              <button type="button" className={styles.zoomIndicator} onClick={onResetZoom} title="Đặt lại phóng to 100%">{Math.round(zoomLevel * 100)}%</button>
              <button type="button" className={styles.iconButton} onClick={onZoomIn} disabled={zoomLevel >= 2.0} title="Phóng to" aria-label="Phóng to"><ZoomIn size={16} /></button>
            </div>
            <button type="button" className={`${styles.toolButton} ${styles.dangerButton}`} onClick={onClearPage} disabled={isReadOnly} title="Xóa trắng trang hiện tại"><Trash2 size={16} aria-hidden="true" /><span>Xóa trang</span></button>
          </div>
        </div>
      </details>
    </div>
  );
}
