"use client";

import React from "react";
import { Check, CloudOff, AlertTriangle, AlertCircle, Loader2 } from "lucide-react";
import type { SyncStatus } from "../types";
import styles from "../MathWorkspace.module.css";

interface SyncStatusBadgeProps {
  status: SyncStatus;
  errorMessage?: string;
  authExpired?: boolean;
  onRetry?: () => void;
  onResolveConflict?: () => void;
  onExportDraft?: () => void;
}

export function SyncStatusBadge({
  status,
  errorMessage,
  authExpired = false,
  onRetry,
  onResolveConflict,
  onExportDraft,
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
        <span>{errorMessage || "Xung đột phiên bản"}</span>
        {onExportDraft && (
          <button type="button" className={styles.statusActionBtn} onClick={onExportDraft}>
            Sao lưu bản nháp
          </button>
        )}
        {onResolveConflict && (
          <button
            type="button"
            className={styles.statusActionBtn}
            onClick={onResolveConflict}
          >
            Bỏ bản nháp và tải bản máy chủ
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
        {authExpired ? (
          <a className={styles.statusActionBtn} href="/login?reason=expired" target="_blank" rel="noopener noreferrer">{"\u0110\u0103ng nh\u1eadp l\u1ea1i"}</a>
        ) : null}
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
