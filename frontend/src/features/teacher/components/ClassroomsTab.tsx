"use client";

import { useMemo, useState } from "react";
import { Users, Search, Plus, CheckCircle2, UserCheck, Calendar } from "lucide-react";
import type { TeacherClassroom, TeacherStudent } from "../api";
import { ClassroomExperience } from "./ClassroomExperience";
import styles from "../TeacherDashboard.module.css";

export interface ClassroomsTabProps {
  classes: TeacherClassroom[];
  selectedClassId: string;
  onSelectClass: (id: string) => void;
  students: TeacherStudent[];
  isLoading: boolean;
  onOpenCreateClass: () => void;
  onViewStudentWorkspace: (studentId: string) => void;
  studentError?: string;
}

export function ClassroomsTab({
  classes,
  selectedClassId,
  onSelectClass,
  students,
  isLoading,
  onOpenCreateClass,
  onViewStudentWorkspace,
  studentError,
}: ClassroomsTabProps) {
  const [view, setView] = useState<"3d" | "list">("3d");
  const [preview, setPreview] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "ACTIVE" | "INACTIVE">("ALL");

  const selectedClass = classes.find((c) => c.id === selectedClassId);

  const filteredStudents = useMemo(() => {
    return students.filter((s) => {
      const matchQuery =
        s.full_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        s.email.toLowerCase().includes(searchQuery.toLowerCase());
      const matchStatus = statusFilter === "ALL" || s.status === statusFilter;
      return matchQuery && matchStatus;
    });
  }, [students, searchQuery, statusFilter]);

  const activeCount = students.filter((s) => s.status === "ACTIVE").length;
  const inactiveCount = students.length - activeCount;

  return (
    <div className={styles.tabContentWrap}>
      <ClassroomExperience students={students} selectedClass={selectedClass} isLoading={isLoading} error={studentError} preview={preview} onPreview={setPreview} view={view} onView={setView} query={searchQuery} onQuery={setSearchQuery} onViewStudentWorkspace={onViewStudentWorkspace} />

      {/* Section 1: Danh sách lớp học giáo viên quản lý */}
      <div className={styles.sectionCard}>
        <div className={styles.sectionCardHeader}>
          <div>
            <h3 className={styles.sectionHeading}>Các lớp học phụ trách</h3>
            <p className={styles.sectionSubheading}>
              Chọn lớp học để xem học sinh, học liệu và thống kê tiến độ học tập
            </p>
          </div>
          <button
            type="button"
            className={styles.btnSecondary}
            onClick={onOpenCreateClass}
          >
            <Plus size={15} aria-hidden="true" />
            Tạo lớp học mới
          </button>
        </div>

        {classes.length === 0 ? (
          <div className={styles.emptyCard}>
            <Users size={36} className={styles.emptyIcon} aria-hidden="true" />
            <h4 className={styles.emptyTitle}>Chưa có lớp học nào</h4>
            <p className={styles.emptyDesc}>
              Bắt đầu tạo lớp học đầu tiên để quản lý danh sách học sinh và phân công bài tập.
            </p>
            <button
              type="button"
              className={styles.btnPrimary}
              onClick={onOpenCreateClass}
            >
              <Plus size={16} /> Tạo lớp học ngay
            </button>
          </div>
        ) : (
          <div className={styles.classCardGrid}>
            {classes.map((c) => {
              const isSelected = c.id === selectedClassId;
              return (
                <div
                  key={c.id}
                  className={`${styles.classRoomCard} ${isSelected ? styles.classRoomCardActive : ""}`}
                  onClick={() => onSelectClass(c.id)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") onSelectClass(c.id);
                  }}
                >
                  <div className={styles.classRoomCardTop}>
                    <span className={styles.classGradeBadge}>Khối {c.grade_level}</span>
                    <span className={styles.classYearBadge}>
                      <Calendar size={12} aria-hidden="true" />
                      {c.academic_year}
                    </span>
                  </div>

                  <h4 className={styles.classRoomName}>{c.name}</h4>

                  <div className={styles.classRoomFooter}>
                    <span className={styles.classStudentCount}>
                      <Users size={14} aria-hidden="true" />
                      {isSelected ? `${students.length} học sinh` : "Nhấp để quản lý"}
                    </span>
                    {isSelected && (
                      <span className={styles.selectedIndicator}>
                        <CheckCircle2 size={15} aria-hidden="true" />
                        Đang chọn
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Keep the existing API-backed student table available. */}
      {selectedClass && view === "list" && !preview && !studentError && (
        <div className={styles.sectionCard}>
          <div className={styles.sectionCardHeader}>
            <div>
              <div className={styles.badgeCluster}>
                <h3 className={styles.sectionHeading}>
                  Danh sách học sinh · {selectedClass.name}
                </h3>
                <span className={styles.studentTotalPill}>{students.length} em</span>
              </div>
              <p className={styles.sectionSubheading}>
                Thông tin tài khoản học sinh thật được kết nối trực tiếp từ hệ thống
              </p>
            </div>

            {/* Filter Pills */}
            <div className={styles.filterPillsGroup}>
              <button
                type="button"
                className={`${styles.filterPill} ${statusFilter === "ALL" ? styles.filterPillActive : ""}`}
                onClick={() => setStatusFilter("ALL")}
              >
                Tất cả ({students.length})
              </button>
              <button
                type="button"
                className={`${styles.filterPill} ${statusFilter === "ACTIVE" ? styles.filterPillActive : ""}`}
                onClick={() => setStatusFilter("ACTIVE")}
              >
                Đang học ({activeCount})
              </button>
              {inactiveCount > 0 && (
                <button
                  type="button"
                  className={`${styles.filterPill} ${statusFilter === "INACTIVE" ? styles.filterPillActive : ""}`}
                  onClick={() => setStatusFilter("INACTIVE")}
                >
                  Tạm dừng ({inactiveCount})
                </button>
              )}
            </div>
          </div>

          {/* Search bar */}
          <div className={styles.tableToolbar}>
            <div className={styles.searchInputWrap}>
              <Search size={16} className={styles.searchIcon} aria-hidden="true" />
              <input
                type="text"
                className={styles.searchInput}
                placeholder="Tìm kiếm học sinh theo họ tên hoặc email..."
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
            <div className={styles.resultsCount}>
              Hiển thị <strong>{filteredStudents.length}</strong> / {students.length} học sinh
            </div>
          </div>

          {/* Student Table */}
          {isLoading ? (
            <div className={styles.tableLoadingState}>
              <div className={styles.spinner} aria-hidden="true" />
              <p>Đang tải danh sách học sinh từ máy chủ...</p>
            </div>
          ) : filteredStudents.length === 0 ? (
            <div className={styles.emptyCard}>
              <UserCheck size={32} className={styles.emptyIcon} aria-hidden="true" />
              <h4 className={styles.emptyTitle}>
                {searchQuery ? "Không tìm thấy học sinh phù hợp" : "Lớp học chưa có học sinh nào"}
              </h4>
              <p className={styles.emptyDesc}>
                {searchQuery
                  ? "Hãy thử tìm kiếm bằng từ khóa khác hoặc chuyển bộ lọc trạng thái."
                  : "Học sinh sẽ xuất hiện tại đây khi tham gia lớp học qua tài khoản hoặc mã mời."}
              </p>
            </div>
          ) : (
            <div className={styles.tableWrap}>
              <table className={styles.dataTable}>
                <thead>
                  <tr>
                    <th scope="col" style={{ width: "45px" }}>#</th>
                    <th scope="col">Học sinh</th>
                    <th scope="col">Email đăng nhập</th>
                    <th scope="col">Khối lớp</th>
                    <th scope="col">Trạng thái</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredStudents.map((student, idx) => {
                    const initials = student.full_name
                      .split(" ")
                      .filter(Boolean)
                      .slice(-2)
                      .map((w) => w[0]?.toUpperCase())
                      .join("") || "HS";

                    return (
                      <tr key={student.student_id}>
                        <td className={styles.tdIndex}>{idx + 1}</td>
                        <td>
                          <div className={styles.studentNameCol}>
                            <div className={styles.studentAvatar} aria-hidden="true">
                              {initials}
                            </div>
                            <div className={styles.studentMetaText}>
                              <strong className={styles.studentFullName}>
                                {student.full_name}
                              </strong>
                              <span className={styles.studentRoleHint}>Học sinh chính thức</span>
                            </div>
                          </div>
                        </td>
                        <td className={styles.tdEmail}>{student.email}</td>
                        <td>
                          <span className={styles.gradeBadgePill}>
                            Khối {selectedClass.grade_level}
                          </span>
                        </td>
                        <td>
                          {student.status === "ACTIVE" ? (
                            <span className={styles.statusPillActive}>
                              <span className={styles.pillDotActive} />
                              Đang học
                            </span>
                          ) : (
                            <span className={styles.statusPillInactive}>
                              <span className={styles.pillDotInactive} />
                              {student.status}
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
