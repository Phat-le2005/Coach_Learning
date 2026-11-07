"use client";

import { useState } from "react";
import { X, UploadCloud, FileText, CheckCircle2 } from "lucide-react";
import type { TeacherClassroom, TeacherSubject } from "../api";
import styles from "../TeacherDashboard.module.css";

export interface UploadMaterialModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedClass?: TeacherClassroom;
  eligibleSubjects: TeacherSubject[];
  onSubmit: (subjectId: string, title: string, file: File) => Promise<void>;
  isBusy: boolean;
  errorMessage?: string;
  successMessage?: string;
}

export function UploadMaterialModal({
  isOpen,
  onClose,
  selectedClass,
  eligibleSubjects,
  onSubmit,
  isBusy,
  errorMessage,
  successMessage,
}: UploadMaterialModalProps) {
  const [title, setTitle] = useState("");
  const [subjectId, setSubjectId] = useState(eligibleSubjects[0]?.id ?? "");
  const [file, setFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [localError, setLocalError] = useState("");
  const resolvedSubjectId = eligibleSubjects.some((s) => s.id === subjectId) ? subjectId : eligibleSubjects[0]?.id ?? "";

  if (!isOpen) return null;

  function handleFileChange(selected: File | null) {
    if (isBusy) return;
    setLocalError("");
    if (!selected) {
      setFile(null);
      return;
    }
    if (selected.size > 25 * 1024 * 1024) {
      setFile(null);
      setLocalError("Tệp vượt quá dung lượng tối đa cho phép (25 MB).");
      return;
    }
    if (!/\.(pdf|png|jpe?g|txt)$/i.test(selected.name)) {
      setFile(null);
      setLocalError("Hệ thống hỗ trợ PDF, ảnh PNG/JPG/JPEG và TXT.");
      return;
    }
    setFile(selected);
    if (!title.trim()) {
      // Auto-fill title from filename without extension
      const cleanName = selected.name.replace(/\.[^/.]+$/, "");
      setTitle(cleanName);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLocalError("");
    if (!file || !title.trim() || !resolvedSubjectId || isBusy) return;
    try {
      await onSubmit(resolvedSubjectId, title.trim(), file);
      setTitle("");
      setFile(null);
    } catch (err) {
      setLocalError(err instanceof Error ? err.message : "Không tải được tài liệu. Vui lòng thử lại.");
    }
  }

  const effectiveError = localError || errorMessage;

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="upload-material-title">
      <div className={styles.modalContent}>
        <div className={styles.modalHeader}>
          <div className={styles.modalTitleGroup}>
            <div className={styles.modalIconWrap}>
              <UploadCloud size={20} />
            </div>
            <div>
              <h2 id="upload-material-title" className={styles.modalTitle}>
                Tải tài liệu bài tập
              </h2>
              <p className={styles.modalSubtitle}>
                {selectedClass ? `Lớp tiếp nhận: ${selectedClass.name} · Khối ${selectedClass.grade_level}` : "Chọn tài liệu học tập hoặc đề thi"}
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
          {effectiveError && (
            <div className={styles.formAlert} role="alert">
              {effectiveError}
            </div>
          )}

          {successMessage && (
            <div className={styles.formSuccess} role="status">
              <CheckCircle2 size={16} />
              {successMessage}
            </div>
          )}

          <div className={styles.formGroup}>
            <label htmlFor="upload-material-subject" className={styles.formLabel}>
              Môn học áp dụng <span className={styles.requiredMark}>*</span>
            </label>
            <select
              id="upload-material-subject"
              className={styles.formSelect}
              value={resolvedSubjectId}
              disabled={isBusy}
              onChange={(e) => setSubjectId(e.target.value)}
              required
            >
              {eligibleSubjects.length === 0 && <option value="">Chưa có môn học phù hợp khối lớp</option>}
              {eligibleSubjects.map((sub) => (
                <option key={sub.id} value={sub.id}>
                  {sub.name} ({sub.code})
                </option>
              ))}
            </select>
          </div>

          <div className={styles.formGroup}>
            <label htmlFor="upload-material-title-input" className={styles.formLabel}>
              Tên tài liệu / Tiêu đề đề bài <span className={styles.requiredMark}>*</span>
            </label>
            <input
              id="upload-material-title-input"
              className={styles.formInput}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="VD: Chuyên đề Đạo hàm & Khảo sát hàm số, Đề ôn tập giữa kì..."
              required
              maxLength={255}
              disabled={isBusy}
            />
          </div>

          <div className={styles.formGroup}>
            <label className={styles.formLabel}>
              Tệp tài liệu (PDF, ảnh hoặc TXT) <span className={styles.requiredMark}>*</span>
            </label>
            <div
              className={`${styles.dropZone} ${isDragging ? styles.dropZoneActive : ""} ${file ? styles.dropZoneHasFile : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setIsDragging(false);
                if (e.dataTransfer.files?.[0]) {
                  handleFileChange(e.dataTransfer.files[0]);
                }
              }}
            >
              <input
                id="upload-file-hidden"
                type="file"
                className={styles.fileInputHidden}
                accept=".pdf,.png,.jpg,.jpeg,.txt,application/pdf,image/png,image/jpeg,text/plain"
                disabled={isBusy}
                onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
              />
              <label htmlFor="upload-file-hidden" className={styles.dropZoneLabel}>
                {file ? (
                  <div className={styles.fileSelectedPreview}>
                    <div className={styles.fileIconBadge}>
                      <FileText size={24} />
                    </div>
                    <div className={styles.fileMeta}>
                      <strong className={styles.fileNameText}>{file.name}</strong>
                      <span className={styles.fileSizeText}>
                        {(file.size / 1024 / 1024).toFixed(2)} MB · Nhấp để chọn tệp khác
                      </span>
                    </div>
                  </div>
                ) : (
                  <>
                    <UploadCloud size={32} className={styles.dropZoneIcon} />
                    <p className={styles.dropZoneMainText}>
                      Kéo thả tệp vào đây hoặc <strong>nhấp để duyệt tệp</strong>
                    </p>
                    <span className={styles.dropZoneSubText}>PDF, ảnh PNG/JPG/JPEG hoặc TXT · Tối đa 25 MB</span>
                  </>
                )}
              </label>
            </div>
          </div>

          <p className={styles.modalSubtitle}>PDF và ảnh sẽ qua OCR bài tập, sau đó mở trang để thầy cô đối chiếu và chọn câu đạt yêu cầu. Có thể tải một ảnh câu hỏi để kiểm tra nhanh. Chỉ các câu được duyệt mới được lưu vào kho học liệu.</p>

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
              disabled={isBusy || !file || !title.trim() || !resolvedSubjectId}
            >
              {isBusy ? (
                <>Đang tải lên máy chủ...</>
              ) : (
                <>
                  <UploadCloud size={16} />
                  {file && /\.(png|jpe?g)$/i.test(file.name) ? "Tải ảnh & xử lý OCR" : file?.name.toLowerCase().endsWith(".pdf") ? "Tải PDF & xử lý OCR" : "Tải lên ngay"}
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
