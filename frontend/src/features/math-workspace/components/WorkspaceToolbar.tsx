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
  RotateCcw,
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
  onOpenVariationTable,
  onTogglePaper,
  paperMode,
  isRecognizingOCR = false,
  strokeCount = 0,
  isReadOnly = false,
  onOpenGraph,
}: WorkspaceToolbarProps) {
  return (
    <div className={styles.toolbar} role="toolbar" aria-label="Thanh công cụ vẽ">
      {/* Group: Primary Tools */}
      <div className={styles.toolGroup}>
        <button type="button" className={`${styles.toolButton} ${currentTool === "lasso" ? styles.active : ""}`}
          onClick={() => onSelectTool("lasso")} title="Khoanh vùng công thức để nhận dạng" aria-pressed={currentTool === "lasso"}>
          <Lasso size={18} /><span className={styles.toolLabel}>Khoanh vùng</span>
        </button>
        {onOpenGraph ? <button type="button" className={styles.toolButton} onClick={onOpenGraph} title="Math View: tự nhận diện và khám phá công thức 2D/3D">
          <Box size={18} /><span className={styles.toolLabel}>Math View 3D</span>
        </button> : null}
        <button
          type="button"
          className={`${styles.toolButton} ${currentTool === "pen" ? styles.active : ""}`}
          onClick={() => onSelectTool("pen")}
          title="Bút viết (P)"
          aria-pressed={currentTool === "pen"}
        >
          <Pen size={18} />
          <span className={styles.toolLabel}>Bút</span>
        </button>

        <button
          type="button"
          className={`${styles.toolButton} ${currentTool === "highlighter" ? styles.active : ""}`}
          onClick={() => onSelectTool("highlighter")}
          title="Bút dạ quang (H)"
          aria-pressed={currentTool === "highlighter"}
        >
          <Highlighter size={18} />
          <span className={styles.toolLabel}>Dạ quang</span>
        </button>

        <button
          type="button"
          className={`${styles.toolButton} ${currentTool === "eraser" ? styles.active : ""}`}
          onClick={() => onSelectTool("eraser")}
          title="Bút xóa nét (E)"
          aria-pressed={currentTool === "eraser"}
        >
          <Eraser size={18} />
          <span className={styles.toolLabel}>Tẩy</span>
        </button>
      </div>

      <div className={styles.divider} />

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
                title={`Độ dày ${w}px`}
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
              title={`Bút dạ ${w}px`}
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

      {/* Group: Paper Grid */}
      <div className={styles.toolGroup}>
        <button
          type="button"
          className={`${styles.iconButton} ${paperGrid === "grid" ? styles.active : ""}`}
          onClick={() => onSelectPaperGrid("grid")}
          title="Lưới ô vuông ca-rô"
        >
          <Grid3X3 size={17} />
        </button>
        <button
          type="button"
          className={`${styles.iconButton} ${paperGrid === "lines" ? styles.active : ""}`}
          onClick={() => onSelectPaperGrid("lines")}
          title="Dòng kẻ ngang"
        >
          <AlignJustify size={17} />
        </button>
        <button
          type="button"
          className={`${styles.iconButton} ${paperGrid === "plain" ? styles.active : ""}`}
          onClick={() => onSelectPaperGrid("plain")}
          title="Giấy trơn không dòng kẻ"
        >
          <File size={17} />
        </button>
      </div>

      <div className={styles.divider} />

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
        <button
          type="button"
          className={`${styles.iconButton} ${styles.dangerButton}`}
          onClick={onClearPage}
          disabled={isReadOnly}
          title="Xóa trắng trang hiện tại"
        >
          <Trash2 size={17} />
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
              onClick={onTriggerOCR}
              disabled={isRecognizingOCR || strokeCount === 0}
              title={
                strokeCount === 0
                  ? "Vẽ công thức lên trang để nhận diện"
                  : "Chia trang viết thành các bước giải để em kiểm tra"
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
                  <span>Trích xuất trang</span>
                </>
              )}
            </button>
          </div>
        </>
      )}

      {onOpenVariationTable ? (
        <>
          <div className={styles.divider} />
          <div className={styles.toolGroup}>
            <button type="button" className={styles.ocrButton} onClick={onOpenVariationTable}
              title={"Tạo bảng biến thiên bằng cách điền các ô"}>
              <Table2 size={16} aria-hidden="true" />
              <span>{"Bảng biến thiên"}</span>
            </button>
          </div>
        </>
      ) : null}

      <div className={styles.divider} />
      <div className={styles.toolGroup}>
        <button type="button" className={`${styles.ocrButton} ${paperMode ? styles.active : ""}`}
          onClick={onTogglePaper} aria-pressed={paperMode} title="Tải ảnh hoặc PDF bài viết trên giấy">
          <Upload size={16} aria-hidden="true" />
          <span>{paperMode ? "Về giấy số" : "Tải bài giấy"}</span>
        </button>
      </div>

      <div className={styles.divider} />

      {/* Group: Zoom Controls */}
      <div className={styles.toolGroup}>
        <button
          type="button"
          className={styles.iconButton}
          onClick={onZoomOut}
          disabled={zoomLevel <= 0.6}
          title="Thu nhỏ"
        >
          <ZoomOut size={16} />
        </button>
        <button
          type="button"
          className={styles.zoomIndicator}
          onClick={onResetZoom}
          title="Đặt lại phóng to 100%"
        >
          {Math.round(zoomLevel * 100)}%
        </button>
        <button
          type="button"
          className={styles.iconButton}
          onClick={onZoomIn}
          disabled={zoomLevel >= 2.0}
          title="Phóng to"
        >
          <ZoomIn size={16} />
        </button>
      </div>
    </div>
  );
}
