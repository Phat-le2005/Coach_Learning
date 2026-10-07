"use client";

import { BookOpenCheck, Lightbulb, Shapes, Sprout } from "lucide-react";
import { motion } from "motion/react";

import { OrganicCard } from "@/components/ui/OrganicCard";
import { useHydratedReducedMotion } from "@/lib/use-hydrated-reduced-motion";

import styles from "../StudentHome.module.css";
import { SectionHeading } from "./SectionHeading";

const coachActions = [
  { label: "Gợi ý nhẹ", icon: Lightbulb },
  { label: "Giải thích khái niệm", icon: BookOpenCheck },
  { label: "Ví dụ tương tự", icon: Shapes },
];

export function CoachCard() {
  const reducedMotion = useHydratedReducedMotion();

  return (
    <section className={styles.coachSection} id="coach" aria-labelledby="coach-title">
      <SectionHeading eyebrow="Quiet intelligence" title="Coach" />
      <OrganicCard className={styles.coachCard} variant="accent">
        <div className={styles.coachVisual} aria-hidden="true">
          <span className={styles.coachGuideBeam} />
          <motion.span
            className={styles.coachOrbit}
            animate={reducedMotion ? undefined : { rotate: 360 }}
            transition={{ duration: 18, repeat: Infinity, ease: "linear" }}
          >
            <i />
          </motion.span>
          <span className={styles.coachOrbitSecondary} />
          <span className={styles.coachFireflyOne} />
          <span className={styles.coachFireflyTwo} />
          <span className={styles.coachCore}><Sprout size={25} /></span>
        </div>
        <p className={styles.coachLabel}>Hỗ trợ đúng lúc</p>
        <h2 id="coach-title">Một gợi ý vừa đủ để bạn tự tìm ra bước tiếp theo.</h2>
        <p className={styles.coachCopy}>
          Khi bạn cần một gợi ý, Coach sẽ bắt đầu từ đúng chỗ bạn đang mắc.
        </p>
        <div className={styles.coachActions} aria-label="Tùy chọn Coach đang ở chế độ xem trước">
          {coachActions.map(({ label, icon: Icon }) => (
            <button type="button" key={label} title="Chức năng sẽ được kết nối sau API freeze">
              <Icon size={17} aria-hidden="true" />
              {label}
            </button>
          ))}
        </div>
        <p className={styles.coachFootnote}>Chưa kết nối AI trong phiên bản visual foundation.</p>
      </OrganicCard>
    </section>
  );
}
