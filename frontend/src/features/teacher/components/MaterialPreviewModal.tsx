"use client";

import { useEffect, useState } from "react";
import { X, BookOpen, Send, CheckCircle2, AlertCircle, FileText, HelpCircle } from "lucide-react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import { teacherApi, type TeacherMaterial, type TeacherMaterialItem } from "../api";
import styles from "../TeacherDashboard.module.css";

export interface MaterialPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
  material: TeacherMaterial | null;
  onOpenAssign: (material: TeacherMaterial) => void;
}

export function MaterialPreviewModal({
  isOpen,
  onClose,
  material,
  onOpenAssign,
}: MaterialPreviewModalProps) {
  const [items, setItems] = useState<TeacherMaterialItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!isOpen || !material) {
      setItems([]);
      setError("");
      return;
    }

    let active = true;
    setIsLoading(true);
    setError("");

    teacherApi
      .materialItems(material.id)
      .then((data) => {
        if (active) setItems(data);
      })
      .catch((err) => {
        if (active) setError(err instanceof Error ? err.message : "Không thể tải danh sách câu hỏi.");
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });

    return () => {
      active = false;
    };
  }, [isOpen, material]);

  if (!isOpen || !material) return null;

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="preview-material-title">
      <div className={styles.modalContentWide}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div className={styles.modalTitleGroup}>
            <div className={styles.modalIconWrap}>
              <BookOpen size={20} />
            </div>
            <div>
              <h2 id="preview-material-title" className={styles.modalTitle}>
                {material.title}
              </h2>
              <p className={styles.modalSubtitle}>
                {material.original_file_name} · {items.length > 0 ? `${items.length} câu hỏi bóc tách` : "Đang kiểm tra câu hỏi"}
              </p>
            </div>
          </div>
          <button
            type="button"
            className={styles.modalCloseBtn}
            onClick={onClose}
            aria-label="Đóng cửa sổ"
          >
            <X size={18} />
          </button>
        </div>

        {/* Content */}
        <div className={styles.modalBodyScrollable}>
          {error && (
            <div className={styles.formAlert} role="alert">
              <AlertCircle size={16} />
              <span>{error}</span>
            </div>
          )}

          {isLoading ? (
            <div className={styles.tableLoadingState}>
              <div className={styles.spinner} aria-hidden="true" />
              <p>Đang tải danh sách câu hỏi bóc tách từ tài liệu...</p>
            </div>
          ) : items.length === 0 ? (
            <div className={styles.emptyCard}>
              <FileText size={36} className={styles.emptyIcon} />
              <h4 className={styles.emptyTitle}>Chưa có câu hỏi nào được bóc tách</h4>
              <p className={styles.emptyDesc}>
                Tài liệu này chưa có câu hỏi sẵn sàng hoặc đang chờ phân tích.
              </p>
            </div>
          ) : (
            <div className={styles.previewQuestionsList}>
              {items.map((item, idx) => (
                <div key={item.id} className={styles.previewQuestionCard}>
                  <div className={styles.previewQuestionHeader}>
                    <span className={styles.previewQuestionBadge}>
                      Câu {idx + 1}
                    </span>
                    <div className={styles.previewMetaCluster}>
                      {item.question_type && (
                        <span className={styles.tagPillSecondary}>
                          {item.question_type === "MULTIPLE_CHOICE" ? "Trắc nghiệm" : "Tự luận"}
                        </span>
                      )}
                      {item.difficulty !== null && (
                        <span className={styles.tagPillMuted}>
                          Độ khó: {Number((item.difficulty * 10).toFixed(1))}/10
                        </span>
                      )}
                    </div>
                  </div>

                  <div className={styles.previewQuestionContent}>
                    <MathRenderer content={item.content} />
                  </div>

                  {item.options && item.options.length > 0 && (
                    <div className={styles.previewOptionsGrid}>
                      {item.options.map((opt) => (
                        <div
                          key={opt.id}
                          className={`${styles.previewOptionRow} ${
                            item.correct_answer === opt.label ? styles.previewOptionCorrect : ""
                          }`}
                        >
                          <span className={styles.optionLabelBadge}>{opt.label}</span>
                          <div className={styles.optionTextContent}>
                            <MathRenderer content={opt.content} inline={true} />
                          </div>
                          {item.correct_answer === opt.label && (
                            <CheckCircle2 size={15} className={styles.textVerdant} />
                          )}
                        </div>
                      ))}
                    </div>
                  )}

                  {item.correct_answer && item.options.length === 0 && (
                    <div className={styles.previewAnswerNotice}>
                      <strong>Đáp án tham chiếu: </strong>
                      <MathRenderer content={item.correct_answer} inline={true} />
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className={styles.modalFooter}>
          <button type="button" className={styles.btnSecondary} onClick={onClose}>
            Đóng
          </button>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={() => {
              onClose();
              onOpenAssign(material);
            }}
            disabled={items.length === 0}
          >
            <Send size={15} />
            Giao bài tập này cho lớp ({items.length} câu)
          </button>
        </div>
      </div>
    </div>
  );
}
