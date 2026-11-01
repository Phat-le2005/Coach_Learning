"use client";

import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Compass,
  GraduationCap,
  Lock,
  Maximize2,
  Minimize2,
  Orbit,
  Search,
  Share2,
  Sparkles,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";

import type {
  KnowledgeForestViewModel,
  KnowledgeProblemTypeNode,
  KnowledgeStatusFilter,
} from "../types";
import styles from "../KnowledgeWorld3D.module.css";

export type KnowledgeScopeFilter =
  | "ALL"
  | "TEACHER_SCOPE"
  | "CURRENT_TEACHING"
  | "FOG_OF_WAR";

export interface KnowledgeNavigationProps {
  data: KnowledgeForestViewModel;
  viewMode: "3D" | "2D";
  onViewModeChange: (mode: "3D" | "2D") => void;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  statusFilter: KnowledgeStatusFilter;
  onStatusFilterChange: (f: KnowledgeStatusFilter) => void;
  scopeFilter?: KnowledgeScopeFilter;
  onScopeFilterChange?: (s: KnowledgeScopeFilter) => void;
  onSelectProblemType?: (pt: KnowledgeProblemTypeNode) => void;
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
  scopeFilter = "ALL",
  onScopeFilterChange,
  onSelectProblemType,
  showPrerequisites,
  onTogglePrerequisites,
  onResetCamera,
  onSelectChapter,
  activeChapterId,
  onToggleFullscreen,
  isFullscreen,
}: KnowledgeNavigationProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const { summary, classroomContext } = data;
  const overallScore = summary.masteryScore ?? 0;

  // Priority nodes for the student's adaptive study pathway in 3D
  const priorityNodes = useMemo(() => {
    const allPts: KnowledgeProblemTypeNode[] = [];
    data.chapters.forEach((ch) =>
      ch.topics.forEach((t) => allPts.push(...t.problemTypes))
    );
    return allPts
      .filter(
        (pt) =>
          pt.state === "WEAK" ||
          pt.scopeState === "CURRENT_TEACHING" ||
          (pt.attemptCount > 0 && pt.state !== "MASTERED")
      )
      .sort((a, b) => {
        const scoreOrder = (pt: KnowledgeProblemTypeNode) => {
          if (pt.state === "WEAK") return 0;
          if (pt.scopeState === "CURRENT_TEACHING" && pt.attemptCount > 0) return 1;
          if (pt.scopeState === "CURRENT_TEACHING") return 2;
          return 3;
        };
        return scoreOrder(a) - scoreOrder(b);
      })
      .slice(0, 4);
  }, [data.chapters]);

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
          {classroomContext?.hasActiveTeacherScope && classroomContext.classroomName && (
            <span
              className={styles.subjectTag}
              style={{
                color: "#fde047",
                background: "rgba(250, 204, 21, 0.14)",
                borderColor: "rgba(250, 204, 21, 0.35)",
              }}
            >
              Lớp: {classroomContext.classroomName}
            </span>
          )}
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
              <span>Tiến độ & Lộ trình 3D</span>
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

            {/* Teacher Curriculum Scope Filter */}
            {classroomContext?.hasActiveTeacherScope && onScopeFilterChange && (
              <div>
                <div className={styles.filterSectionTitle} style={{ display: "flex", alignItems: "center", gap: "5px" }}>
                  <GraduationCap size={12} color="#fde047" />
                  <span>Phạm vi Giáo viên giảng dạy</span>
                </div>
                <div className={styles.filterChipsWrap}>
                  <button
                    className={`${styles.filterChip} ${scopeFilter === "ALL" ? styles.filterChipActive : ""}`}
                    onClick={() => onScopeFilterChange("ALL")}
                  >
                    Toàn cảnh ({summary.problemTypeCount})
                  </button>
                  <button
                    className={`${styles.filterChip} ${scopeFilter === "TEACHER_SCOPE" ? styles.filterChipActive : ""}`}
                    onClick={() => onScopeFilterChange("TEACHER_SCOPE")}
                  >
                    Đã & Đang dạy ({classroomContext.currentTeachingCount + classroomContext.unlockedCount})
                  </button>
                  <button
                    className={`${styles.filterChip} ${scopeFilter === "CURRENT_TEACHING" ? styles.filterChipActive : ""}`}
                    onClick={() => onScopeFilterChange("CURRENT_TEACHING")}
                  >
                    ✦ Đang dạy ({classroomContext.currentTeachingCount})
                  </button>
                  <button
                    className={`${styles.filterChip} ${scopeFilter === "FOG_OF_WAR" ? styles.filterChipActive : ""}`}
                    onClick={() => onScopeFilterChange("FOG_OF_WAR")}
                  >
                    🔒 Sương mù ({classroomContext.fogCount})
                  </button>
                </div>
              </div>
            )}

            {/* AI Priority Pathway from Student Submissions */}
            {priorityNodes.length > 0 && onSelectProblemType && (
              <div>
                <div className={styles.filterSectionTitle} style={{ color: "#fde047" }}>
                  ⚡ Lộ trình AI từ bài làm PDF
                </div>
                <div className={styles.chapterList}>
                  {priorityNodes.map((pt) => (
                    <button
                      key={pt.id}
                      className={styles.chapterItemBtn}
                      onClick={() => onSelectProblemType(pt)}
                      style={{
                        borderColor:
                          pt.state === "WEAK"
                            ? "rgba(248, 113, 113, 0.4)"
                            : "rgba(250, 204, 21, 0.3)",
                        background:
                          pt.state === "WEAK"
                            ? "rgba(127, 29, 29, 0.25)"
                            : "rgba(5, 25, 20, 0.55)",
                      }}
                    >
                      <div style={{ display: "flex", flexDirection: "column", gap: "2px", minWidth: 0 }}>
                        <span className={styles.chapterItemTitle} style={{ maxWidth: "185px" }}>
                          {pt.name}
                        </span>
                        <span
                          style={{
                            fontSize: "10px",
                            color: pt.state === "WEAK" ? "#fca5a5" : "#fde047",
                            display: "flex",
                            alignItems: "center",
                            gap: "4px",
                          }}
                        >
                          {pt.state === "WEAK" ? (
                            <>
                              <AlertTriangle size={10} /> Cần bù lỗ hổng • Luyện bài hệ thống
                            </>
                          ) : (
                            <>
                              <Zap size={10} /> Giáo viên đang dạy • {pt.attemptCount} lượt làm
                            </>
                          )}
                        </span>
                      </div>
                      <span
                        className={styles.chapterItemPercent}
                        style={{ color: pt.state === "WEAK" ? "#fca5a5" : "#8be5c2" }}
                      >
                        {pt.masteryScore !== undefined ? `${pt.masteryScore}%` : "Mới"}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Filter Chips */}
            <div>
              <div className={styles.filterSectionTitle}>Lọc theo mức độ thành thạo</div>
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
