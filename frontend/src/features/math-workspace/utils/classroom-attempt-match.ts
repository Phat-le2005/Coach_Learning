/** Match the problem endpoint and assignment-detail fallback using stable source IDs. */
export function matchesClassroomAttempt(problem: Record<string, unknown>, attempt: Record<string, unknown>): boolean {
  const materialId = problem.student_assignment_material_item_id ?? problem.student_material_item_id
    ?? (problem.source_kind === "TEACHER_MATERIAL" ? problem.id : null);
  if (typeof materialId === "string" && materialId.length > 0) {
    return attempt.student_assignment_material_item_id === materialId;
  }
  const questionItemId = problem.assignment_student_question_id;
  if (typeof questionItemId === "string" && questionItemId.length > 0) {
    return attempt.assignment_student_question_id === questionItemId;
  }
  const questionId = problem.question_id
    ?? (problem.source_kind === "CANONICAL" ? problem.id : null);
  return typeof questionId === "string" && questionId.length > 0
    && attempt.question_id === questionId;
}
