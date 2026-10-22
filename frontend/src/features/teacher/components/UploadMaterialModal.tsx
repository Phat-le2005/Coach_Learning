"use client";

import React, { useState } from "react";
import { X, UploadCloud, FileText, CheckCircle2 } from "lucide-react";
import type { TeacherMaterial, MaterialCategory } from "../types";
import styles from "../TeacherDashboard.module.css";

interface UploadMaterialModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAddMaterial: (material: TeacherMaterial) => void;
}

export function UploadMaterialModal({ isOpen, onClose, onAddMaterial }: UploadMaterialModalProps) {
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState<MaterialCategory>("theory");
  const [topic, setTopic] = useState("Ứng dụng Đạo hàm");
  const [format, setFormat] = useState<"pdf" | "docx" | "exam">("pdf");
  const [description, setDescription] = useState("");
  const [fileName, setFileName] = useState("");

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;

    const newMat: TeacherMaterial = {
      id: `mat-${Date.now()}`,
      title: title.trim(),
      category,
      topic,
      format,
      gradeLevel: 12,
      description: description.trim() || (category === "theory" ? "Tài liệu tóm tắt lý thuyết chuyên đề." : "Phiếu bài tập rèn luyện thực hành."),
      itemCount: category === "practice" ? 8 : 10,
      assignedClassrooms: ["Lớp 12A"],
      updatedAt: "Hôm nay",
      fileSize: "1.5 MB",
      downloadsCount: 0,
    };

    onAddMaterial(newMat);
    onClose();
  };

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="upload-modal-title">
      <div className={styles.modalContent}>
        <div className={styles.modalHeader}>
          <h3 id="upload-modal-title" className={styles.modalTitle}>
            Tải lên tài liệu giảng dạy mới
          </h3>
          <button type="button" className={styles.closeBtn} onClick={onClose} aria-label="Đóng">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className={styles.formGroup}>
            <label className={styles.formLabel} htmlFor="mat-title">Tên tài liệu / Chuyên đề *</label>
            <input
              id="mat-title"
              type="text"
              className={styles.formInput}
              placeholder="VD: Chuyên đề khảo sát hàm số bậc ba..."
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              required
            />
          </div>

          <div className={styles.formGroup} style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
            <div>
              <label className={styles.formLabel} htmlFor="mat-cat">Phân loại kho *</label>
              <select
                id="mat-cat"
                className={styles.formSelect}
                value={category}
                onChange={(e) => setCategory(e.target.value as MaterialCategory)}
              >
                <option value="theory">📖 Lý thuyết chuyên đề</option>
                <option value="practice">✍️ Thực hành / Bài tập</option>
              </select>
            </div>

            <div>
              <label className={styles.formLabel} htmlFor="mat-topic">Chủ đề kiến thức *</label>
              <select
                id="mat-topic"
                className={styles.formSelect}
                value={topic}
                onChange={(e) => setTopic(e.target.value)}
              >
                <option value="Ứng dụng Đạo hàm">Ứng dụng Đạo hàm</option>
                <option value="Nguyên hàm — Tích phân">Nguyên hàm — Tích phân</option>
                <option value="Hình học Oxyz">Hình học Oxyz</option>
                <option value="Xác suất — Thống kê">Xác suất — Thống kê</option>
                <option value="Toán 12 Tổng hợp">Toán 12 Tổng hợp</option>
              </select>
            </div>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.formLabel} htmlFor="mat-format">Định dạng file</label>
            <select
              id="mat-format"
              className={styles.formSelect}
              value={format}
              onChange={(e) => setFormat(e.target.value as "pdf" | "docx" | "exam")}
            >
              <option value="pdf">Tài liệu PDF (.pdf)</option>
              <option value="docx">Tài liệu Word (.docx)</option>
              <option value="exam">Đề thi / Bài tập Canvas (.exam)</option>
            </select>
          </div>

          <div className={styles.formGroup}>
            <label className={styles.formLabel} htmlFor="mat-desc">Mô tả tóm tắt nội dung</label>
            <textarea
              id="mat-desc"
              rows={3}
              className={styles.formTextarea}
              placeholder="Nội dung chính, mục tiêu rèn luyện hoặc các định lý cần nhớ..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1.25rem" }}>
            <button type="button" className={styles.btnSecondary} onClick={onClose}>
              Hủy
            </button>
            <button type="submit" className={styles.btnPrimary}>
              <UploadCloud size={16} />
              Xác nhận tải lên
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
