import type { StudentLearningSubjectRead, StudentMasteryRead } from "@/lib/api/contracts";

import type {
  KnowledgeBiome,
  KnowledgeChapterNode,
  KnowledgeConceptNode,
  KnowledgeForestSummary,
  KnowledgeForestViewModel,
  KnowledgeProblemTypeNode,
  KnowledgeTopicNode,
} from "./types";

const fallbackBiomes: KnowledgeBiome[] = ["meadow", "river", "mountain", "forest", "sky"];

export function toKnowledgeForestViewModel(
  mastery: StudentMasteryRead | null | undefined,
  availableSubjects: StudentLearningSubjectRead[] = [],
  selectedSubjectId?: string
): KnowledgeForestViewModel {
  // Safe fallback when availableSubjects is empty
  if (!availableSubjects || availableSubjects.length === 0) {
    return {
      subject: { id: "", code: "", name: "Chưa có môn học" },
      availableSubjects: [],
      summary: createEmptySummary(),
      chapters: [],
      concepts: [],
      hasCurriculum: false,
      hasEvidence: false,
    };
  }

  // Filter mastery subjects to only those in the student's available scope
  const availableIds = new Set(availableSubjects.map((s) => s.id));
  const availableCodes = new Set(availableSubjects.map((s) => s.code));

  const scopedMasterySubjects = (mastery?.subjects ?? []).filter(
    (subj) => availableIds.has(subj.subject_id) || availableCodes.has(subj.code)
  );

  // Determine active subject from student's available scope
  const requestedAvailableSubject = selectedSubjectId
    ? availableSubjects.find(
        (s) => s.id === selectedSubjectId || s.code.toLowerCase() === selectedSubjectId.toLowerCase()
      )
    : undefined;

  const activeSubjectInfo = requestedAvailableSubject ?? availableSubjects[0];

  // Find corresponding mastery data for this active subject
  const activeMasterySubject = scopedMasterySubjects.find(
    (subj) =>
      subj.subject_id === activeSubjectInfo.id ||
      subj.code.toLowerCase() === activeSubjectInfo.code.toLowerCase()
  );

  if (!activeMasterySubject) {
    return {
      subject: {
        id: activeSubjectInfo.id,
        code: activeSubjectInfo.code,
        name: activeSubjectInfo.name,
      },
      availableSubjects,
      summary: createEmptySummary(),
      chapters: [],
      concepts: [],
      hasCurriculum: false,
      hasEvidence: false,
    };
  }

  // Map chapters, topics, problem types
  let totalMastered = 0;
  let totalPracticing = 0;
  let totalLearning = 0;
  let totalWeak = 0;
  let totalReviewDue = 0;
  let totalNotStarted = 0;
  let totalProblemTypes = 0;

  const chapters: KnowledgeChapterNode[] = activeMasterySubject.chapters.map(
    (chapter, chapterIndex) => {
      const biome = fallbackBiomes[chapterIndex % fallbackBiomes.length];

      const topics: KnowledgeTopicNode[] = chapter.topics.map((topic) => {
        const problemTypes: KnowledgeProblemTypeNode[] = topic.problem_types.map(
          (pt) => {
            totalProblemTypes += 1;

            switch (pt.state) {
              case "MASTERED":
                totalMastered += 1;
                break;
              case "PRACTICING":
                totalPracticing += 1;
                break;
              case "LEARNING":
                totalLearning += 1;
                break;
              case "WEAK":
                totalWeak += 1;
                break;
              case "REVIEW_DUE":
                totalReviewDue += 1;
                break;
              case "NOT_STARTED":
              default:
                totalNotStarted += 1;
                break;
            }

            const hasEvidence = pt.attempt_count > 0;
            return {
              id: pt.problem_type_id,
              code: pt.code,
              name: pt.name,
              topicId: topic.topic_id,
              topicName: topic.name,
              chapterId: chapter.chapter_id,
              chapterName: chapter.name,
              masteryScore: hasEvidence
                ? Math.round(pt.mastery_score * 100)
                : undefined,
              rawMasteryScore: pt.mastery_score,
              confidence: hasEvidence
                ? Math.round(pt.confidence * 100)
                : undefined,
              attemptCount: pt.attempt_count,
              correctCount: pt.correct_count,
              state: pt.state,
              lastPracticedAt: pt.last_practiced_at,
              isReviewDue: pt.state === "REVIEW_DUE",
            };
          }
        );

        const hasTopicEvidence = topic.attempt_count > 0;
        return {
          id: topic.topic_id,
          code: topic.code,
          name: topic.name,
          chapterId: chapter.chapter_id,
          problemTypeCount: topic.problem_type_count,
          startedProblemTypeCount: topic.started_problem_type_count,
          masteryScore: hasTopicEvidence
            ? Math.round(topic.mastery_score * 100)
            : undefined,
          rawMasteryScore: topic.mastery_score,
          state: topic.state,
          attemptCount: topic.attempt_count,
          problemTypes,
        };
      });

      const hasChapterEvidence = chapter.attempt_count > 0;
      return {
        id: chapter.chapter_id,
        code: chapter.code,
        name: chapter.name,
        biome,
        problemTypeCount: chapter.problem_type_count,
        startedProblemTypeCount: chapter.started_problem_type_count,
        masteryScore: hasChapterEvidence
          ? Math.round(chapter.mastery_score * 100)
          : undefined,
        rawMasteryScore: chapter.mastery_score,
        state: chapter.state,
        attemptCount: chapter.attempt_count,
        topics,
      };
    }
  );

  // Map concepts (subject-level knowledge nodes)
  const concepts: KnowledgeConceptNode[] = activeMasterySubject.concepts.map(
    (concept) => {
      const hasEvidence = concept.attempt_count > 0;
      return {
        id: concept.concept_id,
        code: concept.code,
        name: concept.name,
        subjectId: concept.subject_id,
        masteryScore: hasEvidence
          ? Math.round(concept.mastery_score * 100)
          : undefined,
        rawMasteryScore: concept.mastery_score,
        confidence: hasEvidence
          ? Math.round(concept.confidence * 100)
          : undefined,
        attemptCount: concept.attempt_count,
        correctCount: concept.correct_count,
        state: concept.state,
        lastPracticedAt: concept.last_practiced_at,
      };
    }
  );

  const hasSubjectEvidence = activeMasterySubject.attempt_count > 0;
  const summary: KnowledgeForestSummary = {
    problemTypeCount: totalProblemTypes || activeMasterySubject.problem_type_count,
    startedProblemTypeCount: activeMasterySubject.started_problem_type_count,
    masteryScore: hasSubjectEvidence
      ? Math.round(activeMasterySubject.mastery_score * 100)
      : undefined,
    rawMasteryScore: activeMasterySubject.mastery_score,
    confidence: hasSubjectEvidence
      ? Math.round(activeMasterySubject.confidence * 100)
      : undefined,
    attemptCount: activeMasterySubject.attempt_count,
    state: activeMasterySubject.state,
    masteredCount: totalMastered,
    practicingCount: totalPracticing,
    learningCount: totalLearning,
    weakCount: totalWeak,
    reviewDueCount: totalReviewDue,
    notStartedCount: totalNotStarted,
  };

  return {
    subject: {
      id: activeSubjectInfo.id,
      code: activeSubjectInfo.code,
      name: activeSubjectInfo.name,
    },
    availableSubjects,
    summary,
    chapters,
    concepts,
    hasCurriculum: chapters.length > 0,
    hasEvidence: hasSubjectEvidence,
  };
}

function createEmptySummary(): KnowledgeForestSummary {
  return {
    problemTypeCount: 0,
    startedProblemTypeCount: 0,
    rawMasteryScore: 0,
    attemptCount: 0,
    state: "NOT_STARTED",
    masteredCount: 0,
    weakCount: 0,
    learningCount: 0,
    practicingCount: 0,
    reviewDueCount: 0,
    notStartedCount: 0,
  };
}
