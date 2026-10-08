"use client";

import { AlertCircle, CheckCircle2, Clock, Info, Route, Sparkles, Target, Wrench, X } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useId, useRef } from "react";

import { GradientButton } from "@/components/ui/GradientButton";
import { useHydratedReducedMotion } from "@/lib/use-hydrated-reduced-motion";

import type { ResolvedStudentAction } from "../action-resolver";
import { getPriorityReasonCopy } from "../copy";
import type { PriorityViewModel } from "../types";
import styles from "./ActionDetailModal.module.css";

export interface ActionDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  action?: ResolvedStudentAction | null;
  priority?: PriorityViewModel | null;
}

export function ActionDetailModal({ isOpen, onClose, action, priority }: ActionDetailModalProps) {
  const reducedMotion = useHydratedReducedMotion();
  const titleId = useId();
  const modalRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Save previous active element to restore focus on close
    previousFocusRef.current = document.activeElement as HTMLElement | null;

    // Lock background scroll
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Focus close button initially
    closeButtonRef.current?.focus();

    // Focus trap and Escape listener
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key === "Tab") {
        if (!modalRef.current) return;
        const focusable = modalRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;

        const firstElement = focusable[0];
        const lastElement = focusable[focusable.length - 1];

        if (event.shiftKey && document.activeElement === firstElement) {
          event.preventDefault();
          lastElement.focus();
        } else if (!event.shiftKey && document.activeElement === lastElement) {
          event.preventDefault();
          firstElement.focus();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = originalOverflow;
      previousFocusRef.current?.focus();
    };
  }, [isOpen, onClose]);

  if (!isOpen || (!action && !priority)) return null;

  const renderIcon = () => {
    if (priority) return <Target size={16} aria-hidden="true" />;
    if (!action) return <Info size={16} aria-hidden="true" />;
    switch (action.type) {
      case "CONTINUE_REPAIR":
        return <Wrench size={16} aria-hidden="true" />;
      case "CONTINUE_VERIFICATION":
        return <Sparkles size={16} aria-hidden="true" />;
      case "COMPLETE_OVERDUE_ASSIGNMENT":
      case "CONTINUE_ASSIGNMENT":
        return <Clock size={16} aria-hidden="true" />;
      case "LEARNING_PRIORITY":
        return <Target size={16} aria-hidden="true" />;
      case "IDLE":
        return <CheckCircle2 size={16} aria-hidden="true" />;
      default:
        return <Route size={16} aria-hidden="true" />;
    }
  };

  const title = priority ? priority.targetName : action?.title ?? "Chi tiết hành động";
  const badgeLabel = priority ? "Mục tiêu ưu tiên" : action?.badgeLabel ?? "Học tập";
  const description = priority
    ? `Dạng bài này được thuật toán tối ưu hóa đường cong học tập gợi ý dựa trên năng lực và mục tiêu học tập.`
    : action?.description;

  return (
    <div
      className={styles.backdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={onClose}
    >
      <motion.div
        ref={modalRef}
        className={styles.modal}
        onClick={(e) => e.stopPropagation()}
        initial={{ opacity: 0, scale: 0.94, y: 16 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.94, y: 16 }}
        transition={{ duration: reducedMotion ? 0 : 0.22, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className={styles.header}>
          <div className={styles.headerContent}>
            <span className={styles.badge}>
              {renderIcon()}
              {badgeLabel}
            </span>
            <h2 id={titleId} className={styles.title}>
              {title}
            </h2>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            className={styles.closeButton}
            onClick={onClose}
            aria-label="Đóng"
          >
            <X size={18} />
          </button>
        </div>

        <div className={styles.body}>
          {description ? <p className={styles.description}>{description}</p> : null}

          {/* Action details */}
          {action && (action.targetName || action.resourceId || action.phase) ? (
            <div className={styles.detailCard}>
              {action.targetName ? (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Nội dung trọng tâm</span>
                  <span className={styles.detailValue}>{action.targetName}</span>
                </div>
              ) : null}
              {action.targetCode ? (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Mã định danh</span>
                  <span className={styles.codeBadge}>{action.targetCode}</span>
                </div>
              ) : null}
              {action.targetType ? (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Phân loại</span>
                  <span className={styles.detailValue}>{action.targetType}</span>
                </div>
              ) : null}
              {action.phase ? (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Giai đoạn</span>
                  <span className={styles.detailValue}>{action.phase}</span>
                </div>
              ) : null}
              {action.repairCycleIndex !== undefined ? (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Chu kỳ sửa sai</span>
                  <span className={styles.detailValue}>#{action.repairCycleIndex}</span>
                </div>
              ) : null}
              {action.resourceId ? (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Mã phiên</span>
                  <span className={styles.codeBadge}>{action.resourceId}</span>
                </div>
              ) : null}
            </div>
          ) : null}

          {/* Priority details */}
          {priority ? (
            <div className={styles.detailCard}>
              <div className={styles.detailRow}>
                <span className={styles.detailLabel}>Lý do ưu tiên</span>
                <span className={styles.detailValue}>{getPriorityReasonCopy(priority.reasonCode)}</span>
              </div>
              <div className={styles.detailRow}>
                <span className={styles.detailLabel}>Mã dạng bài</span>
                <span className={styles.codeBadge}>{priority.targetCode}</span>
              </div>
              <div className={styles.detailRow}>
                <span className={styles.detailLabel}>Phân loại</span>
                <span className={styles.detailValue}>
                  {priority.targetType === "PROBLEM_TYPE" ? "Dạng bài tập" : priority.targetType}
                </span>
              </div>
              <div className={styles.detailRow}>
                <span className={styles.detailLabel}>Độ vững hiện tại</span>
                <span className={styles.detailValue}>
                  {priority.mastery !== undefined ? `${priority.mastery}%` : "Chưa đủ dữ liệu đo lường"}
                </span>
              </div>
              {priority.desiredDifficulty !== undefined ? (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Độ khó mục tiêu</span>
                  <span className={styles.detailValue}>{priority.desiredDifficulty.toFixed(2)}</span>
                </div>
              ) : null}
              {priority.confidence !== undefined ? (
                <div className={styles.detailRow}>
                  <span className={styles.detailLabel}>Độ tin cậy</span>
                  <span className={styles.detailValue}>{Math.round(priority.confidence * 100)}%</span>
                </div>
              ) : null}
            </div>
          ) : null}

          <div className={styles.guidanceCallout}>
            <p className={styles.guidanceTitle}>
              <AlertCircle size={15} aria-hidden="true" />
              Lộ trình không gian học tập
            </p>
            <p className={styles.guidanceText}>
              {action ? action.guidanceText : "Mục tiêu học tập đã được đồng bộ chính xác từ cơ sở dữ liệu thật."}
            </p>
            <p className={styles.guidanceSubtext}>
              Giao diện làm bài tương tác (Practice Workspace) sẽ được ra mắt trong giai đoạn FE-REAL-04. Toàn bộ dữ liệu
              hiển thị ở đây là số liệu thực 100% từ backend.
            </p>
          </div>
        </div>

        <div className={styles.footer}>
          <GradientButton onClick={onClose}>Đã hiểu</GradientButton>
        </div>
      </motion.div>
    </div>
  );
}
