"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.API_PATHS = exports.ApiNetworkError = exports.ApiResponseError = void 0;
exports.normalizeApiBaseUrl = normalizeApiBaseUrl;
exports.getBackendBaseUrl = getBackendBaseUrl;
exports.createApiClient = createApiClient;
exports.createBackendApiClient = createBackendApiClient;
exports.getHealth = getHealth;
const contracts_1 = require("./contracts");
const validation_1 = require("./validation");
function parsePaperOcr(value, path = "paper_ocr") {
    const row = (0, validation_1.record)(value, path);
    if (row.provider !== "GEMINI")
        throw new validation_1.ApiContractError("Unsupported paper OCR provider", `${path}.provider`);
    return {
        paper_id: (0, validation_1.string)(row.paper_id, `${path}.paper_id`),
        file_sha256: (0, validation_1.string)(row.file_sha256, `${path}.file_sha256`),
        provider: "GEMINI",
        suggestions: (0, validation_1.array)(row.suggestions, `${path}.suggestions`, (value, itemPath) => {
            const item = (0, validation_1.record)(value, itemPath);
            if (!["FORMULA", "TEXT", "TABLE"].includes(item.kind)) {
                throw new validation_1.ApiContractError("Unsupported OCR suggestion kind", `${itemPath}.kind`);
            }
            return {
                page_number: (0, validation_1.integer)(item.page_number, `${itemPath}.page_number`),
                kind: item.kind,
                text: (0, validation_1.string)(item.text, `${itemPath}.text`),
                uncertain: (0, validation_1.boolean)(item.uncertain, `${itemPath}.uncertain`),
            };
        }),
    };
}
function parsePaperAttachment(value, path = "paper") {
    const row = (0, validation_1.record)(value, path);
    const contentType = (0, validation_1.string)(row.content_type, `${path}.content_type`);
    if (!["image/png", "image/jpeg", "application/pdf"].includes(contentType)) {
        throw new validation_1.ApiContractError("Unsupported paper type", `${path}.content_type`);
    }
    return {
        id: (0, validation_1.string)(row.id, `${path}.id`), file_name: (0, validation_1.string)(row.file_name, `${path}.file_name`),
        content_type: contentType,
        size_bytes: (0, validation_1.integer)(row.size_bytes, `${path}.size_bytes`),
        sha256: (0, validation_1.string)(row.sha256, `${path}.sha256`),
        created_at: (0, validation_1.string)(row.created_at, `${path}.created_at`),
    };
}
class ApiResponseError extends Error {
    constructor(message, status, code, category, details) {
        super(message);
        this.status = status;
        this.code = code;
        this.category = category;
        this.details = details;
        this.name = "ApiResponseError";
    }
}
exports.ApiResponseError = ApiResponseError;
class ApiNetworkError extends Error {
    constructor(message, cause) {
        super(message);
        this.cause = cause;
        this.name = "ApiNetworkError";
    }
}
exports.ApiNetworkError = ApiNetworkError;
exports.API_PATHS = {
    login: "/auth/login",
    refresh: "/auth/refresh",
    me: "/auth/me",
    studentLearningState: "/students/me/learning-state",
    studentMastery: "/students/me/mastery",
    studentProblemTypeMastery: (id) => `/students/me/mastery/problem-types/${encodeURIComponent(id)}`,
    studentConceptMastery: (id) => `/students/me/mastery/concepts/${encodeURIComponent(id)}`,
    mathAttempts: "/api/v2/math-solutions/attempts",
    practiceSessions: "/practice/sessions",
    mathPracticeNextProblem: (id) => `/api/v2/math-solutions/practice-sessions/${encodeURIComponent(id)}/next-problem`,
    mathAttempt: (id) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}`,
    mathAttemptProblem: (id) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}/problem`,
    mathAttemptSubmit: (id) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}/submit`,
    mathAttemptAIReview: (id) => `/api/v3/math-solutions/attempts/${encodeURIComponent(id)}/ai-review`,
    mathPaper: (id) => `/api/v3/math-solutions/attempts/${encodeURIComponent(id)}/paper`,
    mathPaperFile: (id, paperId) => `/api/v3/math-solutions/attempts/${encodeURIComponent(id)}/paper/${encodeURIComponent(paperId)}`,
    mathPaperOcr: (id, paperId) => `/api/v3/math-solutions/attempts/${encodeURIComponent(id)}/paper/${encodeURIComponent(paperId)}/ocr`,
    mathAttemptSteps: (id) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}/steps`,
    mathAttemptStepUpdate: (attemptId, stepId) => `/api/v2/math-solutions/attempts/${encodeURIComponent(attemptId)}/steps/${encodeURIComponent(stepId)}`,
    mathAttemptStepDelete: (attemptId, stepId) => `/api/v2/math-solutions/attempts/${encodeURIComponent(attemptId)}/steps/${encodeURIComponent(stepId)}/delete`,
    mathInkDocument: (id) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}/ink`,
    mathInkPage: (id, pageIndex) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}/ink/pages/${pageIndex}`,
    mathOcrRecognize: (id) => `/api/v2/math-solutions/attempts/${encodeURIComponent(id)}/ocr/recognize`,
};
function statusCategory(status) {
    if (status === 401)
        return "unauthorized";
    if (status === 403)
        return "forbidden";
    if (status === 404)
        return "not_found";
    if (status === 409)
        return "conflict";
    if (status === 422)
        return "validation";
    if (status === 503)
        return "unavailable";
    return "http";
}
function parseErrorEnvelope(value) {
    try {
        const outer = (0, validation_1.record)(value, "error_response");
        const detail = (0, validation_1.record)(outer.error, "error_response.error");
        let details;
        if (detail.details !== undefined && detail.details !== null) {
            if (!Array.isArray(detail.details))
                throw new validation_1.ApiContractError("Expected validation issue array", "error_response.error.details");
            details = detail.details.map((item, index) => {
                const issue = (0, validation_1.record)(item, `error_response.error.details[${index}]`);
                return { field: (0, validation_1.string)(issue.field, `error_response.error.details[${index}].field`), message: (0, validation_1.string)(issue.message, `error_response.error.details[${index}].message`) };
            });
        }
        return { error: Object.assign({ code: (0, validation_1.string)(detail.code, "error_response.error.code"), message: (0, validation_1.string)(detail.message, "error_response.error.message") }, (details === undefined ? {} : { details })) };
    }
    catch (_a) {
        return null;
    }
}
function normalizeApiBaseUrl(value) {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password)
        throw new Error("API_BASE_URL must be an HTTP(S) URL without credentials.");
    if (url.pathname !== "/" || url.search || url.hash)
        throw new Error("API_BASE_URL must contain only the origin; canonical API paths are root paths.");
    return url.origin;
}
function getBackendBaseUrl() {
    var _a;
    const value = (_a = process.env.API_BASE_URL) !== null && _a !== void 0 ? _a : process.env.NEXT_PUBLIC_API_BASE_URL;
    if (!value)
        throw new Error("API_BASE_URL is not configured.");
    return normalizeApiBaseUrl(value);
}
function createApiClient({ baseUrl, fetcher = fetch }) {
    const origin = normalizeApiBaseUrl(baseUrl);
    async function request(path, parser, init = {}, accessToken) {
        var _a, _b;
        if (!path.startsWith("/") || path.startsWith("/api/v1"))
            throw new Error(`Non-canonical API path: ${path}`);
        const headers = new Headers(init.headers);
        headers.set("Accept", "application/json");
        if (init.body !== undefined && !(init.body instanceof FormData))
            headers.set("Content-Type", "application/json");
        if (accessToken)
            headers.set("Authorization", `Bearer ${accessToken}`);
        let response;
        try {
            response = await fetcher(`${origin}${path}`, Object.assign(Object.assign({}, init), { headers, cache: "no-store" }));
        }
        catch (error) {
            throw new ApiNetworkError("Không thể kết nối tới EduMS API.", error);
        }
        let body = null;
        const raw = await response.text();
        if (raw) {
            try {
                body = JSON.parse(raw);
            }
            catch (_c) {
                if (response.ok)
                    throw new validation_1.ApiContractError("Expected a JSON response");
            }
        }
        if (!response.ok) {
            const envelope = parseErrorEnvelope(body);
            throw new ApiResponseError((_a = envelope === null || envelope === void 0 ? void 0 : envelope.error.message) !== null && _a !== void 0 ? _a : "EduMS API trả về lỗi không hợp lệ.", response.status, (_b = envelope === null || envelope === void 0 ? void 0 : envelope.error.code) !== null && _b !== void 0 ? _b : "HTTP_ERROR", statusCategory(response.status), envelope === null || envelope === void 0 ? void 0 : envelope.error.details);
        }
        return parser(body);
    }
    return {
        login(input) {
            return request(exports.API_PATHS.login, contracts_1.parseTokenPair, { method: "POST", body: JSON.stringify((0, contracts_1.validateLoginRequest)(input)) });
        },
        refresh(refreshToken) {
            const body = { refresh_token: refreshToken };
            return request(exports.API_PATHS.refresh, contracts_1.parseTokenPair, { method: "POST", body: JSON.stringify(body) });
        },
        me(accessToken) { return request(exports.API_PATHS.me, contracts_1.parseUserRead, { method: "GET" }, accessToken); },
        studentLearningState(accessToken, subjectId) {
            const suffix = subjectId ? `?subject_id=${encodeURIComponent(subjectId)}` : "";
            return request(`${exports.API_PATHS.studentLearningState}${suffix}`, contracts_1.parseStudentLearningState, { method: "GET" }, accessToken);
        },
        studentMastery(accessToken) {
            return request(exports.API_PATHS.studentMastery, contracts_1.parseStudentMastery, { method: "GET" }, accessToken);
        },
        studentProblemTypeMastery(accessToken, problemTypeId) {
            return request(exports.API_PATHS.studentProblemTypeMastery(problemTypeId), contracts_1.parseProblemTypeMastery, { method: "GET" }, accessToken);
        },
        studentConceptMastery(accessToken, conceptId) {
            return request(exports.API_PATHS.studentConceptMastery(conceptId), contracts_1.parseConceptMastery, { method: "GET" }, accessToken);
        },
        listMathAttempts(accessToken, query) {
            return request(`${exports.API_PATHS.mathAttempts}?${(() => {
                const page = (query === null || query === void 0 ? void 0 : query.page) && Number.isFinite(query.page) && query.page >= 1 ? Math.floor(query.page) : 1;
                const size = (query === null || query === void 0 ? void 0 : query.size) && Number.isFinite(query.size) && query.size >= 1 && query.size <= 100 ? Math.floor(query.size) : 20;
                const params = new URLSearchParams({ page: String(page), size: String(size) });
                if ((query === null || query === void 0 ? void 0 : query.status) && query.status.trim().length > 0)
                    params.set("status", query.status.trim());
                return params.toString();
            })()}`, contracts_1.parseMathAttemptsPageRead, { method: "GET" }, accessToken);
        },
        createPracticeSession(accessToken, subjectId) {
            return request(exports.API_PATHS.practiceSessions, contracts_1.parsePracticeSessionStartRead, {
                method: "POST",
                body: JSON.stringify({ subject_id: subjectId, session_type: "PRACTICE", problem_type_ids: [], concept_ids: [] }),
            }, accessToken);
        },
        getMathPracticeNextProblem(accessToken, sessionId) {
            return request(exports.API_PATHS.mathPracticeNextProblem(sessionId), contracts_1.parseProblemRead, { method: "GET" }, accessToken);
        },
        createMathAttempt(accessToken, sessionId, questionId) {
            return request(exports.API_PATHS.mathAttempts, contracts_1.parseSolutionAttemptRead, {
                method: "POST",
                body: JSON.stringify({
                    source_kind: "CANONICAL",
                    context_type: "SELF_PRACTICE",
                    mode: "INDEPENDENT_SOLUTION",
                    create_idempotency_key: `student-workspace:${sessionId}`,
                    question_id: questionId,
                    practice_session_id: sessionId,
                }),
            }, accessToken);
        },
        getMathAttempt(accessToken, attemptId) {
            return request(exports.API_PATHS.mathAttempt(attemptId), contracts_1.parseSolutionAttemptRead, { method: "GET" }, accessToken);
        },
        getMathAttemptProblem(accessToken, attemptId) {
            return request(exports.API_PATHS.mathAttemptProblem(attemptId), contracts_1.parseProblemRead, { method: "GET" }, accessToken);
        },
        getMathInkDocument(accessToken, attemptId) {
            return request(exports.API_PATHS.mathInkDocument(attemptId), contracts_1.parseInkDocumentRead, { method: "GET" }, accessToken);
        },
        getMathInkPage(accessToken, attemptId, pageIndex) {
            return request(exports.API_PATHS.mathInkPage(attemptId, pageIndex), contracts_1.parseInkPageRead, { method: "GET" }, accessToken);
        },
        saveMathInkPage(accessToken, attemptId, pageIndex, payload) {
            return request(exports.API_PATHS.mathInkPage(attemptId, pageIndex), contracts_1.parseInkSaveRead, { method: "PUT", body: JSON.stringify(payload) }, accessToken);
        },
        recognizeMathInk(accessToken, attemptId, payload) {
            return request(exports.API_PATHS.mathOcrRecognize(attemptId), contracts_1.parseOCRRecognizeResponse, { method: "POST", body: JSON.stringify(payload) }, accessToken);
        },
        createMathStep(accessToken, attemptId, payload) {
            return request(exports.API_PATHS.mathAttemptSteps(attemptId), contracts_1.parseSolutionAttemptRead, { method: "POST", body: JSON.stringify(payload) }, accessToken);
        },
        updateMathStep(accessToken, attemptId, stepId, payload) {
            return request(exports.API_PATHS.mathAttemptStepUpdate(attemptId, stepId), contracts_1.parseSolutionAttemptRead, { method: "PATCH", body: JSON.stringify(payload) }, accessToken);
        },
        submitMathAttempt(accessToken, attemptId, payload) {
            return request(exports.API_PATHS.mathAttemptSubmit(attemptId), contracts_1.parseSolutionAttemptRead, { method: "POST", body: JSON.stringify(payload) }, accessToken);
        },
        getMathAIReviewAvailability(accessToken, attemptId) {
            return request(exports.API_PATHS.mathAttemptAIReview(attemptId), contracts_1.parseAIReviewAvailabilityRead, { method: "GET" }, accessToken);
        },
        reviewMathAttempt(accessToken, attemptId) {
            return request(exports.API_PATHS.mathAttemptAIReview(attemptId), contracts_1.parseAIReviewRead, { method: "POST" }, accessToken);
        },
        listMathPaper(accessToken, attemptId) {
            return request(exports.API_PATHS.mathPaper(attemptId), (value) => (0, validation_1.array)(value, "paper", parsePaperAttachment), { method: "GET" }, accessToken);
        },
        uploadMathPaper(accessToken, attemptId, file) {
            const form = new FormData();
            form.append("file", file, file.name);
            return request(exports.API_PATHS.mathPaper(attemptId), parsePaperAttachment, { method: "POST", body: form }, accessToken);
        },
        deleteMathPaper(accessToken, attemptId, paperId) {
            return request(exports.API_PATHS.mathPaperFile(attemptId, paperId), () => undefined, { method: "DELETE" }, accessToken);
        },
        recognizeMathPaper(accessToken, attemptId, paperId) {
            return request(exports.API_PATHS.mathPaperOcr(attemptId, paperId), parsePaperOcr, { method: "POST" }, accessToken);
        },
        deleteMathStep(accessToken, attemptId, stepId, payload) {
            return request(exports.API_PATHS.mathAttemptStepDelete(attemptId, stepId), contracts_1.parseSolutionAttemptRead, { method: "POST", body: JSON.stringify(payload) }, accessToken);
        },
    };
}
function createBackendApiClient() { return createApiClient({ baseUrl: getBackendBaseUrl() }); }
async function getHealth(signal) {
    var _a, _b;
    let response;
    try {
        response = await fetch(`${getBackendBaseUrl()}/health`, { headers: { Accept: "application/json" }, cache: "no-store", signal });
    }
    catch (error) {
        throw new ApiNetworkError("Không thể kết nối tới EduMS API.", error);
    }
    const body = await response.json().catch(() => null);
    if (!response.ok) {
        const envelope = parseErrorEnvelope(body);
        throw new ApiResponseError((_a = envelope === null || envelope === void 0 ? void 0 : envelope.error.message) !== null && _a !== void 0 ? _a : "EduMS API trả về lỗi.", response.status, (_b = envelope === null || envelope === void 0 ? void 0 : envelope.error.code) !== null && _b !== void 0 ? _b : "HTTP_ERROR", statusCategory(response.status), envelope === null || envelope === void 0 ? void 0 : envelope.error.details);
    }
    const source = (0, validation_1.record)(body, "response");
    if (source.status !== "ok")
        throw new validation_1.ApiContractError("Expected status=ok", "response.status");
    return { status: "ok" };
}
