"use client";

import { useState } from "react";
import { X, UploadCloud, FileText, AlertCircle, RefreshCw } from "lucide-react";
import styles from "../TheoryMaps.module.css";

export interface UploadTheoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  classNameTitle?: string;
  eligibleSubjects: { id: string; name: string }[];
  onUpload: (subjectId: string, title: string, file: File) => Promise<void>;
  isBusy: boolean;
}

export function UploadTheoryModal({
  isOpen,
  onClose,
  classNameTitle,
  eligibleSubjects,
  onUpload,
  isBusy,
}: UploadTheoryModalProps) {
  const [title, setTitle] = useState("");
  const [subjectId, setSubjectId] = useState(eligibleSubjects[0]?.id ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [localError, setLocalError] = useState("");

  if (!isOpen) return null;

  const resolvedSubjectId = subjectId || (eligibleSubjects[0]?.id ?? "");

  function handleFileChange(selected: File | null) {
    setLocalError("");
    if (!selected) {
      setFile(null);
      return;
    }
    if (selected.size > 25 * 1024 * 1024) {
      setLocalError("Tệp PDF vượt quá dung lượng tối đa cho phép (25 MB).");
      return;
    }
    if (!selected.name.toLowerCase().endsWith(".pdf") && selected.type !== "application/pdf") {
      setLocalError("Vui lòng chọn tệp tài liệu định dạng PDF.");
      return;
    }
    setFile(selected);
    if (!title.trim()) {
      const cleanName = selected.name.replace(/\.pdf$/i, "").replace(/[_-]+/g, " ").trim();
      setTitle(cleanName);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError("");
    if (!file) {
      setLocalError("Vui lòng chọn tệp PDF bài học.");
      return;
    }
    if (!title.trim()) {
      setLocalError("Vui lòng nhập tên tài liệu.");
      return;
    }
    if (!resolvedSubjectId) {
      setLocalError("Vui lòng chọn môn học phù hợp.");
      return;
    }
    try {
      await onUpload(resolvedSubjectId, title.trim(), file);
      setTitle("");
      setFile(null);
      onClose();
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "Không thể tải lên tệp PDF.");
    }
  }

  const formatSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div
      className={styles.modalOverlay}
      role="dialog"
      aria-modal="true"
      aria-labelledby="upload-theory-title"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isBusy) onClose();
      }}
    >
      <div className={styles.modalContent}>
        <div className={styles.modalHeader}>
          <div className={styles.modalTitleGroup}>
            <div className={styles.modalIconWrap}>
              <UploadCloud size={22} aria-hidden="true" />
            </div>
            <div>
              <h3 id="upload-theory-title" className={styles.modalTitle}>
                Tải lên PDF bài học &amp; Chuyên đề
              </h3>
              <p className={styles.modalSubtitle}>
                {classNameTitle ? `Lớp: ${classNameTitle} · ` : ""}AI Gemini sẽ đọc và kiến tạo Sơ đồ tư duy
              </p>
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
          {localError && (
            <div className={styles.modalErrorBar} role="alert">
              <AlertCircle size={16} aria-hidden="true" />
              <span>{localError}</span>
            </div>
          )}

          <div className={styles.modalFieldGroup}>
            <label htmlFor="theory-doc-title" className={styles.modalLabel}>
              Tên tài liệu / Chuyên đề <span className={styles.requiredMark}>*</span>
            </label>
            <input
              id="theory-doc-title"
              type="text"
              className={styles.modalInput}
              placeholder="Ví dụ: Chuyên đề Đạo hàm & Khảo sát hàm số"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
              maxLength={255}
              disabled={isBusy}
            />
          </div>

          <div className={styles.modalFieldGroup}>
            <label htmlFor="theory-doc-subject" className={styles.modalLabel}>
              Môn học <span className={styles.requiredMark}>*</span>
            </label>
            <select
              id="theory-doc-subject"
              className={styles.modalSelect}
              value={resolvedSubjectId}
              onChange={(e) => setSubjectId(e.target.value)}
              required
              disabled={isBusy}
            >
              {eligibleSubjects.length === 0 && <option value="">Chưa có môn phù hợp</option>}
              {eligibleSubjects.map((sub) => (
                <option key={sub.id} value={sub.id}>
                  {sub.name}
                </option>
              ))}
            </select>
          </div>

          <div className={styles.modalFieldGroup}>
            <label className={styles.modalLabel}>
              Tệp tài liệu PDF <span className={styles.requiredMark}>*</span>
            </label>
            <div
              className={`${styles.dropzone} ${isDragging ? styles.dropzoneActive : ""} ${file ? styles.dropzoneFilled : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                const dropped = e.dataTransfer.files?.[0] ?? null;
                handleFileChange(dropped);
              }}
            >
              <input
                type="file"
                id="theory-pdf-file-picker"
                className={styles.hiddenFileInput}
                accept=".pdf,application/pdf"
                onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
                disabled={isBusy}
              />

              {!file ? (
                <label htmlFor="theory-pdf-file-picker" className={styles.dropzoneLabel}>
                  <div className={styles.dropzoneIconWrap}>
                    <UploadCloud size={30} aria-hidden="true" />
                  </div>
                  <span className={styles.dropzoneMainText}>
                    <strong>Bấm để chọn tệp PDF</strong> hoặc kéo thả vào đây
                  </span>
                  <span className={styles.dropzoneSubText}>
                    Định dạng PDF bài giảng, chuyên đề học tập (Tối đa 25 MB)
                  </span>
                </label>
              ) : (
                <div className={styles.filePreviewRow}>
                  <div className={styles.filePreviewIcon}>
                    <FileText size={28} aria-hidden="true" />
                  </div>
                  <div className={styles.filePreviewInfo}>
                    <strong className={styles.filePreviewName}>{file.name}</strong>
                    <span className={styles.filePreviewSize}>{formatSize(file.size)}</span>
                  </div>
                  <label htmlFor="theory-pdf-file-picker" className={styles.changeFileBtn}>
                    Đổi tệp
                  </label>
                </div>
              )}
            </div>
          </div>

          <div className={styles.modalFooterActions}>
            <button
              type="button"
              className={styles.modalCancelBtn}
              onClick={onClose}
              disabled={isBusy}
            >
              Hủy
            </button>
            <button
              type="submit"
              className={styles.modalSubmitBtn}
              disabled={isBusy || !file || !title.trim()}
            >
              {isBusy ? (
                <>
                  <RefreshCw size={15} className={styles.spinIcon} aria-hidden="true" />
                  Đang tải lên...
                </>
              ) : (
                <>
                  <UploadCloud size={16} aria-hidden="true" />
                  Tải lên &amp; Lưu tài liệu
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
