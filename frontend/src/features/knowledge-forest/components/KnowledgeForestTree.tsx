"use client";

import {
  BookOpen,
  ChevronDown,
  Layers,
  RotateCcw,
  Sparkles,
} from "lucide-react";

import { getBiomeLabel, getMasteryStateLabel } from "../copy";
import { filterKnowledgeForest } from "../filter";
import type {
  KnowledgeChapterNode,
  KnowledgeConceptNode,
  KnowledgeProblemTypeNode,
  KnowledgeStatusFilter,
} from "../types";
import styles from "../KnowledgeForest.module.css";

export interface KnowledgeForestTreeProps {
  chapters: KnowledgeChapterNode[];
  concepts: KnowledgeConceptNode[];
  expandedChapterIds: Set<string>;
  onToggleChapter: (chapterId: string) => void;
  selectedId?: string;
  onSelectProblemType: (problemType: KnowledgeProblemTypeNode) => void;
  onSelectConcept: (concept: KnowledgeConceptNode) => void;
  searchQuery: string;
  statusFilter: KnowledgeStatusFilter;
  onResetFilters?: () => void;
}

export function KnowledgeForestTree({
  chapters,
  concepts,
  expandedChapterIds,
  onToggleChapter,
  selectedId,
  onSelectProblemType,
  onSelectConcept,
  searchQuery,
  statusFilter,
  onResetFilters,
}: KnowledgeForestTreeProps) {
  // Use pure filter utility
  const {
    filteredChapters,
    filteredConcepts,
    totalMatchedCount,
    isFiltered,
  } = filterKnowledgeForest({
    chapters,
    concepts,
    searchQuery,
    statusFilter,
  });

  // Genuinely empty curriculum in database
  if (chapters.length === 0 && concepts.length === 0) {
    return (
      <div className={styles.emptyCard}>
        <Layers size={36} color="var(--text-tertiary)" aria-hidden="true" />
        <h3 className={styles.emptyTitle}>Chưa có cấu trúc môn học</h3>
        <p className={styles.emptyDesc}>
          Môn học này hiện chưa có danh sách chương, chủ đề hoặc khái niệm trong cơ sở dữ liệu.
        </p>
      </div>
    );
  }

  // Active search/filter matched zero nodes (both problem types AND concepts)
  if (totalMatchedCount === 0 && isFiltered) {
    return (
      <div className={styles.emptyCard}>
        <BookOpen size={36} color="var(--text-tertiary)" aria-hidden="true" />
        <h3 className={styles.emptyTitle}>Không tìm thấy kết quả phù hợp</h3>
        <p className={styles.emptyDesc}>
          Không có dạng bài hoặc khái niệm nào khớp với từ khóa &ldquo;{searchQuery}&rdquo; hoặc bộ lọc trạng thái đang chọn.
        </p>
        {onResetFilters ? (
          <button
            type="button"
            className={styles.resetFiltersBtn}
            onClick={onResetFilters}
            aria-label="Xóa tất cả bộ lọc và từ khóa tìm kiếm"
          >
            <RotateCcw size={15} aria-hidden="true" />
            <span>Xóa bộ lọc</span>
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className={styles.treeList}>
      {filteredChapters.map((chapter, index) => {
        const isExpanded = expandedChapterIds.has(chapter.id);
        const biomeName = getBiomeLabel(chapter.biome);
        const chapterProblemCount = chapter.topics.reduce(
          (sum, t) => sum + t.problemTypes.length,
          0
        );

        return (
          <article
            key={chapter.id}
            className={`${styles.chapterCard} ${styles[`biome_${chapter.biome}`]}`}
            aria-labelledby={`chapter-title-${chapter.id}`}
          >
            <button
              type="button"
              className={styles.chapterHeader}
              onClick={() => onToggleChapter(chapter.id)}
              aria-expanded={isExpanded}
              aria-controls={`chapter-body-${chapter.id}`}
            >
              <div className={styles.chapterHeaderLeft}>
                <span className={styles.chapterIndexBadge} aria-hidden="true">
                  {index + 1 < 10 ? `0${index + 1}` : index + 1}
                </span>

                <div className={styles.chapterTitleGroup}>
                  <div className={styles.chapterMetaLine}>
                    <span className={styles.biomeBadge}>{biomeName}</span>
                    <span className={styles.chapterCode}>{chapter.code}</span>
                  </div>
                  <h3 id={`chapter-title-${chapter.id}`} className={styles.chapterTitle}>
                    {chapter.name}
                  </h3>
                </div>
              </div>

              <div className={styles.chapterHeaderRight}>
                <div className={styles.chapterStats}>
                  <span className={styles.chapterProgressText}>
                    {chapter.masteryScore !== undefined ? `${chapter.masteryScore}%` : "—"}
                  </span>
                  <span className={styles.chapterCounts}>
                    {chapterProblemCount} dạng bài · {chapter.topics.length} chủ đề
                  </span>
                </div>

                <ChevronDown
                  className={`${styles.expandIcon} ${isExpanded ? styles.expandIconOpen : ""}`}
                  size={20}
                  aria-hidden="true"
                />
              </div>
            </button>

            {isExpanded ? (
              <div id={`chapter-body-${chapter.id}`} className={styles.chapterBody}>
                <div className={styles.topicList}>
                  {chapter.topics.map((topic) => (
                    <section
                      key={topic.id}
                      className={styles.topicCard}
                      aria-labelledby={`topic-title-${topic.id}`}
                    >
                      <div className={styles.topicHeader}>
                        <div className={styles.topicTitleGroup}>
                          <span className={styles.topicBranchIcon} aria-hidden="true">
                            ↳
                          </span>
                          <h4 id={`topic-title-${topic.id}`} className={styles.topicTitle}>
                            {topic.name}
                          </h4>
                          <span className={styles.chapterCode}>{topic.code}</span>
                        </div>

                        <span className={styles.topicMeta}>
                          {topic.masteryScore !== undefined
                            ? `${topic.masteryScore}%`
                            : "Chưa đo lường"}
                        </span>
                      </div>

                      <div
                        className={styles.problemTypeGrid}
                        role="group"
                        aria-label={`Danh sách dạng bài của ${topic.name}`}
                      >
                        {topic.problemTypes.map((pt) => {
                          const isSelected = selectedId === pt.id;
                          const stateLabel = getMasteryStateLabel(pt.state);
                          const scoreLabel =
                            pt.masteryScore !== undefined
                              ? `${pt.masteryScore}%`
                              : "Chưa bắt đầu";

                          return (
                            <button
                              key={pt.id}
                              type="button"
                              className={`${styles.problemTypeBtn} ${
                                isSelected ? styles.problemTypeBtnSelected : ""
                              }`}
                              onClick={() => onSelectProblemType(pt)}
                              aria-label={`${pt.name}: ${stateLabel}, ${scoreLabel}`}
                            >
                              <div className={styles.problemTypeLeft}>
                                <span
                                  className={`${styles.statusDot} ${styles[`statusDot_${pt.state}`]}`}
                                  aria-hidden="true"
                                />
                                <span className={styles.problemTypeName} title={pt.name}>
                                  {pt.name}
                                </span>
                              </div>

                              <div className={styles.problemTypeRight}>
                                {pt.isReviewDue ? (
                                  <span
                                    className={styles.problemTypeReviewBadge}
                                    title="Đến hạn ôn tập"
                                  >
                                    <RotateCcw size={13} aria-hidden="true" />
                                  </span>
                                ) : null}
                                <span className={styles.problemTypeScore}>{scoreLabel}</span>
                              </div>
                            </button>
                          );
                        })}
                      </div>
                    </section>
                  ))}
                </div>
              </div>
            ) : null}
          </article>
        );
      })}

      {/* Concepts section: preserved even when chapter list is empty or filtered */}
      {filteredConcepts.length > 0 ? (
        <section className={styles.conceptsSection} aria-labelledby="concepts-section-title">
          <div className={styles.conceptsHeader}>
            <h3 id="concepts-section-title" className={styles.conceptsTitle}>
              <Sparkles size={18} color="var(--aqua-600)" aria-hidden="true" />
              Khối kiến thức nền tảng (Concepts)
            </h3>
            <span style={{ fontSize: "0.8rem", color: "var(--text-tertiary)", fontWeight: 600 }}>
              {filteredConcepts.length} khái niệm
            </span>
          </div>

          <div className={styles.conceptsGrid}>
            {filteredConcepts.map((concept) => {
              const isSelected = selectedId === concept.id;
              const stateLabel = getMasteryStateLabel(concept.state);

              return (
                <button
                  key={concept.id}
                  type="button"
                  className={`${styles.problemTypeBtn} ${
                    isSelected ? styles.problemTypeBtnSelected : ""
                  }`}
                  onClick={() => onSelectConcept(concept)}
                  aria-label={`${concept.name}: ${stateLabel}`}
                >
                  <div className={styles.problemTypeLeft}>
                    <span
                      className={`${styles.statusDot} ${styles[`statusDot_${concept.state}`]}`}
                      aria-hidden="true"
                    />
                    <span className={styles.problemTypeName} title={concept.name}>
                      {concept.name}
                    </span>
                  </div>

                  <span className={styles.problemTypeScore}>
                    {concept.masteryScore !== undefined
                      ? `${concept.masteryScore}%`
                      : "Chưa đo lường"}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
}
