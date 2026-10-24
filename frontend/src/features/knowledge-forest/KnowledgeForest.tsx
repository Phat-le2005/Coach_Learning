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
          {/* Mode Switcher Banner in 2D Mode */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: "16px",
              padding: "10px 16px",
              background: "rgba(16, 46, 38, 0.04)",
              borderRadius: "12px",
              border: "1px solid rgba(16, 46, 38, 0.08)",
            }}
          >
            <span style={{ fontSize: "13px", fontWeight: "600", color: "#102e26" }}>
              Đang ở chế độ xem: <strong>Quần đảo Tri thức 2D</strong>
            </span>
            <button
              onClick={() => setViewMode("3D")}
              style={{
                background: "#23a67a",
                color: "#ffffff",
                border: "none",
                borderRadius: "8px",
                padding: "6px 14px",
                fontSize: "12px",
                fontWeight: "700",
                cursor: "pointer",
                boxShadow: "0 2px 8px rgba(35, 166, 122, 0.3)",
              }}
            >
              Chuyển sang Thế giới 3D ✦
            </button>
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

          <KnowledgeDetailDrawer item={selectedItem} onClose={handleCloseDetail} />
        </>
      )}
    </main>
  );
}
