"use client";

import {
  BookMarked,
  CalendarCheck,
  CheckCircle2,
  ClipboardCheck,
  Compass,
  RotateCcw,
  Sparkles,
  Sprout,
  X,
} from "lucide-react";
import { StudyPlanRoadmapModal } from "./StudyPlanRoadmapModal";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { motion } from "motion/react";
import { useId } from "react";

import { fadeUp, staggerContainer } from "@/lib/motion";

import styles from "../StudentHome.module.css";
import type { StudentHomeViewModel } from "../types";
import { SectionHeading } from "./SectionHeading";
import { useGardenMotion, useGardenSectionInView } from "./nature/GardenMotionContext";

export interface LearningPulseProps {
  data: StudentHomeViewModel;
}

function MasteryWreathVisual({
  score,
  hasEvidence,
  label,
  animate,
}: {
  score?: number;
  hasEvidence: boolean;
  label: string;
  animate: boolean;
}) {
  const gradId = useId().replaceAll(":", "");
  const normalized =
    hasEvidence && score !== undefined ? Math.min(100, Math.max(0, score)) : undefined;
  const radius = 33;
  const circumference = 2 * Math.PI * radius;
  const offset =
    normalized === undefined ? circumference : circumference * (1 - normalized / 100);
  const bloomedLeaves = normalized === undefined ? 0 : Math.round((normalized / 100) * 8);

  return (
    <div
      className={styles.masteryWreathWrap}
      role="img"
      aria-label={
        normalized === undefined
          ? `${label}: Chưa đủ dữ liệu đo lường`
          : `${label}: ${Math.round(normalized)}%`
      }
    >
      <svg className={styles.masteryWreathSvg} viewBox="0 0 96 96" aria-hidden="true">
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#23A67A" />
            <stop offset="100%" stopColor="#8BE5C2" />
          </linearGradient>
        </defs>

        {/* 8 Botanical Leaves around the Wreath */}
        {Array.from({ length: 8 }, (_, idx) => {
          const angle = idx * 45 - 90;
          const isBloomed = idx < bloomedLeaves;
          return (
            <g key={idx} transform={`rotate(${angle} 48 48)`}>
              <path
                d="M48 6C51 2 56 3 57 7C53 10 50 9 48 6Z"
                fill={isBloomed ? "#23A67A" : "#DCEFE5"}
                fillOpacity={isBloomed ? "0.88" : "0.7"}
              />
            </g>
          );
        })}

        {/* Track */}
        <circle
          cx="48"
          cy="48"
          r={radius}
          fill="none"
          stroke="rgba(9, 45, 37, 0.09)"
          strokeWidth="6.5"
        />

        {/* Animated Evidence Arc */}
        {normalized !== undefined ? (
          <motion.circle
            cx="48"
            cy="48"
            r={radius}
            fill="none"
            stroke={`url(#${gradId})`}
            strokeWidth="6.5"
            strokeLinecap="round"
            transform="rotate(-90 48 48)"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            whileInView={{ strokeDashoffset: offset }}
            viewport={{ once: true }}
            transition={{ duration: animate ? 0.9 : 0, ease: [0.22, 1, 0.36, 1] }}
          />
        ) : null}
      </svg>

      <div className={styles.masteryWreathCenter}>
        <strong>{normalized === undefined ? "—" : `${Math.round(normalized)}%`}</strong>
        <span>{normalized === undefined ? " mầm non" : "vững"}</span>
      </div>
    </div>
  );
}

