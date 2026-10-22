"use client";

import React, { useState } from "react";
import {
  Users,
  GraduationCap,
  UserPlus,
  Search,
  ExternalLink,
  Award,
  AlertCircle,
  Clock,
} from "lucide-react";
import type { ClassroomOverview, ClassroomStudentInfo } from "../types";
import styles from "../TeacherDashboard.module.css";

interface ClassroomTabProps {
  classroom: ClassroomOverview;
  students: ClassroomStudentInfo[];
  onViewStudentWorkspace: (studentId: string) => void;
}

export function ClassroomTab({
  classroom,
  students,
  onViewStudentWorkspace,
}: ClassroomTabProps) {
  const [searchQuery, setSearchQuery] = useState("");

  const filteredStudents = students.filter((s) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return s.name.toLowerCase().includes(q) || s.email.toLowerCase().includes(q);
  });

  return (
    <div>
      {/* View Header */}
      <div className={styles.viewHeader}>
        <div className={styles.viewTitleGroup}>
          <h2 className={styles.viewTitle}>{classroom.name}</h2>
          <span className={styles.viewSubtitle}>
            Niên khóa {classroom.academicYear} • Khối {classroom.gradeLevel} • Tổng số {classroom.totalStudents} học sinh
          </span>
        </div>

        <div className={styles.viewActions}>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={() => alert("Mở form thêm học sinh mới vào lớp.")}
          >
            <UserPlus size={16} />
            Thêm học sinh
          </button>
        </div>
      </div>

      {/* Classroom Stats Row */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={`${styles.statIconWrap} ${styles.statIconVerdant}`}>
            <Users size={22} />
          </div>
          <div className={styles.statMeta}>
            <span className={styles.statLabel}>Sĩ số hiện diện</span>
            <span className={styles.statValue}>
              {classroom.activeStudents}/{classroom.totalStudents}
            </span>
            <span className={styles.statNote}>35 học sinh hoạt động tuần này</span>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={`${styles.statIconWrap} ${styles.statIconSky}`}>
            <Award size={22} />
          </div>
          <div className={styles.statMeta}>
            <span className={styles.statLabel}>Mức độ làm chủ (Mastery)</span>
            <span className={styles.statValue}>{classroom.averageMastery}%</span>
            <span className={styles.statNote}>Khảo sát hàm số & Đạo hàm</span>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={`${styles.statIconWrap} ${styles.statIconAmber}`}>
            <Clock size={22} />
          </div>
          <div className={styles.statMeta}>
            <span className={styles.statLabel}>Tỷ lệ nộp bài thực hành</span>
            <span className={styles.statValue}>{classroom.assignmentCompletionRate}%</span>
            <span className={styles.statNote}>14/16 bài tập hoàn thành</span>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={`${styles.statIconWrap} ${styles.statIconCoral}`}>
            <AlertCircle size={22} />
          </div>
          <div className={styles.statMeta}>
            <span className={styles.statLabel}>Cần trợ giúp</span>
            <span className={styles.statValue}>{classroom.needsAttentionCount}</span>
            <span className={styles.statNote}>Có lỗ hổng tiệm cận / cực trị</span>
          </div>
        </div>
      </div>

      {/* Search Input */}
      <div style={{ marginBottom: "1rem", position: "relative", maxWidth: "360px" }}>
        <input
          type="text"
          className={styles.formInput}
          style={{ paddingLeft: "2.25rem" }}
          placeholder="Tìm tên hoặc email học sinh..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        <Search
          size={16}
          style={{ position: "absolute", left: "0.75rem", top: "50%", transform: "translateY(-50%)", color: "var(--text-tertiary)" }}
        />
      </div>

      {/* Students Table */}
      <div className={styles.tableCard}>
        <table className={styles.table}>
          <thead>
            <tr>
              <th className={styles.th}>Học sinh</th>
              <th className={styles.th}>Trạng thái</th>
              <th className={styles.th}>Năng lực (Mastery)</th>
              <th className={styles.th}>Bài tập hoàn thành</th>
              <th className={styles.th}>Hoạt động gần nhất</th>
              <th className={styles.th} style={{ textAlign: "right" }}>Thao tác</th>
            </tr>
          </thead>
          <tbody>
            {filteredStudents.map((st) => (
              <tr key={st.id} className={styles.tr}>
                <td className={styles.td}>
                  <div className={styles.studentCell}>
                    <div className={styles.studentAvatar}>{st.avatarSeed}</div>
                    <div className={styles.studentNameGroup}>
                      <span className={styles.studentName}>{st.name}</span>
                      <span className={styles.studentEmail}>{st.email}</span>
                    </div>
                  </div>
                </td>
                <td className={styles.td}>
                  <span
                    className={`${styles.statusPill} ${
                      st.status === "ACTIVE" ? styles.statusPillActive : styles.statusPillInactive
                    }`}
                  >
                    {st.status === "ACTIVE" ? "Đang học" : "Tạm nghỉ"}
                  </span>
                </td>
                <td className={styles.td}>
                  <div>
                    <span style={{ fontWeight: 700, fontSize: "0.85rem", color: st.overallMastery >= 75 ? "var(--verdant-800)" : st.overallMastery >= 60 ? "#b45309" : "#be123c" }}>
                      {st.overallMastery}%
                    </span>
                    <div className={styles.masteryBarWrap}>
                      <div
                        className={styles.masteryBarFill}
                        style={{
                          width: `${st.overallMastery}%`,
                          backgroundColor:
                            st.overallMastery >= 75
                              ? "var(--leaf-mid)"
                              : st.overallMastery >= 60
                              ? "#f59e0b"
                              : "#ef4444",
                        }}
                      />
                    </div>
                  </div>
                </td>
                <td className={styles.td}>
                  <span style={{ fontWeight: 600 }}>{st.completedAssignments}</span>
                  <span style={{ color: "var(--text-tertiary)", fontSize: "0.8rem" }}>
                    /{st.totalAssignments}
                  </span>
                </td>
                <td className={styles.td}>
                  <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                    {st.latestActivityAt}
                  </span>
                </td>
                <td className={styles.td} style={{ textAlign: "right" }}>
                  <button
                    type="button"
                    className={styles.cardActionBtn}
                    onClick={() => onViewStudentWorkspace(st.id)}
                    title="Xem chi tiết trang làm bài và nét vẽ của học sinh này"
                  >
                    <ExternalLink size={13} style={{ marginRight: "3px", verticalAlign: "middle" }} />
                    Xem bài làm
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
