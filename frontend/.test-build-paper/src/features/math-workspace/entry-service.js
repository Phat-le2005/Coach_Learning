"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getWorkspaceSubjects = getWorkspaceSubjects;
require("server-only");
const discovery_1 = require("@/features/self-study/discovery");
const server_policy_1 = require("@/features/self-study/server-policy");
const client_1 = require("@/lib/api/client");
async function getWorkspaceSubjects(accessToken) {
    const client = (0, client_1.createBackendApiClient)();
    const learningState = await client.studentLearningState(accessToken);
    let mastery = null;
    try {
        mastery = await client.studentMastery(accessToken);
        if (mastery.student_id !== learningState.student_id)
            mastery = null;
    }
    catch (_a) {
        // Existing student activity remains accessible if the mastery read model is unavailable.
    }
    return (0, discovery_1.resolveStudentSubjectAccess)(learningState.available_subjects, mastery, (0, server_policy_1.getPublishedSelfStudySubjectCodes)()).subjects;
}
