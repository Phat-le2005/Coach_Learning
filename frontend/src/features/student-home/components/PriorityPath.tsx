"use client";

import { ArrowRight, Route } from "lucide-react";
import { motion } from "motion/react";

import { OrganicCard } from "@/components/ui/OrganicCard";
import { fadeUp, staggerContainer } from "@/lib/motion";

import { getPriorityReasonCopy } from "../copy";
import type { PriorityViewModel } from "../types";
import styles from "../StudentHome.module.css";
import { SectionHeading } from "./SectionHeading";

export interface PriorityPathProps {
  priorities: PriorityViewModel[];
}

export function PriorityPath({ priorities }: PriorityPathProps) {
  return (
    <section className={styles.prioritySection} id="priority-path" aria-labelledby="priority-title">
      <SectionHeading
        eyebrow="Bước tiếp theo"
        title="Lộ trình ưu tiên"
        description="Tập trung vào những mắt xích tạo ra thay đổi lớn nhất."
      />
      <OrganicCard className={styles.priorityCard} variant="solid">
        <span className={styles.priorityCardIcon} aria-hidden="true"><Route size={21} /></span>
        <motion.ol
          className={styles.priorityList}
          variants={staggerContainer}
          initial={false}
          whileInView="visible"
          viewport={{ once: true, amount: 0.2 }}
        >
          {priorities.map((priority, index) => (
            <motion.li
              className={index === 0 ? styles.priorityItemActive : styles.priorityItem}
              variants={fadeUp}
              key={priority.id}
            >
              <span className={styles.priorityNode}>{index + 1}</span>
              <div className={styles.priorityCopy}>
                <small>{getPriorityReasonCopy(priority.reasonCode)}</small>
                <h3>{priority.targetName}</h3>
                <p>
                  {priority.mastery === undefined
                    ? "Chưa có đủ bằng chứng để đo độ vững"
                    : `Độ vững hiện tại ${priority.mastery}%`}
                </p>
              </div>
              <button type="button" className={styles.priorityAction} aria-label={`Mở ${priority.targetName}`}>
                <ArrowRight size={18} />
              </button>
            </motion.li>
          ))}
        </motion.ol>
      </OrganicCard>
    </section>
  );
}
