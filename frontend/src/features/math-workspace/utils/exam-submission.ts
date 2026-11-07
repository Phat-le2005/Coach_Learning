export interface ExamQuestionProgress {
  index: number;
  attemptId: string | null;
  status: string;
  stepCount?: number;
}

/** A question counts as answered if it has confirmed status, active steps, or is the current active attempt with steps. */
export function getExamMissingQuestions<T extends ExamQuestionProgress>(
  questions: T[],
  currentAttemptId: string,
  currentStatus: string | undefined,
  currentHasSteps?: boolean,
): T[] {
  return questions.filter((question) => {
    if (question.attemptId === currentAttemptId) {
      if (currentHasSteps) return false;
      const status = currentStatus ?? question.status;
      return status !== "SUBMITTED" && status !== "EVALUATED";
    }
    if ((question.stepCount ?? 0) > 0) return false;
    return question.status !== "SUBMITTED" && question.status !== "EVALUATED";
  });
}
