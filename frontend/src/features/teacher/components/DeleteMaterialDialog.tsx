"use client";

import { useEffect, useRef } from "react";
import { Trash2 } from "lucide-react";
import type { TeacherMaterial } from "../api";
import styles from "../TeacherDashboard.module.css";

export function DeleteMaterialDialog({ material, busy, error, onCancel, onConfirm }: {
  material: TeacherMaterial; busy: boolean; error: string;
  onCancel: () => void; onConfirm: () => Promise<void>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} className={styles.deleteDialog} aria-labelledby="delete-material-title"
    aria-describedby="delete-material-description" onCancel={(event) => { event.preventDefault(); if (!busy) onCancel(); }}>
    <div className={styles.deleteDialogHeader}>
      <span className={styles.deleteDialogIcon}><Trash2 size={21} aria-hidden="true" /></span>
      <h2 id="delete-material-title" className={styles.modalTitle}>Xóa tài liệu khỏi kho?</h2>
    </div>
    <div className={styles.deleteDialogBody}>
      <p id="delete-material-description">Tài liệu <strong>{material.title}</strong> sẽ được gỡ khỏi kho học liệu và không dùng để giao bài mới.</p>
      <p className={styles.deleteDialogHint}>Các bài đã giao và bài làm của học sinh được giữ nguyên.</p>
      {error && <div className={styles.formAlert} role="alert">{error}</div>}
    </div>
    <div className={styles.deleteDialogActions}>
      <button type="button" autoFocus className={styles.btnSecondary} disabled={busy} onClick={onCancel}>Hủy</button>
      <button type="button" className={styles.btnDeleteMaterial} disabled={busy} onClick={() => void onConfirm()}>
        <Trash2 size={16} aria-hidden="true" />{busy ? "Đang xóa…" : "Xóa khỏi kho"}
      </button>
    </div>
  </dialog>;
}
