"use client";

import { BookMarked, CalendarCheck, ClipboardCheck, Leaf } from "lucide-react";
import { motion } from "motion/react";

import { OrganicCard } from "@/components/ui/OrganicCard";
import { ProgressRing } from "@/components/ui/ProgressRing";
import { fadeUp, staggerContainer } from "@/lib/motion";

import type { StudentHomeViewModel } from "../types";
import styles from "../StudentHome.module.css";
import { SectionHeading } from "./SectionHeading";

export interface LearningPulseProps {
  data: StudentHomeViewModel;
}

export function LearningPulse({ data }: LearningPulseProps) {
  const mastery = data.mastery;
  const review = data.review;
  const assignments = data.assignments;
  const todayPlan = data.todayPlan;

  return (
    <section className={styles.section} id="learning-pulse" aria-labelledby="learning-pulse-title">
      <SectionHeading
        eyebrow="Tín hiệu hiện tại"
        title="Nhịp học hôm nay"
        description="Một góc nhìn ngắn gọn để bạn biết mình đang ở đâu."
      />
      <motion.div
        className={styles.pulseGrid}
        variants={staggerContainer}
        initial={false}
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
      >
        {/* Card 1: Evidence-based Mastery */}
        <motion.div variants={fadeUp}>
          <OrganicCard className={`${styles.metricCard} ${styles.metricCardMastery}`} interactive>
            <span className={styles.metricCloud} aria-hidden="true" />
            <div className={styles.metricCopy}>
              <span className={styles.metricIcon} aria-hidden="true">
                <Leaf size={19} />
              </span>
              <strong>{mastery.label}</strong>
              <small>
                {mastery.hasEvidence
                  ? `${mastery.masteredProblemTypeCount} dạng vững · ${mastery.weakProblemTypeCount} dạng yếu`
                  : "Chưa đủ dữ liệu bài làm"}
              </small>
            </div>
            <ProgressRing value={mastery.score} size={76} label={mastery.label} />
          </OrganicCard>
        </motion.div>

        {/* Card 2: Due Reviews */}
        <motion.div variants={fadeUp}>
          <OrganicCard className={`${styles.metricCard} ${styles.metricCardReview}`} interactive>
            <span className={styles.metricLight} aria-hidden="true" />
            <div className={styles.metricCopy}>
              <span className={`${styles.metricIcon} ${styles.metricIconReview}`} aria-hidden="true">
                <BookMarked size={19} />
              </span>
              <strong>Nội dung cần ôn</strong>
              <small>{review.dueCount > 0 ? "Đến hạn ôn tập hôm nay" : "Đã hoàn thành các lượt ôn"}</small>
            </div>
            <div className={styles.reviewVisual} aria-label={`${review.dueCount} nội dung cần ôn`}>
              <span className={styles.reviewLeafBack} />
              <span className={styles.reviewLeafMiddle} />
              <b>{review.dueCount}</b>
            </div>
          </OrganicCard>
        </motion.div>

        {/* Card 3: Assignments Needing Attention */}
        <motion.div variants={fadeUp}>
          <OrganicCard className={`${styles.metricCard} ${styles.metricCardAssignment}`} interactive>
            <span className={styles.metricRiver} aria-hidden="true" />
            <div className={styles.metricCopy}>
              <span className={`${styles.metricIcon} ${styles.metricIconAssignment}`} aria-hidden="true">
                <ClipboardCheck size={19} />
              </span>
              <strong>Bài tập cần xử lý</strong>
              <small>
                {assignments.activeCount > 0
                  ? `${assignments.overdueCount} quá hạn · ${assignments.inProgressCount} đang làm · ${assignments.pendingCount} chưa nộp`
                  : "Không có bài cần nộp"}
              </small>
            </div>
            <div className={styles.assignmentVisual}>
              <b>{assignments.activeCount}</b>
              {assignments.overdueCount > 0 ? (
                <small style={{ color: "var(--amber-700, #b45309)", fontWeight: 650 }}>
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
          </OrganicCard>
        </motion.div>

        {/* Card 4: Today's Plan */}
        <motion.div variants={fadeUp}>
          <OrganicCard className={`${styles.metricCard} ${styles.metricCardMomentum}`} interactive>
            <span className={styles.metricLeafTrail} aria-hidden="true" />
            <div className={styles.metricCopy}>
              <span className={`${styles.metricIcon} ${styles.metricIconMomentum}`} aria-hidden="true">
                <CalendarCheck size={19} />
              </span>
              <strong>Kế hoạch hôm nay</strong>
              <small>
                {todayPlan
                  ? (todayPlan.notice ?? `${todayPlan.totalEstimatedMinutes} phút ước tính`)
                  : "Chưa có kế hoạch ngày"}
              </small>
            </div>
            <div
              className={styles.momentumVisual}
              aria-label={
                todayPlan
                  ? `Kế hoạch hôm nay: ${todayPlan.completedCount} trên ${todayPlan.totalCount} nhiệm vụ`
                  : "Chưa có kế hoạch hôm nay"
              }
            >
              <b>{todayPlan ? `${todayPlan.completedCount}/${todayPlan.totalCount}` : "—"}</b>
              <small>{todayPlan ? `${todayPlan.totalEstimatedMinutes} phút` : "Chưa lập lịch"}</small>
            </div>
          </OrganicCard>
        </motion.div>
      </motion.div>
    </section>
  );
}
