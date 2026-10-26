"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.parseAttemptsStatusParam = parseAttemptsStatusParam;
exports.parseAttemptsPageParam = parseAttemptsPageParam;
exports.getAttemptStatusMeta = getAttemptStatusMeta;
exports.getAttemptContextLabel = getAttemptContextLabel;
exports.formatAttemptDateTime = formatAttemptDateTime;
exports.toAttemptCardViewModel = toAttemptCardViewModel;
exports.selectContinueLearningAttempts = selectContinueLearningAttempts;
exports.buildPaginationViewModel = buildPaginationViewModel;
exports.filterAndSortAttempts = filterAndSortAttempts;
exports.toStudentAttemptsViewModel = toStudentAttemptsViewModel;
const VALID_FILTER_STATUSES = new Set([
    "ALL",
    "IN_PROGRESS",
    "DRAFT",
    "SUBMITTED",
    "EVALUATED",
    "ABANDONED",
]);
function parseAttemptsStatusParam(raw) {
    if (!raw)
        return "ALL";
    const normalized = raw.trim().toUpperCase();
    return VALID_FILTER_STATUSES.has(normalized) ? normalized : "ALL";
}
function parseAttemptsPageParam(raw) {
    if (!raw)
        return 1;
    const parsed = Number.parseInt(raw.trim(), 10);
    if (!Number.isFinite(parsed) || parsed < 1)
        return 1;
    return parsed;
}
/**
 * Maps real backend SolutionAttemptStatus values to localized Vietnamese UI labels & semantic tones.
 * Never relies on color alone — every status carries an explicit Vietnamese text label.
 */
function getAttemptStatusMeta(status) {
    const normalized = status.trim().toUpperCase();
    switch (normalized) {
        case "DRAFT":
            return {
                code: "DRAFT",
                label: "Bản nháp",
                tone: "draft",
                actionLabel: "Mở bản nháp",
                isResumable: true,
            };
        case "IN_PROGRESS":
            return {
                code: "IN_PROGRESS",
                label: "Đang thực hiện",
                tone: "inProgress",
                actionLabel: "Tiếp tục làm bài",
                isResumable: true,
            };
        case "SUBMITTED":
            return {
                code: "SUBMITTED",
                label: "Đã nộp",
                tone: "submitted",
                actionLabel: "Xem lại lời giải",
                isResumable: false,
            };
        case "EVALUATED":
            return {
                code: "EVALUATED",
                label: "Đã đánh giá",
                tone: "evaluated",
                actionLabel: "Xem kết quả",
                isResumable: false,
            };
        case "ABANDONED":
            return {
                code: "ABANDONED",
                label: "Đã khép lại",
                tone: "abandoned",
                actionLabel: "Xem bản lưu",
                isResumable: false,
            };
        default:
            return {
                code: normalized || "UNKNOWN",
                label: normalized ? `Trạng thái: ${normalized}` : "Chưa rõ trạng thái",
                tone: "draft",
                actionLabel: "Mở bài làm",
                isResumable: false,
            };
    }
}
function getAttemptContextLabel(contextType) {
    switch (contextType === null || contextType === void 0 ? void 0 : contextType.trim().toUpperCase()) {
        case "CLASSROOM_ASSIGNMENT":
            return "Bài tập lớp học";
        case "SELF_PRACTICE":
            return "Phiên tự luyện";
        default:
            return "Bài làm giấy số";
    }
}
function formatAttemptDateTime(isoString) {
    if (!isoString)
        return null;
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime()))
        return null;
    const day = String(date.getDate()).padStart(2, "0");
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const year = date.getFullYear();
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${day}/${month}/${year} · ${hours}:${minutes}`;
}
function toSafeTimestamp(isoString) {
    if (!isoString)
        return 0;
    const ms = Date.parse(isoString);
    return Number.isNaN(ms) ? 0 : ms;
}
/**
 * Converts a real SolutionAttemptRead into an AttemptCardViewModel.
 * Strictly avoids inventing problem titles not present in the API response:
 * uses real context_type + created_at timestamp (or short attempt code fallback).
 */
function toAttemptCardViewModel(attempt) {
    var _a, _b, _c;
    const shortCode = attempt.id.slice(0, 8).toUpperCase();
    const status = getAttemptStatusMeta(attempt.status);
    const contextLabel = getAttemptContextLabel(attempt.context_type);
    const createdAtLabel = formatAttemptDateTime(attempt.created_at);
    const updatedAtLabel = formatAttemptDateTime(attempt.updated_at);
    const submittedAtLabel = formatAttemptDateTime((_a = attempt.submitted_at) !== null && _a !== void 0 ? _a : null);
    const title = createdAtLabel
        ? `${contextLabel} · ${createdAtLabel}`
        : `${contextLabel} #${shortCode}`;
    const stepCount = Array.isArray(attempt.steps) ? attempt.steps.length : null;
    const stepSummaryLabel = stepCount === null
        ? `Phiên bản #${attempt.current_revision}`
        : stepCount === 0
            ? "Chưa lưu bước nhận diện"
            : `${stepCount} bước lời giải đã lưu`;
    const createdTimestampMs = toSafeTimestamp(attempt.created_at);
    const updatedTimestampMs = toSafeTimestamp(attempt.updated_at) || createdTimestampMs;
    const searchableText = [
        title,
        shortCode,
        `#${shortCode}`,
        attempt.id,
        contextLabel,
        status.label,
        status.code,
        createdAtLabel !== null && createdAtLabel !== void 0 ? createdAtLabel : "",
        updatedAtLabel !== null && updatedAtLabel !== void 0 ? updatedAtLabel : "",
        submittedAtLabel !== null && submittedAtLabel !== void 0 ? submittedAtLabel : "",
        stepSummaryLabel,
    ]
        .join(" ")
        .toLowerCase();
    return {
        id: attempt.id,
        href: `/student/attempts/${encodeURIComponent(attempt.id)}`,
        shortCode,
        title,
        contextLabel,
        status,
        createdAtIso: attempt.created_at,
        updatedAtIso: (_b = attempt.updated_at) !== null && _b !== void 0 ? _b : attempt.created_at,
        submittedAtIso: (_c = attempt.submitted_at) !== null && _c !== void 0 ? _c : null,
        createdAtLabel: createdAtLabel !== null && createdAtLabel !== void 0 ? createdAtLabel : `Mã phiên #${shortCode}`,
        updatedAtLabel,
        submittedAtLabel,
        createdTimestampMs,
        updatedTimestampMs,
        stepCount,
        stepSummaryLabel,
        revisionNumber: attempt.current_revision,
        searchableText,
    };
}
/**
 * Selects and orders unfinished attempts (IN_PROGRESS prioritized ahead of DRAFT,
 * then sorted by most recently updated) without duplicates.
 */
