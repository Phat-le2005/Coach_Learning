"use client";

import React from "react";
import {
  ChevronUp,
  ChevronDown,
  History,
  Trash2,
  Edit2,
  FileText,
  Table,
} from "lucide-react";
import type { SolutionStepItem, SignTablePayload } from "../types";
import { STEP_KIND_DISPLAY_NAMES } from "../types";
import { SignTableEditor } from "./SignTableEditor";
import styles from "./StepCard.module.css";

interface StepCardProps {
  step: SolutionStepItem;
  totalSteps: number;
  onMoveUp?: (stepId: string) => void;
  onMoveDown?: (stepId: string) => void;
  onEdit?: (step: SolutionStepItem) => void;
  onDelete?: (stepId: string) => void;
  onViewRevisions?: (step: SolutionStepItem) => void;
  isReadOnly?: boolean;
}

export function StepCard({
  step,
  totalSteps,
  onMoveUp,
  onMoveDown,
  onEdit,
  onDelete,
  onViewRevisions,
  isReadOnly = false,
}: StepCardProps) {
  const isFirst = step.step_index === 1;
  const isLast = step.step_index === totalSteps;
  const isSignTable = step.step_type === "SIGN_TABLE";

  // Check if artifact is a sign table payload
  const signTablePayload: SignTablePayload | null =
    isSignTable && step.artifact?.payload
      ? (step.artifact.payload as SignTablePayload)
      : null;

  return (
    <article className={styles.card} aria-label={`Bước giải ${step.step_index}`}>
      {/* Header */}
      <header className={styles.cardHeader}>
        <div className={styles.headerLeft}>
          <span className={styles.stepIndexBadge}>
            Bước {step.step_index}
          </span>
          <span className={styles.stepKindBadge}>
            {isSignTable ? <Table size={13} /> : <FileText size={13} />}
            {STEP_KIND_DISPLAY_NAMES[step.step_type] || step.step_type}
          </span>
          <span className={styles.revNumberBadge}>
            v{step.step_revision_number}
          </span>
        </div>

        {/* Action Controls */}
        {!isReadOnly && (
          <div className={styles.headerActions}>
            <button
              type="button"
              className={styles.actionBtn}
              onClick={() => onMoveUp?.(step.id)}
              disabled={isFirst}
              title="Di chuyển bước lên trên"
              aria-label="Di chuyển lên"
            >
              <ChevronUp size={16} />
            </button>
            <button
              type="button"
              className={styles.actionBtn}
              onClick={() => onMoveDown?.(step.id)}
              disabled={isLast}
              title="Di chuyển bước xuống dưới"
              aria-label="Di chuyển xuống"
            >
              <ChevronDown size={16} />
            </button>
            <button
              type="button"
              className={styles.actionBtn}
              onClick={() => onViewRevisions?.(step)}
              title="Xem lịch sử các phiên bản của bước này"
              aria-label="Lịch sử phiên bản"
            >
              <History size={16} />
            </button>
            <button
              type="button"
              className={styles.actionBtn}
              onClick={() => onEdit?.(step)}
              title="Chỉnh sửa bước này"
              aria-label="Chỉnh sửa"
            >
              <Edit2 size={16} />
            </button>
            <button
              type="button"
              className={`${styles.actionBtn} ${styles.deleteActionBtn}`}
              onClick={() => onDelete?.(step.id)}
              title="Xóa bước này"
              aria-label="Xóa bước"
            >
              <Trash2 size={16} />
            </button>
          </div>
        )}
      </header>

      {/* Body Content */}
      <div className={styles.cardBody}>
        {/* Sign Table Artifact Display */}
        {signTablePayload && (
          <div className={styles.artifactWrapper}>
            <SignTableEditor
              value={signTablePayload}
              onChange={() => {}}
              isReadOnly={true}
            />
          </div>
        )}

        {/* Formula Display */}
        {step.content_latex && (
          <div className={styles.formulaBox}>
            <code className={styles.formulaCode}>{step.content_latex}</code>
          </div>
        )}

        {/* Explanation Text */}
        {step.explanation_text && (
          <p className={styles.explanationText}>
            {step.explanation_text}
          </p>
        )}
      </div>
    </article>
  );
}
