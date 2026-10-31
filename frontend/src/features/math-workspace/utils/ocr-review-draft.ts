import type { StepKind } from "@/lib/api/contracts";
import { classifyMathStep, type StepClassificationResult } from "./ocr-classifier";

/** A logical solution step, not necessarily identical to a geometric OCR region. */
export interface OcrReviewDraft {
  localId: string;
  pageIndex: number;
  sourceRegionIds: string[];
  sourceStrokeIds: string[];
  rawOcrLatex: string | null;
  contentLatex: string;
  explanationText: string;
  classification: StepClassificationResult;
  selectedStepKind: StepKind | null;
  stepKindSource: "SUGGESTED" | "MANUAL" | "UNRESOLVED";
  contentEdited: boolean;
  reviewStatus: "NEEDS_REVIEW" | "APPROVED" | "SKIPPED";
}

export interface OcrDraftSource {
  localId: string;
  pageIndex: number;
  regionIds: string[];
  strokeIds: string[];
}

function unique(values: readonly string[]): string[] {
  return [...new Set(values)];
}

function suggestion(
  contentLatex: string,
  explanationText: string,
): Pick<OcrReviewDraft, "classification" | "selectedStepKind" | "stepKindSource"> {
  const classification = classifyMathStep({ contentLatex, explanationText });
  return {
    classification,
    selectedStepKind: classification.status === "DETERMINED" ? classification.predictedType : null,
    stepKindSource: classification.status === "DETERMINED" ? "SUGGESTED" : "UNRESOLVED",
  };
}

export function createOcrReviewDraft(source: OcrDraftSource): OcrReviewDraft {
  return {
    localId: source.localId,
    pageIndex: source.pageIndex,
    sourceRegionIds: unique(source.regionIds),
    sourceStrokeIds: unique(source.strokeIds),
    rawOcrLatex: null,
    contentLatex: "",
    explanationText: "",
    ...suggestion("", ""),
    contentEdited: false,
    reviewStatus: "NEEDS_REVIEW",
  };
}

/** OCR can propose content but must never overwrite a student's prior correction or kind selection. */
export function applyOcrToDraft(draft: OcrReviewDraft, rawLatex: string): OcrReviewDraft {
  if (draft.reviewStatus !== "NEEDS_REVIEW") return draft;
  const contentLatex = draft.contentEdited ? draft.contentLatex : rawLatex;
  const next = suggestion(contentLatex, draft.explanationText);
  const manual = draft.stepKindSource === "MANUAL";
  return {
    ...draft,
    rawOcrLatex: rawLatex,
    contentLatex,
    classification: next.classification,
    selectedStepKind: manual ? draft.selectedStepKind : next.selectedStepKind,
    stepKindSource: manual ? "MANUAL" : next.stepKindSource,
  };
}

/** Editing a formula or explanation invalidates previous approval, never the student's chosen kind. */
export function editOcrReviewDraft(
  draft: OcrReviewDraft,
  changes: { contentLatex?: string; explanationText?: string },
): OcrReviewDraft {
  if (draft.reviewStatus === "SKIPPED") return draft;
  const contentLatex = changes.contentLatex ?? draft.contentLatex;
  const explanationText = changes.explanationText ?? draft.explanationText;
  const next = suggestion(contentLatex, explanationText);
  const manual = draft.stepKindSource === "MANUAL";
  return {
    ...draft,
    contentLatex,
    explanationText,
    contentEdited: draft.contentEdited || changes.contentLatex !== undefined,
    classification: next.classification,
    selectedStepKind: manual ? draft.selectedStepKind : next.selectedStepKind,
    stepKindSource: manual ? "MANUAL" : next.stepKindSource,
    reviewStatus: "NEEDS_REVIEW",
  };
}

export function selectOcrDraftKind(draft: OcrReviewDraft, kind: StepKind): OcrReviewDraft {
  return { ...draft, selectedStepKind: kind, stepKindSource: "MANUAL", reviewStatus: "NEEDS_REVIEW" };
}

