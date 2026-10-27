"use client";

import { ArrowRight, ArrowUpRight, Compass, Sparkles, Trees } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { useState } from "react";

import { MasteryBadge } from "@/components/ui/MasteryBadge";
import {
  getMathChapterType,
  MathChapterIllustration,
} from "@/features/knowledge-forest/components/MathChapterIllustration";
import { fadeUp, staggerContainer } from "@/lib/motion";

import { getRegionStateCopy } from "../copy";
import styles from "../StudentHome.module.css";
import type { KnowledgeRegionViewModel } from "../types";
import { SectionHeading } from "./SectionHeading";
import { useGardenMotion, useGardenSectionInView } from "./nature/GardenMotionContext";

export interface KnowledgeGardenProps {
  regions: KnowledgeRegionViewModel[];
  subjectId?: string;
}

interface ChapterGroveTheme {
  themeColor: string;
  canopyTop: string;
  canopyBottom: string;
  accentGlow: string;
  shortTag: string;
  groveName: string;
}

const GROVE_THEMES: ChapterGroveTheme[] = [
  {
    themeColor: "#23A67A",
    canopyTop: "rgba(139, 229, 194, 0.34)",
    canopyBottom: "rgba(35, 166, 122, 0.08)",
    accentGlow: "rgba(35, 166, 122, 0.24)",
    shortTag: "Khảo sát hàm số",
    groveName: "Đảo Đạo Hàm",
  },
  {
    themeColor: "#1E88A8",
    canopyTop: "rgba(184, 227, 222, 0.44)",
    canopyBottom: "rgba(30, 136, 168, 0.08)",
    accentGlow: "rgba(30, 136, 168, 0.22)",
    shortTag: "Mũ & Logarit",
    groveName: "Suối Lôgarit",
  },
  {
    themeColor: "#3D7A68",
    canopyTop: "rgba(139, 229, 194, 0.28)",
    canopyBottom: "rgba(9, 45, 37, 0.08)",
    accentGlow: "rgba(61, 122, 104, 0.22)",
    shortTag: "Vectơ không gian",
    groveName: "Đỉnh Không Gian",
  },
  {
    themeColor: "#C58B2A",
    canopyTop: "rgba(232, 191, 106, 0.34)",
    canopyBottom: "rgba(197, 139, 42, 0.08)",
    accentGlow: "rgba(232, 191, 106, 0.28)",
    shortTag: "Mẫu ghép nhóm",
    groveName: "Đồi Thống Kê",
  },
  {
    themeColor: "#2B937F",
    canopyTop: "rgba(139, 229, 194, 0.36)",
    canopyBottom: "rgba(43, 147, 127, 0.09)",
    accentGlow: "rgba(43, 147, 127, 0.24)",
    shortTag: "Nguyên hàm & Tích phân",
    groveName: "Thung Lũng Tích Phân",
  },
  {
    themeColor: "#1F7A73",
    canopyTop: "rgba(184, 227, 222, 0.4)",
    canopyBottom: "rgba(31, 122, 115, 0.09)",
    accentGlow: "rgba(31, 122, 115, 0.24)",
    shortTag: "Tọa độ Oxyz",
    groveName: "Rừng Tọa Độ",
  },
  {
    themeColor: "#23A67A",
    canopyTop: "rgba(232, 191, 106, 0.25)",
    canopyBottom: "rgba(35, 166, 122, 0.09)",
    accentGlow: "rgba(35, 166, 122, 0.24)",
    shortTag: "Xác suất có điều kiện",
    groveName: "Vườn Xác Suất",
  },
];

