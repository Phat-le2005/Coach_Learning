"use client";

import { Users, Award, ClipboardList, AlertTriangle, ArrowRight, Sparkles, Plus, UploadCloud, BookOpen } from "lucide-react";
import type { TeacherAnalytics, TeacherClassroom, TeacherStudent, TeacherAssignment } from "../api";
import styles from "../TeacherDashboard.module.css";

export interface TeacherCockpitBannerProps {
  teacherName: string;
  selectedClass?: TeacherClassroom;
  students: TeacherStudent[];
  assignments: TeacherAssignment[];
  analytics: TeacherAnalytics | null;
  onOpenCreateClass: () => void;
  onOpenUpload: () => void;
  onSelectTab: (tab: "classes" | "materials" | "theory" | "submissions" | "analytics") => void;
}

export function TeacherCockpitBanner({
  teacherName,
  selectedClass,
  students,
  assignments,
  analytics,
  onOpenCreateClass,
  onOpenUpload,
  onSelectTab,
}: TeacherCockpitBannerProps) {
  const activeStudents = students.filter((s) => s.status === "ACTIVE").length;
  const totalStudents = students.length;

  const subjectProgress = analytics?.subject_progress[0];
  const avgMasteryPercent = subjectProgress?.average_mastery !== undefined
    ? Math.round(subjectProgress.average_mastery * 100)
    : undefined;

  const attentionCount = analytics?.students_needing_attention.length ?? 0;
  const submissionsCount = analytics?.assignment_completion.submitted_count ?? 0;

  return (
    <div className={styles.cockpitBanner}>
      {/* Welcome Banner */}
      <div className={styles.cockpitWelcome}>
        <div className={styles.cockpitIntro}>
          <div className={styles.cockpitTag}>
            <Sparkles size={13} aria-hidden="true" />
            Không gian Cố vấn Giảng dạy
          </div>
          <h2 className={styles.cockpitGreeting}>
            Chào Thầy/Cô {teacherName}!
          </h2>
          <p className={styles.cockpitClassMeta}>
            {selectedClass ? (
              <>
                Đang quản lý <strong>{selectedClass.name}</strong> · Khối {selectedClass.grade_level} · Năm học {selectedClass.academic_year}
              </>
            ) : (
              "Chọn hoặc tạo một lớp học để bắt đầu theo dõi sức khỏe học tập của học sinh."
            )}
          </p>
        </div>

        <div className={styles.cockpitActions}>
          <button
            type="button"
            className={styles.bannerActionBtn}
            onClick={onOpenCreateClass}
          >
            <Plus size={15} aria-hidden="true" />
            Tạo lớp mới
          </button>

          {selectedClass && (
            <button
              type="button"
              className={styles.bannerActionBtn}
              onClick={onOpenUpload}
            >
              <UploadCloud size={15} aria-hidden="true" />
              Tải tài liệu lớp
            </button>
          )}

          <button
            type="button"
            className={styles.bannerTheoryBtn}
            onClick={() => onSelectTab("theory")}
          >
            <BookOpen size={15} aria-hidden="true" />
            Kho lý thuyết lớp học
            <ArrowRight size={14} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* KPI Overview Cards */}
      <div className={styles.kpiGrid}>
        {/* KPI 1: Sĩ số lớp */}
        <div
          className={`${styles.kpiCard} ${styles.kpiCardClickable}`}
          onClick={() => onSelectTab("classes")}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onSelectTab("classes");
          }}
        >
          <div className={`${styles.kpiIconWrap} ${styles.kpiIconEmerald}`}>
            <Users size={24} aria-hidden="true" />
          </div>
          <div className={styles.kpiMeta}>
            <span className={styles.kpiLabel}>Sĩ số lớp</span>
            <div className={styles.kpiValueRow}>
              <strong className={styles.kpiValue}>{totalStudents}</strong>
              <span className={styles.kpiUnit}>học sinh</span>
            </div>
            <span className={styles.kpiSub}>
              {activeStudents} đang hoạt động · {totalStudents - activeStudents} tạm dừng
            </span>
          </div>
        </div>

        {/* KPI 2: Độ vững kiến thức */}
        <div
          className={`${styles.kpiCard} ${styles.kpiCardClickable}`}
          onClick={() => onSelectTab("analytics")}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onSelectTab("analytics");
          }}
        >
          <div className={`${styles.kpiIconWrap} ${styles.kpiIconMint}`}>
            <Award size={24} aria-hidden="true" />
          </div>
          <div className={styles.kpiMeta}>
            <span className={styles.kpiLabel}>Độ vững môn học</span>
            <div className={styles.kpiValueRow}>
              <strong className={styles.kpiValue}>
                {avgMasteryPercent !== undefined ? `${avgMasteryPercent}%` : "—"}
              </strong>
              <span className={styles.kpiUnit}>trung bình</span>
            </div>
            {avgMasteryPercent !== undefined ? (
              <div className={styles.kpiMiniProgress}>
                <div
                  className={styles.kpiMiniBar}
                  style={{ width: `${Math.max(6, avgMasteryPercent)}%` }}
                />
              </div>
            ) : (
              <span className={styles.kpiSub}>Chưa đủ dữ liệu bài làm</span>
            )}
          </div>
        </div>

        {/* KPI 3: Bài tập & Nộp bài */}
        <div
          className={`${styles.kpiCard} ${styles.kpiCardClickable}`}
          onClick={() => onSelectTab("submissions")}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onSelectTab("submissions");
          }}
        >
          <div className={`${styles.kpiIconWrap} ${styles.kpiIconSky}`}>
            <ClipboardList size={24} aria-hidden="true" />
          </div>
          <div className={styles.kpiMeta}>
            <span className={styles.kpiLabel}>Bài tập đã giao</span>
            <div className={styles.kpiValueRow}>
              <strong className={styles.kpiValue}>{assignments.length}</strong>
              <span className={styles.kpiUnit}>đợt giao</span>
            </div>
            <span className={styles.kpiSub}>
              {submissionsCount} lượt nộp từ học sinh
            </span>
          </div>
        </div>

        {/* KPI 4: Học sinh cần chú ý */}
        <div
          className={`${styles.kpiCard} ${styles.kpiCardClickable} ${attentionCount > 0 ? styles.kpiCardAlert : ""}`}
          onClick={() => onSelectTab("analytics")}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") onSelectTab("analytics");
          }}
        >
          <div className={`${styles.kpiIconWrap} ${attentionCount > 0 ? styles.kpiIconAmber : styles.kpiIconMuted}`}>
            <AlertTriangle size={24} aria-hidden="true" />
          </div>
          <div className={styles.kpiMeta}>
            <span className={styles.kpiLabel}>Cần đồng hành</span>
            <div className={styles.kpiValueRow}>
              <strong className={styles.kpiValue}>{attentionCount}</strong>
              <span className={styles.kpiUnit}>em cần lưu ý</span>
            </div>
            <span className={styles.kpiSub}>
              {attentionCount > 0 ? "Bấm để xem danh sách cảnh báo" : "Không có cảnh báo ngắt quãng"}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
