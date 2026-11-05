"use client";

import { ClipboardList, Calendar, CheckCircle2, Clock, HelpCircle, FileCheck2, User, AlertCircle } from "lucide-react";
import type { TeacherAssignment, TeacherClassroom, TeacherRoster } from "../api";
import styles from "../TeacherDashboard.module.css";

export interface SubmissionsTabProps {
  selectedClass?: TeacherClassroom;
  assignments: TeacherAssignment[];
  assignmentId: string;
  onSelectAssignment: (id: string) => void;
  roster: TeacherRoster | null;
  rosterError?: string;
  isLoading: boolean;
  focusedStudent?: { id: string; name: string } | null;
  onClearStudent?: () => void;
}

export function SubmissionsTab({
  selectedClass,
  assignments,
  assignmentId,
  onSelectAssignment,
  roster,
  rosterError,
  isLoading,
  focusedStudent,
  onClearStudent,
}: SubmissionsTabProps) {
  const visibleRoster = roster?.roster.filter((student) => !focusedStudent || student.student_id === focusedStudent.id) ?? [];
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "Không có hạn";
    try {
      return new Intl.DateTimeFormat("vi-VN", {
        dateStyle: "short",
        timeStyle: "short",
      }).format(new Date(dateStr));
    } catch {
      return dateStr;
    }
  };

  const getScoreBadgeClass = (score: number | null) => {
    if (score === null) return styles.scoreBadgeUnscored;
    if (score >= 8) return styles.scoreBadgeHigh;
    if (score >= 5) return styles.scoreBadgeMid;
    return styles.scoreBadgeLow;
  };

  if (!selectedClass) {
    return (
      <div className={styles.sectionCard}>
        <div className={styles.emptyCard}>
          <AlertCircle size={32} className={styles.emptyIcon} aria-hidden="true" />
          <h4 className={styles.emptyTitle}>Chưa chọn lớp học</h4>
          <p className={styles.emptyDesc}>Vui lòng chọn một lớp học để theo dõi danh sách bài giao và tiến độ nộp bài.</p>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.tabContentWrap}>
      <div className={styles.sectionCard}>
        <div className={styles.sectionCardHeader}>
          <div>
            <div className={styles.badgeCluster}>
              <h3 className={styles.sectionHeading}>
                Bài giao &amp; Tiến độ nộp bài · {selectedClass.name}
              </h3>
              <span className={styles.studentTotalPill}>{assignments.length} đợt giao</span>
            </div>
            <p className={styles.sectionSubheading}>
              Chọn bài tập bên dưới để kiểm tra danh sách học sinh đã nộp, trạng thái và điểm số
            </p>
          </div>
        </div>

        {focusedStudent && <div className={styles.tableToolbar} role="status"><span>Đang xem bài của <strong>{focusedStudent.name}</strong></span><button type="button" className={styles.btnSecondary} onClick={onClearStudent}>Xem cả lớp</button></div>}

        {isLoading ? (
          <div className={styles.tableLoadingState}>
            <div className={styles.spinner} aria-hidden="true" />
            <p>Đang tải danh sách bài giao...</p>
          </div>
        ) : assignments.length === 0 ? (
          <div className={styles.emptyCard}>
            <ClipboardList size={36} className={styles.emptyIcon} aria-hidden="true" />
            <h4 className={styles.emptyTitle}>Lớp học chưa có bài giao nào</h4>
            <p className={styles.emptyDesc}>
              Hiện tại chưa có đợt giao bài tập nào được tạo cho lớp {selectedClass.name}.
            </p>
          </div>
        ) : (
          <div className={styles.assignmentsSplitLayout}>
            {/* Left: Danh sách bài tập */}
            <div className={styles.assignmentsListPane}>
              <h4 className={styles.paneSubHeading}>Các bài tập trong lớp</h4>
              <div className={styles.assignmentCardsList}>
                {assignments.map((item) => {
                  const isSelected = item.id === assignmentId;
                  return (
                    <div
                      key={item.id}
                      className={`${styles.assignmentCard} ${isSelected ? styles.assignmentCardActive : ""}`}
                      onClick={() => onSelectAssignment(item.id)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") onSelectAssignment(item.id);
                      }}
                    >
                      <div className={styles.assignmentCardTop}>
                        <span className={styles.assignmentStatusPill}>{item.status}</span>
                        <span className={styles.assignmentQuestionsCount}>
                          {item.question_count} câu hỏi
                        </span>
                      </div>

                      <h4 className={styles.assignmentTitle}>{item.title}</h4>

                      <div className={styles.assignmentDueDate}>
                        <Clock size={13} aria-hidden="true" />
                        <span>Hạn nộp: {formatDate(item.due_at)}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Right: Chi tiết Roster nộp bài */}
            <div className={styles.rosterDetailPane}>
              {!assignmentId ? (
                <div className={styles.emptyDetailPrompt}>
                  <ClipboardList size={32} className={styles.emptyIcon} aria-hidden="true" />
                  <h4>Chọn một bài tập từ cột bên trái</h4>
                  <p>Hệ thống sẽ hiển thị danh sách học sinh, tình trạng làm bài và điểm số chi tiết.</p>
                </div>
              ) : rosterError ? (
                <div className={styles.formAlert} role="alert">
                  {rosterError}
                </div>
              ) : roster ? (
                <div className={styles.rosterCardContent}>
                  <div className={styles.rosterHeader}>
                    <div>
                      <h4 className={styles.rosterTitle}>{roster.title}</h4>
                      <p className={styles.rosterMeta}>
                        Tổng số học sinh: <strong>{roster.total_students}</strong>
                      </p>
                    </div>

                    <div className={styles.rosterStatsRow}>
                      <div className={styles.rosterStatChip}>
                        <CheckCircle2 size={15} className={styles.textVerdant} aria-hidden="true" />
                        <span>Đã nộp: <strong>{roster.submitted_count}</strong></span>
                      </div>
                      <div className={styles.rosterStatChip}>
                        <FileCheck2 size={15} className={styles.textSky} aria-hidden="true" />
                        <span>Đã chấm: <strong>{roster.graded_count}</strong></span>
                      </div>
                    </div>
                  </div>

                  {visibleRoster.length === 0 ? (
                    <div className={styles.emptyCard}>
                      <User size={28} className={styles.emptyIcon} aria-hidden="true" />
                      <p className={styles.emptyDesc}>{focusedStudent ? "Chưa có bài làm của học sinh này trong bài tập đã chọn." : "Chưa có học sinh nào nộp bài tập này."}</p>
                    </div>
                  ) : (
                    <div className={styles.tableWrap}>
                      <table className={styles.dataTable}>
                        <thead>
                          <tr>
                            <th scope="col" style={{ width: "45px" }}>#</th>
                            <th scope="col">Học sinh</th>
                            <th scope="col">Trạng thái</th>
                            <th scope="col">Điểm số</th>
                            <th scope="col">Thời điểm nộp</th>
                          </tr>
                        </thead>
                        <tbody>
                          {visibleRoster.map((student, idx) => (
                            <tr key={student.student_id}>
                              <td className={styles.tdIndex}>{idx + 1}</td>
                              <td>
                                <strong className={styles.studentFullName}>
                                  {student.student_name}
                                </strong>
                              </td>
                              <td>
                                <span className={student.status === "SUBMITTED" ? styles.statusPillActive : styles.statusPillInactive}>
                                  {student.status === "SUBMITTED" ? "Đã nộp" : student.status}
                                </span>
                              </td>
                              <td>
                                <span className={`${styles.scoreBadge} ${getScoreBadgeClass(student.score)}`}>
                                  {student.score !== null ? `${Number(student.score.toFixed(2))}/10` : "Chưa chấm"}
                                </span>
                              </td>
                              <td className={styles.tdDate}>
                                {formatDate(student.submitted_at)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              ) : (
                <div className={styles.tableLoadingState}>
                  <div className={styles.spinner} aria-hidden="true" />
                  <p>Đang tải thông tin nộp bài của học sinh...</p>
                </div>
              )}
            </div>
          </div>
        )}

        <div className={styles.pedagogicalNotice}>
          <HelpCircle size={16} aria-hidden="true" />
          <span>
            Hệ thống chấm điểm của EduMS bảo toàn 100% dữ liệu thực từ giáo viên và bộ quy tắc toán học, không suy diễn điểm ảo khi học sinh chưa nộp bài.
          </span>
        </div>
      </div>
    </div>
  );
}
