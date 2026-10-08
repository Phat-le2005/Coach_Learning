"use client";

import { useMemo, useState } from "react";

import { KnowledgeDetailDrawer, type SelectedKnowledgeItem } from "./components/KnowledgeDetailDrawer";
import { KnowledgeForestFilters } from "./components/KnowledgeForestFilters";
import { KnowledgeForestHeader } from "./components/KnowledgeForestHeader";
import { KnowledgeForestTree } from "./components/KnowledgeForestTree";
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
  const [selectedItem, setSelectedItem] = useState<SelectedKnowledgeItem>(() => {
    if (!initialSelectedId) return null;
    for (const chapter of data.chapters) {
      for (const topic of chapter.topics) {
        const foundPt = topic.problemTypes.find((pt) => pt.id === initialSelectedId);
        if (foundPt) return { kind: "problem_type", data: foundPt };
      }
    }
    const foundConcept = data.concepts.find((c) => c.id === initialSelectedId);
    if (foundConcept) return { kind: "concept", data: foundConcept };
    return null;
  });

  // Default: first 2 chapters expanded or all if <= 3
  const [expandedChapterIds, setExpandedChapterIds] = useState<Set<string>>(() => {
    const ids = new Set<string>();
    data.chapters.slice(0, 3).forEach((ch) => ids.add(ch.id));
    return ids;
  });

  const allChapterIds = useMemo(() => new Set(data.chapters.map((ch) => ch.id)), [data.chapters]);
  const isAllExpanded = expandedChapterIds.size >= allChapterIds.size && allChapterIds.size > 0;

  const handleToggleExpandAll = () => {
    if (isAllExpanded) {
      setExpandedChapterIds(new Set());
    } else {
      setExpandedChapterIds(new Set(allChapterIds));
    }
  };

  const handleToggleChapter = (chapterId: string) => {
    setExpandedChapterIds((prev) => {
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

  const selectedId =
    selectedItem?.kind === "problem_type"
      ? selectedItem.data.id
      : selectedItem?.kind === "concept"
      ? selectedItem.data.id
      : undefined;

  return (
    <main className={styles.pageContainer}>
      <KnowledgeForestHeader data={data} />

      {data.hasCurriculum ? (
        <>
          <KnowledgeForestFilters
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            statusFilter={statusFilter}
            onStatusFilterChange={setStatusFilter}
            allExpanded={isAllExpanded}
            onToggleExpandAll={handleToggleExpandAll}
          />

          <KnowledgeForestTree
            chapters={data.chapters}
            concepts={data.concepts}
            expandedChapterIds={expandedChapterIds}
            onToggleChapter={handleToggleChapter}
            selectedId={selectedId}
            onSelectProblemType={handleSelectProblemType}
            onSelectConcept={handleSelectConcept}
            searchQuery={searchQuery}
            statusFilter={statusFilter}
          />
        </>
      ) : (
        <div className={styles.emptyCard}>
          <h3 className={styles.emptyTitle}>Chưa có chương trình học cho môn này</h3>
          <p className={styles.emptyDesc}>
            Môn học &ldquo;{data.subject.name}&rdquo; hiện chưa có dữ liệu chương và chủ đề được phát
            hành. Hãy quay lại sau khi giáo viên hoặc quản trị viên cập nhật chương trình.
          </p>
        </div>
      )}

      <KnowledgeDetailDrawer item={selectedItem} onClose={handleCloseDrawer} />
    </main>
  );
}
