"use client";

import React from "react";
import {
  BarChart3,
  TrendingUp,
  AlertTriangle,
  CheckCircle,
  HelpCircle,
  ArrowRight,
  Sparkles,
  Users,
} from "lucide-react";
import type { CompetencyTopicMetric, ClassroomStudentInfo } from "../types";
import styles from "../TeacherDashboard.module.css";

interface CompetencyTabProps {
  metrics: CompetencyTopicMetric[];
  students: ClassroomStudentInfo[];
  onSelectStudentForWorkspace: (studentId: string) => void;
}

export function CompetencyTab({
  metrics,
  students,
  onSelectStudentForWorkspace,
}: CompetencyTabProps) {
  const strongCount = metrics.filter((m) => m.status === "STRONG").length;
  const weakCount = metrics.filter((m) => m.status === "WEAK").length;

  const strugglingStudents = students.filter((s) => s.overallMastery < 65 || s.weakTopics.length > 0);

  return (
    <div>
      {/* View Header */}
      <div className={styles.viewHeader}>
        <div className={styles.viewTitleGroup}>
          <h2 className={styles.viewTitle}>Báo cáo & Thống kê năng lực học sinh</h2>
          <span className={styles.viewSubtitle}>
            Phân tích tỷ lệ làm chủ theo dạng toán, lỗ hổng nhận thức và danh sách học sinh cần bồi dưỡng
          </span>
        </div>

        <div className={styles.viewActions}>
          <button
            type="button"
            className={styles.btnSecondary}
            onClick={() => alert("Xuất báo cáo PDF bảng thống kê năng lực lớp 12A.")}
          >
            Xuất báo cáo PDF
          </button>
        </div>
      </div>

      {/* Overview Metric Cards */}
      <div className={styles.statsRow}>
        <div className={styles.statCard}>
          <div className={`${styles.statIconWrap} ${styles.statIconVerdant}`}>
            <TrendingUp size={22} />
          </div>
          <div className={styles.statMeta}>
            <span className={styles.statLabel}>Chỉ số làm chủ trung bình</span>
            <span className={styles.statValue}>74%</span>
            <span className={styles.statNote}>+6% so với tháng trước</span>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={`${styles.statIconWrap} ${styles.statIconSky}`}>
            <CheckCircle size={22} />
          </div>
          <div className={styles.statMeta}>
            <span className={styles.statLabel}>Dạng toán đã làm chủ vững</span>
            <span className={styles.statValue}>{strongCount} dạng</span>
            <span className={styles.statNote}>Đạt chuẩn &gt; 75% học sinh đúng</span>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={`${styles.statIconWrap} ${styles.statIconCoral}`}>
            <AlertTriangle size={22} />
          </div>
          <div className={styles.statMeta}>
            <span className={styles.statLabel}>Dạng bài có lỗ hổng lớn</span>
            <span className={styles.statValue}>{weakCount} dạng</span>
            <span className={styles.statNote}>Tiệm cận xiên & Toán thực tế</span>
          </div>
        </div>

        <div className={styles.statCard}>
          <div className={`${styles.statIconWrap} ${styles.statIconAmber}`}>
            <Users size={22} />
          </div>
          <div className={styles.statMeta}>
            <span className={styles.statLabel}>Học sinh cần kèm cặp</span>
            <span className={styles.statValue}>{strugglingStudents.length} em</span>
            <span className={styles.statNote}>Dưới 65% hoặc sai bước cơ bản</span>
          </div>
        </div>
      </div>

      <div className={styles.competencyGrid}>
        {/* Left Column: Topic Mastery Bars */}
        <div className={styles.topicListCard}>
          <h3 style={{ fontSize: "1.05rem", fontWeight: 700, margin: "0 0 1rem", color: "var(--text-primary)" }}>
            Mức độ làm chủ theo từng dạng toán (Curriculum Topics)
          </h3>

          <div>
            {metrics.map((t) => {
              const fillColor =
                t.status === "STRONG"
                  ? "var(--leaf-mid)"
                  : t.status === "AVERAGE"
                  ? "#f59e0b"
                  : "#ef4444";

              const textColor =
                t.status === "STRONG"
                  ? "var(--verdant-800)"
                  : t.status === "AVERAGE"
                  ? "#b45309"
                  : "#991b1b";

              return (
                <div key={t.code} className={styles.topicItem}>
                  <div className={styles.topicHeader}>
                    <span className={styles.topicName}>{t.name}</span>
                    <span className={styles.topicScore} style={{ color: textColor }}>
                      {t.masteryPercent}% ({t.studentCountPassed}/{t.studentCountTotal} em đạt)
                    </span>
                  </div>

                  <div className={styles.topicProgressTrack}>
                    <div
                      className={styles.topicProgressFill}
                      style={{
                        width: `${t.masteryPercent}%`,
                        backgroundColor: fillColor,
                      }}
                    />
                  </div>

                  {t.commonMisconception && (
                    <div className={styles.topicMisconception}>
                      <AlertTriangle size={13} style={{ flexShrink: 0 }} />
                      <span>Lỗi ngộ nhận phổ biến: {t.commonMisconception}</span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Column: Students Needing Attention */}
        <div>
          <div className={styles.topicListCard} style={{ marginBottom: "1.25rem" }}>
            <h3 style={{ fontSize: "1.05rem", fontWeight: 700, margin: "0 0 0.85rem", color: "var(--text-primary)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <AlertTriangle size={18} style={{ color: "#ef4444" }} />
              Học sinh cần chú ý hỗ trợ
            </h3>

            <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: "0 0 1rem" }}>
              Hệ thống AI phát hiện các em này đang gặp vướng mắc hoặc có tỷ lệ làm bài chưa đạt chuẩn:
            </p>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {strugglingStudents.map((st) => (
                <div
                  key={st.id}
                  style={{
                    padding: "0.75rem",
                    borderRadius: "10px",
                    background: "var(--surface-muted)",
                    border: "1px solid var(--border-soft)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.25rem" }}>
                    <span style={{ fontWeight: 700, fontSize: "0.9rem" }}>{st.name}</span>
                    <span style={{ fontWeight: 700, fontSize: "0.85rem", color: "#b45309" }}>
                      {st.overallMastery}%
                    </span>
                  </div>

                  <div style={{ fontSize: "0.76rem", color: "var(--text-secondary)", marginBottom: "0.5rem" }}>
                    Chủ đề yếu: {st.weakTopics.length > 0 ? st.weakTopics.join(", ") : "Cần hoàn thành thêm bài thực hành"}
                  </div>

                  <button
                    type="button"
                    className={styles.cardActionBtn}
                    style={{ width: "100%", textAlign: "center" }}
                    onClick={() => onSelectStudentForWorkspace(st.id)}
                  >
                    Xem bài làm & Hướng dẫn em này →
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* AI Pedagogical Suggestion Card */}
          <div
            style={{
              padding: "1.25rem",
              background: "linear-gradient(135deg, var(--mint-100), var(--surface-sky-mist))",
              borderRadius: "14px",
              border: "1px solid var(--mint-300)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontWeight: 700, fontSize: "0.9rem", color: "var(--verdant-900)", marginBottom: "0.4rem" }}>
              <Sparkles size={16} />
              Gợi ý sư phạm từ EduMS AI
            </div>
            <p style={{ fontSize: "0.8rem", color: "var(--text-primary)", lineHeight: 1.5, margin: 0 }}>
              Nên dành 15 phút đầu buổi tới để củng cố dạng bài <strong>Đường tiệm cận đứng và tiệm cận xiên</strong>. Có 17 học sinh đang nhầm lẫn điều kiện nghiệm mẫu trùng với tử số khi khảo sát đồ thị phân thức bậc nhất trên bậc nhất.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
