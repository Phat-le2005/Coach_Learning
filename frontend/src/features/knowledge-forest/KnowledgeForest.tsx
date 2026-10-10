"use client";

import { useMemo, useState } from "react";

import { KnowledgeDetailDrawer, type SelectedKnowledgeItem } from "./components/KnowledgeDetailDrawer";
import { KnowledgeForestFilters } from "./components/KnowledgeForestFilters";
import { KnowledgeForestHeader } from "./components/KnowledgeForestHeader";
import { KnowledgeForestTree } from "./components/KnowledgeForestTree";
import { filterKnowledgeForest } from "./filter";
import type {
  KnowledgeConceptNode,
  KnowledgeForestViewModel,
  KnowledgeProblemTypeNode,
  KnowledgeStatusFilter,
} from "./types";
import styles from "./KnowledgeForest.module.css";

export interface KnowledgeForestProps {
  data: KnowledgeForestViewModel;
  initialSelectedId?: string;
}

export function KnowledgeForest({ data, initialSelectedId }: KnowledgeForestProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<KnowledgeStatusFilter>("ALL");

  // Resolve initial item from initialSelectedId within this subject's hierarchy
  const initialResolved = useMemo(() => {
    if (!initialSelectedId) return { item: null, chapterId: null };
    for (const chapter of data.chapters) {
      for (const topic of chapter.topics) {
        const foundPt = topic.problemTypes.find((pt) => pt.id === initialSelectedId);
        if (foundPt) {
          return {
            item: { kind: "problem_type" as const, data: foundPt },
            chapterId: chapter.id,
          };
        }
      }
    }
    const foundConcept = data.concepts.find((c) => c.id === initialSelectedId);
    if (foundConcept) {
      return {
        item: { kind: "concept" as const, data: foundConcept },
        chapterId: null,
      };
    }
    return { item: null, chapterId: null };
  }, [data.chapters, data.concepts, initialSelectedId]);

  const [selectedItem, setSelectedItem] = useState<SelectedKnowledgeItem>(initialResolved.item);

  // Manual expanded chapters: defaults to first 3 chapters + the chapter containing initialSelectedId (if any)
  const [manualExpandedChapterIds, setManualExpandedChapterIds] = useState<Set<string>>(() => {
    const ids = new Set<string>();
    data.chapters.slice(0, 3).forEach((ch) => ids.add(ch.id));
    if (initialResolved.chapterId) {
      ids.add(initialResolved.chapterId);
    }
    return ids;
  });

  // Calculate filtered results and auto-expanded chapters
  const {
    totalMatchedCount,
    autoExpandedChapterIds,
    isFiltered,
  } = useMemo(
    () =>
      filterKnowledgeForest({
        chapters: data.chapters,
        concepts: data.concepts,
        searchQuery,
        statusFilter,
      }),
    [data.chapters, data.concepts, searchQuery, statusFilter]
  );

  // When searching, auto-expand matching chapters; when search is cleared, restore manual expansions
  const isSearchActive = Boolean(searchQuery.trim());
  const effectiveExpandedChapterIds = isSearchActive
    ? autoExpandedChapterIds
    : manualExpandedChapterIds;

  const allChapterIds = useMemo(() => new Set(data.chapters.map((ch) => ch.id)), [data.chapters]);
  const isAllExpanded =
    effectiveExpandedChapterIds.size >= allChapterIds.size && allChapterIds.size > 0;

  const handleToggleExpandAll = () => {
    if (isAllExpanded) {
      setManualExpandedChapterIds(new Set());
    } else {
      setManualExpandedChapterIds(new Set(allChapterIds));
    }
  };

  const handleToggleChapter = (chapterId: string) => {
    setManualExpandedChapterIds((prev) => {
      const next = new Set(prev);
      if (next.has(chapterId)) {
        next.delete(chapterId);
      } else {
        next.add(chapterId);
      }
      return next;
    });
  };

  const handleSelectProblemType = (problemType: KnowledgeProblemTypeNode) => {
    setSelectedItem({ kind: "problem_type", data: problemType });
  };

  const handleSelectConcept = (concept: KnowledgeConceptNode) => {
    setSelectedItem({ kind: "concept", data: concept });
  };

  const handleCloseDrawer = () => {
    setSelectedItem(null);
  };

  const handleResetFilters = () => {
    setSearchQuery("");
    setStatusFilter("ALL");
  };

  const selectedId =
    selectedItem?.kind === "problem_type"
      ? selectedItem.data.id
      : selectedItem?.kind === "concept"
      ? selectedItem.data.id
      : undefined;

  return (
    <main className={styles.pageContainer}>
      <KnowledgeForestHeader data={data} />

      {data.availableSubjects.length === 0 ? (
        <div className={styles.emptyCard} data-testid="empty-no-subjects">
          <h3 className={styles.emptyTitle}>Chưa có môn tự học được phát hành</h3>
          <p className={styles.emptyDesc}>
            Tài khoản chưa có hoạt động học tập và chưa có môn nào vượt qua cổng phát hành dành cho
            tự học. EduMS không hiển thị curriculum staging để thay thế.
          </p>
        </div>
      ) : data.hasCurriculum ? (
        <>
          <KnowledgeForestFilters
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            allExpanded={isAllExpanded}
            onToggleExpandAll={handleToggleExpandAll}
            matchCount={totalMatchedCount}
            isFiltered={isFiltered}
            onResetFilters={handleResetFilters}
          />

          <KnowledgeForestTree
            chapters={data.chapters}
            concepts={data.concepts}
            expandedChapterIds={effectiveExpandedChapterIds}
            onToggleChapter={handleToggleChapter}
            selectedId={selectedId}
            onSelectProblemType={handleSelectProblemType}
            onSelectConcept={handleSelectConcept}
            searchQuery={searchQuery}
            statusFilter={statusFilter}
            onResetFilters={handleResetFilters}
          />
        </>
      ) : (
        <div className={styles.emptyCard} data-testid="empty-no-curriculum">
          <h3 className={styles.emptyTitle}>Chưa có chương trình học cho môn này</h3>
          <p className={styles.emptyDesc}>
            Môn học &ldquo;{data.subject.name}&rdquo; hiện chưa có dữ liệu chương và chủ đề được phát
            hành trong hệ thống. Hãy quay lại sau khi giáo viên hoặc quản trị viên cập nhật chương trình.
          </p>
        </div>
      )}

      <KnowledgeDetailDrawer item={selectedItem} onClose={handleCloseDrawer} />
    </main>
  );
}
