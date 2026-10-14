"use client";

import React from "react";
import { Check, CloudOff, AlertTriangle, AlertCircle, Loader2 } from "lucide-react";
import type { SyncStatus } from "../types";
import styles from "../MathWorkspace.module.css";

interface SyncStatusBadgeProps {
  status: SyncStatus;
  errorMessage?: string;
  onRetry?: () => void;
  onResolveConflict?: () => void;
}

export function SyncStatusBadge({
  status,
  errorMessage,
  onRetry,
  onResolveConflict,
}: SyncStatusBadgeProps) {
  if (status === "saving") {
    return (
      <div className={`${styles.statusBadge} ${styles.statusSaving}`} role="status">
        <Loader2 className={`${styles.statusIcon} ${styles.spin}`} size={14} />
        <span>Đang lưu...</span>
      </div>
    );
  }

  if (status === "saved") {
    return (
      <div className={`${styles.statusBadge} ${styles.statusSaved}`} role="status">
        <Check className={styles.statusIcon} size={14} />
        <span>Đã lưu vào máy chủ</span>
      </div>
    );
  }

  if (status === "offline") {
    return (
      <div className={`${styles.statusBadge} ${styles.statusOffline}`} role="status">
        <CloudOff className={styles.statusIcon} size={14} />
        <span>Đã lưu offline</span>
      </div>
    );
  }

  if (status === "conflict") {
    return (
      <div className={`${styles.statusBadge} ${styles.statusConflict}`} role="alert">
        <AlertTriangle className={styles.statusIcon} size={14} />
        <span>Xung đột phiên bản</span>
        {onResolveConflict && (
          <button
            type="button"
            className={styles.statusActionBtn}
            onClick={onResolveConflict}
          >
            Tải bản mới nhất
          </button>
        )}
      </div>
    );
  }

  if (status === "error") {
    return (
      <div className={`${styles.statusBadge} ${styles.statusError}`} role="alert">
        <AlertCircle className={styles.statusIcon} size={14} />
        <span>{errorMessage || "Lỗi lưu trữ"}</span>
        {onRetry && (
          <button type="button" className={styles.statusActionBtn} onClick={onRetry}>
            Thử lại
          </button>
        )}
      </div>
    );
  }

  return (
    <div className={`${styles.statusBadge} ${styles.statusUnsaved}`} role="status">
      <span className={styles.statusDot} />
      <span>Chưa lưu</span>
    </div>
  );
}
