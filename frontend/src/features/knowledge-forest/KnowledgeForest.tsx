"use client";

import { useMemo, useState } from "react";

import { KnowledgeDetailDrawer, type SelectedKnowledgeItem } from "./components/KnowledgeDetailDrawer";
import { KnowledgeForestFilters } from "./components/KnowledgeForestFilters";
import { KnowledgeForestHeader } from "./components/KnowledgeForestHeader";
import { KnowledgeWorldFallback } from "./components/KnowledgeWorldFallback";
import { KnowledgeWorld3D } from "./components/KnowledgeWorld3D";
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
  const [viewMode, setViewMode] = useState<"3D" | "2D">("3D");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<KnowledgeStatusFilter>("ALL");

  const initialChapterId = useMemo(() => {
    if (!initialSelectedId) return undefined;
    const matched = data.chapters.find((candidate) => candidate.id === initialSelectedId);
    return matched?.id;
  }, [data.chapters, initialSelectedId]);

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

  if (data.availableSubjects.length === 0) {
    return (
      <main className={styles.pageContainer}>
        <KnowledgeForestHeader data={data} />
        <div className={styles.emptyCard} data-testid="empty-no-subjects">
          <h3 className={styles.emptyTitle}>Chưa có môn tự học được phát hành</h3>
          <p className={styles.emptyDesc}>
            Tài khoản chưa có hoạt động học tập và chưa có môn nào vượt qua cổng phát hành dành cho
            tự học. EduMS không hiển thị curriculum staging để thay thế.
          </p>
        </div>
      </main>
    );
  }

  if (!data.hasCurriculum) {
    return (
      <main className={styles.pageContainer}>
        <KnowledgeForestHeader data={data} />
        <div className={styles.emptyCard} data-testid="empty-no-curriculum">
          <h3 className={styles.emptyTitle}>Chưa có chương trình học cho môn này</h3>
          <p className={styles.emptyDesc}>
            Môn học &ldquo;{data.subject.name}&rdquo; hiện chưa có dữ liệu chương, chủ đề và dạng bài
            được phát hành trong hệ thống.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className={styles.pageContainer} style={{ padding: viewMode === "3D" ? 0 : undefined }}>
      {viewMode === "3D" ? (
        <KnowledgeWorld3D
          data={data}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          initialChapterId={initialChapterId}
          selectedId={selectedItem?.kind === "problem_type" ? selectedItem.data.id : undefined}
          onSelectProblemType={handleSelectProblemType}
          onClearSelection={handleCloseDetail}
          searchQuery={searchQuery}
          onSearchChange={setSearchQuery}
          statusFilter={statusFilter}
          onStatusFilterChange={setStatusFilter}
          onResetFilters={handleResetFilters}
        />
      ) : (
        <>
          <KnowledgeForestHeader data={data} />
          <div className={styles.modeStrip}>
            <p>Bản đồ 2D <span>Chọn một dạng bài để xem chi tiết và luyện tập.</span></p>
            <button type="button" onClick={() => setViewMode("3D")}>Khám phá cây 3D</button>
          </div>

          <KnowledgeForestFilters
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            matchCount={totalMatchedCount}
            isFiltered={isFiltered}
            onResetFilters={handleResetFilters}
          />

          <KnowledgeWorldFallback
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

          <KnowledgeDetailDrawer
            item={selectedItem}
            subjectId={data.subject.id}
            onClose={handleCloseDetail}
          />

        </>
      )}
    </main>
  );
}
