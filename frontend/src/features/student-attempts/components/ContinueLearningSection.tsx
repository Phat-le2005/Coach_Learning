"use client";

import { ArrowRight, Clock, FileEdit, Layers, PenTool } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { fadeUp, staggerContainer } from "@/lib/motion";

import styles from "../StudentAttempts.module.css";
import type { AttemptCardViewModel } from "../types";

export interface ContinueLearningSectionProps {
  items: AttemptCardViewModel[];
  totalActiveCount: number;
}

export function ContinueLearningSection({
  items,
  totalActiveCount,
}: ContinueLearningSectionProps) {
  if (items.length === 0) {
    return null;
  }

  const [primary, ...secondary] = items;

  return (
    <motion.section
      className={styles.continueSection}
      aria-labelledby="continue-learning-heading"
      variants={staggerContainer}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.2 }}
    >
      <div className={styles.sectionHeaderRow}>
        <div>
          <p className={styles.sectionEyebrow}>Tiếp nối mạch tư duy</p>
          <h2 id="continue-learning-heading" className={styles.sectionTitle}>
            Bài làm đang thực hiện
          </h2>
          <p className={styles.sectionSubtitle}>
            Quay lại đúng trang giấy số bạn đang viết dở mà không mất nét bút hay bước giải đã lưu.
          </p>
        </div>

        <span className={styles.continueCountPill}>
          <Clock size={14} aria-hidden="true" />
          {totalActiveCount} bài chưa nộp
        </span>
      </div>

      {/* Primary Resumable Attempt Card */}
      <motion.div className={styles.continuePrimaryCard} variants={fadeUp}>
        <div className={styles.continueCardInfo}>
          <div className={styles.continueDocIcon} aria-hidden="true">
            <PenTool size={22} strokeWidth={2} />
          </div>

          <div className={styles.continueTextGroup}>
            <div className={styles.continueBadgeLine}>
              <span
                className={`${styles.statusBadge} ${styles[`tone_${primary.status.tone}`]}`}
              >
                <FileEdit size={12} aria-hidden="true" />
                {primary.status.label}
              </span>
              <span className={styles.codeTag}>#{primary.shortCode}</span>
            </div>

            <h3 className={styles.continueCardTitle}>{primary.title}</h3>

            <div className={styles.continueMetaRow}>
              <span className={styles.continueMetaItem}>
                <Clock size={13} aria-hidden="true" />
                Tạo lúc: {primary.createdAtLabel}
              </span>
              {primary.updatedAtLabel && primary.updatedAtLabel !== primary.createdAtLabel ? (
                <span className={styles.continueMetaItem}>
                  Cập nhật: {primary.updatedAtLabel}
                </span>
              ) : null}
              <span className={styles.continueMetaItem}>
                <Layers size={13} aria-hidden="true" />
                {primary.stepSummaryLabel}
              </span>
            </div>
          </div>
        </div>

        <Link href={primary.href} className={styles.continueResumeBtn}>
          <span>Tiếp tục làm bài</span>
          <ArrowRight size={17} aria-hidden="true" />
        </Link>
      </motion.div>

      {/* Additional Unfinished Attempts (if any) */}
      {secondary.length > 0 ? (
        <motion.div className={styles.continueSecondaryGrid} variants={fadeUp}>
          {secondary.map((item) => (
            <Link key={item.id} href={item.href} className={styles.continueSecondaryCard}>
              <div>
                <div className={styles.continueBadgeLine}>
                  <span
                    className={`${styles.statusBadge} ${styles[`tone_${item.status.tone}`]}`}
                  >
                    {item.status.label}
                  </span>
                  <span className={styles.codeTag}>#{item.shortCode}</span>
                </div>
                <p className={styles.continueSecondaryTitle}>{item.title}</p>
                <p className={styles.continueSecondaryMeta}>
                  Tạo lúc {item.createdAtLabel} · {item.stepSummaryLabel}
                </p>
              </div>
              <span className={styles.continueSecondaryArrow}>
                Tiếp tục
                <ArrowRight size={15} aria-hidden="true" />
              </span>
            </Link>
          ))}
        </motion.div>
      ) : null}
    </motion.section>
  );
}
