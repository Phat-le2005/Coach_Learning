"use client";

import { ArrowRight, BookOpenText, Sprout } from "lucide-react";
import { motion } from "motion/react";

import { GradientButton } from "@/components/ui/GradientButton";
import { fadeUp } from "@/lib/motion";

import styles from "../StudentHome.module.css";
import type { StudentHomeViewModel } from "../types";
import { useGardenMotion, useGardenSectionInView } from "./nature/GardenMotionContext";

export interface PracticePathwayProps {
  data: StudentHomeViewModel;
}

export function PracticePathway({ data }: PracticePathwayProps) {
  const { shouldAnimate } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLElement>("160px 0px");
  const active = shouldAnimate && isInView;
  const isSelfStudyOnboarding = data.learningContext.mode === "SELF_STUDY_ONBOARDING";
  const hasNoSubjects = data.availableSubjects.length === 0;

  return (
    <section
      ref={ref}
      className={`${styles.pathwaySection} ${!active ? styles.sectionAnimPaused : ""}`}
      aria-label="Lối đi vào trang làm bài"
    >
      {/* Optional Self-Study Onboarding or Empty Subject Gate */}
      {isSelfStudyOnboarding ? (
        <motion.div
          className={styles.gardenGateBanner}
          variants={fadeUp}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, amount: 0.25 }}
        >
          <span className={styles.selfStudyIcon} aria-hidden="true">
            <Sprout size={22} />
          </span>
          <div className={styles.selfStudyCopy}>
            <p className={styles.selfStudyEyebrow}>Lối học cá nhân</p>
            <h2>Bắt đầu tự học {data.subject.name}</h2>
            <p>
              Khám phá chương, chủ đề và dạng bài đã được phát hành. Bạn không cần tham gia lớp
              hoặc đặt mục tiêu thi để bắt đầu.
            </p>
          </div>
          <GradientButton
            href={`/student/knowledge?subject_id=${encodeURIComponent(data.subject.id)}`}
          >
            Bắt đầu tự học
            <ArrowRight size={17} aria-hidden="true" />
          </GradientButton>
        </motion.div>
      ) : hasNoSubjects ? (
        <div className={styles.realDataEmpty}>
          <h3>Chưa có môn tự học được phát hành</h3>
          <p>
            Tài khoản chưa có hoạt động học tập và hệ thống chưa phát hành môn tự học phù hợp.
            EduMS không dùng dữ liệu staging hoặc số liệu giả để lấp trạng thái này.
          </p>
        </div>
      ) : null}

      {/* Main Garden Pathway Signpost Card */}
      <motion.div
        className={styles.pathwayClearing}
        variants={fadeUp}
        initial={false}
        whileInView="visible"
        viewport={{ once: true, amount: 0.2 }}
      >
        {/* Background Curved Garden Trail, Low Shrubs & Swaying Wildflowers SVG */}
        <svg
          className={styles.pathwaySceneSvg}
          viewBox="0 0 1200 185"
          preserveAspectRatio="none"
          fill="none"
          aria-hidden="true"
        >
          <defs>
            <linearGradient id="gardenTrailFill" x1="0" y1="0" x2="1200" y2="0" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#E8BF6A" stopOpacity="0.06" />
              <stop offset="50%" stopColor="#E8BF6A" stopOpacity="0.22" />
              <stop offset="100%" stopColor="#8BE5C2" stopOpacity="0.14" />
            </linearGradient>
          </defs>

          {/* Soft Winding Garden Footpath */}
          <path
            d="M-30 162C195 118 405 174 635 138C845 106 1020 144 1230 116V185H-30V162Z"
            fill="url(#gardenTrailFill)"
          />
          <path
            d="M-20 156C205 114 410 168 640 134C850 102 1025 138 1220 112"
            stroke="#23A67A"
            strokeOpacity="0.22"
            strokeWidth="1.8"
            strokeDasharray="7 7"
          />

          {/* Low Verdant Shrubs Left & Right */}
          <path
            d="M16 185C16 156 42 142 68 148C82 132 114 134 128 154C146 148 168 160 172 185H16Z"
            fill="#8BE5C2"
            fillOpacity="0.34"
          />
          <path
            d="M1018 185C1022 158 1046 146 1072 152C1088 134 1122 136 1138 156C1156 150 1178 162 1184 185H1018Z"
            fill="#23A67A"
            fillOpacity="0.18"
          />

          {/* Swaying Wildflowers Left */}
          <g className={styles.pathwayFlowerSway}>
            <path d="M88 182Q92 154 84 136" stroke="#23A67A" strokeOpacity="0.55" strokeWidth="1.6" strokeLinecap="round" />
            <circle cx="84" cy="134" r="4.5" fill="#F7F7EE" />
            <circle cx="84" cy="134" r="2.2" fill="#E8BF6A" />

            <path d="M112 184Q118 162 124 146" stroke="#23A67A" strokeOpacity="0.48" strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="124" cy="144" r="4" fill="#8BE5C2" />
            <circle cx="124" cy="144" r="1.8" fill="#092D25" />
          </g>

          {/* Swaying Wildflowers Right */}
          <g className={styles.pathwayFlowerSwayDelayed}>
            <path d="M1086 183Q1080 154 1090 135" stroke="#23A67A" strokeOpacity="0.55" strokeWidth="1.6" strokeLinecap="round" />
            <circle cx="1090" cy="133" r="4.5" fill="#F7F7EE" />
            <circle cx="1090" cy="133" r="2.2" fill="#E8BF6A" />

            <path d="M1116 184Q1122 162 1114 147" stroke="#23A67A" strokeOpacity="0.45" strokeWidth="1.4" strokeLinecap="round" />
            <circle cx="1114" cy="145" r="3.8" fill="#E8BF6A" />
          </g>
        </svg>

        {/* Garden Signpost Card */}
        <div className={styles.pathwaySignpostCard}>
          <div className={styles.pathwaySignpostIconWrap} aria-hidden="true">
            <span className={styles.pathwaySignpostPost} />
            <span className={styles.selfStudyIcon}>
              <BookOpenText size={22} />
            </span>
          </div>

          <div className={styles.selfStudyCopy}>
            <p className={styles.selfStudyEyebrow}>Trang làm bài · Lối đi thực hành</p>
            <h2>Viết lời giải trên giấy số</h2>
            <p>
              Mở bài làm đã có hoặc bắt đầu từ câu hỏi được duyệt. Bạn luôn kiểm tra công thức OCR
              trước khi xác nhận.
            </p>
          </div>

          <div className={styles.pathwayCtaCluster}>
            <span className={styles.ctaFireflyOne} aria-hidden="true" />
            <span className={styles.ctaFireflyTwo} aria-hidden="true" />
            <span className={styles.ctaFireflyThree} aria-hidden="true" />
            <GradientButton href="/student/attempts">
              Vào trang làm bài
              <ArrowRight size={17} aria-hidden="true" />
            </GradientButton>
          </div>
        </div>
      </motion.div>
    </section>
  );
}
