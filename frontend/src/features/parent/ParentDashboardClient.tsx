"use client";

import { useEffect, useState } from "react";
import {
  UsersRound,
  RefreshCw,
  ChevronDown,
  Sparkles,
  Clock,
  CheckCircle2,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Minus,
  BookOpen,
  Calendar,
  Award,
  HeartHandshake,
  ShieldCheck,
  Target,
  AlertCircle,
} from "lucide-react";
import { AccountMenu } from "@/components/auth/AccountMenu";
import { AppFooter } from "@/components/app-shell/AppFooter";
import styles from "@/features/teacher/TeacherDashboard.module.css";
import {
  parentApi,
  ParentApiError,
  type ParentStudentProgress,
  type ParentStudentSummary,
  type ParentWeeklyAISummary,
  type ParentWeeklyData,
} from "./api";

export type ParentTabKey = "overview" | "curriculum" | "weekly" | "ai-companion";

const getErrorMessage = (error: unknown) =>
  error instanceof ParentApiError ? error.message : "Không thể tải dữ liệu từ máy chủ backend.";

function formatRelationship(rel: string): string {
  switch (rel.toUpperCase()) {
    case "MOTHER":
      return "Mẹ";
    case "FATHER":
      return "Bố";
    case "GUARDIAN":
      return "Người giám hộ";
    default:
      return rel;
  }
}

function formatTrendLabel(trend: string): { label: string; color: string; bg: string } {
  switch (trend.toUpperCase()) {
    case "IMPROVING":
      return { label: "Tiến bộ tích cực", color: "#165944", bg: "rgba(139, 229, 194, 0.35)" };
    case "NEEDS_ATTENTION":
      return { label: "Cần đồng hành", color: "#991b1b", bg: "#fee2e2" };
    default:
      return { label: "Ổn định", color: "#0369a1", bg: "rgba(92, 169, 214, 0.2)" };
  }
}

