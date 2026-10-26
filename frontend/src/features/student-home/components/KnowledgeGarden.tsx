"use client";

import { ArrowRight, ArrowUpRight, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { MasteryBadge } from "@/components/ui/MasteryBadge";
import {
  getMathChapterType,
  MathChapterIllustration,
} from "@/features/knowledge-forest/components/MathChapterIllustration";
import { fadeUp, staggerContainer } from "@/lib/motion";

import { getRegionStateCopy } from "../copy";
import type { KnowledgeRegionViewModel } from "../types";
import styles from "../StudentHome.module.css";
import { SectionHeading } from "./SectionHeading";

export interface KnowledgeGardenProps {
  regions: KnowledgeRegionViewModel[];
  subjectId?: string;
}

interface ChapterConfig {
  themeColor: string;
  accentGlow: string;
  shortTag: string;
}

const CHAPTER_CONFIGS: ChapterConfig[] = [
  {
    themeColor: "#10b981", // Ch 1: Đạo hàm
    accentGlow: "rgba(16, 185, 129, 0.22)",
    shortTag: "Khảo sát hàm số",
  },
  {
    themeColor: "#0284c7", // Ch 2: Mũ & Logarit
    accentGlow: "rgba(2, 132, 199, 0.22)",
    shortTag: "Mũ & Logarit",
  },
  {
    themeColor: "#7c3aed", // Ch 3: Vectơ Oxyz
    accentGlow: "rgba(124, 58, 237, 0.22)",
    shortTag: "Vectơ không gian",
  },
  {
    themeColor: "#d97706", // Ch 4: Thống kê
    accentGlow: "rgba(217, 119, 6, 0.22)",
    shortTag: "Mẫu ghép nhóm",
  },
  {
    themeColor: "#e11d48", // Ch 5: Tích phân
    accentGlow: "rgba(225, 29, 72, 0.22)",
    shortTag: "Nguyên hàm & Tích phân",
  },
  {
    themeColor: "#0d9488", // Ch 6: Mặt phẳng Oxyz
    accentGlow: "rgba(13, 148, 136, 0.22)",
    shortTag: "Tọa độ không gian",
  },
  {
    themeColor: "#059669", // Ch 7: Xác suất
    accentGlow: "rgba(5, 150, 105, 0.22)",
    shortTag: "Xác suất có điều kiện",
  },
];

export function KnowledgeGarden({ regions, subjectId }: KnowledgeGardenProps) {
  const knowledgeHref = subjectId
    ? `/student/knowledge?subject_id=${encodeURIComponent(subjectId)}`
    : "/student/knowledge";

  return (
    <section className={styles.section} id="knowledge-garden" aria-labelledby="knowledge-garden-title">
      <SectionHeading
        eyebrow="Bản đồ năng lực"
        title="Chòm sao tri thức"
        description="Mỗi chòm sao tượng trưng cho một chuyên đề toán học trọng tâm với đồ thị, mô hình và công thức đặc trưng."
        action={
          <Link href={knowledgeHref} className={styles.gardenExploreLink}>
            Mở Toàn Cảnh Vũ Trụ <ArrowUpRight size={15} />
          </Link>
        }
      />

      {regions.length === 0 ? (
        <div className={styles.realDataEmpty}>
          <h3>Chưa có dữ liệu chương và chủ đề</h3>
          <p>Dữ liệu học tập chưa trả về cấu trúc chương/chủ đề. EduMS không dựng dữ liệu giả để lấp khoảng trống này.</p>
        </div>
      ) : null}

      {regions.length > 0 ? (
        <div className={styles.gardenScrollFrame}>
          <motion.div
            className={styles.gardenGrid}
            variants={staggerContainer}
            initial={false}
            whileInView="visible"
            viewport={{ once: true, amount: 0.15 }}
          >
            {regions.map((region, index) => {
              const mathType = getMathChapterType(region.label, index);
              const cfg = CHAPTER_CONFIGS[mathType % CHAPTER_CONFIGS.length];
              const chapterHref = `${knowledgeHref}${knowledgeHref.includes("?") ? "&" : "?"}node=${encodeURIComponent(region.id)}`;
              const progress = region.progress ?? 0;

              return (
                <motion.div variants={fadeUp} key={region.id} className={styles.gardenCardWrap}>
                  <Link href={chapterHref} className={styles.mathCard}>
                    {/* Ambient Subtle Nebula Corner Glow */}
                    <span
                      className={styles.mathCardAmbientGlow}
                      style={{ background: cfg.accentGlow }}
                      aria-hidden="true"
                    />

                    {/* Top Content Area */}
                    <div>
                      {/* Chapter Pill & Mastery Badge */}
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "8px", marginBottom: "10px" }}>
                        <span
                          className={styles.mathChapterBadge}
                          style={{
                            background: `${cfg.themeColor}15`,
                            color: cfg.themeColor,
                            border: `1px solid ${cfg.themeColor}35`,
                          }}
                        >
                          <Sparkles size={11} />
                          Chương 0{index + 1}
                        </span>
                        <MasteryBadge
                          state={region.state === "not_started" ? "not_measured" : region.state}
                          label={getRegionStateCopy(region.state)}
                        />
                      </div>

                      {/* Mathematical Problem-Type Visual Illustration */}
                      <div className={styles.mathIllustrationBox}>
                        <MathChapterIllustration
                          type={mathType}
                          index={index}
                          className={styles.mathIllustrationSvg}
                        />
                      </div>

                      {/* Chapter Title */}
                      <h3 className={styles.mathCardTitle} title={region.label}>
                        {region.label}
                      </h3>
                    </div>

                    {/* Footer Area: Mastery Meter & CTA */}
                    <div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", fontSize: "0.75rem", fontWeight: 700, marginBottom: "6px" }}>
                        <span style={{ fontSize: "0.72rem", color: "var(--text-tertiary)" }}>
                          {cfg.shortTag}
                        </span>
                        <span style={{ color: cfg.themeColor }}>
                          {region.progress !== undefined ? `${region.progress}%` : "Chưa đo"}
                        </span>
                      </div>

                      <div className={styles.mathProgressBar}>
                        <div
                          className={styles.mathProgressFill}
                          style={{
                            width: `${Math.max(6, progress)}%`,
                            background: `linear-gradient(90deg, #4f9678, ${cfg.themeColor})`,
                            boxShadow: `0 0 8px ${cfg.themeColor}80`,
                          }}
                        >
                          <span className={styles.mathProgressSparkle} />
                        </div>
                      </div>

                      {/* Bottom Action Row */}
                      <div className={styles.mathCardFooter}>
                        <span>Khám phá chòm sao</span>
                        <span
                          className={styles.mathActionArrow}
                          style={{ background: `${cfg.themeColor}18`, color: cfg.themeColor }}
                        >
                          <ArrowRight size={14} />
                        </span>
                      </div>
                    </div>
                  </Link>
                </motion.div>
              );
            })}
          </motion.div>
        </div>
      ) : null}
    </section>
  );
}
