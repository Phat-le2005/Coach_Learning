"use client";

import { RotateCcw, Search, X } from "lucide-react";

import { STATUS_FILTERS } from "../copy";
import type { KnowledgeStatusFilter } from "../types";
import styles from "../KnowledgeForest.module.css";

export interface KnowledgeForestFiltersProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  statusFilter: KnowledgeStatusFilter;
  onStatusFilterChange: (status: KnowledgeStatusFilter) => void;
  matchCount?: number;
  isFiltered?: boolean;
  onResetFilters?: () => void;
}

export function KnowledgeForestFilters({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  matchCount,
  isFiltered,
  onResetFilters,
}: KnowledgeForestFiltersProps) {
  return (
    <div className={styles.toolbar} role="search" aria-label="Bộ lọc và tìm kiếm lá tri thức">
      <div className={styles.toolbarTop}>
        <div className={styles.searchWrap}>
          <Search className={styles.searchIcon} size={17} aria-hidden="true" />
          <input
            id="knowledge-search-input"
            type="search"
            className={styles.searchInput}
            placeholder="Tìm dạng bài, chủ đề hoặc chương..."
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            aria-label="Tìm kiếm dạng bài trên cây"
          />
          {searchQuery ? (
            <button type="button" className={styles.searchClear} onClick={() => onSearchChange("")} aria-label="Xóa từ khóa tìm kiếm">
              <X size={14} />
            </button>
          ) : null}
        </div>
        <div className={styles.toolbarActions}>
          {isFiltered && matchCount !== undefined ? <span className={styles.filterResultsPill} aria-live="polite">{matchCount} lá phù hợp</span> : null}
          {isFiltered && onResetFilters ? (
            <button type="button" className={styles.filterClearBtn} onClick={onResetFilters} aria-label="Xóa tất cả bộ lọc và tìm kiếm">
              <RotateCcw size={13} aria-hidden="true" /> Xóa lọc
            </button>
          ) : null}
        </div>
      </div>
      <div className={styles.filterPills} role="group" aria-label="Lọc lá theo trạng thái học tập">
        {STATUS_FILTERS.map((item) => {
          const isActive = statusFilter === item.id;
          return (
            <button key={item.id} type="button" className={`${styles.filterPill} ${isActive ? styles.filterPillActive : ""}`} onClick={() => onStatusFilterChange(item.id)} aria-pressed={isActive}>
              {item.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}
