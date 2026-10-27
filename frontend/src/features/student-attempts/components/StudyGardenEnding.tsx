"use client";

import { ArrowUp, House } from "lucide-react";
import Link from "next/link";

import {
  useGardenMotion,
  useGardenSectionInView,
} from "@/features/student-home/components/nature/GardenMotionContext";

import styles from "../StudentAttempts.module.css";

export interface StudyGardenEndingProps {
  defaultSubjectId?: string;
}

export function StudyGardenEnding({ defaultSubjectId }: StudyGardenEndingProps) {
  const { shouldAnimate } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLElement>("160px 0px");
  const isAnimating = shouldAnimate && isInView;

  const homeHref = defaultSubjectId
    ? `/student?subject_id=${encodeURIComponent(defaultSubjectId)}`
    : "/student";

  return (
    <footer
      ref={ref}
      className={`${styles.endingSection} ${!isAnimating ? styles.sectionPaused : ""}`}
      aria-label="Chân trang không gian bài làm"
    >
      <span className={styles.endingGlow} aria-hidden="true" />

      <svg
        className={styles.endingMeadowSvg}
        viewBox="0 0 960 88"
        preserveAspectRatio="none"
        fill="none"
        aria-hidden="true"
      >
        {/* Rolling Soft Grass Waves */}
        <path
          d="M0 64C150 42 310 44 480 60C650 76 810 46 960 58V88H0V64Z"
          fill="#8BE5C2"
          fillOpacity="0.34"
        />
        <path
          d="M0 72C190 58 370 78 570 64C740 52 865 62 960 70V88H0V72Z"
          fill="#23A67A"
          fillOpacity="0.22"
        />

        {/* Gently Swaying Wildflowers & Grass Blades */}
        <g className={styles.endingFlowerSway} transform="translate(182, 34)">
          <path d="M12 34C12 22 10 12 7 4" stroke="#23A67A" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M12 34C14 24 18 15 22 8" stroke="#1B7C5B" strokeWidth="1.6" strokeLinecap="round" />
          <circle cx="7" cy="4" r="3.5" fill="#E8BF6A" />
          <circle cx="22" cy="8" r="2.8" fill="#F7F7EE" stroke="#23A67A" strokeWidth="1" />
        </g>

        <g className={styles.endingFlowerSwayDelayed} transform="translate(468, 30)">
          <path d="M10 38C10 25 12 14 15 5" stroke="#23A67A" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M10 38C7 27 4 19 1 12" stroke="#1B7C5B" strokeWidth="1.5" strokeLinecap="round" />
          <circle cx="15" cy="5" r="3.4" fill="#8BE5C2" stroke="#1B7C5B" strokeWidth="1" />
        </g>

        <g className={styles.endingFlowerSway} transform="translate(764, 34)">
          <path d="M10 34C10 22 13 13 16 5" stroke="#23A67A" strokeWidth="1.8" strokeLinecap="round" />
          <circle cx="16" cy="5" r="3.5" fill="#E8BF6A" />
        </g>
      </svg>

      <p className={styles.endingCaption}>
        Mỗi bước biến đổi được viết ra là một hạt mầm tri thức lớn dần theo nhịp học của riêng bạn.
      </p>

      <div className={styles.endingActions}>
        <a href="#student-attempts-top" className={styles.endingTopBtn}>
          <ArrowUp size={14} aria-hidden="true" />
          Lên đầu trang
        </a>
        <Link href={homeHref} className={styles.endingTopBtn}>
          <House size={14} aria-hidden="true" />
          Về Khu vườn học tập
        </Link>
      </div>
    </footer>
  );
}
