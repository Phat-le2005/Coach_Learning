import type {
  StudentLearningSubjectRead,
  StudentMasteryRead,
  SubjectMasteryRead,
} from "../../lib/api/contracts";

export interface StudentSubjectAccess {
  /** Subjects backed by real student activity or explicitly released for self-study. */
  subjects: StudentLearningSubjectRead[];
  /** Subjects added by the self-study publication gate, before the first activity exists. */
  discoveryOnlySubjectIds: string[];
}

const SUBJECT_CODE_PATTERN = /^[A-Z0-9][A-Z0-9_:-]{0,63}$/;

export class SelfStudyPublicationPolicyError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SelfStudyPublicationPolicyError";
  }
}

export function parsePublishedSelfStudySubjectCodes(rawValue: string | undefined): string[] {
  if (!rawValue) return [];

  const codes = rawValue
    .split(",")
    .map((value) => value.trim().toUpperCase())
    .filter((value) => SUBJECT_CODE_PATTERN.test(value));

  return [...new Set(codes)];
}

/**
 * Reads an environment-owned publication policy without silently converting a
 * missing or malformed deployment setting into "no subjects are available".
 * An explicitly empty value remains a valid fail-closed policy.
 */
export function requirePublishedSelfStudySubjectCodes(
  rawValue: string | undefined
): string[] {
  if (rawValue === undefined) {
    throw new SelfStudyPublicationPolicyError(
      "SELF_STUDY_PUBLISHED_SUBJECT_CODES must be configured explicitly."
    );
  }

  const configuredValues = rawValue
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
  if (configuredValues.some((value) => !SUBJECT_CODE_PATTERN.test(value.toUpperCase()))) {
    throw new SelfStudyPublicationPolicyError(
      "SELF_STUDY_PUBLISHED_SUBJECT_CODES contains an invalid subject code."
    );
  }

  return parsePublishedSelfStudySubjectCodes(rawValue);
}

function hasBrowsableCurriculum(subject: SubjectMasteryRead): boolean {
  return subject.chapters.some((chapter) =>
    chapter.topics.some((topic) => topic.problem_types.length > 0)
  );
}

/**
 * Extends the student's real activity scope with curriculum subjects that have been
 * explicitly released for self-study by server configuration. Mastery is used only
 * as the authenticated curriculum read model; it is never treated as a publication
 * decision on its own.
 */
export function resolveStudentSubjectAccess(
  activitySubjects: readonly StudentLearningSubjectRead[],
  mastery: StudentMasteryRead | null | undefined,
  publishedSelfStudyCodes: readonly string[]
): StudentSubjectAccess {
  const subjects = activitySubjects.map((subject) => ({ ...subject }));
  const knownIds = new Set(subjects.map((subject) => subject.id));
  const knownCodes = new Set(subjects.map((subject) => subject.code.toUpperCase()));
  const allowedCodes = new Set(publishedSelfStudyCodes.map((code) => code.toUpperCase()));
  const discoveryOnlySubjectIds: string[] = [];

  for (const subject of mastery?.subjects ?? []) {
    const normalizedCode = subject.code.toUpperCase();
    if (
      !allowedCodes.has(normalizedCode) ||
      knownIds.has(subject.subject_id) ||
      knownCodes.has(normalizedCode) ||
      !hasBrowsableCurriculum(subject)
    ) {
      continue;
    }

    subjects.push({
      id: subject.subject_id,
      code: subject.code,
      name: subject.name,
    });
    knownIds.add(subject.subject_id);
    knownCodes.add(normalizedCode);
    discoveryOnlySubjectIds.push(subject.subject_id);
  }

  return { subjects, discoveryOnlySubjectIds };
}

export function selectAccessibleSubject(
  access: StudentSubjectAccess,
  requestedSubjectId: string | undefined,
  focusSubjectId: string | null
): StudentLearningSubjectRead | undefined {
  if (requestedSubjectId) {
    const normalizedRequest = requestedSubjectId.toLowerCase();
    return access.subjects.find(
      (subject) =>
        subject.id === requestedSubjectId || subject.code.toLowerCase() === normalizedRequest
    );
  }

  return (
    access.subjects.find((subject) => subject.id === focusSubjectId) ?? access.subjects[0]
  );
}
