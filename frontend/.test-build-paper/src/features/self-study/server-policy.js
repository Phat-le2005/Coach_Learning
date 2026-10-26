"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getPublishedSelfStudySubjectCodes = getPublishedSelfStudySubjectCodes;
require("server-only");
const discovery_1 = require("./discovery");
/**
 * Deployment-owned release gate. This must stay server-only because it is an
 * a publication policy, not a browser preference.
 */
function getPublishedSelfStudySubjectCodes() {
    return (0, discovery_1.requirePublishedSelfStudySubjectCodes)(process.env.SELF_STUDY_PUBLISHED_SUBJECT_CODES);
}
