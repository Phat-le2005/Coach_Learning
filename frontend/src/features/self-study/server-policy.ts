import "server-only";

import { parsePublishedSelfStudySubjectCodes } from "./discovery";

/**
 * Deployment-owned release gate. This must stay server-only because it is an
 * a publication policy, not a browser preference.
 */
export function getPublishedSelfStudySubjectCodes(): string[] {
  return parsePublishedSelfStudySubjectCodes(
    process.env.SELF_STUDY_PUBLISHED_SUBJECT_CODES
  );
}
