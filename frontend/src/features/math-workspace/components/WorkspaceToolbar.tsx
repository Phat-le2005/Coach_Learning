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
}: WorkspaceToolbarProps) {
  return (
    <div className={styles.toolbar} role="toolbar" aria-label="Thanh công cụ vẽ">
      {/* Group: Primary Tools */}
      <div className={styles.toolGroup}>
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
          title="Xóa trắng trang hiện tại"
        >
          <Trash2 size={17} />
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