export function LearningPulse({ data }: LearningPulseProps) {
  const router = useRouter();
  const [showGoalModal, setShowGoalModal] = useState(false);
  const [showRoadmapModal, setShowRoadmapModal] = useState(false);
  const [targetScore, setTargetScore] = useState<number>(8.0);
  const [dailyMinutes, setDailyMinutes] = useState<number>(30);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isRecalculating, setIsRecalculating] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  const handleCreateGoal = async () => {
    setIsSubmitting(true);
    setFeedbackMsg(null);
    try {
      const res = await fetch("/api/student/study-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: "create_goal",
          subject_id: data.subject.id,
          target_score: targetScore,
          available_daily_minutes: dailyMinutes,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.message || "Không thể khởi tạo mục tiêu.");
      }
      setFeedbackMsg("🌱 Đã gieo lộ trình 7 ngày thành công!");
      setTimeout(() => {
        setShowGoalModal(false);
        router.refresh();
      }, 900);
    } catch (e: any) {
      setFeedbackMsg(e.message || "Có lỗi xảy ra.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRecalculate = async () => {
    setIsRecalculating(true);
    try {
      const res = await fetch("/api/student/study-plan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "recalculate", horizon_days: 7 }),
      });
      if (res.ok) {
        router.refresh();
      }
    } catch {
      // ignore
    } finally {
      setIsRecalculating(false);
    }
  };

  const { shouldAnimate } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLElement>("180px 0px");
  const active = shouldAnimate && isInView;

  const mastery = data.mastery;
  const review = data.review;
  const assignments = data.assignments;
  const todayPlan = data.todayPlan;
  const hasClassroomContext = data.learningContext.mode === "CLASSROOM";

  // Truthful ratio for classroom assignment bar when active tasks exist
  const assignmentCompletionRatio =
    hasClassroomContext && assignments.activeCount > 0
      ? Math.max(
          0.12,
          Math.min(
            1,
            (assignments.activeCount - assignments.overdueCount) /
              Math.max(1, assignments.activeCount)
          )
        )
      : hasClassroomContext
      ? 1
      : 0;

  // Stepping stones for Today's Plan (strictly derived from real todayPlan counts)
  const totalStones = todayPlan
    ? Math.min(6, Math.max(1, todayPlan.totalCount))
    : 4;
  const litStones = todayPlan
    ? Math.min(totalStones, Math.round((todayPlan.completedCount / Math.max(1, todayPlan.totalCount)) * totalStones))
    : 0;

  return (
    <section
      ref={ref}
      className={`${styles.section} ${styles.pulseTerraceSection} ${
        !active ? styles.sectionAnimPaused : ""
      }`}
      id="learning-pulse"
      aria-labelledby="learning-pulse-title"
    >
      {/* Subtle Canopy Foliage Framing at Terrace Edges */}
      <svg
        className={styles.pulseCanopyDecor}
        viewBox="0 0 180 90"
        fill="none"
        aria-hidden="true"
      >
        <path
          d="M178 8C136 16 98 34 64 62M134 18C112 10 88 12 68 24"
          stroke="#23A67A"
          strokeOpacity="0.32"
          strokeWidth="1.8"
          strokeLinecap="round"
        />
        <path d="M68 24C82 10 100 12 110 24C94 32 78 30 68 24Z" fill="#8BE5C2" fillOpacity="0.55" />
        <path d="M64 62C46 56 32 62 26 76C44 80 58 74 64 62Z" fill="#23A67A" fillOpacity="0.34" />
      </svg>

      <SectionHeading
        eyebrow="Khu vườn tiến bộ · Tín hiệu hiện tại"
        title="Nhịp học hôm nay"
        description="Bốn mảnh vườn phản chiếu trung thực năng lực, lịch ôn tập và nhịp bước trong ngày của bạn."
      />

      <motion.div
        className={styles.pulseGrid}
        variants={staggerContainer}
        initial={false}
        whileInView="visible"
        viewport={{ once: true, amount: 0.18 }}
      >
        {/* Card 1: Evidence-based Mastery — Sapling & Leaf Wreath */}
        <motion.div variants={fadeUp}>
          <article className={`${styles.pulseGardenCard} ${styles.pulseCardMastery}`}>
            <span className={styles.pulseBotanicalLeaf} aria-hidden="true" />
            <div className={styles.metricCopy}>
              <span className={styles.metricIcon} aria-hidden="true">
                <Sprout size={19} />
              </span>
              <span className={styles.pulseCardKicker}>Mầm năng lực</span>
              <strong>{mastery.label}</strong>
              <small>
                {mastery.hasEvidence
                  ? `${mastery.masteredProblemTypeCount} dạng vững · ${mastery.weakProblemTypeCount} dạng cần chăm`
                  : "Chưa đủ dữ liệu bài làm"}
              </small>
            </div>
            <MasteryWreathVisual
              score={mastery.score}
              hasEvidence={mastery.hasEvidence}
              label={mastery.label}
              animate={shouldAnimate}
            />
          </article>
        </motion.div>

        {/* Card 2: Due Reviews — Pressed Botanical Leaves */}
        <motion.div variants={fadeUp}>
          <article className={`${styles.pulseGardenCard} ${styles.pulseCardReview}`}>
            <span className={styles.pulseSunFleck} aria-hidden="true" />
            <div className={styles.metricCopy}>
              <span className={`${styles.metricIcon} ${styles.metricIconReview}`} aria-hidden="true">
                <BookMarked size={19} />
              </span>
              <span className={styles.pulseCardKicker}>Lá nhắc ôn tập</span>
              <strong>Nội dung cần ôn</strong>
              <small>
                {review.dueCount > 0
                  ? review.dueTargets[0]?.targetName
                    ? `Ưu tiên: ${review.dueTargets[0].targetName}`
                    : "Đến hạn ôn tập hôm nay"
                  : "Đã hoàn thành các lượt ôn"}
              </small>
            </div>

            <div
              className={`${styles.reviewBotanicalCluster} ${
                review.dueCount > 0 ? styles.reviewClusterDue : ""
              }`}
              aria-label={`${review.dueCount} nội dung cần ôn`}
            >
              <svg className={styles.reviewLeavesSvg} viewBox="0 0 84 88" fill="none" aria-hidden="true">
                <g className={styles.swaySlowLeft}>
                  <path
                    d="M24 72C10 52 12 26 32 14C44 30 40 56 24 72Z"
                    fill={review.dueCount > 0 ? "#E8BF6A" : "#8BE5C2"}
                    fillOpacity="0.55"
                  />
                </g>
                <g className={styles.swaySlowRight}>
                  <path
                    d="M52 74C68 58 72 32 56 16C42 30 40 56 52 74Z"
                    fill="#23A67A"
                    fillOpacity="0.42"
                  />
                </g>
                <path
                  d="M42 78C26 56 28 26 42 10C56 26 58 56 42 78Z"
                  fill="#F7F7EE"
                  stroke={review.dueCount > 0 ? "#E8BF6A" : "#23A67A"}
                  strokeWidth="1.6"
                />
              </svg>
              <b className={styles.reviewCountNumber}>{review.dueCount}</b>
            </div>
          </article>
        </motion.div>

        {/* Card 3: Classroom Assignments — Organic Garden Task Board */}
        <motion.div variants={fadeUp}>
          <article
            className={`${styles.pulseGardenCard} ${styles.pulseCardAssignment}`}
            style={{ cursor: "pointer" }}
            onClick={() => router.push("/student/attempts?tab=classroom")}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                router.push("/student/attempts?tab=classroom");
              }
            }}
          >
            <div className={styles.metricCopy}>
              <span
                className={`${styles.metricIcon} ${styles.metricIconAssignment}`}
                aria-hidden="true"
              >
                <ClipboardCheck size={19} />
              </span>
              <span className={styles.pulseCardKicker}>Bảng việc trên lớp</span>
              <strong>Bài tập từ lớp</strong>
              <small>
                {!hasClassroomContext
                  ? "Không áp dụng trong lối tự học hiện tại"
                  : assignments.activeCount > 0
                  ? `${assignments.overdueCount} quá hạn · ${assignments.inProgressCount} đang làm · ${assignments.pendingCount} chưa nộp`
                  : "Không có bài cần nộp"}
              </small>
            </div>

            <div className={styles.assignmentBoardVisual}>
              <b>{hasClassroomContext ? assignments.activeCount : "—"}</b>
              <div className={styles.organicBarTrack} aria-hidden="true">
                <motion.span
                  className={styles.organicBarFill}
                  initial={{ scaleX: 0 }}
                  whileInView={{ scaleX: assignmentCompletionRatio }}
                  viewport={{ once: true }}
                  transition={{ duration: shouldAnimate ? 0.85 : 0, ease: [0.22, 1, 0.36, 1] }}
                />
              </div>
              {!hasClassroomContext ? (
                <small>Chưa có ngữ cảnh lớp</small>
              ) : assignments.overdueCount > 0 ? (
                <small className={styles.overdueWarnText}>
                  {assignments.overdueCount} bài quá hạn
                </small>
              ) : assignments.inProgressCount > 0 ? (
                <small>{assignments.inProgressCount} bài đang làm</small>
              ) : assignments.pendingCount > 0 ? (
                <small>{assignments.pendingCount} bài chưa nộp</small>
              ) : (
                <small>Đã hoàn thành tất cả</small>
              )}
            </div>
          </article>
        </motion.div>

        {/* Card 4: Today's Plan — Stepping-Stone Path */}
        <motion.div variants={fadeUp}>
          <article className={`${styles.pulseGardenCard} ${styles.pulseCardPlan}`}>
            <div className={styles.pulseCardTopRow}>
              <div className={styles.metricCopy}>
                <span
                  className={`${styles.metricIcon} ${styles.metricIconMomentum}`}
                  aria-hidden="true"
                >
                  <CalendarCheck size={19} />
                </span>
                <span className={styles.pulseCardKicker}>Lối bước trong ngày</span>
                <strong>Kế hoạch hôm nay</strong>
                <small>
                  {todayPlan
                    ? todayPlan.notice ?? `${todayPlan.totalEstimatedMinutes} phút ước tính`
                    : "Chưa có kế hoạch ngày"}
                </small>
              </div>

              <div
                className={styles.planTrailVisual}
                aria-label={
                  todayPlan
                    ? `Kế hoạch hôm nay: ${todayPlan.completedCount} trên ${todayPlan.totalCount} nhiệm vụ`
                    : "Chưa có kế hoạch hôm nay"
                }
              >
                <b>{todayPlan ? `${todayPlan.completedCount}/${todayPlan.totalCount}` : "—"}</b>
                <div className={styles.steppingStonesRow} aria-hidden="true">
                  {Array.from({ length: totalStones }, (_, idx) => {
                    const isLit = Boolean(todayPlan && idx < litStones);
                    return (
                      <span
                        key={idx}
                        className={`${styles.steppingStoneDot} ${
                          isLit ? styles.steppingStoneLit : ""
                        }`}
                      />
                    );
                  })}
                </div>
                <small>{todayPlan ? `${todayPlan.totalEstimatedMinutes} phút` : "Chưa lập lịch"}</small>
              </div>
            </div>

            {!todayPlan || todayPlan.totalCount === 0 ? (
              <button
                type="button"
                onClick={() => setShowGoalModal(true)}
                className={styles.pulsePlanPrimaryBtn}
              >
                <Sparkles size={14} aria-hidden="true" />
                Gieo lộ trình 7 ngày
              </button>
            ) : (
              <div className={styles.pulsePlanActionStack}>
                <button
                  type="button"
                  onClick={() => setShowRoadmapModal(true)}
                  className={styles.pulsePlanPrimaryBtn}
                >
                  <Compass size={13} aria-hidden="true" />
                  Xem lộ trình 7 ngày
                </button>
                <button
                  type="button"
                  onClick={handleRecalculate}
                  disabled={isRecalculating}
                  className={styles.pulsePlanSecondaryBtn}
                  title="Tái cân bằng khối lượng học 7 ngày theo nhịp mới"
                >
                  <RotateCcw size={11} aria-hidden="true" />
                  {isRecalculating ? "Đang tính..." : "Tái tính nhịp học 7 ngày"}
                </button>
              </div>
            )}
          </article>
        </motion.div>
      </motion.div>

      {/* Actionable Today's Tasks Banner */}
      {todayPlan && todayPlan.tasks && todayPlan.tasks.length > 0 && (
        <div className={styles.todayTasksSection}>
          <div className={styles.todayTasksHeader}>
            <div>
              <span className={styles.todayTasksEyebrow}>Kế hoạch ngày thích ứng</span>
              <h3 className={styles.todayTasksTitle}>🌱 Nhiệm vụ học tập cần hoàn thành hôm nay</h3>
              <p className={styles.todayTasksDescription}>
                Dựa trên năng lực hiện tại và mục tiêu thi cử 2026. Hoàn thành bài tập sẽ tự động cập nhật độ vững của Cây Tri Thức và nhịp học 7 ngày.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setShowRoadmapModal(true)}
              className={styles.openRoadmapButton}
            >
              <CalendarCheck size={16} />
              <span>Xem toàn bộ lộ trình 7 ngày →</span>
            </button>
          </div>

          <div className={styles.todayTasksGrid}>
            {todayPlan.tasks.map((task, idx) => (
              <div
                key={task.id || idx}
                className={`${styles.todayTaskCard} ${task.isCompleted ? styles.todayTaskCardCompleted : ""}`}
              >
                <div className={styles.todayTaskCardHeader}>
                  <span
                    className={`${styles.todayTaskBadge} ${
                      task.taskType === "REPAIR" || task.taskType === "REMEDIAL_PRACTICE"
                        ? styles.badgeRemedial
                        : task.taskType === "REVIEW" || task.taskType === "SPACED_REVIEW"
                        ? styles.badgeReview
                        : task.taskType === "LEARN" || task.taskType === "CONCEPT_ACQUISITION"
                        ? styles.badgeRemedial
                        : styles.badgePractice
                    }`}
                  >
                    {task.taskType === "REPAIR" || task.taskType === "REMEDIAL_PRACTICE"
                      ? "🛠️ Vá lỗ hổng"
                      : task.taskType === "REVIEW" || task.taskType === "SPACED_REVIEW"
                      ? "🔄 Ôn ngắt quãng"
                      : task.taskType === "LEARN"
                      ? "📖 Bài trọng tâm"
                      : task.taskType === "MINI_TEST"
                      ? "🏆 Kiểm tra ngắn"
                      : task.taskType === "EXAM"
                      ? "📝 Luyện đề"
                      : "✍️ Luyện dạng toán"}
                  </span>
                  <span className={styles.todayTaskDuration}>
                    ⏱️ {task.estimatedMinutes} phút
                  </span>
                </div>

                <h4 className={styles.todayTaskTitle}>{task.title}</h4>

                {task.topicName && (
                  <span className={styles.todayTaskTopic}>{task.topicName}</span>
                )}

                <div className={styles.todayTaskFooter}>
                  {task.isCompleted ? (
                    <span className={styles.todayTaskCompletedPill}>
                      <CheckCircle2 size={14} />
                      Đã hoàn thành
                    </span>
                  ) : (
                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                      {(task.taskType === "LEARN" || task.taskType === "CONCEPT_ACQUISITION") && (
                        <a
                          href="/student/theory"
                          className={styles.todayTaskActionBtn}
                          style={{
                            background: "rgba(59, 130, 246, 0.14)",
                            color: "#93c5fd",
                            borderColor: "rgba(59, 130, 246, 0.3)",
                          }}
                        >
                          📖 Xem lý thuyết
                        </a>
                      )}
                      <a
                        href={
                          task.problemTypeId
                            ? `/student/practice?problem_type_id=${task.problemTypeId}&subject_id=${data.subject.id}`
                            : task.conceptId
                            ? `/student/practice?concept_id=${task.conceptId}&subject_id=${data.subject.id}`
                            : `/student/practice?subject_id=${data.subject.id}`
                        }
                        className={styles.todayTaskActionBtn}
                      >
                        ✍️ Luyện ngay
                      </a>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {showGoalModal && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="goal-modal-title"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 9999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "16px",
            background: "rgba(9, 45, 37, 0.65)",
            backdropFilter: "blur(12px)",
          }}
          onClick={() => setShowGoalModal(false)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              width: "min(100%, 480px)",
              background: "#ffffff",
              borderRadius: "20px",
              padding: "24px",
              boxShadow: "0 20px 48px rgba(9, 45, 37, 0.35)",
              border: "1px solid rgba(139, 229, 194, 0.4)",
              display: "flex",
              flexDirection: "column",
              gap: "18px",
            }}
          >
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
              <div>
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "4px 10px",
                    borderRadius: "999px",
                    background: "rgba(35, 166, 122, 0.12)",
                    color: "#23a67a",
                    fontSize: "0.76rem",
                    fontWeight: 700,
                    marginBottom: "6px",
                  }}
                >
                  <Sparkles size={13} />
                  Cá nhân hóa lộ trình
                </span>
                <h3 id="goal-modal-title" style={{ margin: 0, fontSize: "1.25rem", fontWeight: 800, color: "#092d25" }}>
                  Gieo mục tiêu & Sinh lộ trình 7 ngày
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowGoalModal(false)}
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  color: "#6b7280",
                  padding: "4px",
                }}
              >
                <X size={18} />
              </button>
            </div>

            <p style={{ margin: 0, fontSize: "0.85rem", color: "#4b5563", lineHeight: 1.5 }}>
              EduMS sẽ phân tích mục tiêu điểm số và thời lượng học của bạn để sinh lịch học 7 ngày tối ưu nhất cho môn {data.subject.name}.
            </p>

            {/* Step 1: Target Score */}
            <div>
              <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 700, color: "#111827", marginBottom: "8px" }}>
                1. Mục tiêu điểm số môn {data.subject.name}:
              </label>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "8px" }}>
                {[
                  { score: 7.0, label: "7.0+", sub: "Vững cơ bản" },
                  { score: 8.0, label: "8.0+", sub: "Bứt phá khá giỏi" },
                  { score: 9.0, label: "9.0+", sub: "Vận dụng cao" },
                ].map((item) => (
                  <button
                    key={item.score}
                    type="button"
                    onClick={() => setTargetScore(item.score)}
                    style={{
                      padding: "10px 8px",
                      borderRadius: "12px",
                      border: targetScore === item.score ? "2px solid #23a67a" : "1px solid #e5e7eb",
                      background: targetScore === item.score ? "rgba(35, 166, 122, 0.08)" : "#f9fafb",
                      cursor: "pointer",
                      textAlign: "center",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <strong style={{ display: "block", fontSize: "0.95rem", color: targetScore === item.score ? "#23a67a" : "#111827" }}>
                      {item.label}
                    </strong>
                    <span style={{ fontSize: "0.72rem", color: "#6b7280" }}>{item.sub}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Step 2: Available minutes */}
            <div>
              <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 700, color: "#111827", marginBottom: "8px" }}>
                2. Quỹ thời gian tự học mỗi ngày:
              </label>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "8px" }}>
                {[15, 30, 45, 60].map((mins) => (
                  <button
                    key={mins}
                    type="button"
                    onClick={() => setDailyMinutes(mins)}
                    style={{
                      padding: "8px 6px",
                      borderRadius: "10px",
                      border: dailyMinutes === mins ? "2px solid #23a67a" : "1px solid #e5e7eb",
                      background: dailyMinutes === mins ? "rgba(35, 166, 122, 0.08)" : "#f9fafb",
                      cursor: "pointer",
                      textAlign: "center",
                      fontWeight: 700,
                      fontSize: "0.86rem",
                      color: dailyMinutes === mins ? "#23a67a" : "#374151",
                    }}
                  >
                    {mins} phút
                  </button>
                ))}
              </div>
            </div>

            {/* Step 3: Exam */}
            <div
              style={{
                padding: "10px 14px",
                borderRadius: "12px",
                background: "#f0fdf4",
                border: "1px solid #bbf7d0",
                fontSize: "0.82rem",
                color: "#166534",
                display: "flex",
                alignItems: "center",
                gap: "8px",
              }}
            >
              <CalendarCheck size={16} />
              <span>Kỳ thi: <strong>Tốt nghiệp THPT & Tuyển sinh ĐH 2026 (25/06/2026)</strong></span>
            </div>

            {feedbackMsg && (
              <div
                style={{
                  padding: "8px 12px",
                  borderRadius: "8px",
                  background: feedbackMsg.includes("thành công") ? "#dcfce7" : "#fee2e2",
                  color: feedbackMsg.includes("thành công") ? "#15803d" : "#b91c1c",
                  fontSize: "0.82rem",
                  fontWeight: 600,
                }}
              >
                {feedbackMsg}
              </div>
            )}

            <button
              type="button"
              onClick={handleCreateGoal}
              disabled={isSubmitting}
              style={{
                width: "100%",
                padding: "12px",
                borderRadius: "12px",
                background: "linear-gradient(135deg, #23a67a 0%, #10b981 100%)",
                color: "#ffffff",
                border: "none",
                fontWeight: 750,
                fontSize: "0.95rem",
                cursor: isSubmitting ? "wait" : "pointer",
                boxShadow: "0 4px 14px rgba(35, 166, 122, 0.35)",
              }}
            >
              {isSubmitting ? "Đang sinh lộ trình..." : "Khởi tạo lộ trình học tập ngay"}
            </button>
          </div>
        </div>
      )}

      <StudyPlanRoadmapModal
        isOpen={showRoadmapModal}
        onClose={() => setShowRoadmapModal(false)}
        subjectId={data.subject.id}
        onRecalculateDone={() => router.refresh()}
      />
    </section>
  );
}