function selectContinueLearningAttempts(candidates, limit = 3) {
    const uniqueById = new Map();
    for (const item of candidates) {
        const code = item.status.trim().toUpperCase();
        if (code !== "IN_PROGRESS" && code !== "DRAFT")
            continue;
        if (!uniqueById.has(item.id)) {
            uniqueById.set(item.id, item);
        }
    }
    return Array.from(uniqueById.values())
        .map(toAttemptCardViewModel)
        .sort((a, b) => {
        if (a.status.code !== b.status.code) {
            return a.status.code === "IN_PROGRESS" ? -1 : 1;
        }
        if (b.updatedTimestampMs !== a.updatedTimestampMs) {
            return b.updatedTimestampMs - a.updatedTimestampMs;
        }
        return b.createdTimestampMs - a.createdTimestampMs;
    })
        .slice(0, Math.max(1, limit));
}
function buildPaginationViewModel(pageData) {
    const total = Math.max(0, pageData.total);
    const size = Math.max(1, pageData.size);
    const totalPages = total === 0 ? 0 : Math.max(1, pageData.total_pages || Math.ceil(total / size));
    const page = Math.max(1, pageData.page);
    const countOnPage = pageData.items.length;
    const rangeStart = total === 0 || countOnPage === 0 ? 0 : (page - 1) * size + 1;
    const rangeEnd = rangeStart === 0 ? 0 : Math.min(total, rangeStart + countOnPage - 1);
    return {
        page,
        size,
        total,
        totalPages,
        rangeStart,
        rangeEnd,
        hasPreviousPage: page > 1 && totalPages > 0,
        hasNextPage: totalPages > 0 && page < totalPages,
    };
}
function filterAndSortAttempts(items, searchQuery, sortOrder) {
    const normalizedQuery = searchQuery.trim().toLowerCase();
    const filtered = normalizedQuery
        ? items.filter((item) => item.searchableText.includes(normalizedQuery))
        : [...items];
    filtered.sort((a, b) => {
        if (sortOrder === "created_asc") {
            return a.createdTimestampMs - b.createdTimestampMs || a.id.localeCompare(b.id);
        }
        if (sortOrder === "created_desc") {
            return b.createdTimestampMs - a.createdTimestampMs || b.id.localeCompare(a.id);
        }
        // Default: updated_desc
        return (b.updatedTimestampMs - a.updatedTimestampMs ||
            b.createdTimestampMs - a.createdTimestampMs ||
            b.id.localeCompare(a.id));
    });
    return filtered;
}
function toStudentAttemptsViewModel(input) {
    var _a, _b, _c, _d;
    const resumablePool = [
        ...((_b = (_a = input.inProgressPage) === null || _a === void 0 ? void 0 : _a.items) !== null && _b !== void 0 ? _b : []),
        ...((_d = (_c = input.draftPage) === null || _c === void 0 ? void 0 : _c.items) !== null && _d !== void 0 ? _d : []),
        ...input.attemptsPage.items,
    ];
    const continueLearningItems = selectContinueLearningAttempts(resumablePool, 3);
    const totalActiveCount = input.inProgressPage && input.draftPage
        ? Math.max(0, input.inProgressPage.total) + Math.max(0, input.draftPage.total)
        : continueLearningItems.length;
    return {
        student: {
            displayName: input.displayName.trim() || "Bạn",
            email: input.email,
        },
        subjects: input.subjects,
        subjectsLoaded: input.subjectsLoaded,
        defaultSubjectId: input.defaultSubjectId,
        activeStatusFilter: input.activeStatusFilter,
        continueLearningItems,
        totalActiveCount,
        libraryItems: input.attemptsPage.items.map(toAttemptCardViewModel),
        pagination: buildPaginationViewModel(input.attemptsPage),
    };
}
