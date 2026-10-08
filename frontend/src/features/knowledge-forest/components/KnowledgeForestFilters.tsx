"use client";

import { ChevronsDownUp, ChevronsUpDown, RotateCcw, Search, X } from "lucide-react";

import { STATUS_FILTERS } from "../copy";
import type { KnowledgeStatusFilter } from "../types";
import styles from "../KnowledgeForest.module.css";

export interface KnowledgeForestFiltersProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  statusFilter: KnowledgeStatusFilter;
  onStatusFilterChange: (status: KnowledgeStatusFilter) => void;
  allExpanded: boolean;
  onToggleExpandAll: () => void;
  matchCount?: number;
  isFiltered?: boolean;
  onResetFilters?: () => void;
}

export function KnowledgeForestFilters({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  allExpanded,
  onToggleExpandAll,
  matchCount,
  isFiltered,
  onResetFilters,
}: KnowledgeForestFiltersProps) {
  return (
    <div className={styles.toolbar} role="search" aria-label="Bộ lọc và tìm kiếm tri thức">
      <div className={styles.toolbarTop}>
        <div className={styles.searchWrap}>
          <Search className={styles.searchIcon} size={17} aria-hidden="true" />
          <input
            id="knowledge-search-input"
            type="search"
            className={styles.searchInput}
            placeholder="Tìm theo tên dạng bài, chủ đề, chương hoặc mã kiến thức..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label="Tìm kiếm kiến thức"
          />
          {searchQuery ? (
            <button
              type="button"
              className={styles.searchClear}
              onClick={() => onSearchChange("")}
              aria-label="Xóa từ khóa tìm kiếm"
            >
              <X size={14} />
            </button>
          ) : null}
        </div>

        <div className={styles.toolbarActions}>
          {isFiltered && matchCount !== undefined ? (
            <span className={styles.filterResultsPill} aria-live="polite">
              {matchCount} kết quả
            </span>
          ) : null}

          {isFiltered && onResetFilters ? (
            <button
              type="button"
              className={styles.filterClearBtn}
              onClick={onResetFilters}
              aria-label="Xóa tất cả bộ lọc và tìm kiếm"
            >
              <RotateCcw size={13} aria-hidden="true" />
              <span>Xóa lọc</span>
            </button>
          ) : null}

          <button
            type="button"
            className={styles.toggleExpandBtn}
            onClick={onToggleExpandAll}
            aria-label={allExpanded ? "Thu gọn tất cả chương" : "Mở rộng tất cả chương"}
          >
            {allExpanded ? (
              <>
                <ChevronsDownUp size={15} aria-hidden="true" />
                <span>Thu gọn tất cả</span>
              </>
            ) : (
              <>
                <ChevronsUpDown size={15} aria-hidden="true" />
                <span>Mở rộng tất cả</span>
              </>
            )}
          </button>
        </div>
      </div>

      <div className={styles.filterPills} role="group" aria-label="Lọc theo trạng thái học tập">
        {STATUS_FILTERS.map((item) => {
          const isActive = statusFilter === item.id;
          return (
            <button
              key={item.id}
              type="button"
              className={`${styles.filterPill} ${isActive ? styles.filterPillActive : ""}`}
              onClick={() => onStatusFilterChange(item.id)}
              aria-pressed={isActive}
            >
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
