"use client";

import { BookMarked, CalendarCheck, ClipboardCheck, Sprout } from "lucide-react";
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
          <article className={`${styles.pulseGardenCard} ${styles.pulseCardAssignment}`}>
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
          </article>
        </motion.div>
      </motion.div>
    </section>
  );
}
