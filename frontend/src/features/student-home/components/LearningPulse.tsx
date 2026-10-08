"use client";

import { BookMarked, ClipboardCheck, Leaf, Sprout } from "lucide-react";
import { motion } from "motion/react";
import type { CSSProperties } from "react";

import { OrganicCard } from "@/components/ui/OrganicCard";
import { ProgressRing } from "@/components/ui/ProgressRing";
import { fadeUp, staggerContainer } from "@/lib/motion";

import type { StudentHomeViewModel } from "../types";
import styles from "../StudentHome.module.css";
import { SectionHeading } from "./SectionHeading";

export interface LearningPulseProps {
  data: StudentHomeViewModel;
}

type ProgressStyle = CSSProperties & { "--metric-progress": string };

export function LearningPulse({ data }: LearningPulseProps) {
  const completion = data.assignments.completion ?? 0;
  const progressStyle: ProgressStyle = { "--metric-progress": `${Math.min(100, Math.max(0, completion))}%` };

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
        <motion.div variants={fadeUp}>
          <OrganicCard className={`${styles.metricCard} ${styles.metricCardMastery}`} interactive>
            <span className={styles.metricCloud} aria-hidden="true" />
            <div className={styles.metricCopy}>
              <span className={styles.metricIcon} aria-hidden="true">
                <Leaf size={19} />
              </span>
              <strong>{data.mastery.label}</strong>
              <small>Mastery tổng hợp</small>
            </div>
            <ProgressRing value={data.mastery.score} size={76} label={data.mastery.label} />
          </OrganicCard>
        </motion.div>

        <motion.div variants={fadeUp}>
          <OrganicCard className={`${styles.metricCard} ${styles.metricCardReview}`} interactive>
            <span className={styles.metricLight} aria-hidden="true" />
            <div className={styles.metricCopy}>
              <span className={`${styles.metricIcon} ${styles.metricIconReview}`} aria-hidden="true">
                <BookMarked size={19} />
              </span>
              <strong>Nội dung cần ôn</strong>
              <small>Đến hạn hôm nay</small>
            </div>
            <div className={styles.reviewVisual} aria-label={`${data.review.dueCount} nội dung cần ôn`}>
              <span className={styles.reviewLeafBack} />
              <span className={styles.reviewLeafMiddle} />
              <b>{data.review.dueCount}</b>
            </div>
          </OrganicCard>
        </motion.div>

        <motion.div variants={fadeUp}>
          <OrganicCard className={`${styles.metricCard} ${styles.metricCardAssignment}`} interactive>
            <span className={styles.metricRiver} aria-hidden="true" />
            <div className={styles.metricCopy}>
              <span className={`${styles.metricIcon} ${styles.metricIconAssignment}`} aria-hidden="true">
                <ClipboardCheck size={19} />
              </span>
              <strong>Bài tập đang làm</strong>
              <small>{data.assignments.activeCount} bài đang hoạt động</small>
            </div>
            <div className={styles.assignmentVisual} style={progressStyle}>
              <b>{data.assignments.activeCount}</b>
              <span aria-hidden="true"><i /></span>
              <small>{completion}% tiến độ</small>
            </div>
          </OrganicCard>
        </motion.div>

        <motion.div variants={fadeUp}>
          <OrganicCard className={`${styles.metricCard} ${styles.metricCardMomentum}`} interactive>
            <span className={styles.metricLeafTrail} aria-hidden="true" />
            <div className={styles.metricCopy}>
              <span className={`${styles.metricIcon} ${styles.metricIconMomentum}`} aria-hidden="true">
                <Sprout size={19} />
              </span>
              <strong>Nhịp học liên tục</strong>
              <small>{data.momentum.activeDays} ngày gần nhất</small>
            </div>
            <div className={styles.momentumVisual} aria-label={`${data.momentum.activeDays} ngày học liên tục`}>
              <div aria-hidden="true">
                {data.momentum.week.map((active, index) => (
                  <span className={active ? styles.momentumActive : ""} key={`day-${index + 1}`} />
                ))}
              </div>
              <b>{data.momentum.activeDays}</b>
            </div>
          </OrganicCard>
        </motion.div>
      </motion.div>
    </section>
  );
}