export function canApproveOcrDraft(draft: OcrReviewDraft): boolean {
  return draft.reviewStatus !== "SKIPPED"
    && draft.selectedStepKind !== null
    && Boolean(draft.contentLatex.trim() || draft.explanationText.trim());
}

export function approveOcrDraft(draft: OcrReviewDraft): OcrReviewDraft {
  if (!canApproveOcrDraft(draft)) throw new Error("OCR_DRAFT_NOT_READY");
  return { ...draft, reviewStatus: "APPROVED" };
}

export function skipOcrDraft(draft: OcrReviewDraft): OcrReviewDraft {
  return { ...draft, reviewStatus: "SKIPPED" };
}

/** Merge only draft data. It does not modify ink or create a server mutation. */
export function mergeOcrReviewDrafts(
  first: OcrReviewDraft,
  second: OcrReviewDraft,
  localId: string,
): OcrReviewDraft {
  if (first.pageIndex !== second.pageIndex) throw new Error("OCR_DRAFT_DIFFERENT_PAGES");
  if (first.reviewStatus === "APPROVED" || second.reviewStatus === "APPROVED") {
    throw new Error("OCR_DRAFT_ALREADY_APPROVED");
  }
  const joinedLatex = [first.contentLatex, second.contentLatex].filter(Boolean).join("\n");
  const joinedExplanation = [first.explanationText, second.explanationText].filter(Boolean).join("\n");
  const next = suggestion(joinedLatex, joinedExplanation);
  return {
    localId,
    pageIndex: first.pageIndex,
    sourceRegionIds: unique([...first.sourceRegionIds, ...second.sourceRegionIds]),
    sourceStrokeIds: unique([...first.sourceStrokeIds, ...second.sourceStrokeIds]),
    rawOcrLatex: [first.rawOcrLatex, second.rawOcrLatex].filter((v) => v != null).join("\n") || null,
    contentLatex: joinedLatex,
    explanationText: joinedExplanation,
    classification: next.classification,
    // Do not guess that either source kind still describes their combined logical step.
    selectedStepKind: null,
    stepKindSource: "UNRESOLVED",
    contentEdited: true,
    reviewStatus: "NEEDS_REVIEW",
  };
}

/** Explicit, student-provided split; both drafts retain the source ink for traceability. */
export function splitOcrReviewDraft(
  draft: OcrReviewDraft,
  first: { localId: string; contentLatex: string; explanationText?: string },
  second: { localId: string; contentLatex: string; explanationText?: string },
): [OcrReviewDraft, OcrReviewDraft] {
  if (draft.reviewStatus === "APPROVED") throw new Error("OCR_DRAFT_ALREADY_APPROVED");
  if (first.localId === second.localId) throw new Error("OCR_DRAFT_DUPLICATE_ID");
  if (!first.contentLatex.trim() && !first.explanationText?.trim()) throw new Error("OCR_DRAFT_EMPTY_PART");
  if (!second.contentLatex.trim() && !second.explanationText?.trim()) throw new Error("OCR_DRAFT_EMPTY_PART");
  const part = (value: typeof first): OcrReviewDraft => {
    const latex = value.contentLatex;
    const explanation = value.explanationText ?? "";
    return {
      ...draft,
      localId: value.localId,
      sourceRegionIds: [...draft.sourceRegionIds],
      sourceStrokeIds: [...draft.sourceStrokeIds],
      contentLatex: latex,
      explanationText: explanation,
      ...suggestion(latex, explanation),
      contentEdited: true,
      reviewStatus: "NEEDS_REVIEW",
    };
  };
  return [part(first), part(second)];
}

export function reorderOcrReviewDrafts(
  drafts: readonly OcrReviewDraft[],
  from: number,
  to: number,
): OcrReviewDraft[] {
  if (!Number.isInteger(from) || !Number.isInteger(to)
    || from < 0 || to < 0 || from >= drafts.length || to >= drafts.length) {
    return [...drafts];
  }
  const result = [...drafts];
  const [moved] = result.splice(from, 1);
  result.splice(to, 0, moved);
  return result;
}
