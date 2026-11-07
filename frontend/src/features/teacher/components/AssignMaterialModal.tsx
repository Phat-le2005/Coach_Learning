"use client";

import { useEffect, useState } from "react";
import { X, Send, Calendar, Clock, CheckCircle2, AlertCircle, Sparkles, BookOpen, Layers } from "lucide-react";
import { teacherApi, type TeacherAssignment, type TeacherClassroom, type TeacherMaterial, type TeacherMaterialItem } from "../api";
import styles from "../TeacherDashboard.module.css";

export interface AssignMaterialModalProps {
  isOpen: boolean;
  onClose: () => void;
  selectedClass?: TeacherClassroom;
  material: TeacherMaterial | null;
  onSuccess: (newAssignment: TeacherAssignment) => void;
}

export function AssignMaterialModal({
  isOpen,
  onClose,
  selectedClass,
  material,
  onSuccess,
}: AssignMaterialModalProps) {
  const [title, setTitle] = useState("");
  const [deliveryMode, setDeliveryMode] = useState<"PRACTICE" | "EXAM">("PRACTICE");
  const [dueAt, setDueAt] = useState("");
  const [items, setItems] = useState<TeacherMaterialItem[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isLoadingItems, setIsLoadingItems] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  useEffect(() => {
    if (!isOpen || !material) {
      setTitle("");
      setDeliveryMode("PRACTICE");
      setDueAt("");
      setItems([]);
      setSelectedIds(new Set());
      setErrorMessage("");
      return;
    }

    setTitle(material.title || "Bài tập giao từ tài liệu PDF");
    let active = true;
    setIsLoadingItems(true);
    setErrorMessage("");

    teacherApi
      .materialItems(material.id)
      .then((data) => {
        if (!active) return;
        setItems(data);
        setSelectedIds(new Set(data.map((i) => i.id)));
      })
      .catch((err) => {
        if (active) setErrorMessage(err instanceof Error ? err.message : "Không thể tải danh sách câu hỏi.");
      })
      .finally(() => {
        if (active) setIsLoadingItems(false);
      });

    return () => {
      active = false;
    };
  }, [isOpen, material]);

  if (!isOpen || !material || !selectedClass) return null;

  const toggleSelectAll = () => {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.map((i) => i.id)));
    }
  };

  const toggleItem = (id: string) => {
    const next = new Set(selectedIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    setSelectedIds(next);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || selectedIds.size === 0 || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage("");

    try {
      // 1. Ensure material is prepared (has confirmed taxonomy & READY status)
      await teacherApi.prepareMaterialForAssignment(material.id);

      // 2. Create the assignment with configured delivery mode
      const selectedItemIdsList = items
        .filter((item) => selectedIds.has(item.id))
        .map((item) => item.id);

      const created = await teacherApi.createAssignmentFromMaterial(selectedClass.id, {
        title: title.trim(),
        subjectId: material.subject_id,
        deliveryMode,
        dueAt: dueAt ? new Date(dueAt).toISOString() : null,
        teacherMaterialItemIds: selectedItemIdsList,
      });

      // 3. Publish the assignment to the active class
      const published = await teacherApi.publishAssignment(created.id);

      onSuccess(published);
      onClose();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : "Không thể khởi tạo đợt giao bài.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className={styles.modalOverlay} role="dialog" aria-modal="true" aria-labelledby="assign-material-title">
      <div className={styles.modalContentWide}>
        {/* Header */}
        <div className={styles.modalHeader}>
          <div className={styles.modalTitleGroup}>
            <div className={styles.modalIconWrap}>
              <Send size={20} />
            </div>
            <div>
              <h2 id="assign-material-title" className={styles.modalTitle}>
                Giao bài tập cho lớp {selectedClass.name}
              </h2>
              <p className={styles.modalSubtitle}>
                Trích xuất từ: {material.title} ({material.original_file_name})
              </p>
            </div>
          </div>
          <button
            type="button"
            className={styles.modalCloseBtn}
            onClick={onClose}
            aria-label="Đóng cửa sổ"
            disabled={isSubmitting}
          >
            <X size={18} />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className={styles.modalFormWrapper}>
          <div className={styles.modalBodyScrollable}>
            {errorMessage && (
              <div className={styles.formAlert} role="alert">
                <AlertCircle size={16} />
                <span>{errorMessage}</span>
              </div>
            )}

          {/* Title */}
          <div className={styles.formGroup}>
            <label htmlFor="assign-title" className={styles.formLabel}>
              Tiêu đề đợt giao bài <span className={styles.requiredMark}>*</span>
            </label>
            <input
              id="assign-title"
              type="text"
              className={styles.formInput}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="VD: Phiếu luyện tập Chuyên đề 1, Bài kiểm tra 45 phút..."
              required
              disabled={isSubmitting}
            />
          </div>

          {/* Delivery Mode: 2 Modes Selection */}
          <div className={styles.formGroup}>
            <label className={styles.formLabel}>
              Chế độ làm bài &amp; Chấm điểm <span className={styles.requiredMark}>*</span>
            </label>
            <div className={styles.deliveryModeGrid}>
              {/* Mode 1: Practice / Formative */}
              <label
                className={`${styles.deliveryModeCard} ${
                  deliveryMode === "PRACTICE" ? styles.deliveryModeCardActive : ""
                }`}
              >
                <input
                  type="radio"
                  name="delivery_mode"
                  value="PRACTICE"
                  checked={deliveryMode === "PRACTICE"}
                  onChange={() => setDeliveryMode("PRACTICE")}
                  className={styles.radioHidden}
                  disabled={isSubmitting}
                />
                <div className={styles.deliveryModeHeader}>
                  <div className={styles.modeIconPillGreen}>
                    <Sparkles size={16} />
                  </div>
                  <div>
                    <strong className={styles.modeCardTitle}>Học &amp; Luyện tập từng câu</strong>
                    <span className={styles.modeTagGreen}>Chấm ngay từng câu</span>
                  </div>
                </div>
                <p className={styles.modeCardDesc}>
                  Học sinh làm từng câu (Câu 1 ➔ Câu 10). Bấm kiểm tra để AI chấm từng bước ngay lập tức, hiển thị giải thích sửa lỗi và cập nhật trực tiếp Cây tri thức &amp; Lộ trình.
                </p>
              </label>

              {/* Mode 2: Exam / Summative */}
              <label
                className={`${styles.deliveryModeCard} ${
                  deliveryMode === "EXAM" ? styles.deliveryModeCardActivePurple : ""
                }`}
              >
                <input
                  type="radio"
                  name="delivery_mode"
                  value="EXAM"
                  checked={deliveryMode === "EXAM"}
                  onChange={() => setDeliveryMode("EXAM")}
                  className={styles.radioHidden}
                  disabled={isSubmitting}
                />
                <div className={styles.deliveryModeHeader}>
                  <div className={styles.modeIconPillPurple}>
                    <Layers size={16} />
                  </div>
                  <div>
                    <strong className={styles.modeCardTitle}>Kiểm tra / Thi (Exam)</strong>
                    <span className={styles.modeTagPurple}>Nộp 1 lần &amp; GV duyệt</span>
                  </div>
                </div>
                <p className={styles.modeCardDesc}>
                  Học sinh làm trọn bộ câu hỏi (lưu nháp tự động), khóa gợi ý và khóa xem đáp án. Bấm &quot;Nộp bài thi&quot; một lần để AI chấm hàng loạt và chuyển Giáo viên kiểm duyệt.
                </p>
              </label>
            </div>
          </div>

          {/* Due date */}
          <div className={styles.formGroup}>
            <label htmlFor="assign-due-at" className={styles.formLabel}>
              Hạn nộp bài (tùy chọn)
            </label>
            <div className={styles.inputWithIcon}>
              <Calendar size={16} className={styles.fieldIcon} />
              <input
                id="assign-due-at"
                type="datetime-local"
                className={styles.formInput}
                value={dueAt}
                onChange={(e) => setDueAt(e.target.value)}
                disabled={isSubmitting}
              />
            </div>
          </div>

          {/* Question selection */}
          <div className={styles.formGroup}>
            <div className={styles.sectionRowBetween}>
              <label className={styles.formLabel}>
                Chọn các câu hỏi giao cho học sinh ({selectedIds.size}/{items.length} câu)
              </label>
              <button
                type="button"
                className={styles.btnTextAction}
                onClick={toggleSelectAll}
                disabled={isSubmitting || items.length === 0}
              >
                {selectedIds.size === items.length ? "Bỏ chọn tất cả" : "Chọn tất cả"}
              </button>
            </div>

            {isLoadingItems ? (
              <div className={styles.tableLoadingState}>
                <div className={styles.spinner} aria-hidden="true" />
                <p>Đang tải danh sách câu hỏi...</p>
              </div>
            ) : items.length === 0 ? (
              <p className={styles.emptyTextMuted}>Không có câu hỏi nào để chọn.</p>
            ) : (
              <div className={styles.itemsChecklistWrap}>
                {items.map((item, idx) => {
                  const isChecked = selectedIds.has(item.id);
                  const cleanSnippet = item.content.replace(/^câu\s*\d+\s*[:.]\s*/i, "").trim();
                  return (
                    <label
                      key={item.id}
                      className={`${styles.itemCheckRow} ${isChecked ? styles.itemCheckRowSelected : ""}`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleItem(item.id)}
                        disabled={isSubmitting}
                        className={styles.checkboxInput}
                      />
                      <div className={styles.itemCheckInfo}>
                        <span className={styles.itemNumberBadge}>Câu {idx + 1}</span>
                        <p className={styles.itemSnippet}>{cleanSnippet.slice(0, 140)}...</p>
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
          </div>
          </div>

          {/* Modal Footer - Fixed Sticky at bottom */}
          <div className={styles.modalFooter}>
            <button
              type="button"
              className={styles.btnSecondary}
              onClick={onClose}
              disabled={isSubmitting}
            >
              Hủy
            </button>
            <button
              type="submit"
              className={styles.btnPrimary}
              disabled={isSubmitting || !title.trim() || selectedIds.size === 0}
            >
              {isSubmitting ? (
                <>Đang chuẩn bị &amp; giao bài...</>
              ) : (
                <>
                  <Send size={15} />
                  Xác nhận giao bài ({selectedIds.size} câu)
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
