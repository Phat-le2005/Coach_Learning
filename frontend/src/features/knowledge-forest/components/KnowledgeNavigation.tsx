"use client";

import {
  BookOpen,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Compass,
  Filter,
  Maximize2,
  Minimize2,
  Orbit,
  RotateCcw,
  Search,
  Share2,
  Sparkles,
} from "lucide-react";
import { useState } from "react";

import type {
  KnowledgeChapterNode,
  KnowledgeForestViewModel,
  KnowledgeStatusFilter,
} from "../types";
import styles from "../KnowledgeWorld3D.module.css";

export interface KnowledgeNavigationProps {
  data: KnowledgeForestViewModel;
  viewMode: "3D" | "2D";
  onViewModeChange: (mode: "3D" | "2D") => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  statusFilter: KnowledgeStatusFilter;
  onStatusFilterChange: (f: KnowledgeStatusFilter) => void;
  showPrerequisites: boolean;
  onTogglePrerequisites: () => void;
  onResetCamera: () => void;
  onSelectChapter: (chapterId: string) => void;
  activeChapterId?: string;
  onToggleFullscreen: () => void;
  isFullscreen: boolean;
}

const FILTER_OPTIONS: Array<{ key: KnowledgeStatusFilter; label: string }> = [
  { key: "ALL", label: "Tất cả" },
  { key: "MASTERED", label: "Thành thạo" },
  { key: "PRACTICING", label: "Đang luyện" },
  { key: "LEARNING", label: "Đang học" },
  { key: "WEAK", label: "Cần củng cố" },
  { key: "REVIEW_DUE", label: "Đến hạn ôn" },
  { key: "NOT_STARTED", label: "Chưa học" },
];

