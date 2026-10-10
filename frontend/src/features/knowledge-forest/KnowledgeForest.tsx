"use client";

import { useMemo, useState } from "react";

import { KnowledgeDetailDrawer, type SelectedKnowledgeItem } from "./components/KnowledgeDetailDrawer";
import { KnowledgeForestFilters } from "./components/KnowledgeForestFilters";
import { KnowledgeForestHeader } from "./components/KnowledgeForestHeader";
import { KnowledgeForestTree } from "./components/KnowledgeForestTree";
import { filterKnowledgeForest } from "./filter";
import type {
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

  // Concepts are intentionally absent from the tree until API v1 exposes real PT mappings.
  const initialResolved = useMemo(() => {
    if (!initialSelectedId) return null;
    for (const chapter of data.chapters) {
      for (const topic of chapter.topics) {
        const problemType = topic.problemTypes.find((candidate) => candidate.id === initialSelectedId);
        if (problemType) return { kind: "problem_type" as const, data: problemType };
      }
    }
    return null;
  }, [data.chapters, initialSelectedId]);

  const [selectedItem, setSelectedItem] = useState<SelectedKnowledgeItem>(initialResolved);
  const { totalMatchedCount, isFiltered } = useMemo(
    () =>
      filterKnowledgeForest({
        chapters: data.chapters,
        concepts: [],
        searchQuery,
        statusFilter,
      }),
    [data.chapters, searchQuery, statusFilter]
  );

  const handleSelectProblemType = (problemType: KnowledgeProblemTypeNode) => {
    setSelectedItem({ kind: "problem_type", data: problemType });
  };

  const handleResetFilters = () => {
    setSearchQuery("");
    setStatusFilter("ALL");
  };

  const handleCloseDetail = () => {
    setSelectedItem(null);
    const url = new URL(window.location.href);
    if (url.searchParams.has("node")) {
      url.searchParams.delete("node");
      window.history.pushState(null, "", `${url.pathname}${url.search}${url.hash}`);
    }
  };

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
            matchCount={totalMatchedCount}
            isFiltered={isFiltered}
            onResetFilters={handleResetFilters}
          />
          <KnowledgeForestTree
            chapters={data.chapters}
            subjectName={data.subject.name}
            selectedId={selectedItem?.kind === "problem_type" ? selectedItem.data.id : undefined}
            initialNodeId={initialSelectedId}
            onSelectProblemType={handleSelectProblemType}
            onClearSelection={() => setSelectedItem(null)}
            searchQuery={searchQuery}
            statusFilter={statusFilter}
            onResetFilters={handleResetFilters}
          />
        </>
      ) : (
        <div className={styles.emptyCard} data-testid="empty-no-curriculum">
          <h3 className={styles.emptyTitle}>Chưa có chương trình học cho môn này</h3>
          <p className={styles.emptyDesc}>
            Môn học &ldquo;{data.subject.name}&rdquo; hiện chưa có dữ liệu chương, chủ đề và dạng bài
            được phát hành trong hệ thống.
          </p>
        </div>
      )}

      <KnowledgeDetailDrawer item={selectedItem} onClose={handleCloseDetail} />
    </main>
  );
}
