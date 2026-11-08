"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { UploadCloud, Search, FileText, Calendar, Filter, Sparkles, AlertCircle, Eye, Send, Trash2, Download, FilePenLine } from "lucide-react";
import { teacherApi, type TeacherAssignment, type TeacherClassroom, type TeacherMaterial, type TeacherSubject } from "../api";
import { MaterialPreviewModal } from "./MaterialPreviewModal";
import { AssignMaterialModal } from "./AssignMaterialModal";
import styles from "../TeacherDashboard.module.css";
import { teacherPdfApi, type TeacherPdfImport } from "../pdf-api";
import { ExercisePdfReview, PDF_IMPORT_STATUS } from "./ExercisePdfReview";
import reviewStyles from "./ExercisePdfReview.module.css";
import { DeleteMaterialDialog } from "./DeleteMaterialDialog";

export interface MaterialsTabProps {
  selectedClass?: TeacherClassroom;
  materials: TeacherMaterial[];
  subjects: TeacherSubject[];
  isLoading: boolean;
  onOpenUpload: () => void;
  onAssignmentCreated?: (assignment: TeacherAssignment) => void;
  pdfImportId?: string;
  onOpenPdfImport?: (id: string) => void;
  onMaterialSubmitted?: (material: TeacherMaterial) => void;
  onMaterialDeleted?: (materialId: string) => void;
}

