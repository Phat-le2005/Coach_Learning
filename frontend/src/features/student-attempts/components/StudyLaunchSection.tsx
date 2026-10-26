"use client";

import { AlertTriangle, FilePenLine, Sprout } from "lucide-react";
import { motion } from "motion/react";

import { StartWorkspaceForm } from "@/app/student/attempts/StartWorkspaceForm";
import { StepReviewDemoForm } from "@/app/student/attempts/StepReviewDemoForm";
import {
  useGardenMotion,
  useGardenSectionInView,
} from "@/features/student-home/components/nature/GardenMotionContext";
import { fadeUp } from "@/lib/motion";

import styles from "../StudentAttempts.module.css";
import type { StudentAttemptsSubjectOption } from "../types";

export interface StudyLaunchSectionProps {
  subjects: StudentAttemptsSubjectOption[];
  subjectsLoaded: boolean;
  defaultSubjectId?: string;
}

export function StudyLaunchSection({
  subjects,
  subjectsLoaded,
  defaultSubjectId,
}: StudyLaunchSectionProps) {
  const { shouldAnimate } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLElement>("160px 0px");
  const isAnimating = shouldAnimate && isInView;

  return (
    <motion.section
      ref={ref}
      id="study-launch-panel"
      className={`${styles.launchSection} ${!isAnimating ? styles.sectionPaused : ""}`}
      aria-labelledby="study-launch-heading"
      variants={fadeUp}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, amount: 0.2 }}
    >
      <div className={styles.launchCard}>
        <div className={styles.launchMain}>
          <div className={styles.launchHeaderRow}>
            <div className={styles.launchIconDual} aria-hidden="true">
              <FilePenLine size={24} strokeWidth={2} />
              <span className={styles.launchSproutAccent}>
                <Sprout size={13} strokeWidth={2.2} />
              </span>
            </div>

            <div>
              <p className={styles.launchEyebrow}>Study Launch Panel · Trang giấy số</p>
              <h2 id="study-launch-heading" className={styles.launchTitle}>
                Bắt đầu một bài làm mới
              </h2>
            </div>
          </div>

          <p className={styles.launchDescription}>
            Hệ thống chỉ chọn câu hỏi thực đã được duyệt. Bạn viết lời giải trực tiếp trên giấy số,
            lưu nét viết tự động và kiểm tra gợi ý nhận diện công thức trước khi xác nhận từng bước.
          </p>

          {subjectsLoaded ? (
            <StartWorkspaceForm subjects={subjects} defaultSubjectId={defaultSubjectId} />
          ) : (
            <div className={styles.launchUnavailableNotice} role="status">
              <AlertTriangle size={18} aria-hidden="true" />
              <span>
                Chưa tải được danh sách môn học để bắt đầu bài mới. Bạn vẫn có thể mở và tiếp tục
                các bài làm đã lưu ở bên dưới.
              </span>
            </div>
          )}
          {process.env.NODE_ENV !== "production" && subjects.some((subject) => subject.code === "MATH_G12") ? (
            <StepReviewDemoForm />
          ) : null}
        </div>

        {/* Animated Open Math Notebook, Poised Pen & Swaying Botanical Sprig */}
        <div className={styles.launchIllustrationWrap} aria-hidden="true">
          <svg className={styles.launchNotebookSvg} viewBox="0 0 260 172" fill="none">
            {/* Soft Desk Shadow */}
            <ellipse cx="128" cy="148" rx="92" ry="12" fill="#092D25" fillOpacity="0.08" />

            {/* Swaying Botanical Sprig Beside the Notebook */}
            <g className={styles.notebookSprigGroup} transform="translate(178, 22)">
              <path
                d="M8 94C18 72 30 48 48 26M22 66C14 54 14 40 22 30M34 48C46 42 58 44 66 54"
                stroke="#23A67A"
                strokeWidth="2.2"
                strokeLinecap="round"
              />
              <path
                d="M22 30C32 34 34 46 26 56C16 50 14 38 22 30Z"
                fill="#8BE5C2"
                fillOpacity="0.85"
              />
              <path
                d="M66 54C56 62 44 60 38 50C48 42 60 44 66 54Z"
                fill="#23A67A"
                fillOpacity="0.72"
              />
              <path
                d="M48 26C54 16 66 14 74 20C68 30 56 32 48 26Z"
                fill="#E8BF6A"
                fillOpacity="0.82"
              />
            </g>

            {/* Open Notebook Cover & Pages */}
            <rect
              x="26"
              y="38"
              width="176"
              height="106"
              rx="14"
              fill="#165A43"
            />
            {/* Left Page */}
            <path
              d="M32 43H111C113 43 114 45 114 47V137C114 135 108 134 102 134H32V43Z"
              fill="#FDFDF9"
            />
            {/* Right Page */}
            <path
              d="M196 43H117C115 43 114 45 114 47V137C114 135 120 134 126 134H196V43Z"
              fill="#F7F7EE"
            />
            {/* Center Spine */}
            <line x1="114" y1="44" x2="114" y2="137" stroke="#D3E4DC" strokeWidth="2" />

            {/* Subtle Math Ruled Lines & Sketched Function Curve */}
            <line x1="44" y1="60" x2="100" y2="60" stroke="#DCEAE3" strokeWidth="1.5" />
            <line x1="44" y1="74" x2="96" y2="74" stroke="#DCEAE3" strokeWidth="1.5" />
            <line x1="44" y1="88" x2="102" y2="88" stroke="#DCEAE3" strokeWidth="1.5" />
            <path
              d="M46 116C58 96 72 96 82 108C90 118 98 114 104 98"
              stroke="#23A67A"
              strokeWidth="2"
              strokeLinecap="round"
            />

            <line x1="126" y1="60" x2="182" y2="60" stroke="#DCEAE3" strokeWidth="1.5" />
            <line x1="126" y1="74" x2="176" y2="74" stroke="#DCEAE3" strokeWidth="1.5" />
            <path
              d="M128 96H164"
              stroke="#165A43"
              strokeOpacity="0.55"
              strokeWidth="2"
              strokeLinecap="round"
            />
            <circle cx="132" cy="114" r="3" fill="#23A67A" />
            <line x1="140" y1="114" x2="178" y2="114" stroke="#8BE5C2" strokeWidth="2.5" strokeLinecap="round" />

            {/* Poised Stylus / Pen Resting Gently Above Right Page */}
            <g className={styles.notebookPenGroup}>
              <path
                d="M158 92L208 42C211 39 216 39 219 42C222 45 222 50 219 53L169 103L154 107L158 92Z"
                fill="#092D25"
              />
              <path d="M158 92L169 103L154 107L158 92Z" fill="#E8BF6A" />
              <path d="M198 52L209 63" stroke="#8BE5C2" strokeWidth="2.2" strokeLinecap="round" />
            </g>
          </svg>
        </div>
      </div>
    </motion.section>
  );
}
