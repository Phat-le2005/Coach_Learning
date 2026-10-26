"use client";

import { ArrowRight, CheckCircle2, ChevronRight, Sparkles } from "lucide-react";
import { motion } from "motion/react";

import { fadeUp, staggerContainer } from "@/lib/motion";

import { getPriorityReasonCopy } from "../copy";
import type { PriorityViewModel } from "../types";
import styles from "../StudentHome.module.css";
import { SectionHeading } from "./SectionHeading";

export interface PriorityPathProps {
  priorities: PriorityViewModel[];
  onSelectPriority?: (priority: PriorityViewModel) => void;
}

export function PriorityPath({ priorities, onSelectPriority }: PriorityPathProps) {
  return (
    <section className={styles.prioritySection} id="priority-path" aria-labelledby="priority-title">
      <SectionHeading
        eyebrow="Bước tiếp theo theo dữ liệu thật"
        title="Lộ trình kiến thức ưu tiên"
        description="Được tính toán từ các mắt xích bạn cần củng cố nhất để tối ưu điểm số."
      />

      <div className={styles.priorityContainerNew}>
        {/* Subtle Ambient Corner Glow */}
        <span
          style={{
            position: "absolute",
            top: "-60px",
            left: "-60px",
            width: "220px",
            height: "220px",
            borderRadius: "50%",
            background: "rgba(99, 201, 154, 0.35)",
            filter: "blur(50px)",
            pointerEvents: "none",
            opacity: 0.4,
          }}
          aria-hidden="true"
        />

        {priorities.length === 0 ? (
          <div style={{ textAlign: "center", padding: "48px 16px" }}>
            <CheckCircle2 size={38} style={{ margin: "0 auto 12px", color: "#10b981" }} />
            <h3 style={{ fontSize: "1.1rem", fontWeight: 750, color: "var(--text-primary)", margin: "0 0 6px" }}>
              Mọi mục tiêu đã hoàn thành!
            </h3>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", margin: 0 }}>
              Bạn đã hoàn thành tốt các bài tập ưu tiên. Hãy mở Vũ trụ tri thức để khám phá thêm.
            </p>
          </div>
        ) : null}

        {priorities.length > 0 ? (
          <motion.ol
            className={styles.priorityListNew}
            variants={staggerContainer}
            initial={false}
            whileInView="visible"
            viewport={{ once: true, amount: 0.2 }}
          >
            {/* Vertical Guide Rail linking steps */}
            <div className={styles.priorityRailNew} aria-hidden="true" />

            {priorities.map((priority, index) => {
              const isFirst = index === 0;
              const mastery = priority.mastery ?? 0;

              return (
                <motion.li
                  variants={fadeUp}
                  key={priority.id}
                  style={{ position: "relative", zIndex: 1, listStyle: "none" }}
                >
                  <div
                    onClick={() => onSelectPriority?.(priority)}
                    className={`${styles.priorityItemNew} ${isFirst ? styles.priorityItemHero : ""}`}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        onSelectPriority?.(priority);
                      }
                    }}
                  >
                    {/* Left: Step Node & Copy */}
                    <div className={styles.priorityItemLeft}>
                      {/* Step Number Circle */}
                      <div className={`${styles.priorityNodeNum} ${isFirst ? styles.priorityNodeNumHero : ""}`}>
                        {index + 1}
                      </div>

                      {/* Content Body */}
                      <div className={styles.priorityItemBody}>
                        <div className={styles.priorityBadgeRow}>
                          {isFirst ? (
                            <span className={styles.priorityHeroPill}>
                              <Sparkles size={11} />
                              Ưu tiên số 1 hôm nay
                            </span>
                          ) : null}
                          <span className={styles.priorityReasonBadge}>
                            {getPriorityReasonCopy(priority.reasonCode)}
                          </span>
                        </div>

                        <h4 className={styles.priorityItemTitle}>
                          {priority.targetName}
                        </h4>

                        <div className={styles.priorityItemMeta}>
                          <span>
                            Độ vững: <strong style={{ color: "var(--text-secondary)" }}>{priority.mastery !== undefined ? `${priority.mastery}%` : "Chưa đo"}</strong>
                          </span>
                          {/* Mini Progress Bar */}
                          <div className={styles.priorityMiniBar}>
                            <div
                              className={styles.priorityMiniFill}
                              style={{ width: `${Math.max(6, mastery)}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Right Action Button */}
                    <div style={{ flexShrink: 0 }}>
                      {isFirst ? (
                        <button
                          type="button"
                          className={styles.priorityActionBtn}
                        >
                          Luyện tập ngay
                          <ArrowRight size={13} style={{ color: "#6ee7b7" }} />
                        </button>
                      ) : (
                        <div className={styles.priorityArrowIcon}>
                          <ChevronRight size={18} />
                        </div>
                      )}
                    </div>
                  </div>
                </motion.li>
              );
            })}
          </motion.ol>
        ) : null}
      </div>
    </section>
  );
}