export function KnowledgeNavigation({
  data,
  viewMode,
  onViewModeChange,
  searchQuery,
  onSearchChange,
  statusFilter,
  onStatusFilterChange,
  showPrerequisites,
  onTogglePrerequisites,
  onResetCamera,
  onSelectChapter,
  activeChapterId,
  onToggleFullscreen,
  isFullscreen,
}: KnowledgeNavigationProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const { summary } = data;
  const overallScore = summary.masteryScore ?? 0;

  return (
    <>
      {/* Top Floating Glass Navigation */}
      <nav className={styles.topNav} aria-label="Thanh điều hướng vũ trụ tri thức">
        <div className={styles.topNavLeft}>
          <div className={styles.brandBadge}>
            <Sparkles size={16} />
            <span>EduMS 3D</span>
          </div>
          <span className={styles.subjectTitle}>{data.subject.name}</span>
          <span className={styles.subjectTag}>GDPT 2018</span>
        </div>

        {/* Search */}
        <div className={styles.topNavCenter}>
          <Search className={styles.searchIcon} size={16} aria-hidden="true" />
          <input
            type="text"
            className={styles.searchInput}
            placeholder="Tìm kiếm dạng bài, chuyên đề..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            aria-label="Tìm kiếm kiến thức"
          />
        </div>

        {/* Action Controls */}
        <div className={styles.topNavRight}>
          {/* Mode Switcher 3D / 2D */}
          <div className={styles.viewModeToggle}>
            <button
              className={`${styles.viewModeBtn} ${viewMode === "3D" ? styles.viewModeBtnActive : ""}`}
              onClick={() => onViewModeChange("3D")}
              title="Chế độ Cây tri thức 3D"
            >
              3D Tree
            </button>
            <button
              className={`${styles.viewModeBtn} ${viewMode === "2D" ? styles.viewModeBtnActive : ""}`}
              onClick={() => onViewModeChange("2D")}
              title="Chế độ Quần đảo 2D"
            >
              2D Bản đồ
            </button>
          </div>

          {/* Toggle Prerequisite Arcs */}
          {viewMode === "3D" && (
            <button
              className={`${styles.navIconButton} ${showPrerequisites ? styles.navIconButtonActive : ""}`}
              onClick={onTogglePrerequisites}
              title={showPrerequisites ? "Ẩn quan hệ tiên quyết" : "Hiện quan hệ tiên quyết"}
              aria-label="Bật tắt đường nối tiên quyết"
            >
              <Share2 size={16} />
            </button>
          )}

          {/* Reset View */}
          {viewMode === "3D" && (
            <button
              className={styles.navIconButton}
              onClick={onResetCamera}
              title="Quay về góc nhìn toàn cảnh"
              aria-label="Góc nhìn toàn cảnh"
            >
              <Compass size={16} />
            </button>
          )}

          {/* Fullscreen */}
          <button
            className={styles.navIconButton}
            onClick={onToggleFullscreen}
            title={isFullscreen ? "Thu nhỏ" : "Toàn màn hình"}
            aria-label="Chế độ toàn màn hình"
          >
            {isFullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </nav>

      {/* Floating Collapsible Left Sidebar */}
      {sidebarCollapsed ? (
        <button
          className={styles.sidebarToggleTrigger}
          onClick={() => setSidebarCollapsed(false)}
          title="Mở bảng điều khiển"
          aria-label="Mở bảng điều khiển"
        >
          <ChevronRight size={20} />
        </button>
      ) : (
        <aside
          className={styles.leftSidebar}
          role="complementary"
          aria-label="Bảng điều khiển môn học"
        >
          <div className={styles.sidebarHeader}>
            <div className={styles.sidebarTitle}>
              <Orbit size={16} color="#8be5c2" />
              <span>Tiến độ chương trình</span>
            </div>
            <button
              className={styles.sidebarCollapseBtn}
              onClick={() => setSidebarCollapsed(true)}
              aria-label="Thu gọn bảng điều khiển"
            >
              <ChevronLeft size={18} />
            </button>
          </div>

          <div className={styles.sidebarContent}>
            {/* Subject Mastery Gauge */}
            <div className={styles.masteryOverviewCard}>
              <div className={styles.masteryGaugeRing}>
                <svg width="52" height="52" style={{ transform: "rotate(-90deg)" }}>
                  <circle
                    cx="26"
                    cy="26"
                    r="22"
                    fill="none"
                    stroke="rgba(139, 229, 194, 0.15)"
                    strokeWidth="4"
                  />
                  <circle
                    cx="26"
                    cy="26"
                    r="22"
                    fill="none"
                    stroke="#23a67a"
                    strokeWidth="4"
                    strokeDasharray={2 * Math.PI * 22}
                    strokeDashoffset={(2 * Math.PI * 22) * (1 - overallScore / 100)}
                    strokeLinecap="round"
                  />
                </svg>
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "12px",
                    fontWeight: "800",
                    color: "#f7f7ee",
                  }}
                >
                  {overallScore}%
                </div>
              </div>
              <div className={styles.masteryGaugeText}>
                <span className={styles.masteryScoreValue}>
                  {summary.masteredCount} / {summary.problemTypeCount}
                </span>
                <span className={styles.masteryScoreLabel}>Dạng bài thành thạo</span>
              </div>
            </div>

            {/* Filter Chips */}
            <div>
              <div className={styles.filterSectionTitle}>Lọc theo trạng thái</div>
              <div className={styles.filterChipsWrap}>
                {FILTER_OPTIONS.map((opt) => (
                  <button
                    key={opt.key}
                    className={`${styles.filterChip} ${statusFilter === opt.key ? styles.filterChipActive : ""}`}
                    onClick={() => onStatusFilterChange(opt.key)}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Chapter List Accordion */}
            <div>
              <div className={styles.filterSectionTitle}>Nhánh tri thức ({data.chapters.length})</div>
              <div className={styles.chapterList}>
                {data.chapters.map((ch, idx) => {
                  const isActive = ch.id === activeChapterId;
                  const percent = ch.masteryScore ?? 0;
                  return (
                    <button
                      key={ch.id}
                      className={`${styles.chapterItemBtn} ${isActive ? styles.chapterItemActive : ""}`}
                      onClick={() => onSelectChapter(ch.id)}
                    >
                      <span className={styles.chapterItemTitle}>
                        {idx + 1}. {ch.name}
                      </span>
                      <span className={styles.chapterItemPercent}>{percent}%</span>
                    </button>
                  );
                })}
              </div>
            </div>
          </div>
        </aside>
      )}
    </>
  );
}
