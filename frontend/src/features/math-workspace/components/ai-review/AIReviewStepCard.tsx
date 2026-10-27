"use client";

import React, { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Eye, Sparkles } from "lucide-react";
import {
  parseVariationTablePayload,
  type AIStepSuggestionRead,
  type SolutionStepRead,
  type VariationTablePayload,
} from "@/lib/api/contracts";
import { OcrMathPreview } from "../OcrMathPreview";
import { VariationTableGrid } from "../VariationTableModal";
import {
  formatAuthenticStepTitle,
  formatStepScoreDisplay,
  formatStepVerdictMeta,
  type AIReviewStepCardState,
  type StepVerdict,
} from "../../utils/ai-review-controller";
import styles from "./AIReview.module.css";

interface AIReviewStepCardProps {
  grade: AIStepSuggestionRead;
  step: SolutionStepRead | undefined;
  cardState: AIReviewStepCardState;
  isSelected: boolean;
  onSelectStep: (stepIndex: number) => void;
  onToggleExpand: (stepIndex: number) => void;
  onInspectOnPaper: (stepIndex: number) => void;
}

function getVariationPayload(
  step: SolutionStepRead | undefined,
): VariationTablePayload | null {
  if (step?.artifact?.artifact_type !== "VARIATION_TABLE") return null;
  try {
    return parseVariationTablePayload(step.artifact.payload);
  } catch {
    return null;
  }
}

function VerdictAnimatedSvg({ verdict }: { verdict: StepVerdict }) {
  if (verdict === "VALID") {
    return (
      <span
        className={`${styles.verdictSvgWrap} ${styles.verdictSvgValid}`}
        aria-hidden="true"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path
            d="M5 13l4 4L19 7"
            stroke="currentColor"
            strokeWidth="2.6"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={styles.animatedStrokePath}
          />
        </svg>
      </span>
    );
  }

  if (verdict === "INVALID") {
    return (
      <span
        className={`${styles.verdictSvgWrap} ${styles.verdictSvgInvalid}`}
        aria-hidden="true"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path
            d="M12 8v5m0 3.5h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={styles.animatedStrokePath}
          />
        </svg>
      </span>
    );
  }

  return (
    <span
      className={`${styles.verdictSvgWrap} ${styles.verdictSvgNeedsReview}`}
      aria-hidden="true"
    >
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
        <path
          d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3m.08 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          stroke="currentColor"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={styles.animatedStrokePath}
        />
      </svg>
    </span>
  );
}

