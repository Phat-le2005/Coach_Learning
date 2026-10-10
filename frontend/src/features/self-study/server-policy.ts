import "server-only";

import { requirePublishedSelfStudySubjectCodes } from "./discovery";

/**
 * Deployment-owned release gate. This must stay server-only because it is an
 * a publication policy, not a browser preference.
 */
export function getPublishedSelfStudySubjectCodes(): string[] {
  return requirePublishedSelfStudySubjectCodes(
    process.env.SELF_STUDY_PUBLISHED_SUBJECT_CODES
  );
}
