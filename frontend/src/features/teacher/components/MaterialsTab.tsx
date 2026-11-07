"use client";

import { useMemo, useState } from "react";
import { UploadCloud, Search, FileText, Calendar, Filter, Sparkles, AlertCircle, Eye, Send } from "lucide-react";
import type { TeacherAssignment, TeacherClassroom, TeacherMaterial, TeacherSubject } from "../api";
import { MaterialPreviewModal } from "./MaterialPreviewModal";
import { AssignMaterialModal } from "./AssignMaterialModal";
import styles from "../TeacherDashboard.module.css";

export interface MaterialsTabProps {
  selectedClass?: TeacherClassroom;
  materials: TeacherMaterial[];
  subjects: TeacherSubject[];
  isLoading: boolean;
  onOpenUpload: () => void;
  onAssignmentCreated?: (assignment: TeacherAssignment) => void;
}

export function MaterialsTab({
  selectedClass,
  materials,
  subjects,
  isLoading,
  onOpenUpload,
  onAssignmentCreated,
}: MaterialsTabProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSubjectFilter, setSelectedSubjectFilter] = useState("");
  const [selectedPreviewMaterial, setSelectedPreviewMaterial] = useState<TeacherMaterial | null>(null);
  const [selectedAssignMaterial, setSelectedAssignMaterial] = useState<TeacherMaterial | null>(null);

  const formatSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium" }).format(new Date(dateStr));
    } catch {
      return dateStr;
    }
  };

  const filteredMaterials = useMemo(() => {
    return materials.filter((item) => {
      const matchQuery =
        item.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        item.original_file_name.toLowerCase().includes(searchQuery.toLowerCase());
      const matchSubject = !selectedSubjectFilter || item.subject_id === selectedSubjectFilter;
      return matchQuery && matchSubject;
    });
  }, [materials, searchQuery, selectedSubjectFilter]);

  if (!selectedClass) {
    return (
      <div className={styles.sectionCard}>
        <div className={styles.emptyCard}>
          <AlertCircle size={32} className={styles.emptyIcon} aria-hidden="true" />
          <h4 className={styles.emptyTitle}>Chưa chọn lớp học</h4>
          <p className={styles.emptyDesc}>
            Vui lòng chọn hoặc tạo một lớp học để quản lý kho tài liệu và đề thi bài tập.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.tabContentWrap}>
      <div className={styles.sectionCard}>
        {/* Header */}
        <div className={styles.sectionCardHeader}>
          <div>
            <div className={styles.badgeCluster}>
              <h3 className={styles.sectionHeading}>
                Kho học liệu &amp; Đề thi · {selectedClass.name}
              </h3>
              <span className={styles.studentTotalPill}>{materials.length} tệp</span>
            </div>
            <p className={styles.sectionSubheading}>
              Tài liệu PDF/TXT được lưu trữ an toàn trên máy chủ EduMS, dùng làm ngữ cảnh bài tập và đề kiểm tra
            </p>
          </div>

          <button
            type="button"
            className={styles.btnPrimary}
            onClick={onOpenUpload}
          >
            <UploadCloud size={16} aria-hidden="true" />
            Tải lên tài liệu mới
          </button>
        </div>

        {/* Toolbar & Filters */}
        <div className={styles.materialsToolbar}>
          <div className={styles.searchInputWrap}>
            <Search size={16} className={styles.searchIcon} aria-hidden="true" />
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Tìm kiếm tài liệu theo tiêu đề hoặc tên tệp..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            {searchQuery && (
              <button
                type="button"
                className={styles.searchClearBtn}
                onClick={() => setSearchQuery("")}
                aria-label="Xóa từ khóa tìm kiếm"
              >
                ✕
              </button>
            )}
          </div>

          <div className={styles.subjectFilterWrap}>
            <Filter size={15} className={styles.filterIcon} aria-hidden="true" />
            <select
              className={styles.filterSelect}
              value={selectedSubjectFilter}
              onChange={(e) => setSelectedSubjectFilter(e.target.value)}
              aria-label="Lọc theo môn học"
            >
              <option value="">Tất cả môn học</option>
              {subjects.map((sub) => (
                <option key={sub.id} value={sub.id}>
                  {sub.name} ({sub.code})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Materials List */}
        {isLoading ? (
          <div className={styles.tableLoadingState}>
            <div className={styles.spinner} aria-hidden="true" />
            <p>Đang tải danh sách tài liệu...</p>
          </div>
        ) : filteredMaterials.length === 0 ? (
          <div className={styles.emptyCard}>
            <FileText size={36} className={styles.emptyIcon} aria-hidden="true" />
            <h4 className={styles.emptyTitle}>
              {searchQuery || selectedSubjectFilter
                ? "Không tìm thấy tài liệu phù hợp bộ lọc"
                : "Chưa có tài liệu nào trong lớp học này"}
            </h4>
            <p className={styles.emptyDesc}>
              {searchQuery || selectedSubjectFilter
                ? "Hãy thử tìm kiếm với từ khóa khác hoặc xóa bộ lọc môn học."
                : "Tải lên đề ôn tập, bài giảng PDF để chia sẻ với học sinh và khai thác sơ đồ tư duy lý thuyết."}
            </p>
            {!searchQuery && !selectedSubjectFilter && (
              <button
                type="button"
                className={styles.btnPrimary}
                onClick={onOpenUpload}
              >
                <UploadCloud size={16} /> Tải tài liệu ngay
              </button>
            )}
          </div>
        ) : (
          <div className={styles.materialGridModern}>
            {filteredMaterials.map((item) => {
              const isPdf = item.original_file_name.endsWith(".pdf") || item.mime_type.includes("pdf");
              const subject = subjects.find((s) => s.id === item.subject_id);

              return (
                <article key={item.id} className={styles.materialCardModern}>
                  <div className={styles.materialCardHeader}>
                    <span className={isPdf ? styles.badgeFormatPdf : styles.badgeFormatTxt}>
                      <FileText size={13} aria-hidden="true" />
                      {isPdf ? "PDF" : "TXT"}
                    </span>
                    <span className={styles.materialStatusPill}>
                      {item.status === "APPROVED" ? "Đã duyệt" : item.status}
                    </span>
                  </div>

                  <h4 className={styles.materialCardTitle} title={item.title}>
                    {item.title}
                  </h4>

                  <p className={styles.materialFileName} title={item.original_file_name}>
                    {item.original_file_name}
                  </p>

                  <div className={styles.materialCardMeta}>
                    <span className={styles.materialSubjectTag}>
                      {subject?.name || "Môn học"}
                    </span>
                    <span className={styles.materialSizeText}>
                      {formatSize(item.file_size_bytes)}
                    </span>
                  </div>

                  <div className={styles.materialCardFooter}>
                    <span className={styles.materialDateText}>
                      <Calendar size={12} aria-hidden="true" />
                      {formatDate(item.created_at)}
                    </span>
                    <span className={styles.materialVerifiedHint}>
                      <Sparkles size={12} aria-hidden="true" />
                      Đã lưu trữ an toàn
                    </span>
                  </div>

                  <div className={styles.materialCardActions}>
                    <button
                      type="button"
                      className={styles.btnSecondarySmall}
                      onClick={() => setSelectedPreviewMaterial(item)}
                    >
                      <Eye size={13} /> Xem câu hỏi
                    </button>
                    <button
                      type="button"
                      className={styles.btnPrimarySmall}
                      onClick={() => setSelectedAssignMaterial(item)}
                    >
                      <Send size={13} /> Giao cho lớp
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>

      {/* Modals */}
      <MaterialPreviewModal
        isOpen={Boolean(selectedPreviewMaterial)}
        onClose={() => setSelectedPreviewMaterial(null)}
        material={selectedPreviewMaterial}
        onOpenAssign={(mat) => setSelectedAssignMaterial(mat)}
      />

      <AssignMaterialModal
        isOpen={Boolean(selectedAssignMaterial)}
        onClose={() => setSelectedAssignMaterial(null)}
        selectedClass={selectedClass}
        material={selectedAssignMaterial}
        onSuccess={(created) => {
          onAssignmentCreated?.(created);
        }}
      />
    </div>
  );
}
