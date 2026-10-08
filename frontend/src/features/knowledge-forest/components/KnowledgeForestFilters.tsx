"use client";

import { ChevronsDownUp, ChevronsUpDown, Search, X } from "lucide-react";

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
}

export function KnowledgeForestFilters({
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  allExpanded,
  onToggleExpandAll,
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
            placeholder="Tìm theo tên dạng bài hoặc mã kiến thức..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label="Tìm kiếm dạng bài"
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
