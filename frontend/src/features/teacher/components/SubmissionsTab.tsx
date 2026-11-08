"use client";

import { useState } from "react";
import { ClipboardList, Calendar, CheckCircle2, Clock, HelpCircle, FileCheck2, User, AlertCircle, Eye, Sparkles, Layers } from "lucide-react";
import type { TeacherAssignment, TeacherClassroom, TeacherRoster } from "../api";
import { TeacherSubmissionReviewModal } from "./TeacherSubmissionReviewModal";
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
  onRefreshRoster?: () => void;
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
  onRefreshRoster,
}: SubmissionsTabProps) {
  const [reviewingStudent, setReviewingStudent] = useState<{ id: string; name: string } | null>(null);
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
    const s10 = score <= 1.0 ? score * 10 : score;
    if (s10 >= 8) return styles.scoreBadgeHigh;
    if (s10 >= 5) return styles.scoreBadgeMid;
    return styles.scoreBadgeLow;
  };

  const formatScore = (score: number | null) => {
    if (score === null) return "Chưa chấm";
    const s10 = score <= 1.0 ? score * 10 : score;
    return `${Number(s10.toFixed(1))}/10`;
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
                Bài giao &amp; Chấm bài
              </h3>
              <span className={styles.studentTotalPill}>{assignments.length} đợt giao</span>
            </div>
            <p className={styles.sectionSubheading}>
              {selectedClass.name} · Chọn bài giao để xem bài nộp và duyệt điểm.
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
                        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelectAssignment(item.id); }
                      }}
                    >
                      <div className={styles.assignmentCardTop}>
                        <span className={styles.assignmentStatusPill}>{({ DRAFT: "Bản nháp", PUBLISHED: "Đang giao", CLOSED: "Đã đóng", SUBMITTED: "Đã nộp", GRADED: "Đã chấm" } as Record<string, string>)[item.status] ?? item.status}</span>
                        {item.delivery_mode && (
                          <span
                            className={
                              item.delivery_mode === "EXAM"
                                ? styles.modeTagPurpleSmall
                                : styles.modeTagGreenSmall
                            }
                          >
                            {item.delivery_mode === "EXAM" ? "Đề Thi" : "Luyện tập"}
                          </span>
                        )}
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
                    <div className={`${styles.tableWrap} ${styles.mobileRoster}`} role="region" aria-label="Danh sách bài nộp của học sinh" tabIndex={0}>
                      <table className={styles.dataTable}>
                        <thead>
                          <tr>
                            <th scope="col" style={{ width: "45px" }}>#</th>
                            <th scope="col">Học sinh</th>
                            <th scope="col">Trạng thái</th>
                            <th scope="col">Điểm số</th>
                            <th scope="col">Thời điểm nộp</th>
                            <th scope="col" style={{ textAlign: "right", width: "160px" }}>Thao tác</th>
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
                                  {student.status === "SUBMITTED" ? "Chờ GV duyệt" : student.status === "GRADED" ? "Đã duyệt" : student.status}
                                </span>
                              </td>
                              <td>
                                {student.score !== null ? (
                                  <span className={`${styles.scoreBadge} ${getScoreBadgeClass(student.score)}`}>
                                    {formatScore(student.score)}
                                  </span>
                                ) : student.provisional_score !== null && student.provisional_score !== undefined ? (
                                  <span className={`${styles.scoreBadge} ${styles.scoreBadgeMid}`} title="Điểm AI sơ bộ từ các bước giải">
                                    AI: {formatScore(student.provisional_score)}
                                  </span>
                                ) : (
                                  <span className={`${styles.scoreBadge} ${styles.scoreBadgeUnscored}`}>
                                    Chưa chấm
                                  </span>
                                )}
                              </td>
                              <td className={styles.tdDate}>
                                {formatDate(student.submitted_at)}
                              </td>
                              <td className={styles.tdActionRight}>
                                {student.status === "SUBMITTED" || student.status === "GRADED" ? (
                                  <button
                                    type="button"
                                    className={styles.btnSecondarySmall}
                                    onClick={() =>
                                      setReviewingStudent({
                                        id: student.student_id,
                                        name: student.student_name,
                                      })
                                    }
                                  >
                                    <Eye size={13} /> Xem &amp; Duyệt bài
                                  </button>
                                ) : (
                                  <span className={styles.tagPillMuted}>Chưa nộp</span>
                                )}
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
            Điểm AI là gợi ý sơ bộ. Mở bài làm để đối chiếu và xác nhận điểm của học sinh.
          </span>
        </div>
      </div>

      <TeacherSubmissionReviewModal
        isOpen={Boolean(reviewingStudent)}
        onClose={() => setReviewingStudent(null)}
        assignmentId={assignmentId}
        studentId={reviewingStudent?.id || ""}
        studentName={reviewingStudent?.name}
        onUpdated={() => {
          onRefreshRoster?.();
        }}
      />
    </div>
  );
}
