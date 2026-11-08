import "server-only";

import { resolveStudentSubjectAccess } from "@/features/self-study/discovery";
import { getPublishedSelfStudySubjectCodes } from "@/features/self-study/server-policy";
import { createBackendApiClient } from "@/lib/api/client";
import type { StudentLearningSubjectRead } from "@/lib/api/contracts";

export async function getWorkspaceSubjects(accessToken: string): Promise<StudentLearningSubjectRead[]> {
  const client = createBackendApiClient();
  const learningState = await client.studentLearningState(accessToken);
  let mastery = null;
  try {
    mastery = await client.studentMastery(accessToken);
    if (mastery.student_id !== learningState.student_id) mastery = null;
  } catch {
    // Existing student activity remains accessible if the mastery read model is unavailable.
  }
  const access = resolveStudentSubjectAccess(
    learningState.available_subjects,
    mastery,
    getPublishedSelfStudySubjectCodes(),
  );
  const browsable = new Set(access.curriculumSubjectIds ?? []);
  return [...access.subjects.filter((subject) => browsable.has(subject.id)),
    ...access.subjects.filter((subject) => !browsable.has(subject.id))];
}
