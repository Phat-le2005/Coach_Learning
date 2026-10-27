"use client";

import {
  Archive,
  ArrowRight,
  Award,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Clock,
  FileCheck2,
  FileClock,
  FilePen,
  FileText,
  LayoutGrid,
  List,
  RotateCcw,
  Search,
  Sprout,
  X,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { fadeUp } from "@/lib/motion";

import { filterAndSortAttempts } from "../adapter";
import styles from "../StudentAttempts.module.css";
import type {
  AttemptCardViewModel,
  AttemptsFilterStatus,
  AttemptsPaginationViewModel,
  AttemptsSortOrder,
  AttemptStatusTone,
  AttemptsViewMode,
} from "../types";

const VIEW_MODE_STORAGE_KEY = "edums_attempts_view_mode";

interface StatusFilterTab {
  value: AttemptsFilterStatus;
  label: string;
}

const STATUS_FILTER_TABS: StatusFilterTab[] = [
  { value: "ALL", label: "Tất cả trạng thái" },
  { value: "IN_PROGRESS", label: "Đang thực hiện" },
  { value: "DRAFT", label: "Bản nháp" },
  { value: "SUBMITTED", label: "Đã nộp" },
  { value: "EVALUATED", label: "Đã đánh giá" },
];

function StatusIcon({ tone }: { tone: AttemptStatusTone }) {
  switch (tone) {
    case "inProgress":
      return <Clock size={12} aria-hidden="true" />;
    case "submitted":
      return <CheckCircle2 size={12} aria-hidden="true" />;
    case "evaluated":
      return <Award size={12} aria-hidden="true" />;
    case "abandoned":
      return <Archive size={12} aria-hidden="true" />;
    default:
      return <FilePen size={12} aria-hidden="true" />;
  }
}

function DocumentIcon({ tone }: { tone: AttemptStatusTone }) {
  switch (tone) {
    case "inProgress":
      return <FileClock size={21} strokeWidth={1.9} aria-hidden="true" />;
    case "submitted":
    case "evaluated":
      return <FileCheck2 size={21} strokeWidth={1.9} aria-hidden="true" />;
    case "draft":
      return <FilePen size={21} strokeWidth={1.9} aria-hidden="true" />;
    default:
      return <FileText size={21} strokeWidth={1.9} aria-hidden="true" />;
  }
}

function buildAttemptsHref(params: {
  page?: number;
  status?: AttemptsFilterStatus;
  subjectId?: string;
}): string {
  const sp = new URLSearchParams();
  if (params.subjectId) {
    sp.set("subject_id", params.subjectId);
  }
  if (params.status && params.status !== "ALL") {
    sp.set("status", params.status);
  }
  if (params.page && params.page > 1) {
    sp.set("page", String(params.page));
  }
  const query = sp.toString();
  return query ? `/student/attempts?${query}` : "/student/attempts";
}

function buildVisiblePageNumbers(current: number, totalPages: number): number[] {
  if (totalPages <= 1) return [1];
  const pages = new Set<number>([1, totalPages, current, current - 1, current + 1]);
  return Array.from(pages)
    .filter((p) => p >= 1 && p <= totalPages)
    .sort((a, b) => a - b);
}

export interface AttemptsLibrarySectionProps {
  items: AttemptCardViewModel[];
  pagination: AttemptsPaginationViewModel;
  activeStatusFilter: AttemptsFilterStatus;
  defaultSubjectId?: string;
}

export function AttemptsLibrarySection({
  items,
  pagination,
  activeStatusFilter,
  defaultSubjectId,
}: AttemptsLibrarySectionProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [sortOrder, setSortOrder] = useState<AttemptsSortOrder>("updated_desc");
  const [viewMode, setViewMode] = useState<AttemptsViewMode>("grid");

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(VIEW_MODE_STORAGE_KEY);
      if (saved === "list" || saved === "grid") {
        setViewMode(saved);
      }
    } catch {
      // Ignore storage access errors
    }
  }, []);

  const handleChangeViewMode = (mode: AttemptsViewMode) => {
    setViewMode(mode);
    try {
      window.localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
    } catch {
      // Ignore storage errors
    }
  };

  const displayedItems = useMemo(
    () => filterAndSortAttempts(items, searchQuery, sortOrder),
    [items, searchQuery, sortOrder]
  );

  const visiblePages = useMemo(
    () => buildVisiblePageNumbers(pagination.page, pagination.totalPages),
    [pagination.page, pagination.totalPages]
  );

  const hasSearchFilter = searchQuery.trim().length > 0;
  const isCompletelyEmptyAccount = pagination.total === 0 && activeStatusFilter === "ALL";

  return (
    <motion.section
      id="attempts-library"
      className={styles.librarySection}
      aria-labelledby="attempts-library-heading"
      variants={fadeUp}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.1 }}
    >
      {/* Header */}
      <div className={styles.sectionHeaderRow}>
        <div>
          <p className={styles.sectionEyebrow}>Thư viện lưu trữ cá nhân</p>
          <h2 id="attempts-library-heading" className={styles.sectionTitle}>
            Lịch sử bài làm của tôi
          </h2>
          <p className={styles.sectionSubtitle}>
            Tra cứu theo ngày giờ, mã phiên hoặc lọc theo trạng thái hoàn thành.
          </p>
        </div>
      </div>

      {/* Toolbar: Search, Sort, View Toggle, and Backend-Synced Status Filters */}
      <div className={styles.toolbar}>
        <div className={styles.toolbarTopRow}>
          <div className={styles.searchBox}>
            <Search size={17} className={styles.searchIcon} aria-hidden="true" />
            <input
              type="search"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Tìm theo ngày (VD: 25/10), mã # phiên hoặc trạng thái..."
              aria-label="Tìm kiếm bài làm trong trang hiện tại"
              className={styles.searchInput}
            />
            {hasSearchFilter ? (
              <button
                type="button"
                onClick={() => setSearchQuery("")}
                className={styles.searchClearBtn}
                aria-label="Xóa từ khóa tìm kiếm"
              >
                <X size={14} aria-hidden="true" />
              </button>
            ) : null}
          </div>

          <div className={styles.toolbarControlsRight}>
            <div className={styles.sortControlWrap}>
              <label htmlFor="attempts-sort-select" className={styles.sortLabel}>
                Sắp xếp:
              </label>
              <select
                id="attempts-sort-select"
                value={sortOrder}
                onChange={(event) => setSortOrder(event.target.value as AttemptsSortOrder)}
                className={styles.sortSelect}
              >
                <option value="updated_desc">Cập nhật gần nhất</option>
                <option value="created_desc">Mới tạo nhất</option>
                <option value="created_asc">Cũ nhất trước</option>
              </select>
            </div>

            <div className={styles.viewToggleGroup} role="group" aria-label="Chế độ hiển thị">
              <button
                type="button"
                onClick={() => handleChangeViewMode("grid")}
                className={`${styles.viewToggleBtn} ${
                  viewMode === "grid" ? styles.viewToggleBtnActive : ""
                }`}
                aria-pressed={viewMode === "grid"}
                title="Xem dạng thẻ (Grid)"
              >
                <LayoutGrid size={16} aria-hidden="true" />
              </button>
              <button
                type="button"
                onClick={() => handleChangeViewMode("list")}
                className={`${styles.viewToggleBtn} ${
                  viewMode === "list" ? styles.viewToggleBtnActive : ""
                }`}
                aria-pressed={viewMode === "list"}
                title="Xem dạng danh sách (List)"
              >
                <List size={16} aria-hidden="true" />
              </button>
            </div>
          </div>
        </div>

        {/* Status Filter Pills (Backed by real API status query parameter) */}
        <nav className={styles.statusFilterRow} aria-label="Lọc theo trạng thái bài làm">
          {STATUS_FILTER_TABS.map((tab) => {
            const isActive = activeStatusFilter === tab.value;
            return (
              <Link
                key={tab.value}
                href={buildAttemptsHref({
                  page: 1,
                  status: tab.value,
                  subjectId: defaultSubjectId,
                })}
                scroll={false}
                className={isActive ? styles.filterPillActive : styles.filterPill}
                aria-current={isActive ? "true" : undefined}
              >
                {tab.label}
              </Link>
            );
          })}
        </nav>
      </div>

      {/* Truthful Count & Pagination Context */}
      {pagination.total > 0 ? (
        <div className={styles.librarySummaryBar} aria-live="polite">
          <span>
            Hiển thị{" "}
            <strong>
              {hasSearchFilter
                ? `${displayedItems.length} kết quả khớp`
                : `${pagination.rangeStart}–${pagination.rangeEnd}`}
            </strong>{" "}
            trên tổng số <strong>{pagination.total}</strong> lượt làm bài
            {pagination.totalPages > 1
              ? ` (Trang ${pagination.page}/${pagination.totalPages})`
              : ""}
          </span>
          {hasSearchFilter && pagination.totalPages > 1 ? (
            <span>Tìm nhanh trên trang {pagination.page} hiện tại</span>
          ) : null}
        </div>
      ) : null}

      {/* Content Area: Empty State vs Attempt Cards */}
      {isCompletelyEmptyAccount ? (
        <div className={styles.emptyLibraryState}>
          <div className={styles.emptyIllustration} aria-hidden="true">
            <Sprout size={36} strokeWidth={1.8} />
          </div>
          <h3 className={styles.emptyTitle}>Khu vườn bài làm đang chờ trang viết đầu tiên</h3>
          <p className={styles.emptyDescription}>
            Bạn chưa có lượt làm bài nào. Hãy chọn môn học ở khung &ldquo;Bắt đầu một bài làm
            mới&rdquo; phía trên để mở trang giấy số đầu tiên.
          </p>
          <a href="#workspace-subject" className={styles.emptyResetBtn}>
            Chọn môn học để bắt đầu
          </a>
        </div>
      ) : displayedItems.length === 0 ? (
        <div className={styles.emptyLibraryState}>
          <div className={styles.emptyIllustration} aria-hidden="true">
            <Search size={32} strokeWidth={1.8} />
          </div>
          <h3 className={styles.emptyTitle}>Không tìm thấy bài làm phù hợp</h3>
          <p className={styles.emptyDescription}>
            {hasSearchFilter
              ? `Không có lượt làm bài nào khớp từ khóa "${searchQuery.trim()}" trên trang này.`
              : "Chưa có lượt làm bài nào thuộc trạng thái bạn đang lọc."}
          </p>
          {hasSearchFilter ? (
            <button
              type="button"
              onClick={() => setSearchQuery("")}
              className={styles.emptyResetBtn}
            >
              <RotateCcw size={14} aria-hidden="true" />
              Xóa từ khóa tìm kiếm
            </button>
          ) : (
            <Link
              href={buildAttemptsHref({ page: 1, status: "ALL", subjectId: defaultSubjectId })}
              scroll={false}
              className={styles.emptyResetBtn}
            >
              <RotateCcw size={14} aria-hidden="true" />
              Xem tất cả trạng thái
            </Link>
          )}
        </div>
      ) : (
        <ul className={viewMode === "grid" ? styles.libraryGrid : styles.libraryList}>
          {displayedItems.map((item) => {
            const isRow = viewMode === "list";
            return (
              <li key={item.id}>
                <article
                  className={`${styles.attemptCard} ${isRow ? styles.attemptCardRow : ""}`}
                >
                  <div className={styles.attemptCardTop}>
                    <div className={styles.attemptDocBadge}>
                      <DocumentIcon tone={item.status.tone} />
                    </div>

                    <div className={styles.attemptBody}>
                      <div className={styles.attemptStatusLine}>
                        <span
                          className={`${styles.statusBadge} ${
                            styles[`tone_${item.status.tone}`]
                          }`}
                        >
                          <StatusIcon tone={item.status.tone} />
                          {item.status.label}
                        </span>
                        <span className={styles.codeTag}>#{item.shortCode}</span>
                      </div>

                      <h3 className={styles.attemptTitle}>{item.title}</h3>

                      <div className={styles.attemptMetaList}>
                        <span className={styles.attemptMetaChip}>
                          Tạo lúc: {item.createdAtLabel}
                        </span>
                        {item.submittedAtLabel ? (
                          <span className={styles.attemptMetaChip}>
                            Đã nộp: {item.submittedAtLabel}
                          </span>
                        ) : item.updatedAtLabel &&
                          item.updatedAtLabel !== item.createdAtLabel ? (
                          <span className={styles.attemptMetaChip}>
                            Cập nhật: {item.updatedAtLabel}
                          </span>
                        ) : null}
                      </div>
                    </div>
                  </div>

                  <div className={styles.attemptFooter}>
                    <span className={styles.stepCountBadge}>{item.stepSummaryLabel}</span>

                    <Link
                      href={item.href}
                      className={
                        item.status.isResumable
                          ? styles.openAttemptBtnPrimary
                          : styles.openAttemptBtn
                      }
                    >
                      <span>{item.status.actionLabel}</span>
                      <ArrowRight size={15} aria-hidden="true" />
                    </Link>
                  </div>
                </article>
              </li>
            );
          })}
        </ul>
      )}

      {/* Contract-Faithful Backend Pagination Controls */}
      {pagination.totalPages > 1 ? (
        <nav className={styles.paginationNav} aria-label="Phân trang danh sách bài làm">
          <span className={styles.paginationInfo}>
            Trang <strong>{pagination.page}</strong> / <strong>{pagination.totalPages}</strong> ·
            Tổng cộng <strong>{pagination.total}</strong> bài làm
          </span>

          <div className={styles.paginationControls}>
            {pagination.hasPreviousPage ? (
              <Link
                href={buildAttemptsHref({
                  page: pagination.page - 1,
                  status: activeStatusFilter,
                  subjectId: defaultSubjectId,
                })}
                scroll={false}
                className={styles.pageLink}
                aria-label="Trang trước"
              >
                <ChevronLeft size={15} aria-hidden="true" />
                <span>Trước</span>
              </Link>
            ) : (
              <span className={styles.pageLinkDisabled} aria-disabled="true">
                <ChevronLeft size={15} aria-hidden="true" />
                <span>Trước</span>
              </span>
            )}

            {visiblePages.map((p) =>
              p === pagination.page ? (
                <span key={p} className={styles.pageLinkActive} aria-current="page">
                  {p}
                </span>
              ) : (
                <Link
                  key={p}
                  href={buildAttemptsHref({
                    page: p,
                    status: activeStatusFilter,
                    subjectId: defaultSubjectId,
                  })}
                  scroll={false}
                  className={styles.pageLink}
                >
                  {p}
                </Link>
              )
            )}

            {pagination.hasNextPage ? (
              <Link
                href={buildAttemptsHref({
                  page: pagination.page + 1,
                  status: activeStatusFilter,
                  subjectId: defaultSubjectId,
                })}
                scroll={false}
                className={styles.pageLink}
                aria-label="Trang sau"
              >
                <span>Sau</span>
                <ChevronRight size={15} aria-hidden="true" />
              </Link>
            ) : (
              <span className={styles.pageLinkDisabled} aria-disabled="true">
                <span>Sau</span>
                <ChevronRight size={15} aria-hidden="true" />
              </span>
            )}
          </div>
        </nav>
      ) : null}
    </motion.section>
  );
}
