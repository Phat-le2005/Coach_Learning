"use client";

import { BookOpenCheck, Clock3, House, Leaf, PenLine } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import {
  useGardenMotion,
  useGardenSectionInView,
} from "@/features/student-home/components/nature/GardenMotionContext";
import { fadeUp, staggerContainer } from "@/lib/motion";

import styles from "../StudentAttempts.module.css";

export interface StudyWelcomeHeroProps {
  totalAttempts: number;
  activeAttemptsCount: number;
  defaultSubjectId?: string;
}

export function StudyWelcomeHero({
  totalAttempts,
  activeAttemptsCount,
  defaultSubjectId,
}: StudyWelcomeHeroProps) {
  const { shouldAnimate } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLElement>("140px 0px");
  const isAnimating = shouldAnimate && isInView;

  const homeHref = defaultSubjectId
    ? `/student?subject_id=${encodeURIComponent(defaultSubjectId)}`
    : "/student";

  return (
    <motion.section
      ref={ref}
      className={`${styles.hero} ${!isAnimating ? styles.heroPaused : ""}`}
      aria-labelledby="study-garden-hero-title"
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
    >
      {/* Left: Breadcrumb, Heading, Description, Real Summary Pills & Quick Anchor */}
      <motion.div className={styles.heroCopy} variants={fadeUp}>
        <nav className={styles.breadcrumb} aria-label="Đường dẫn">
          <Link href={homeHref} className={styles.breadcrumbLink}>
            <House size={14} aria-hidden="true" />
            <span>Khu vườn học tập</span>
          </Link>
          <span className={styles.breadcrumbSep} aria-hidden="true">
            /
          </span>
          <span className={styles.breadcrumbCurrent} aria-current="page">
            Không gian bài làm
          </span>
        </nav>

        <div className={styles.heroBadgeRow}>
          <span className={styles.heroSanctuaryBadge}>
            <Leaf size={12} aria-hidden="true" />
            Góc học tập yên tĩnh · Living Study Garden
          </span>

          <span className={styles.heroStatPill}>
            <BookOpenCheck size={13} aria-hidden="true" />
            {totalAttempts === 0
              ? "Sẵn sàng cho bài đầu tiên"
              : `${totalAttempts} lượt làm bài đã lưu`}
          </span>

          {activeAttemptsCount > 0 ? (
            <span className={styles.heroStatPill}>
              <Clock3 size={13} aria-hidden="true" />
              {activeAttemptsCount} bài đang mở
            </span>
          ) : null}
        </div>

        <h1 id="study-garden-hero-title" className={styles.heroTitle}>
          Không gian bài làm
        </h1>
        <p className={styles.heroSubtitle}>
          Nơi lưu giữ từng bước giải và hành trình tiến bộ của bạn.
        </p>

        <div className={styles.heroQuickActions}>
          <a href="#study-launch-panel" className={styles.heroJumpBtn}>
            <PenLine size={16} aria-hidden="true" />
            Bắt đầu bài mới
          </a>
          <Link href={homeHref} className={styles.heroSecondaryLink}>
            Về khu vườn trung tâm
          </Link>
        </div>
      </motion.div>

      {/* Right: Multi-layered Animated Study Garden Corner SVG Diorama */}
      <motion.div className={styles.heroDioramaWrap} variants={fadeUp} aria-hidden="true">
        <svg
          className={styles.heroDioramaSvg}
          viewBox="0 0 520 230"
          preserveAspectRatio="xMidYMid slice"
          fill="none"
        >
          <defs>
            <radialGradient id="studySunGrad" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#F7F7EE" stopOpacity="0.92" />
              <stop offset="45%" stopColor="#E8BF6A" stopOpacity="0.46" />
              <stop offset="100%" stopColor="#E8BF6A" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="studyBeamGrad" x1="120" y1="10" x2="310" y2="220" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#F7F7EE" stopOpacity="0.28" />
              <stop offset="60%" stopColor="#8BE5C2" stopOpacity="0.08" />
              <stop offset="100%" stopColor="#092D25" stopOpacity="0" />
            </linearGradient>
          </defs>

          {/* Soft Morning Sun & Diagonal Beam */}
          <circle
            className={styles.dioramaSunGlow}
            cx="118"
            cy="52"
            r="52"
            fill="url(#studySunGrad)"
          />
          <polygon points="88,0 168,0 326,230 205,230" fill="url(#studyBeamGrad)" />

          {/* Thin Drifting Clouds */}
          <g className={styles.dioramaCloudOne} opacity="0.28">
            <path
              d="M14 54H98C105 54 111 49 111 42C111 36 106 31 99 30C96 25 90 22 84 22C76 22 70 26 67 33C64 31 60 30 56 30C47 30 40 36 39 44C36 43 33 42 30 42C22 42 16 47 14 54Z"
              fill="#F7F7EE"
            />
          </g>
          <g className={styles.dioramaCloudTwo} opacity="0.2">
            <path
              d="M40 82H112C118 82 123 78 123 72C123 67 119 63 113 62C110 58 105 56 100 56C93 56 88 59 86 65C83 63 80 62 76 62C69 62 63 67 62 74C59 73 57 72 54 72C47 72 42 76 40 82Z"
              fill="#B8E3DE"
            />
          </g>

          {/* Occasional Distant Bird Pair Gliding Along a Gentle Bezier Arc */}
          <g className={styles.dioramaBirdArc}>
            <g transform="translate(36, 48) scale(0.75)">
              <path
                className={styles.dioramaBirdWing}
                d="M0 6C4 1 9 0 13 5C17 0 22 1 26 6C21 4 16 5 13 8C10 5 5 4 0 6Z"
                fill="#F7F7EE"
              />
            </g>
            <g transform="translate(16, 56) scale(0.58)">
              <path
                className={styles.dioramaBirdWingDelayed}
                d="M0 6C4 1 9 0 13 5C17 0 22 1 26 6C21 4 16 5 13 8C10 5 5 4 0 6Z"
                fill="#B8E3DE"
              />
            </g>
          </g>

          {/* Multi-layered Mountains & Rolling Garden Hills */}
          <path
            d="M0 166L76 124C106 108 142 110 170 128L252 174L344 118C374 100 412 102 440 122L520 172V230H0V166Z"
            fill="#8BE5C2"
            fillOpacity="0.18"
          />
          <path
            d="M0 186C98 156 196 152 292 178C388 204 452 162 520 174V230H0V186Z"
            fill="#23A67A"
            fillOpacity="0.34"
          />
          <path
            d="M0 202C128 186 248 210 378 192C442 183 488 188 520 196V230H0V202Z"
            fill="#092D25"
            fillOpacity="0.72"
          />

          {/* Cozy Garden Study Bench & Open Book Table Under the Tree */}
          <g transform="translate(262, 162)">
            <rect x="8" y="22" width="54" height="4.5" rx="2.2" fill="#E8BF6A" fillOpacity="0.82" />
            <rect x="16" y="26.5" width="4" height="14" rx="1.5" fill="#092D25" />
            <rect x="50" y="26.5" width="4" height="14" rx="1.5" fill="#092D25" />
            {/* Open Notebook Resting on the Garden Table */}
            <path
              d="M21 21.5C26 19 31 19.5 35 21.5C39 19.5 44 19 49 21.5L47 16.5C42 15 38 15.8 35 17.8C32 15.8 28 15 23 16.5L21 21.5Z"
              fill="#F7F7EE"
            />
            {/* Warm Study Lantern Glow */}
            <circle cx="56" cy="17" r="4" fill="#E8BF6A" />
            <circle cx="56" cy="17" r="10" fill="#E8BF6A" fillOpacity="0.26" />
          </g>

          {/* Stylized Swaying Study Shade Tree */}
          <g transform="translate(348, 28)">
            {/* Trunk & Branches */}
            <path
              d="M66 174C65 142 68 114 62 84C58 66 44 52 28 44M63 96C78 80 96 70 112 64M60 76C48 64 34 58 20 56"
              stroke="#092D25"
              strokeWidth="7"
              strokeLinecap="round"
            />
            <path
              d="M66 174C65 142 68 114 62 84"
              stroke="#23A67A"
              strokeOpacity="0.35"
              strokeWidth="2.5"
              strokeLinecap="round"
            />
            {/* Swaying Layered Canopy */}
            <g className={styles.dioramaTreeCanopy}>
              <ellipse cx="62" cy="52" rx="58" ry="36" fill="#17694E" />
              <ellipse cx="32" cy="60" rx="38" ry="26" fill="#23A67A" fillOpacity="0.88" />
              <ellipse cx="92" cy="62" rx="36" ry="24" fill="#1E8A66" />
              <g className={styles.dioramaLeafCluster}>
                <ellipse cx="54" cy="36" rx="34" ry="20" fill="#8BE5C2" fillOpacity="0.44" />
                <circle cx="28" cy="48" r="3" fill="#E8BF6A" fillOpacity="0.82" />
                <circle cx="88" cy="44" r="2.6" fill="#F7F7EE" fillOpacity="0.7" />
              </g>
            </g>
          </g>

          {/* Two Gentle Leaves Drifting from the Study Tree in the Breeze */}
          <g className={styles.dioramaFloatingLeafOne} transform="translate(366, 86)">
            <path d="M10 1C5 2 1 5 1 10C6 10 9 7 10 1Z" fill="#8BE5C2" />
          </g>
          <g className={styles.dioramaFloatingLeafTwo} transform="translate(394, 98)">
            <path d="M9 1C4 2 1 5 1 9C5 9 8 6 9 1Z" fill="#E8BF6A" />
          </g>
        </svg>
      </motion.div>
    </motion.section>
  );
}
