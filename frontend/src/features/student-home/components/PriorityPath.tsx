"use client";

import { ArrowRight, CheckCircle2, Compass, Sparkles } from "lucide-react";
import { motion, useScroll, useSpring } from "motion/react";
import { useRef } from "react";

import { fadeUp, staggerContainer } from "@/lib/motion";

import { getPriorityReasonCopy } from "../copy";
import styles from "../StudentHome.module.css";
import type { PriorityViewModel } from "../types";
import { SectionHeading } from "./SectionHeading";
import { useGardenMotion } from "./nature/GardenMotionContext";

export interface PriorityPathProps {
  priorities: PriorityViewModel[];
  onSelectPriority?: (priority: PriorityViewModel) => void;
}

function getMasteryStateText(mastery?: number): string {
  if (mastery === undefined) return "Chưa đo lường";
  if (mastery >= 80) return `Đã vững · ${mastery}%`;
  if (mastery >= 50) return `Đang phát triển · ${mastery}%`;
  return `Cần chăm sóc · ${mastery}%`;
}

export function PriorityPath({ priorities, onSelectPriority }: PriorityPathProps) {
  const { shouldAnimate } = useGardenMotion();
  const containerRef = useRef<HTMLDivElement>(null);

  // Scroll-linked progressive trail drawing along the milestone path
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start 82%", "end 58%"],
  });
  const smoothPathLength = useSpring(scrollYProgress, {
    stiffness: 90,
    damping: 24,
    restDelta: 0.002,
  });

  return (
    <section
      className={`${styles.section} ${styles.journeySection}`}
      id="priority-path"
      aria-labelledby="priority-title"
    >
      <SectionHeading
        eyebrow="Con đường qua khu vườn · Bước tiếp theo"
        title="Lộ trình kiến thức ưu tiên"
        description="Mỗi cột mốc trên lối mòn được chọn lọc từ dữ liệu học thật để giúp bạn tiến bộ vững vàng nhất."
      />

      <div ref={containerRef} className={styles.journeyGardenWrap}>
        {/* Subtle Botanical Trailside Ferns & Soft Sun Glow */}
        <span className={styles.journeyAmbientGlow} aria-hidden="true" />

        {priorities.length === 0 ? (
          <div className={styles.journeyEmptyClearing}>
            <span className={styles.journeyEmptyIcon} aria-hidden="true">
              <CheckCircle2 size={32} />
            </span>
            <h3>Con đường hôm nay đã quang đãng!</h3>
            <p>
              Bạn đã hoàn thành tốt các mục tiêu ưu tiên hiện tại. Hãy dạo bước sang Cây Tri Thức
              3D để khám phá thêm những vùng kiến thức mới.
            </p>
          </div>
        ) : (
          <div className={styles.journeyTimelineStage}>
            {/* Progressive Scroll-Drawn Winding Garden Path SVG */}
            <svg
              className={styles.journeyTrailSvg}
              viewBox="0 0 48 600"
              preserveAspectRatio="none"
              fill="none"
              aria-hidden="true"
            >
              {/* Soft base stone trail */}
              <path
                d="M24 8C34 110 14 210 24 310C34 410 16 500 24 592"
                stroke="rgba(35, 166, 122, 0.18)"
                strokeWidth="3"
                strokeDasharray="6 7"
                strokeLinecap="round"
              />
              {/* Living emerald trail drawn progressively on scroll */}
              <motion.path
                d="M24 8C34 110 14 210 24 310C34 410 16 500 24 592"
                stroke="#23A67A"
                strokeWidth="3.5"
                strokeLinecap="round"
                style={{
                  pathLength: shouldAnimate ? smoothPathLength : 1,
                }}
              />
            </svg>

            <motion.ol
              className={styles.journeyMilestoneList}
              variants={staggerContainer}
              initial={false}
              whileInView="visible"
              viewport={{ once: true, amount: 0.15 }}
            >
              {priorities.map((priority, index) => {
                const isFirst = index === 0;
                const mastery = priority.mastery ?? 0;

                return (
                  <motion.li
                    variants={fadeUp}
                    key={priority.id}
                    className={styles.journeyMilestoneRow}
                  >
                    {/* Milestone Cairn Marker on the Trail */}
                    <div
                      className={`${styles.journeyMarkerCairn} ${
                        isFirst ? styles.journeyMarkerPrimary : ""
                      }`}
                      aria-hidden="true"
                    >
                      <span>{index + 1}</span>
                    </div>

                    {/* Interactive Milestone Card */}
                    <div
                      onClick={() => onSelectPriority?.(priority)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          onSelectPriority?.(priority);
                        }
                      }}
                      role="button"
                      tabIndex={0}
                      className={`${styles.journeyMilestoneCard} ${
                        isFirst ? styles.journeyMilestoneCardPrimary : ""
                      }`}
                    >
                      <div className={styles.journeyCardBody}>
                        <div className={styles.priorityBadgeRow}>
                          {isFirst ? (
                            <span className={styles.priorityHeroPill}>
                              <Sparkles size={11} aria-hidden="true" />
                              Cột mốc ưu tiên số 1
                            </span>
                          ) : null}
                          <span className={styles.priorityReasonBadge}>
                            {getPriorityReasonCopy(priority.reasonCode)}
                          </span>
                          <span className={styles.journeyCodeTag}>{priority.targetCode}</span>
                        </div>

                        <h3 className={styles.journeyMilestoneTitle}>{priority.targetName}</h3>

                        <div className={styles.journeyStatusRow}>
                          <span className={styles.journeyStateLabel}>
                            Trạng thái: <strong>{getMasteryStateText(priority.mastery)}</strong>
                          </span>
                          <div className={styles.priorityMiniBar} aria-hidden="true">
                            <div
                              className={styles.priorityMiniFill}
                              style={{ width: `${Math.max(8, mastery)}%` }}
                            />
                          </div>
                        </div>
                      </div>

                      <div className={styles.journeyCardAction}>
                        <span
                          className={
                            isFirst ? styles.priorityActionBtn : styles.journeySecondaryBtn
                          }
                        >
                          {isFirst ? (
                            <>
                              Khám phá mốc này
                              <ArrowRight size={14} aria-hidden="true" />
                            </>
                          ) : (
                            <>
                              <Compass size={14} aria-hidden="true" />
                              Xem lộ trình
                            </>
                          )}
                        </span>
                      </div>
                    </div>
                  </motion.li>
                );
              })}
            </motion.ol>
          </div>
        )}
      </div>
    </section>
  );
}
