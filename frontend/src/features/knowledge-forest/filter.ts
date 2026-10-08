import type {
  KnowledgeChapterNode,
  KnowledgeConceptNode,
  KnowledgeProblemTypeNode,
  KnowledgeStatusFilter,
  KnowledgeTopicNode,
} from "./types";

/**
 * Normalizes Vietnamese text by stripping diacritics, accents, and casing.
 * Handles "đ/Đ" explicitly and NFC/NFD decomposition.
 */
export function normalizeSearchText(input: string): string {
  if (!input) return "";
  return input
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "d")
    .trim();
}

/**
 * Checks if a target string matches a query either directly (case-insensitive)
 * or with Vietnamese diacritics removed.
 */
export function matchesKeyword(
  target: string,
  rawQuery: string,
  normalizedQuery: string
): boolean {
  if (!rawQuery || !normalizedQuery) return true;
  if (!target) return false;

  const lowerTarget = target.toLowerCase();
  if (lowerTarget.includes(rawQuery.toLowerCase())) {
    return true;
  }

  const normalizedTarget = normalizeSearchText(target);
  return normalizedTarget.includes(normalizedQuery);
}

export interface FilterKnowledgeForestParams {
  chapters: KnowledgeChapterNode[];
  concepts: KnowledgeConceptNode[];
  searchQuery: string;
  statusFilter: KnowledgeStatusFilter;
}

export interface FilteredKnowledgeResult {
  filteredChapters: KnowledgeChapterNode[];
  filteredConcepts: KnowledgeConceptNode[];
  matchingProblemTypeCount: number;
  matchingConceptCount: number;
  totalMatchedCount: number;
  autoExpandedChapterIds: Set<string>;
  isFiltered: boolean;
}

/**
 * Pure filter utility for Knowledge Forest.
 * Supports:
 * - Case-insensitive & diacritics-insensitive search (tiếng Việt có dấu và không dấu).
 * - Matches on chapter name/code, topic name/code, problem type name/code, concept name/code.
 * - If a chapter matches keyword, shows its problem types conforming to status filter.
 * - If a topic matches keyword, shows its problem types conforming to status filter.
 * - Prunes empty chapters and topics when filtering.
 * - Counts both problem types and concepts in totalMatchedCount.
 * - Concept-only results are preserved and rendered.
 * - Identifies auto-expanded chapters when search query is active.
 */
export function filterKnowledgeForest({
  chapters,
  concepts,
  searchQuery,
  statusFilter,
}: FilterKnowledgeForestParams): FilteredKnowledgeResult {
  const trimmedQuery = searchQuery.trim();
  const normalizedQuery = normalizeSearchText(trimmedQuery);
  const isSearchActive = Boolean(normalizedQuery);
  const isStatusActive = statusFilter !== "ALL";
  const isFiltered = isSearchActive || isStatusActive;

  const autoExpandedChapterIds = new Set<string>();

  const filteredChapters: KnowledgeChapterNode[] = [];
  let matchingProblemTypeCount = 0;

  for (const chapter of chapters) {
    const chapterMatchesQuery =
      isSearchActive &&
      (matchesKeyword(chapter.name, trimmedQuery, normalizedQuery) ||
        matchesKeyword(chapter.code, trimmedQuery, normalizedQuery));

    const matchingTopics: KnowledgeTopicNode[] = [];

    for (const topic of chapter.topics) {
      const topicMatchesQuery =
        chapterMatchesQuery ||
        (isSearchActive &&
          (matchesKeyword(topic.name, trimmedQuery, normalizedQuery) ||
            matchesKeyword(topic.code, trimmedQuery, normalizedQuery)));

      const matchingProblemTypes: KnowledgeProblemTypeNode[] = [];

      for (const pt of topic.problemTypes) {
        // Status check
        if (isStatusActive && pt.state !== statusFilter) {
          continue;
        }

        // Query check
        const ptMatchesQuery =
          !isSearchActive ||
          topicMatchesQuery ||
          matchesKeyword(pt.name, trimmedQuery, normalizedQuery) ||
          matchesKeyword(pt.code, trimmedQuery, normalizedQuery);

        if (ptMatchesQuery) {
          matchingProblemTypes.push(pt);
        }
      }

      // Rule: Do not keep empty topics when filtering or if topic has no items
      if (matchingProblemTypes.length > 0) {
        matchingTopics.push({
          ...topic,
          problemTypes: matchingProblemTypes,
        });
      }
    }

    // Rule: Do not keep empty chapters when filtering or if chapter has no matching items
    if (matchingTopics.length > 0) {
      const chapterProblemCount = matchingTopics.reduce(
        (sum, t) => sum + t.problemTypes.length,
        0
      );
      matchingProblemTypeCount += chapterProblemCount;

      filteredChapters.push({
        ...chapter,
        topics: matchingTopics,
      });

      if (isSearchActive) {
        autoExpandedChapterIds.add(chapter.id);
      }
    }
  }

  // Filter concepts (subject-level branch)
  const filteredConcepts: KnowledgeConceptNode[] = [];

  for (const concept of concepts) {
    if (isStatusActive && concept.state !== statusFilter) {
      continue;
    }

    const conceptMatchesQuery =
      !isSearchActive ||
      matchesKeyword(concept.name, trimmedQuery, normalizedQuery) ||
      matchesKeyword(concept.code, trimmedQuery, normalizedQuery);

    if (conceptMatchesQuery) {
      filteredConcepts.push(concept);
    }
  }

  const matchingConceptCount = filteredConcepts.length;
  const totalMatchedCount = matchingProblemTypeCount + matchingConceptCount;

  return {
    filteredChapters,
    filteredConcepts,
    matchingProblemTypeCount,
    matchingConceptCount,
    totalMatchedCount,
    autoExpandedChapterIds,
    isFiltered,
  };
}