export function AIReviewStepCard({
  grade,
  step,
  cardState,
  isSelected,
  onSelectStep,
  onToggleExpand,
  onInspectOnPaper,
}: AIReviewStepCardProps) {
  const cardRef = useRef<HTMLElement | null>(null);
  const [isScanningBeat, setIsScanningBeat] = useState(cardState === "active");

  useEffect(() => {
    if (cardState === "active") {
      setIsScanningBeat(true);
      cardRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "nearest",
      });
      const timer = window.setTimeout(() => {
        setIsScanningBeat(false);
      }, 480);
      return () => window.clearTimeout(timer);
    } else {
      setIsScanningBeat(false);
    }
  }, [cardState]);

  if (cardState === "pending") {
    return (
      <div
        className={styles.stepCardPending}
        aria-label={`Bước ${grade.step_index} đang chờ trình chiếu`}
      >
        <span>Bước {grade.step_index}</span>
        <span className={styles.stepPendingPulse}>
          <Sparkles size={13} />
          Đang chờ lượt chấm...
        </span>
      </div>
    );
  }

  const verdictMeta = formatStepVerdictMeta(grade.verdict);
  const scoreDisplay = formatStepScoreDisplay(grade.score);
  const variationPayload = getVariationPayload(step);
  const authenticTitle = formatAuthenticStepTitle(
    step?.step_type,
    Boolean(variationPayload),
  );
  const isExpanded = cardState === "active" || cardState === "expanded";

  const toneCardClass = isScanningBeat
    ? styles.stepCardScanningBeat
    : grade.verdict === "VALID"
      ? styles.stepCardValid
      : grade.verdict === "INVALID"
        ? styles.stepCardInvalid
        : styles.stepCardNeedsReview;

  const badgeToneClass =
    grade.verdict === "VALID"
      ? styles.verdictBadgeValid
      : grade.verdict === "INVALID"
        ? styles.verdictBadgeInvalid
        : styles.verdictBadgeNeedsReview;

  const feedbackBoxToneClass =
    grade.verdict === "VALID"
      ? styles.feedbackBoxValid
      : grade.verdict === "INVALID"
        ? styles.feedbackBoxInvalid
        : styles.feedbackBoxNeedsReview;

  return (
    <article
      ref={cardRef}
      className={`${styles.stepCard} ${toneCardClass} ${
        isSelected ? styles.stepCardSelected : ""
      } ${cardState === "active" ? styles.stepCardActive : ""}`}
      aria-label={`Nhận xét Bước ${grade.step_index}`}
    >
      {isScanningBeat && (
        <div className={styles.stepCardScanSweep} aria-hidden="true" />
      )}

      <div
        className={styles.stepCardHeader}
        onClick={() => {
          onSelectStep(grade.step_index);
          onToggleExpand(grade.step_index);
        }}
        role="button"
        tabIndex={0}
        aria-expanded={isExpanded}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onSelectStep(grade.step_index);
            onToggleExpand(grade.step_index);
          }
        }}
      >
        <div className={styles.stepHeaderLeft}>
          {isScanningBeat ? (
            <span className={styles.stepScanningSpinner} aria-hidden="true" />
          ) : (
            <VerdictAnimatedSvg verdict={grade.verdict} />
          )}
          <span className={styles.stepNumberLabel}>
            Bước {grade.step_index}
          </span>
          {authenticTitle && (
            <span className={styles.stepAuthenticKind}>{authenticTitle}</span>
          )}
        </div>

        <div className={styles.stepHeaderRight}>
          {isScanningBeat ? (
            <span
              className={`${styles.verdictBadge} ${styles.verdictBadgeScanning}`}
            >
              Đang phân tích...
            </span>
          ) : (
            <>
              {scoreDisplay !== null && (
                <span
                  className={styles.scoreBadge}
                  title="Điểm bước giải tham khảo"
                >
                  {scoreDisplay}
                </span>
              )}
              <span
                className={`${styles.verdictBadge} ${badgeToneClass}`}
                aria-label={verdictMeta.ariaLabel}
              >
                {verdictMeta.label}
              </span>
            </>
          )}
          {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
        </div>
      </div>

      {!isExpanded && !isScanningBeat && (
        <div className={styles.stepCollapsedSnippet}>{grade.feedback}</div>
      )}

      {isExpanded && (
        <div className={styles.stepBody}>
          {step && (
            <div className={styles.studentConfirmedBox}>
              <span className={styles.studentConfirmedLabel}>
                Bước giải bạn đã xác nhận
              </span>
              {variationPayload ? (
                <div className={styles.studentConfirmedContent}>
                  <VariationTableGrid value={variationPayload} />
                </div>
              ) : (
                step.content_latex && (
                  <div className={styles.studentConfirmedContent}>
                    <OcrMathPreview latex={step.content_latex} />
                  </div>
                )
              )}
              {step.explanation_text && (
                <p className={styles.studentExplanationText}>
                  {step.explanation_text}
                </p>
              )}
            </div>
          )}

          {isScanningBeat ? (
            <div className={styles.stepScanningBanner}>
              <span
                className={styles.stepScanningSpinner}
                aria-hidden="true"
              />
              <span>
                Gemini đang kiểm tra phép biến đổi Bước {grade.step_index} với
                đáp án tham chiếu...
              </span>
            </div>
          ) : (
            <>
              <div className={`${styles.feedbackBox} ${feedbackBoxToneClass}`}>
                <span className={styles.feedbackLabel}>Nhận xét từ AI</span>
                <p className={styles.feedbackText}>{grade.feedback}</p>
              </div>

              <div className={styles.stepCardFooter}>
                <button
                  type="button"
                  onClick={() => onInspectOnPaper(grade.step_index)}
                  className={styles.stepActionBtn}
                >
                  <Eye size={13} />
                  <span>Đối chiếu trên bài viết</span>
                </button>
                <button
                  type="button"
                  onClick={() => onToggleExpand(grade.step_index)}
                  className={styles.stepActionBtn}
                >
                  <span>Thu gọn</span>
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </article>
  );
}