export function MaterialsTab({
  selectedClass,
  materials,
  subjects,
  isLoading,
  onOpenUpload,
  onAssignmentCreated,
  pdfImportId,
  onOpenPdfImport,
  onMaterialSubmitted,
  onMaterialDeleted,
}: MaterialsTabProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedSubjectFilter, setSelectedSubjectFilter] = useState("");
  const [selectedPreviewMaterial, setSelectedPreviewMaterial] = useState<TeacherMaterial | null>(null);
  const [selectedAssignMaterial, setSelectedAssignMaterial] = useState<TeacherMaterial | null>(null);
  const [imports, setImports] = useState<TeacherPdfImport[]>([]);
  const [importError, setImportError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<TeacherMaterial | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const [deleteNotice, setDeleteNotice] = useState("");
  const uploadButton = useRef<HTMLButtonElement>(null);
  const deleteTrigger = useRef<HTMLButtonElement | null>(null);

  async function deleteMaterial() {
    if (!deleteTarget || deleteBusy) return;
    setDeleteBusy(true); setDeleteError("");
    try {
      await teacherApi.deleteMaterial(deleteTarget.id);
      onMaterialDeleted?.(deleteTarget.id);
      if (selectedPreviewMaterial?.id === deleteTarget.id) setSelectedPreviewMaterial(null);
      if (selectedAssignMaterial?.id === deleteTarget.id) setSelectedAssignMaterial(null);
      setDeleteNotice(`Đã xóa ${deleteTarget.title} khỏi kho học liệu.`);
      setDeleteTarget(null);
      requestAnimationFrame(() => uploadButton.current?.focus());
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "Không thể xóa tài liệu. Vui lòng thử lại.");
    } finally { setDeleteBusy(false); }
  }

  useEffect(() => {
    if (!selectedClass || pdfImportId) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    setImports([]); setImportError("");
    const classId = selectedClass.id;
    async function load() {
      try {
        const drafts = await teacherPdfApi.list(classId);
        if (!active) return;
        setImports(drafts.filter((d) => d.status !== "SUBMITTED")); setImportError("");
        if (drafts.some((d) => ["QUEUED", "PROCESSING"].includes(d.status))) timer = setTimeout(load, 5000);
      } catch (err) {
        if (active) setImportError(err instanceof Error ? err.message : "Không tải được bản nháp OCR.");
      }
    }
    void load();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [selectedClass?.id, pdfImportId]);

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

  if (pdfImportId) {
    return <ExercisePdfReview key={pdfImportId} jobId={pdfImportId} onClose={() => onOpenPdfImport?.("")} onSubmitted={(material) => onMaterialSubmitted?.(material)} onOpenRevision={(id) => onOpenPdfImport?.(id)} />;
  }

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
      <div className={`${styles.sectionCard} ${styles.materialsSection}`}>
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
              Tải PDF hoặc ảnh, duyệt câu hỏi sau OCR và lưu thành tài liệu bài tập để giao cho lớp.
            </p>
          </div>

          <button
            ref={uploadButton}
            type="button"
            className={styles.btnPrimary}
            onClick={onOpenUpload}
          >
            <UploadCloud size={16} aria-hidden="true" />
            Tải lên tài liệu mới
          </button>
        </div>

        {importError && <p className={styles.formAlert} role="alert">{importError}</p>}
        {deleteNotice && <p className={styles.formSuccess} role="status">{deleteNotice}</p>}
        {imports.length > 0 && <div className={reviewStyles.drafts}>
          <h4>Bản nháp OCR đang xử lý / chờ duyệt ({imports.length})</h4>
          {imports.map((draft) => <div key={draft.id} className={reviewStyles.draftRow}>
            <div><strong>{draft.title}</strong><p>{PDF_IMPORT_STATUS[draft.status]} · {draft.original_file_name}{draft.status === "PROCESSING" ? ` · ${draft.progress.processed_pages ?? 0}/${draft.progress.selected_pages ?? "…"} trang` : ""}</p></div>
            <button className={styles.btnSecondarySmall} onClick={() => onOpenPdfImport?.(draft.id)}><Eye size={14} aria-hidden="true" /> {draft.status === "NEEDS_REVIEW" ? "Duyệt câu hỏi" : "Xem tiến độ"}</button>
          </div>)}
        </div>}

        {/* Toolbar & Filters */}
        <div className={styles.materialsToolbar}>
          <div className={`${styles.searchInputWrap} ${styles.materialSearch}`}>
            <Search size={16} className={styles.searchIcon} aria-hidden="true" />
            <input
              type="text"
              className={styles.searchInput}
              placeholder="Tìm kiếm tài liệu theo tiêu đề hoặc tên tệp..."
              aria-label="Tìm kiếm học liệu"
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
              const isReviewed = item.mime_type === "application/json";
              const subject = subjects.find((s) => s.id === item.subject_id);

              return (
                <article key={item.id} className={styles.materialCardModern}>
                  <div className={styles.materialCardHeader}>
                    <span className={isPdf ? styles.badgeFormatPdf : styles.badgeFormatTxt}>
                      <FileText size={13} aria-hidden="true" />
                      {isReviewed ? "Bài tập" : isPdf ? "PDF" : "TXT"}
                    </span>
                    <div className={styles.materialStatusActions}><span className={styles.materialStatusPill}>
                      {({ READY: "Đã duyệt", APPROVED: "Đã duyệt", PUBLISHED: "Đã phát hành", NEEDS_REVIEW: "Cần duyệt", PARSED: "Đã tách câu", UPLOADED: "Đã tải lên", MAPPING_PENDING: "Chờ phân loại", FAILED: "Xử lý lỗi" } as Record<string, string>)[item.status] ?? item.status}
                    </span>
                    <button type="button" className={styles.deleteMaterialButton} aria-label={`Xóa tài liệu ${item.title}`}
                      onClick={(event) => { deleteTrigger.current = event.currentTarget; setDeleteTarget(item); setDeleteError(""); setDeleteNotice(""); }}>
                      <Trash2 size={15} aria-hidden="true" /> Xóa
                    </button></div>
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
                    {isReviewed && <a className={styles.materialUtilityAction} href={`/api/teacher/materials/${item.id}/document`} aria-label="Tải bản đã duyệt">
                      <Download size={14} aria-hidden="true" /> Tải bản duyệt
                    </a>}
                    {item.pdf_import_id && <button type="button" className={styles.materialUtilityAction} aria-label="Xem nguồn / Chỉnh sửa"
                      onClick={() => onOpenPdfImport?.(item.pdf_import_id!)}>
                      <FilePenLine size={14} aria-hidden="true" /> Nguồn / chỉnh sửa
                    </button>}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>

      {/* Modals */}
      {deleteTarget && <DeleteMaterialDialog material={deleteTarget} busy={deleteBusy} error={deleteError} onConfirm={deleteMaterial}
        onCancel={() => { setDeleteTarget(null); requestAnimationFrame(() => deleteTrigger.current?.focus()); }} />}
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