export function KnowledgeGarden({ regions, subjectId }: KnowledgeGardenProps) {
  const { shouldAnimate } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLElement>("200px 0px");
  const active = shouldAnimate && isInView;
  const [focusedRegionId, setFocusedRegionId] = useState<string | null>(null);

  const knowledgeHref = subjectId
    ? `/student/knowledge?subject_id=${encodeURIComponent(subjectId)}`
    : "/student/knowledge";

  const focusedRegion = regions.find((r) => r.id === focusedRegionId) ?? null;

  return (
    <section
      ref={ref}
      className={`${styles.section} ${styles.forestSection} ${
        !active ? styles.sectionAnimPaused : ""
      }`}
      id="knowledge-garden"
      aria-labelledby="knowledge-garden-title"
    >
      {/* Dappled Forest Sunlight & Canopy Backdrop */}
      <div className={styles.forestStageAtmosphere} aria-hidden="true">
        <span className={styles.forestSunShaftLeft} />
        <span className={styles.forestSunShaftRight} />

        {/* Interconnected Root / Stream Path weaving across the Grove */}
        <svg
          className={styles.forestRootNetworkSvg}
          viewBox="0 0 1280 340"
          preserveAspectRatio="none"
          fill="none"
        >
          <path
            d="M20 210C210 135 420 275 640 185C860 95 1060 250 1260 165"
            stroke="#23A67A"
            strokeOpacity="0.18"
            strokeWidth="2.5"
            strokeDasharray="8 8"
          />
          <path
            d="M60 250C290 195 510 295 760 215C960 150 1120 230 1250 198"
            stroke="#E8BF6A"
            strokeOpacity="0.22"
            strokeWidth="1.6"
          />
        </svg>
      </div>

      <SectionHeading
        eyebrow="Rừng tri thức · Bản đồ năng lực"
        title="Khu rừng tri thức"
        description="Mỗi chương học là một đảo cây tri thức sống động, kết nối trực tiếp với mô hình toán học và mức độ thành thạo thật của bạn."
        action={
          <Link href={knowledgeHref} className={styles.gardenExploreLink}>
            <Trees size={16} aria-hidden="true" />
            Mở Cây Tri Thức 3D <ArrowUpRight size={15} aria-hidden="true" />
          </Link>
        }
      />

      {regions.length === 0 ? (
        <div className={styles.realDataEmpty}>
          <h3>Chưa có dữ liệu chương và chủ đề</h3>
          <p>
            Dữ liệu học tập chưa trả về cấu trúc chương/chủ đề. EduMS không dựng dữ liệu giả để
            lấp khoảng trống này.
          </p>
        </div>
      ) : null}

      {regions.length > 0 ? (
        <>
          {/* Interactive Chapter Grove Selector Pills */}
          <div className={styles.groveSelectorBar} role="toolbar" aria-label="Chọn cụm chương để làm nổi bật">
            <button
              type="button"
              onClick={() => setFocusedRegionId(null)}
              className={`${styles.grovePill} ${
                focusedRegionId === null ? styles.grovePillActive : ""
              }`}
            >
              <Compass size={13} aria-hidden="true" />
              Toàn khu rừng ({regions.length})
            </button>
            {regions.map((region, idx) => {
              const isSelected = focusedRegionId === region.id;
              return (
                <button
                  key={region.id}
                  type="button"
                  onClick={() =>
                    setFocusedRegionId((prev) => (prev === region.id ? null : region.id))
                  }
                  className={`${styles.grovePill} ${isSelected ? styles.grovePillActive : ""}`}
                >
                  <span>Chương 0{idx + 1}</span>
                  {region.progress !== undefined ? (
                    <em className={styles.grovePillPercent}>{region.progress}%</em>
                  ) : null}
                </button>
              );
            })}
          </div>

          {/* Highlighted Chapter Callout when a specific chapter pill is selected */}
          {focusedRegion ? (
            <div className={styles.focusedGroveBanner}>
              <div>
                <span className={styles.focusedGroveEyebrow}>Đang soi sáng cụm tri thức</span>
                <strong>{focusedRegion.label}</strong>
                <span>
                  {getRegionStateCopy(focusedRegion.state)}
                  {focusedRegion.progress !== undefined
                    ? ` · ${focusedRegion.progress}% thành thạo`
                    : " · Chưa có bài làm đo lường"}
                </span>
              </div>
              <Link
                href={`${knowledgeHref}${
                  knowledgeHref.includes("?") ? "&" : "?"
                }node=${encodeURIComponent(focusedRegion.id)}`}
                className={styles.focusedGroveCta}
              >
                Đi sâu vào nhánh này <ArrowRight size={15} aria-hidden="true" />
              </Link>
            </div>
          ) : null}

          <div className={styles.gardenScrollFrame}>
            <motion.div
              className={styles.gardenGrid}
              variants={staggerContainer}
              initial={false}
              whileInView="visible"
              viewport={{ once: true, amount: 0.12 }}
            >
              {regions.map((region, index) => {
                const mathType = getMathChapterType(region.label, index);
                const cfg = GROVE_THEMES[mathType % GROVE_THEMES.length];
                const chapterHref = `${knowledgeHref}${
                  knowledgeHref.includes("?") ? "&" : "?"
                }node=${encodeURIComponent(region.id)}`;
                const progress = region.progress ?? 0;
                const isHighlighted = focusedRegionId === region.id;
                const isDimmed = focusedRegionId !== null && !isHighlighted;

                return (
                  <motion.div
                    variants={fadeUp}
                    key={region.id}
                    className={`${styles.gardenCardWrap} ${
                      isDimmed ? styles.gardenCardDimmed : ""
                    }`}
                  >
                    <Link
                      href={chapterHref}
                      className={`${styles.groveIslandCard} ${
                        isHighlighted ? styles.groveIslandCardHighlighted : ""
                      }`}
                      onMouseEnter={() => {
                        if (focusedRegionId !== null) setFocusedRegionId(region.id);
                      }}
                    >
                      {/* Botanical Canopy Aura */}
                      <span
                        className={styles.mathCardAmbientGlow}
                        style={{ background: cfg.accentGlow }}
                        aria-hidden="true"
                      />

                      <div>
                        {/* Header Row: Chapter Tag & Mastery Badge */}
                        <div className={styles.groveCardHeaderRow}>
                          <span
                            className={styles.mathChapterBadge}
                            style={{
                              background: `${cfg.themeColor}16`,
                              color: cfg.themeColor,
                              border: `1px solid ${cfg.themeColor}36`,
                            }}
                          >
                            <Sparkles size={11} aria-hidden="true" />
                            Chương 0{index + 1}
                          </span>
                          <MasteryBadge
                            state={region.state === "not_started" ? "not_measured" : region.state}
                            label={getRegionStateCopy(region.state)}
                          />
                        </div>

                        {/* Living Botanical + Math Terrarium Box */}
                        <div
                          className={styles.groveTerrariumBox}
                          style={{
                            background: `linear-gradient(170deg, ${cfg.canopyTop} 0%, ${cfg.canopyBottom} 100%)`,
                          }}
                        >
                          {/* Miniature Swaying Trees & Glowing Spores inside the Island */}
                          <svg
                            className={styles.groveMiniFoliageSvg}
                            viewBox="0 0 260 112"
                            preserveAspectRatio="none"
                            fill="none"
                            aria-hidden="true"
                          >
                            {/* Soft island hill */}
                            <path
                              d="M0 98C65 84 125 94 195 86C225 83 246 88 260 94V112H0V98Z"
                              fill={cfg.themeColor}
                              fillOpacity="0.11"
                            />
                            {/* Swaying miniature tree on left */}
                            <g className={styles.groveMiniTreeSway}>
                              <line
                                x1="20"
                                y1="100"
                                x2="20"
                                y2="74"
                                stroke="#092D25"
                                strokeOpacity="0.32"
                                strokeWidth="2"
                                strokeLinecap="round"
                              />
                              <circle cx="20" cy="70" r="10" fill="#8BE5C2" fillOpacity="0.45" />
                              <circle cx="14" cy="75" r="7" fill="#23A67A" fillOpacity="0.32" />
                            </g>
                            {/* Glowing spores */}
                            <circle cx="238" cy="22" r="2.8" fill="#E8BF6A" fillOpacity="0.8" />
                            <circle cx="42" cy="24" r="2" fill="#23A67A" fillOpacity="0.55" />
                          </svg>

                          <MathChapterIllustration
                            type={mathType}
                            index={index}
                            className={styles.mathIllustrationSvg}
                          />
                        </div>

                        {/* Chapter Full Title */}
                        <h3 className={styles.mathCardTitle} title={region.label}>
                          {region.label}
                        </h3>
                      </div>

                      {/* Footer: Botanical Mastery Bar & Explore Link */}
                      <div>
                        <div className={styles.groveMetaRow}>
                          <span className={styles.groveBiomeTag}>{cfg.shortTag}</span>
                          <span style={{ color: cfg.themeColor }}>
                            {region.progress !== undefined ? `${region.progress}%` : "Chưa đo"}
                          </span>
                        </div>

                        <div className={styles.mathProgressBar}>
                          <motion.div
                            className={styles.mathProgressFill}
                            initial={{ scaleX: 0 }}
                            whileInView={{ scaleX: 1 }}
                            viewport={{ once: true }}
                            transition={{
                              duration: shouldAnimate ? 0.75 : 0,
                              delay: shouldAnimate ? index * 0.05 : 0,
                              ease: [0.22, 1, 0.36, 1],
                            }}
                            style={{
                              width: `${Math.max(7, progress)}%`,
                              transformOrigin: "left center",
                              background: `linear-gradient(90deg, #23A67A, ${cfg.themeColor})`,
                            }}
                          >
                            <span className={styles.mathProgressSparkle} />
                          </motion.div>
                        </div>

                        <div className={styles.mathCardFooter}>
                          <span>Khám phá đảo tri thức</span>
                          <span
                            className={styles.mathActionArrow}
                            style={{
                              background: `${cfg.themeColor}18`,
                              color: cfg.themeColor,
                            }}
                          >
                            <ArrowRight size={14} aria-hidden="true" />
                          </span>
                        </div>
                      </div>
                    </Link>
                  </motion.div>
                );
              })}
            </motion.div>
          </div>
        </>
      ) : null}
    </section>
  );
}
