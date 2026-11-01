"use client";

import { useState } from "react";
import { X, Users, Sparkles } from "lucide-react";
import styles from "../TeacherDashboard.module.css";

export interface CreateClassModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (name: string, academicYear: string, gradeLevel: number) => Promise<void>;
  isBusy: boolean;
  errorMessage?: string;
}

export function CreateClassModal({
  isOpen,
  onClose,
  onSubmit,
  isBusy,
  errorMessage,
}: CreateClassModalProps) {
  const currentYear = new Date().getFullYear();
  const defaultYear = `${currentYear}-${currentYear + 1}`;

  const [name, setName] = useState("");
  const [academicYear, setAcademicYear] = useState(defaultYear);
  const [gradeLevel, setGradeLevel] = useState(12);

  if (!isOpen) return null;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !academicYear.trim() || isBusy) return;
    await onSubmit(name.trim(), academicYear.trim(), gradeLevel);
    setName("");
  }

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="create-class-title">
      <div className={styles.modalContent}>
        <div className={styles.modalHeader}>
          <div className={styles.modalTitleGroup}>
            <div className={styles.modalIconWrap}>
              <Users size={20} />
            </div>
            <div>
              <h2 id="create-class-title" className={styles.modalTitle}>
                Tạo lớp học mới
              </h2>
              <p className={styles.modalSubtitle}>Khởi tạo không gian học tập và quản lý học sinh theo khối</p>
            </div>
          </div>
          <button
            type="button"
            className={styles.modalCloseBtn}
            onClick={onClose}
            aria-label="Đóng cửa sổ"
            disabled={isBusy}
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className={styles.modalForm}>
          {errorMessage && (
            <div className={styles.formAlert} role="alert">
              {errorMessage}
            </div>
          )}

          <div className={styles.formGroup}>
            <label htmlFor="create-class-name" className={styles.formLabel}>
              Tên lớp học <span className={styles.requiredMark}>*</span>
            </label>
            <input
              id="create-class-name"
              className={styles.formInput}
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="VD: Lớp 12A1 Chuyên Toán, Lớp 12B5..."
              required
              maxLength={200}
              autoFocus
            />
            <span className={styles.formHelperText}>Đặt tên dễ nhận diện cho bạn và học sinh</span>
          </div>

          <div className={styles.formRowTwo}>
            <div className={styles.formGroup}>
              <label htmlFor="create-class-grade" className={styles.formLabel}>
                Khối lớp <span className={styles.requiredMark}>*</span>
              </label>
              <select
                id="create-class-grade"
                className={styles.formSelect}
                value={gradeLevel}
                onChange={(e) => setGradeLevel(Number(e.target.value))}
                required
              >
                <option value={12}>Khối 12 (Lớp 12)</option>
                <option value={11}>Khối 11 (Lớp 11)</option>
                <option value={10}>Khối 10 (Lớp 10)</option>
              </select>
            </div>

            <div className={styles.formGroup}>
              <label htmlFor="create-class-year" className={styles.formLabel}>
                Năm học <span className={styles.requiredMark}>*</span>
              </label>
              <input
                id="create-class-year"
                className={styles.formInput}
                value={academicYear}
                onChange={(e) => setAcademicYear(e.target.value)}
                placeholder="VD: 2026-2027"
                required
                maxLength={20}
              />
            </div>
          </div>

          <div className={styles.modalFooter}>
            <button
              type="button"
              className={styles.btnSecondary}
              onClick={onClose}
              disabled={isBusy}
            >
              Hủy
            </button>
            <button
              type="submit"
              className={styles.btnPrimary}
              disabled={isBusy || !name.trim()}
            >
              {isBusy ? (
                <>Đang khởi tạo...</>
              ) : (
                <>
                  <Sparkles size={16} />
                  Khởi tạo lớp học
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