export function ParentDashboardClient({
  parentName,
  parentEmail,
  initialTab = "overview",
}: {
  parentName: string;
  parentEmail: string;
  initialTab?: ParentTabKey;
}) {
  const [tab, setTab] = useState<ParentTabKey>(initialTab);
  const [students, setStudents] = useState<ParentStudentSummary[]>([]);
  const [selectedStudentId, setSelectedStudentId] = useState<string>("");
  const [initialLoading, setInitialLoading] = useState(true);
  const [initialError, setInitialError] = useState("");
  const [reloadCount, setReloadCount] = useState(0);

  // Selected student detail states
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [progress, setProgress] = useState<ParentStudentProgress | null>(null);
  const [weeklyData, setWeeklyData] = useState<ParentWeeklyData | null>(null);
  const [targetDate, setTargetDate] = useState<string>("");

  // AI Summary states
  const [aiSummary, setAiSummary] = useState<ParentWeeklyAISummary | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");

  useEffect(() => {
    if (initialTab) setTab(initialTab);
  }, [initialTab]);

  const handleSelectTab = (nextTab: ParentTabKey) => {
    setTab(nextTab);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", nextTab);
      window.history.replaceState({}, "", url.toString());
    }
  };

  // 1. Load linked students
  useEffect(() => {
    let active = true;
    setInitialLoading(true);
    setInitialError("");

    parentApi
      .students()
      .then((list) => {
        if (!active) return;
        setStudents(list);
        setSelectedStudentId((current) =>
          list.some((s) => s.student_id === current) ? current : list[0]?.student_id ?? ""
        );
      })
      .catch((err) => {
        if (active) setInitialError(getErrorMessage(err));
      })
      .finally(() => {
        if (active) setInitialLoading(false);
      });

    return () => {
      active = false;
    };
  }, [reloadCount]);

  // 2. Load progress & weekly data when student or targetDate changes
  useEffect(() => {
    if (!selectedStudentId) {
      setProgress(null);
      setWeeklyData(null);
      setAiSummary(null);
      return;
    }

    let active = true;
    setDetailLoading(true);
    setDetailError("");

    Promise.all([
      parentApi.studentProgress(selectedStudentId),
      parentApi.studentWeeklyData(selectedStudentId, targetDate || undefined),
    ])
      .then(([prog, week]) => {
        if (!active) return;
        setProgress(prog);
        setWeeklyData(week);
      })
      .catch((err) => {
        if (active) setDetailError(getErrorMessage(err));
      })
      .finally(() => {
        if (active) setDetailLoading(false);
      });

    return () => {
      active = false;
    };
  }, [selectedStudentId, targetDate, reloadCount]);

  // Reset AI summary when switching student or week
  useEffect(() => {
    setAiSummary(null);
    setAiError("");
  }, [selectedStudentId, targetDate]);

  const handleGenerateAiSummary = async () => {
    if (!selectedStudentId) return;
    setAiLoading(true);
    setAiError("");
    try {
      const res = await parentApi.generateAiSummary(selectedStudentId, targetDate || undefined);
      setAiSummary(res);
    } catch (err) {
      setAiError(getErrorMessage(err));
    } finally {
      setAiLoading(false);
    }
  };

  const selectedStudent = students.find((s) => s.student_id === selectedStudentId);
  const initials = parentName
    ? parentName
        .split(" ")
        .filter(Boolean)
        .slice(-2)
        .map((w) => w[0]?.toUpperCase())
        .join("")
    : "PH";

  const trendBadge = selectedStudent
    ? formatTrendLabel(progress?.overall_learning_trend ?? selectedStudent.overall_learning_trend)
    : null;

  const avgSubjectMastery =
    progress && progress.subject_progress.length > 0
      ? Math.round(
          (progress.subject_progress.reduce((acc, s) => acc + s.mastery_score, 0) /
            progress.subject_progress.length) *
            100
        )
      : undefined;

  return (
    <div className={styles.dashboard}>
      {/* Sticky Header */}
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.headerTop}>
            <div className={styles.headerLeft}>
              <div className={styles.teacherAvatar} aria-hidden="true">
                {initials}
              </div>
              <div className={styles.teacherInfo}>
                <div className={styles.teacherNameRow}>
                  <h1 className={styles.teacherName}>{parentName}</h1>
                  <span className={styles.roleBadge}>
                    <UsersRound size={13} aria-hidden="true" />
                    Đồng hành Phụ huynh
                  </span>
                </div>
                <p className={styles.teacherSubtitle}>
                  Cổng thông tin Tiến độ Học tập &amp; Khuyến nghị Sư phạm Gia đình EduMS
                </p>
              </div>
            </div>

            <div className={styles.headerRight}>
              {/* Student Selector */}
              <div className={styles.classSelectorCard}>
                <label htmlFor="parent-student-select" className={styles.classSelectorLabel}>
                  Con đang theo dõi:
                </label>
                <div className={styles.classSelectWrap}>
                  <select
                    id="parent-student-select"
                    className={styles.classSelectControl}
                    value={selectedStudentId}
                    onChange={(e) => setSelectedStudentId(e.target.value)}
                    aria-label="Chọn con em liên kết"
                    disabled={students.length === 0}
                  >
                    {students.length === 0 && <option value="">Chưa liên kết học sinh</option>}
                    {students.map((st) => (
                      <option key={st.student_id} value={st.student_id}>
                        {st.student_name} · Lớp {st.grade_level} ({formatRelationship(st.relationship_type)})
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={14} className={styles.selectChevron} aria-hidden="true" />
                </div>
              </div>

              <button
                type="button"
                className={styles.btnSecondary}
                onClick={() => setReloadCount((c) => c + 1)}
                disabled={initialLoading || detailLoading}
                title="Làm mới dữ liệu học tập của con"
              >
                <RefreshCw
                  size={15}
                  className={initialLoading || detailLoading ? styles.spinIcon : ""}
                  aria-hidden="true"
                />
                <span className={styles.hideMobile}>Làm mới</span>
              </button>

              <div className={styles.accountMenuWrap}>
                <AccountMenu fullName={parentName} email={parentEmail} role="PARENT" compact />
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className={styles.mainContent}>
        {(initialError || detailError) && (
          <div className={styles.systemAlertBar} role="alert">
            <AlertCircle size={18} aria-hidden="true" />
            <span>{initialError || detailError}</span>
            <button
              type="button"
              onClick={() => setReloadCount((c) => c + 1)}
              className={styles.alertActionBtn}
            >
              <RefreshCw size={14} /> Thử lại
            </button>
          </div>
        )}

        {/* Cockpit Welcome Banner & KPI Cards */}
        <div className={styles.cockpitBanner}>
          <div className={styles.cockpitWelcome}>
            <div className={styles.cockpitIntro}>
              <div className={styles.cockpitTag}>
                <HeartHandshake size={13} aria-hidden="true" />
                Không gian Đồng hành Gia đình
              </div>
              <h2 className={styles.cockpitGreeting}>Kính chào Phụ huynh {parentName}!</h2>
              <p className={styles.cockpitClassMeta}>
                {selectedStudent ? (
                  <>
                    Đang theo dõi tiến độ của <strong>{selectedStudent.student_name}</strong> · Khối{" "}
                    {selectedStudent.grade_level}
                    {selectedStudent.school_name ? ` · ${selectedStudent.school_name}` : ""} · Quan hệ:{" "}
                    <strong>{formatRelationship(selectedStudent.relationship_type)}</strong>
                  </>
                ) : (
                  "Tài khoản phụ huynh chỉ hiển thị dữ liệu khi đã có liên kết xác thực (is_active=true) với hồ sơ học sinh."
                )}
              </p>
              {progress?.trend_description && (
                <p
                  style={{
                    marginTop: "8px",
                    fontSize: "0.88rem",
                    color: "#173f34",
                    background: "rgba(255,255,255,0.7)",
                    padding: "8px 12px",
                    borderRadius: "10px",
                    border: "1px solid rgba(40,105,85,0.16)",
                  }}
                >
                  <strong>Nhận định tổng quan:</strong> {progress.trend_description}
                </p>
              )}
            </div>

            {selectedStudent && (
              <div className={styles.cockpitActions}>
                {trendBadge && (
                  <span
                    style={{
                      padding: "6px 12px",
                      borderRadius: "999px",
                      fontSize: "0.8rem",
                      fontWeight: 750,
                      color: trendBadge.color,
                      background: trendBadge.bg,
                    }}
                  >
                    {trendBadge.label}
                  </span>
                )}
                <button
                  type="button"
                  className={styles.bannerTheoryBtn}
                  onClick={() => {
                    handleSelectTab("ai-companion");
                    if (!aiSummary && !aiLoading) {
                      void handleGenerateAiSummary();
                    }
                  }}
                >
                  <Sparkles size={15} aria-hidden="true" />
                  Tổng kết tuần cùng Cố vấn AI
                </button>
              </div>
            )}
          </div>

          {/* 4 KPI Cards */}
          <div className={styles.kpiGrid}>
            {/* KPI 1: Thời lượng học tuần này */}
            <div
              className={`${styles.kpiCard} ${styles.kpiCardClickable}`}
              onClick={() => handleSelectTab("weekly")}
              role="button"
              tabIndex={0}
            >
              <div className={`${styles.kpiIconWrap} ${styles.kpiIconEmerald}`}>
                <Clock size={24} aria-hidden="true" />
              </div>
              <div className={styles.kpiMeta}>
                <span className={styles.kpiLabel}>Thời lượng tự học tuần</span>
                <div className={styles.kpiValueRow}>
                  <strong className={styles.kpiValue}>
                    {weeklyData?.total_study_time_minutes ?? selectedStudent?.weekly_study_time_minutes ?? 0}
                  </strong>
                  <span className={styles.kpiUnit}>phút / tuần</span>
                </div>
                <span className={styles.kpiSub}>
                  {weeklyData
                    ? `${weeklyData.daily_study_time.filter((d) => d.study_time_minutes > 0 || d.questions_attempted > 0).length}/7 ngày có hoạt động`
                    : "Tổng hợp từ phiên học & luyện tập"}
                </span>
              </div>
            </div>

            {/* KPI 2: Hoàn thành kế hoạch học tập */}
            <div
              className={`${styles.kpiCard} ${styles.kpiCardClickable}`}
              onClick={() => handleSelectTab("overview")}
              role="button"
              tabIndex={0}
            >
              <div className={`${styles.kpiIconWrap} ${styles.kpiIconSky}`}>
                <Target size={24} aria-hidden="true" />
              </div>
              <div className={styles.kpiMeta}>
                <span className={styles.kpiLabel}>Kế hoạch học tập</span>
                <div className={styles.kpiValueRow}>
                  <strong className={styles.kpiValue}>
                    {progress
                      ? `${Math.round(progress.study_plan_completion.completion_rate * 100)}%`
                      : "—"}
                  </strong>
                  <span className={styles.kpiUnit}>hoàn thành</span>
                </div>
                <span className={styles.kpiSub}>
                  {progress
                    ? `${progress.study_plan_completion.completed_tasks}/${progress.study_plan_completion.total_tasks} nhiệm vụ đang mở`
                    : "Chưa có dữ liệu kế hoạch"}
                </span>
              </div>
            </div>

            {/* KPI 3: Độ vững chương trình */}
            <div
              className={`${styles.kpiCard} ${styles.kpiCardClickable}`}
              onClick={() => handleSelectTab("curriculum")}
              role="button"
              tabIndex={0}
            >
              <div className={`${styles.kpiIconWrap} ${styles.kpiIconMint}`}>
                <Award size={24} aria-hidden="true" />
              </div>
              <div className={styles.kpiMeta}>
                <span className={styles.kpiLabel}>Mức độ nắm bài</span>
                <div className={styles.kpiValueRow}>
                  <strong className={styles.kpiValue}>
                    {avgSubjectMastery !== undefined ? `${avgSubjectMastery}%` : "—"}
                  </strong>
                  <span className={styles.kpiUnit}>trung bình môn</span>
                </div>
                {avgSubjectMastery !== undefined ? (
                  <div className={styles.kpiMiniProgress}>
                    <div
                      className={styles.kpiMiniBar}
                      style={{ width: `${Math.max(6, avgSubjectMastery)}%` }}
                    />
                  </div>
                ) : (
                  <span className={styles.kpiSub}>Theo dõi theo từng chương &amp; chủ đề</span>
                )}
              </div>
            </div>

            {/* KPI 4: Lưu ý đồng hành */}
            <div
              className={`${styles.kpiCard} ${styles.kpiCardClickable} ${
                (progress?.important_intervention_alerts.length ?? selectedStudent?.active_alerts_count ?? 0) > 0
                  ? styles.kpiCardAlert
                  : ""
              }`}
              onClick={() => handleSelectTab("overview")}
              role="button"
              tabIndex={0}
            >
              <div
                className={`${styles.kpiIconWrap} ${
                  (progress?.important_intervention_alerts.length ?? selectedStudent?.active_alerts_count ?? 0) > 0
                    ? styles.kpiIconAmber
                    : styles.kpiIconMuted
                }`}
              >
                <AlertTriangle size={24} aria-hidden="true" />
              </div>
              <div className={styles.kpiMeta}>
                <span className={styles.kpiLabel}>Lưu ý đồng hành</span>
                <div className={styles.kpiValueRow}>
                  <strong className={styles.kpiValue}>
                    {progress?.important_intervention_alerts.length ?? selectedStudent?.active_alerts_count ?? 0}
                  </strong>
                  <span className={styles.kpiUnit}>điểm cần lưu ý</span>
                </div>
                <span className={styles.kpiSub}>
                  {(progress?.important_intervention_alerts.length ?? 0) > 0
                    ? "Có gợi ý hỗ trợ con tại nhà"
                    : "Nhịp học đang duy trì tốt"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className={styles.tabsStickyWrap}>
          <nav className={styles.tabsBar} aria-label="Điều hướng cổng phụ huynh">
            <button
              type="button"
              onClick={() => handleSelectTab("overview")}
              className={`${styles.tabItem} ${tab === "overview" ? styles.tabItemActive : ""}`}
            >
              <HeartHandshake size={16} aria-hidden="true" />
              <span>Tổng quan &amp; Lưu ý đồng hành</span>
              {progress && progress.important_intervention_alerts.length > 0 && (
                <span className={styles.tabAlertBadge}>
                  {progress.important_intervention_alerts.length}
                </span>
              )}
            </button>

            <button
              type="button"
              onClick={() => handleSelectTab("curriculum")}
              className={`${styles.tabItem} ${tab === "curriculum" ? styles.tabItemActive : ""}`}
            >
              <BookOpen size={16} aria-hidden="true" />
              <span>Tiến độ Môn học &amp; Chương</span>
              {progress && (
                <span className={styles.tabCounterBadge}>{progress.chapter_progress.length}</span>
              )}
            </button>

            <button
              type="button"
              onClick={() => handleSelectTab("weekly")}
              className={`${styles.tabItem} ${tab === "weekly" ? styles.tabItemActive : ""}`}
            >
              <Calendar size={16} aria-hidden="true" />
              <span>Nhật ký Tuần &amp; Điểm kiểm tra</span>
            </button>

            <button
              type="button"
              onClick={() => handleSelectTab("ai-companion")}
              className={`${styles.tabItem} ${tab === "ai-companion" ? styles.tabItemActive : ""}`}
            >
              <Sparkles size={16} aria-hidden="true" />
              <span>Bản tin Sư phạm AI</span>
            </button>
          </nav>
        </div>

        {/* Content Area */}
        {initialLoading ? (
          <div className={styles.sectionCard}>
            <div className={styles.tableLoadingState}>
              <div className={styles.spinner} aria-hidden="true" />
              <p>Đang tải danh sách học sinh liên kết...</p>
            </div>
          </div>
        ) : students.length === 0 ? (
          <div className={styles.sectionCard}>
            <div className={styles.emptyCard}>
              <UsersRound size={36} className={styles.emptyIcon} aria-hidden="true" />
              <h3 className={styles.emptyTitle}>Chưa có hồ sơ học sinh liên kết</h3>
              <p className={styles.emptyDesc}>
                Tài khoản phụ huynh của bạn hiện chưa được gắn kết hoạt động (ACTIVE) với học sinh nào trong cơ sở dữ liệu. Vui lòng liên hệ nhà trường hoặc quản trị viên để thiết lập liên kết.
              </p>
            </div>
          </div>
        ) : (
          <div className={styles.viewContainer}>
            {/* Linked Children Selector Cards if multiple children */}
            {students.length > 1 && (
              <div className={styles.sectionCard}>
                <div className={styles.sectionCardHeader}>
                  <div>
                    <h3 className={styles.sectionHeading}>Danh sách con em đang đồng hành</h3>
                    <p className={styles.sectionSubheading}>
                      Chọn học sinh để xem báo cáo tiến độ chi tiết
                    </p>
                  </div>
                </div>
                <div className={styles.classCardGrid}>
                  {students.map((st) => {
                    const isSelected = st.student_id === selectedStudentId;
                    const tBadge = formatTrendLabel(st.overall_learning_trend);
                    return (
                      <div
                        key={st.student_id}
                        className={`${styles.classRoomCard} ${isSelected ? styles.classRoomCardActive : ""}`}
                        onClick={() => setSelectedStudentId(st.student_id)}
                        role="button"
                        tabIndex={0}
                      >
                        <div className={styles.classRoomCardTop}>
                          <span className={styles.classGradeBadge}>Khối {st.grade_level}</span>
                          <span
                            style={{
                              fontSize: "0.72rem",
                              fontWeight: 700,
                              padding: "2px 8px",
                              borderRadius: "999px",
                              color: tBadge.color,
                              background: tBadge.bg,
                            }}
                          >
                            {tBadge.label}
                          </span>
                        </div>
                        <h4 className={styles.classRoomName}>{st.student_name}</h4>
                        <div className={styles.classRoomFooter}>
                          <span>{st.weekly_study_time_minutes} phút/tuần</span>
                          <span>{formatRelationship(st.relationship_type)}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* TAB 1: OVERVIEW & ALERTS & WEAK AREAS */}
            {tab === "overview" && (
              <div className={styles.tabContentWrap}>
                {/* 1. Lưu ý đồng hành từ hệ thống */}
                <div className={styles.sectionCard}>
                  <div className={styles.sectionCardHeader}>
                    <div>
                      <div className={styles.badgeCluster}>
                        <h3 className={styles.sectionHeading}>
                          Gợi ý đồng hành &amp; Cảnh báo sớm cho gia đình
                        </h3>
                        <span
                          className={
                            (progress?.important_intervention_alerts.length ?? 0) > 0
                              ? styles.badgeAlertCount
                              : styles.studentTotalPill
                          }
                        >
                          {progress?.important_intervention_alerts.length ?? 0} lưu ý
                        </span>
                      </div>
                      <p className={styles.sectionSubheading}>
                        Tổng hợp các tín hiệu quan trọng (như gián đoạn học tập, hổng kiến thức nền tảng) kèm theo gợi ý hành động nhẹ nhàng, khích lệ cho phụ huynh.
                      </p>
                    </div>
                  </div>

                  {!progress || progress.important_intervention_alerts.length === 0 ? (
                    <div className={styles.alertEmptyCard}>
                      <CheckCircle2 size={32} className={styles.textVerdant} aria-hidden="true" />
                      <div>
                        <h4 className={styles.emptyTitle}>Con đang duy trì nhịp học tập tích cực</h4>
                        <p className={styles.emptyDesc}>
                          Hiện tại không có cảnh báo can thiệp nào. Gia đình hãy tiếp tục khích lệ tinh thần tự giác của con!
                        </p>
                      </div>
                    </div>
                  ) : (
                    <div className={styles.attentionGrid}>
                      {progress.important_intervention_alerts.map((alert, idx) => (
                        <div key={`${alert.rule_code}-${idx}`} className={styles.attentionCard}>
                          <div className={styles.attentionCardHeader}>
                            <strong className={styles.studentFullName}>{alert.title}</strong>
                            <span className={styles.severityBadgeHigh}>
                              <AlertTriangle size={12} aria-hidden="true" />
                              {alert.severity}
                            </span>
                          </div>
                          <div className={styles.attentionReasonBox}>{alert.message}</div>
                          <div className={styles.attentionCardActionHint}>
                            💡 <strong>Cách phụ huynh đồng hành:</strong> {alert.suggested_action_for_parent}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 2. Nhóm bài toán con đang gặp khó khăn (ProblemType level) */}
                <div className={styles.sectionCard}>
                  <div className={styles.sectionCardHeader}>
                    <div>
                      <div className={styles.badgeCluster}>
                        <h3 className={styles.sectionHeading}>
                          Nhóm bài toán con đang cần củng cố thêm
                        </h3>
                        <span className={styles.badgeAmberCount}>
                          {progress?.major_weak_areas.length ?? 0} nhóm bài
                        </span>
                      </div>
                      <p className={styles.sectionSubheading}>
                        Hiển thị ở cấp độ dạng bài thực tế giúp phụ huynh nắm bắt đúng trọng tâm mà không gây áp lực vì các lỗi nhỏ lẻ.
                      </p>
                    </div>
                  </div>

                  {!progress || progress.major_weak_areas.length === 0 ? (
                    <div className={styles.emptyCard}>
                      <CheckCircle2 size={32} className={styles.textVerdant} aria-hidden="true" />
                      <h4 className={styles.emptyTitle}>Chưa ghi nhận dạng bài yếu kéo dài</h4>
                      <p className={styles.emptyDesc}>
                        Các dạng bài con đã luyện tập đều đạt mức thành thạo ổn định hoặc mới bắt đầu làm quen.
                      </p>
                    </div>
                  ) : (
                    <div className={styles.weakGrid}>
                      {progress.major_weak_areas.map((wa) => (
                        <div key={wa.problem_type_id} className={styles.weakCard}>
                          <div className={styles.weakCardTop}>
                            <span className={styles.weakCardBadge}>{wa.subject_name}</span>
                            <span className={styles.weakStudentCount}>{wa.attempt_count} lần luyện tập</span>
                          </div>
                          <h4 className={styles.weakProblemTitle}>{wa.problem_type_name}</h4>
                          <p style={{ margin: "4px 0", fontSize: "0.86rem", color: "#52675d" }}>
                            {wa.parent_friendly_message}
                          </p>
                          <div className={styles.weakScoreRow}>
                            <span>Mức độ nắm vững hiện tại:</span>
                            <strong className={styles.weakScoreValue}>
                              {Math.round(wa.mastery_score * 100)}%
                            </strong>
                          </div>
                          {wa.related_concept_name && (
                            <div className={styles.weakPedagogicalTip}>
                              🔗 <strong>Kiến thức nền tảng liên quan:</strong> Cần ôn lại khái niệm{" "}
                              <em>{wa.related_concept_name}</em>.
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* Privacy & Pedagogical Safety Notice */}
                <div className={styles.pedagogicalNoticeCard}>
                  <ShieldCheck size={20} className={styles.noticeIcon} aria-hidden="true" />
                  <div>
                    <h4 className={styles.noticeHeading}>
                      Cam kết Quyền riêng tư &amp; Sư phạm tích cực của EduMS
                    </h4>
                    <p className={styles.noticeText}>
                      Để tôn trọng không gian tự học an toàn của con, cổng Phụ huynh chỉ cung cấp dữ liệu tổng hợp xác định, không hiển thị tin nhắn hỏi đáp riêng tư với AI gia sư và không so sánh xếp hạng giữa các học sinh.
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* TAB 2: CURRICULUM PROGRESS (SUBJECTS, CHAPTERS, TOPICS) */}
            {tab === "curriculum" && (
              <div className={styles.tabContentWrap}>
                {/* Subject Summary */}
                <div className={styles.sectionCard}>
                  <div className={styles.sectionCardHeader}>
                    <div>
                      <h3 className={styles.sectionHeading}>Tổng quan theo Môn học</h3>
                      <p className={styles.sectionSubheading}>
                        Tỷ lệ chủ đề đã đạt ngưỡng nắm vững (&ge; 70%) trên tổng số chủ đề của môn
                      </p>
                    </div>
                  </div>

                  {!progress || progress.subject_progress.length === 0 ? (
                    <div className={styles.emptyCard}>
                      <BookOpen size={32} className={styles.emptyIcon} />
                      <h4 className={styles.emptyTitle}>Chưa có dữ liệu môn học</h4>
                    </div>
                  ) : (
                    <div className={styles.chaptersGridModern}>
                      {progress.subject_progress.map((subj) => {
                        const pct = Math.round(subj.mastery_score * 100);
                        return (
                          <div key={subj.subject_id} className={styles.chapterCardModern}>
                            <div className={styles.chapterCardTop}>
                              <span className={styles.chapterSubjectPill}>{subj.subject_name}</span>
                              <span className={styles.chapterProficientText}>
                                Đã vững <strong>{subj.completed_topics_count}</strong>/{subj.total_topics_count} chủ đề
                              </span>
                            </div>
                            <h4 className={styles.chapterCardTitle}>{subj.subject_name}</h4>
                            <div className={styles.chapterMasterySection}>
                              <div className={styles.chapterMasteryHeader}>
                                <span>Độ làm chủ môn học</span>
                                <strong className={styles.chapterMasteryNum}>{pct}%</strong>
                              </div>
                              <div className={styles.chapterProgressBarTrack}>
                                <div
                                  className={styles.chapterProgressBarFill}
                                  style={{ width: `${Math.max(4, pct)}%` }}
                                />
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Chapter Progress */}
                <div className={styles.sectionCard}>
                  <div className={styles.sectionCardHeader}>
                    <div>
                      <h3 className={styles.sectionHeading}>Chi tiết từng Chương trong Chương trình</h3>
                      <p className={styles.sectionSubheading}>
                        Trạng thái từng chương: Đã làm chủ (&ge; 80%), Đang tiến bộ (50–79%), Cần củng cố (&lt; 50%)
                      </p>
                    </div>
                  </div>

                  {!progress || progress.chapter_progress.length === 0 ? (
                    <div className={styles.emptyCard}>
                      <BookOpen size={32} className={styles.emptyIcon} />
                      <h4 className={styles.emptyTitle}>Chưa có dữ liệu theo chương</h4>
                    </div>
                  ) : (
                    <div className={styles.chaptersGridModern}>
                      {progress.chapter_progress.map((chap) => {
                        const pct = Math.round(chap.mastery_score * 100);
                        const statusLabel =
                          chap.status === "MASTERED"
                            ? "Đã vững"
                            : chap.status === "IN_PROGRESS"
                              ? "Đang học"
                              : "Cần củng cố";
                        return (
                          <div key={chap.chapter_id} className={styles.chapterCardModern}>
                            <div className={styles.chapterCardTop}>
                              <span className={styles.chapterSubjectPill}>{chap.subject_name}</span>
                              <span className={styles.chapterProficientText}>
                                <strong>{statusLabel}</strong>
                              </span>
                            </div>
                            <h4 className={styles.chapterCardTitle}>{chap.chapter_name}</h4>
                            <div className={styles.chapterMasterySection}>
                              <div className={styles.chapterMasteryHeader}>
                                <span>Mức độ thành thạo</span>
                                <strong className={styles.chapterMasteryNum}>{pct}%</strong>
                              </div>
                              <div className={styles.chapterProgressBarTrack}>
                                <div
                                  className={styles.chapterProgressBarFill}
                                  style={{ width: `${Math.max(4, pct)}%` }}
                                />
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* TAB 3: WEEKLY BREAKDOWN & EXAM TRENDS */}
            {tab === "weekly" && (
              <div className={styles.tabContentWrap}>
                <div className={styles.sectionCard}>
                  <div className={styles.sectionCardHeader}>
                    <div>
                      <h3 className={styles.sectionHeading}>
                        Biểu đồ Thời gian Tự học trong Tuần
                        {weeklyData
                          ? ` (${weeklyData.week_start_date} → ${weeklyData.week_end_date})`
                          : ""}
                      </h3>
                      <p className={styles.sectionSubheading}>
                        {weeklyData?.overall_weekly_summary ??
                          "Theo dõi sự đều đặn qua từng ngày từ Thứ 2 đến Chủ nhật"}
                      </p>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                      <label htmlFor="weekly-date-picker" style={{ fontSize: "0.82rem", fontWeight: 600 }}>
                        Chọn ngày trong tuần:
                      </label>
                      <input
                        id="weekly-date-picker"
                        type="date"
                        value={targetDate}
                        onChange={(e) => setTargetDate(e.target.value)}
                        style={{
                          padding: "6px 10px",
                          borderRadius: "10px",
                          border: "1px solid rgba(40,105,85,0.25)",
                          fontSize: "0.85rem",
                        }}
                      />
                      {targetDate && (
                        <button
                          type="button"
                          className={styles.btnSecondary}
                          onClick={() => setTargetDate("")}
                        >
                          Tuần hiện tại
                        </button>
                      )}
                    </div>
                  </div>

                  {weeklyData && (
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(135px, 1fr))",
                        gap: "12px",
                      }}
                    >
                      {weeklyData.daily_study_time.map((day) => {
                        const active = day.study_time_minutes > 0 || day.questions_attempted > 0;
                        return (
                          <div
                            key={day.date}
                            style={{
                              padding: "14px",
                              borderRadius: "16px",
                              background: active
                                ? "linear-gradient(145deg, #ffffff 0%, rgba(220, 239, 229, 0.45) 100%)"
                                : "rgba(255, 255, 255, 0.65)",
                              border: active
                                ? "1.5px solid #286955"
                                : "1px solid rgba(40, 105, 85, 0.14)",
                              display: "flex",
                              flexDirection: "column",
                              gap: "6px",
                            }}
                          >
                            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                              <strong style={{ fontSize: "0.9rem", color: "#102e26" }}>{day.day_of_week}</strong>
                              <span style={{ fontSize: "0.75rem", color: "#647b70" }}>{day.date.slice(5)}</span>
                            </div>
                            <div style={{ fontSize: "1.4rem", fontWeight: 800, color: active ? "#173f34" : "#74847c" }}>
                              {day.study_time_minutes} <span style={{ fontSize: "0.8rem", fontWeight: 600 }}>phút</span>
                            </div>
                            <div style={{ fontSize: "0.78rem", color: "#52675d" }}>
                              {day.questions_attempted} câu hỏi đã giải
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>

                {/* Exam & Assignment Trend */}
                <div className={styles.sectionCard}>
                  <div className={styles.sectionCardHeader}>
                    <div>
                      <h3 className={styles.sectionHeading}>Xu hướng Điểm bài tập &amp; Đánh giá gần đây</h3>
                      <p className={styles.sectionSubheading}>
                        Tổng hợp các bài tập lớn và đề kiểm tra đã nộp theo thang điểm 10
                      </p>
                    </div>
                  </div>

                  {!progress || progress.exam_trend.length === 0 ? (
                    <div className={styles.emptyCard}>
                      <Calendar size={32} className={styles.emptyIcon} />
                      <h4 className={styles.emptyTitle}>Chưa có bài kiểm tra đã chấm điểm</h4>
                      <p className={styles.emptyDesc}>
                        Khi con hoàn thành và nộp các bài giao trên lớp hoặc đề thi thử, kết quả sẽ hiển thị tại đây.
                      </p>
                    </div>
                  ) : (
                    <div className={styles.chaptersGridModern}>
                      {progress.exam_trend.map((item, idx) => (
                        <div key={`${item.title}-${idx}`} className={styles.chapterCardModern}>
                          <div className={styles.chapterCardTop}>
                            <span className={styles.chapterSubjectPill}>{item.assessment_type}</span>
                            <span
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "4px",
                                fontSize: "0.78rem",
                                fontWeight: 700,
                                color:
                                  item.trend_direction === "UP"
                                    ? "#165944"
                                    : item.trend_direction === "DOWN"
                                      ? "#991b1b"
                                      : "#52675d",
                              }}
                            >
                              {item.trend_direction === "UP" && <TrendingUp size={14} />}
                              {item.trend_direction === "DOWN" && <TrendingDown size={14} />}
                              {item.trend_direction === "STABLE" && <Minus size={14} />}
                              {item.trend_direction === "UP"
                                ? "Tăng"
                                : item.trend_direction === "DOWN"
                                  ? "Giảm"
                                  : "Ổn định"}
                            </span>
                          </div>
                          <h4 className={styles.chapterCardTitle}>{item.title}</h4>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: "6px" }}>
                            <span style={{ fontSize: "0.82rem", color: "#647b70" }}>
                              {new Date(item.date).toLocaleDateString("vi-VN")} · {item.total_questions} câu
                            </span>
                            <strong style={{ fontSize: "1.35rem", fontWeight: 800, color: "#102e26" }}>
                              {item.score.toFixed(1)}/10
                            </strong>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* TAB 4: AI WEEKLY PEDAGOGICAL COMPANION */}
            {tab === "ai-companion" && (
              <div className={styles.tabContentWrap}>
                <div className={styles.sectionCard}>
                  <div className={styles.sectionCardHeader}>
                    <div>
                      <div className={styles.badgeCluster}>
                        <h3 className={styles.sectionHeading}>
                          Bản tin Sư phạm Hàng tuần dành cho Phụ huynh
                        </h3>
                        {aiSummary && (
                          <span className={styles.studentTotalPill}>
                            {aiSummary.is_fallback ? "Bản tổng hợp xác định (Deterministic)" : "Bản tổng hợp AI Sư phạm"}
                          </span>
                        )}
                      </div>
                      <p className={styles.sectionSubheading}>
                        Phân tích 4 phần rõ ràng: Tiến độ tuần qua, Khó khăn hiện tại, Định hướng tuần tới và tối đa 2 gợi ý thiết thực để cha mẹ đồng hành cùng con.
                      </p>
                    </div>
                    <button
                      type="button"
                      className={styles.btnPrimary}
                      onClick={() => void handleGenerateAiSummary()}
                      disabled={aiLoading}
                    >
                      <Sparkles size={15} />
                      {aiLoading ? "Đang tổng hợp..." : aiSummary ? "Tạo lại bản tin tuần" : "Tạo bản tin tuần này"}
                    </button>
                  </div>

                  {aiError && (
                    <div className={styles.systemAlertBar} role="alert">
                      <AlertCircle size={18} />
                      <span>{aiError}</span>
                    </div>
                  )}

                  {!aiSummary && !aiLoading ? (
                    <div className={styles.emptyCard}>
                      <Sparkles size={32} className={styles.emptyIcon} />
                      <h4 className={styles.emptyTitle}>Bấm &ldquo;Tạo bản tin tuần này&rdquo; để nhận phân tích</h4>
                      <p className={styles.emptyDesc}>
                        Hệ thống sẽ tổng hợp dữ liệu thời lượng học, hoàn thành nhiệm vụ và các dạng bài của con để đưa ra khuyến nghị đồng hành phù hợp nhất.
                      </p>
                    </div>
                  ) : aiLoading ? (
                    <div className={styles.tableLoadingState}>
                      <div className={styles.spinner} aria-hidden="true" />
                      <p>Đang phân tích dữ liệu học tập tuần và soạn bản tin sư phạm...</p>
                    </div>
                  ) : (
                    aiSummary && (
                      <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))" }}>
                        <div className={styles.chapterCardModern}>
                          <span className={styles.chapterSubjectPill}>1. Ghi nhận Tiến độ</span>
                          <h4 className={styles.chapterCardTitle} style={{ marginTop: "8px" }}>
                            Điểm tích cực trong tuần ({aiSummary.week_start_date} → {aiSummary.week_end_date})
                          </h4>
                          <p style={{ fontSize: "0.9rem", lineHeight: 1.55, color: "#173329", margin: "6px 0 0" }}>
                            {aiSummary.progress}
                          </p>
                        </div>

                        <div className={styles.chapterCardModern}>
                          <span className={styles.chapterSubjectPill}>2. Thách thức Hiện tại</span>
                          <h4 className={styles.chapterCardTitle} style={{ marginTop: "8px" }}>
                            Trọng tâm kiến thức cần tháo gỡ
                          </h4>
                          <p style={{ fontSize: "0.9rem", lineHeight: 1.55, color: "#173329", margin: "6px 0 0" }}>
                            {aiSummary.current_challenge}
                          </p>
                        </div>

                        <div className={styles.chapterCardModern}>
                          <span className={styles.chapterSubjectPill}>3. Kế hoạch Tuần tới</span>
                          <h4 className={styles.chapterCardTitle} style={{ marginTop: "8px" }}>
                            Định hướng học tập tiếp theo
                          </h4>
                          <p style={{ fontSize: "0.9rem", lineHeight: 1.55, color: "#173329", margin: "6px 0 0" }}>
                            {aiSummary.next_week}
                          </p>
                        </div>

                        <div className={styles.chapterCardModern}>
                          <span className={styles.chapterSubjectPill}>4. Gợi ý cho Gia đình</span>
                          <h4 className={styles.chapterCardTitle} style={{ marginTop: "8px" }}>
                            Cách phụ huynh có thể giúp con (Tối đa 2 gợi ý)
                          </h4>
                          <ul style={{ margin: "8px 0 0", paddingLeft: "18px", fontSize: "0.9rem", lineHeight: 1.55, color: "#173329" }}>
                            {aiSummary.how_parent_can_help.map((rec, index) => (
                              <li key={index} style={{ marginBottom: "6px" }}>
                                {rec}
                              </li>
                            ))}
                          </ul>
                        </div>
                      </div>
                    )
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </main>

      <AppFooter variant="default" />
    </div>
  );
}
