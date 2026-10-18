"use client";

import React, { useState, useEffect } from "react";
import { History, RotateCcw, X, Clock, FileCode, CheckCircle, Loader2 } from "lucide-react";
import type { StepRevisionItem, SolutionStepItem } from "../types";
import { STEP_KIND_DISPLAY_NAMES } from "../types";
import styles from "./RevisionViewerModal.module.css";

interface RevisionViewerModalProps {
  isOpen: boolean;
  onClose: () => void;
  step: SolutionStepItem | null;
  attemptId: string;
  accessToken: string;
  onRollback: (stepId: string, toRevision: number) => Promise<void>;
  apiBaseUrl?: string;
}

export function RevisionViewerModal({
  isOpen,
  onClose,
  step,
  attemptId,
  accessToken,
  onRollback,
  apiBaseUrl,
}: RevisionViewerModalProps) {
  const [revisions, setRevisions] = useState<StepRevisionItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isRollingBack, setIsRollingBack] = useState<number | null>(null);

  useEffect(() => {
    if (!isOpen || !step) {
      setRevisions([]);
      return;
    }

    const fetchRevisions = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const baseUrl = apiBaseUrl || "";
        const res = await fetch(
          `${baseUrl}/api/v2/math-solutions/attempts/${attemptId}/steps/${step.id}/revisions`,
          {
            headers: {
              Authorization: `Bearer ${accessToken}`,
              Accept: "application/json",
            },
          },
        );
        if (!res.ok) {
          throw new Error(`Không thể nạp lịch sử phiên bản (mã lỗi: ${res.status})`);
        }
        const data = await res.json();
        setRevisions(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Đã có lỗi xảy ra");
      } finally {
        setIsLoading(false);
      }
    };

    fetchRevisions();
  }, [isOpen, step, attemptId, accessToken]);

  if (!isOpen || !step) return null;

  const handleRollbackClick = async (revNum: number) => {
    if (!confirm(`Bạn có chắc chắn muốn khôi phục bước giải này về Phiên bản ${revNum}?`)) {
      return;
    }
    setIsRollingBack(revNum);
    try {
      await onRollback(step.id, revNum);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Lỗi khi khôi phục phiên bản");
    } finally {
      setIsRollingBack(null);
    }
  };

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="rev-title">
      <div className={styles.modalContainer}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div className={styles.headerTitleWrap}>
            <History className={styles.headerIcon} size={20} />
            <div>
              <h2 id="rev-title" className={styles.modalTitle}>
                Lịch sử phiên bản: Bước {step.step_index}
              </h2>
              <span className={styles.modalSubtitle}>
                {STEP_KIND_DISPLAY_NAMES[step.step_type] || step.step_type}
              </span>
            </div>
          </div>
          <button
            type="button"
            className={styles.closeBtn}
            onClick={onClose}
            aria-label="Đóng hộp thoại"
          >
            <X size={20} />
          </button>
        </div>

        {/* Content */}
        <div className={styles.modalContent}>
          {isLoading && (
            <div className={styles.loadingState}>
              <Loader2 className={styles.spinIcon} size={24} />
              <span>Đang tải lịch sử phiên bản...</span>
            </div>
          )}

          {error && (
            <div className={styles.errorAlert} role="alert">
              <span>{error}</span>
            </div>
          )}

          {!isLoading && revisions.length === 0 && !error && (
            <div className={styles.emptyState}>
              <span>Chưa có bản ghi lịch sử nào cho bước này.</span>
            </div>
          )}

          {!isLoading && revisions.length > 0 && (
            <div className={styles.revisionList}>
              {revisions.map((rev) => {
                const isCurrent = rev.step_revision_number === step.step_revision_number;
                return (
                  <div
                    key={rev.id}
                    className={`${styles.revisionCard} ${isCurrent ? styles.currentRevisionCard : ""}`}
                  >
                    <div className={styles.revisionCardHeader}>
                      <div className={styles.revMeta}>
                        <span className={styles.revBadge}>
                          Phiên bản #{rev.step_revision_number}
                        </span>
                        {isCurrent && (
                          <span className={styles.activeTag}>
                            <CheckCircle size={12} /> Hiện tại
                          </span>
                        )}
                        <span className={styles.reasonBadge}>
                          Lý do: {rev.change_reason}
                        </span>
                      </div>

                      <div className={styles.timeTag}>
                        <Clock size={12} />
                        {new Date(rev.created_at).toLocaleTimeString("vi-VN", {
                          hour: "2-digit",
                          minute: "2-digit",
                          second: "2-digit",
                        })}
                      </div>
                    </div>

                    <div className={styles.revFormulaPreview}>
                      <FileCode size={14} className={styles.codeIcon} />
                      <code>{rev.content_latex || "(Không có công thức LaTeX)"}</code>
                    </div>

                    {rev.explanation_text && (
                      <p className={styles.revExplanation}>
                        {rev.explanation_text}
                      </p>
                    )}

                    {!isCurrent && (
                      <div className={styles.cardActions}>
                        <button
                          type="button"
                          className={styles.rollbackBtn}
                          disabled={isRollingBack !== null}
                          onClick={() => handleRollbackClick(rev.step_revision_number)}
                        >
                          {isRollingBack === rev.step_revision_number ? (
                            <Loader2 className={styles.spinIcon} size={14} />
                          ) : (
                            <RotateCcw size={14} />
                          )}
                          Khôi phục phiên bản này
                        </button>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={styles.modalFooter}>
          <button type="button" className={styles.cancelBtn} onClick={onClose}>
            Đóng
          </button>
        </div>
      </div>
    </div>
  );
}
