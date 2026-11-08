const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function studentQuestionImagePath(assignmentId: string, itemId: string, index: string): string | null {
  if (!UUID.test(assignmentId) || !UUID.test(itemId) || !/^\d{1,6}$/.test(index)) return null;
  return `/students/me/assignments/${assignmentId}/material-items/${itemId}/assets/${index}`;
}
