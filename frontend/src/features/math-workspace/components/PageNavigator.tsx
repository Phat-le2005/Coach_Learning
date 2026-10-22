"use client";

import React from "react";
import { ChevronLeft, ChevronRight, Plus, Trash2 } from "lucide-react";
import { MAX_PAGES } from "../types";
import styles from "../MathWorkspace.module.css";

interface PageNavigatorProps {
  currentPageIndex: number;
  pageCount: number;
  onSelectPage: (index: number) => void;
  onAddPage: () => void;
  onDeleteCurrentPage: () => void;
  canDeleteCurrentPage: boolean;
}

export function PageNavigator({
  currentPageIndex,
  pageCount,
  onSelectPage,
  onAddPage,
  onDeleteCurrentPage,
  canDeleteCurrentPage,
}: PageNavigatorProps) {
  const isFirstPage = currentPageIndex === 0;
  const isLastPage = currentPageIndex === pageCount - 1;
  const canAddPage = pageCount < MAX_PAGES;

  return (
    <nav className={styles.pageNavigator} aria-label="Điều hướng các trang giải bài">
      <div className={styles.navControls}>
        <button
          type="button"
          className={styles.navButton}
          onClick={() => onSelectPage(currentPageIndex - 1)}
          disabled={isFirstPage}
          title="Trang trước (Phím [)"
          aria-label="Trang trước"
        >
          <ChevronLeft size={18} />
        </button>

        <div className={styles.pageIndicator}>
          <span className={styles.currentNumber}>{currentPageIndex + 1}</span>
          <span className={styles.slash}>/</span>
          <span className={styles.totalNumber}>{pageCount}</span>
        </div>

        <button
          type="button"
          className={styles.navButton}
          onClick={() => onSelectPage(currentPageIndex + 1)}
          disabled={isLastPage}
          title="Trang sau (Phím ])"
          aria-label="Trang sau"
        >
          <ChevronRight size={18} />
        </button>
      </div>

      {/* Page Tabs */}
      <div className={styles.pageTabsContainer}>
        {Array.from({ length: pageCount }).map((_, i) => (
          <button
            key={i}
            type="button"
            className={`${styles.pageTab} ${i === currentPageIndex ? styles.activePageTab : ""}`}
            onClick={() => onSelectPage(i)}
            title={`Chuyển đến trang ${i + 1}`}
          >
            {i + 1}
          </button>
        ))}
      </div>

      <div className={styles.navActions}>
        <button
          type="button"
          className={styles.addPageButton}
          onClick={onAddPage}
          disabled={!canAddPage}
          title={canAddPage ? "Thêm trang mới (Tối đa 30 trang)" : "Đã đạt giới hạn tối đa 30 trang"}
        >
          <Plus size={16} />
          <span>Thêm trang</span>
        </button>

        {canDeleteCurrentPage && (
          <button
            type="button"
            className={styles.deletePageButton}
            onClick={onDeleteCurrentPage}
            title="Xóa trang hiện tại"
            aria-label="Xóa trang hiện tại"
          >
            <Trash2 size={15} />
          </button>
        )}
      </div>
    </nav>
  );
}
