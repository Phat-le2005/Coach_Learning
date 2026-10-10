"use client";

import { AlertCircle, Calendar, CheckCircle2, Clock, Info, RotateCcw, Target, X } from "lucide-react";
import { useEffect, useId, useRef } from "react";

import { GradientButton } from "@/components/ui/GradientButton";
import { getMasteryStateDescription, getMasteryStateLabel } from "../copy";
import type { KnowledgeConceptNode, KnowledgeProblemTypeNode } from "../types";
import styles from "../KnowledgeForest.module.css";

export type SelectedKnowledgeItem =
  | { kind: "problem_type"; data: KnowledgeProblemTypeNode }
  | { kind: "concept"; data: KnowledgeConceptNode }
  | null;

export interface KnowledgeDetailDrawerProps {
  item: SelectedKnowledgeItem;
  onClose: () => void;
}

export function KnowledgeDetailDrawer({ item, onClose }: KnowledgeDetailDrawerProps) {
  const titleId = useId();
  const drawerRef = useRef<HTMLDivElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);
  const previousFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!item) return;

    // Save previous active element to restore focus on close
    previousFocusRef.current = document.activeElement as HTMLElement | null;

    // Focus close button initially
    closeBtnRef.current?.focus();

    // Lock background scroll
    const originalOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    // Handle keydown for Escape and Focus Trap
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }

      if (event.key === "Tab") {
        if (!drawerRef.current) return;
        const focusable = drawerRef.current.querySelectorAll<HTMLElement>(
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
      // Restore focus
      previousFocusRef.current?.focus();
    };
  }, [item, onClose]);

  if (!item) return null;

  const isProblemType = item.kind === "problem_type";
  const { data } = item;

  const stateLabel = getMasteryStateLabel(data.state);
  const stateDesc = getMasteryStateDescription(data.state);

  const formattedDate = data.lastPracticedAt
    ? new Date(data.lastPracticedAt).toLocaleDateString("vi-VN", {
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "Chưa luyện tập";

  return (
    <div
      className={styles.drawerBackdrop}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      onClick={onClose}
    >
      <div
        ref={drawerRef}
        className={styles.drawer}
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.drawerHeader}>
          <div>
            <div className={styles.breadcrumb} style={{ marginBottom: 6 }}>
              {isProblemType ? (
                <>
                  <span>{(data as KnowledgeProblemTypeNode).chapterName}</span>
                  <span aria-hidden="true">›</span>
                  <span>{(data as KnowledgeProblemTypeNode).topicName}</span>
                </>
              ) : (
                <span>Khối kiến thức nền tảng</span>
              )}
            </div>
            <h2 id={titleId} style={{ margin: 0, fontSize: "1.3rem", fontWeight: 750, color: "var(--text-primary)" }}>
              {data.name}
            </h2>
          </div>

          <button
            ref={closeBtnRef}
            type="button"
            className={styles.drawerCloseBtn}
            onClick={onClose}
            aria-label="Đóng bảng chi tiết"
          >
            <X size={18} />
          </button>
        </div>

        <div className={styles.drawerBody}>
          {/* Status summary card */}
          <div className={styles.drawerCard}>
            <div className={styles.drawerRow}>
              <span className={styles.drawerLabel}>Trạng thái học tập</span>
              <span className={styles.drawerValue} style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <span className={`${styles.statusDot} ${styles[`statusDot_${data.state}`]}`} />
                {stateLabel}
              </span>
            </div>

            <div className={styles.drawerRow}>
              <span className={styles.drawerLabel}>Mã chuẩn kiến thức</span>
              <span className={styles.chapterCode}>{data.code}</span>
            </div>

            <p style={{ margin: "4px 0 0", fontSize: "0.82rem", lineHeight: 1.5, color: "var(--text-secondary)" }}>
              {stateDesc}
            </p>
          </div>

          {/* Metric details */}
          <div className={styles.drawerCard}>
            <div className={styles.drawerRow}>
              <span className={styles.drawerLabel}>Độ vững đo lường</span>
              <span className={styles.drawerValue}>
                {data.masteryScore !== undefined ? `${data.masteryScore}%` : "Chưa đo lường (0 lượt)"}
              </span>
            </div>

            {data.confidence !== undefined ? (
              <div className={styles.drawerRow}>
                <span className={styles.drawerLabel}>Độ tin cậy thuật toán</span>
                <span className={styles.drawerValue}>{data.confidence}%</span>
              </div>
            ) : null}

            <div className={styles.drawerRow}>
              <span className={styles.drawerLabel}>Số lượt làm bài</span>
              <span className={styles.drawerValue}>
                {data.attemptCount} lượt ({data.correctCount} đúng)
              </span>
            </div>

            <div className={styles.drawerRow}>
              <span className={styles.drawerLabel}>Lần luyện tập gần nhất</span>
              <span className={styles.drawerValue}>{formattedDate}</span>
            </div>

            {isProblemType && (data as KnowledgeProblemTypeNode).isReviewDue ? (
              <div
                style={{
                  marginTop: 6,
                  padding: "10px 12px",
                  borderRadius: 12,
                  background: "rgb(242 223 184 / 50%)",
                  border: "1px solid rgb(216 161 67 / 35%)",
                  color: "#76581f",
                  fontSize: "0.8rem",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <RotateCcw size={15} flex-shrink={0} />
                <span>Dạng bài này đã đến chu kỳ ôn tập giãn cách để chống quên lãng.</span>
              </div>
            ) : null}
          </div>

          {/* Truthful Practice Workspace boundary */}
          <div className={styles.guidanceCard}>
            <div className={styles.guidanceTitle}>
              <Info size={16} aria-hidden="true" />
              <span>{isProblemType ? "Dạng bài đã được chọn" : "Kiến thức nền tảng"}</span>
            </div>
            <p style={{ margin: 0 }}>
              {isProblemType
                ? "Dạng bài này đã sẵn sàng làm phạm vi cho phiên tự học. EduMS chỉ bắt đầu luyện tập sau khi backend xác nhận có câu hỏi đã duyệt và được phân loại đầy đủ; hệ thống không tạo phiên rỗng hoặc giả định câu hỏi khả dụng."
                : "Hãy chọn một dạng bài trong chương để chuẩn bị phạm vi luyện tập. Khái niệm này không tự động tạo mục tiêu thi hoặc kế hoạch học."}
            </p>
          </div>
        </div>

        <div className={styles.drawerFooter}>
          <GradientButton style={{ width: "100%" }} onClick={onClose}>
            Đã xem thông tin
          </GradientButton>
        </div>
      </div>
    </div>
  );
}
