"use client";

import { motion, useScroll, useTransform } from "motion/react";
import type { CSSProperties } from "react";

import {
  BotanicalLeafSvg,
  type LeafShape,
} from "@/features/student-home/components/nature/BirdsAndLeaves";
import { CloudLayer } from "@/features/student-home/components/nature/CloudLayer";
import { FloatingParticles } from "@/features/student-home/components/nature/FloatingParticles";
import { useGardenMotion } from "@/features/student-home/components/nature/GardenMotionContext";

import styles from "../StudentAttempts.module.css";

interface StudyMarginLeaf {
  left: string;
  size: number;
  dur: string;
  del: string;
  sway: string;
  drift: string;
  shape: LeafShape;
  color: string;
}

// Calmer, sparser margin leaf density than Student Home so reading & study focus stay serene
const STUDY_MARGIN_LEAVES: StudyMarginLeaf[] = [
  {
    left: "3.4%",
    size: 17,
    dur: "23s",
    del: "-4s",
    sway: "4.6s",
    drift: "34px",
    shape: "bodhi",
    color: "#23A67A",
  },
  {
    left: "92.2%",
    size: 16,
    dur: "25s",
    del: "-13s",
    sway: "4.9s",
    drift: "-32px",
    shape: "willow",
    color: "#8BE5C2",
  },
  {
    left: "8.8%",
    size: 15,
    dur: "27s",
    del: "-19s",
    sway: "4.4s",
    drift: "26px",
    shape: "sunlit",
    color: "#E8BF6A",
  },
];

export function StudyGardenBackdrop() {
  const { shouldAnimate, isMobile } = useGardenMotion();
  const { scrollYProgress } = useScroll();

  const enableParallax = shouldAnimate && !isMobile;
  const horizonY = useTransform(
    scrollYProgress,
    [0, 1],
    enableParallax ? ["0%", "-10%"] : ["0%", "0%"]
  );

  const visibleLeaves = isMobile ? STUDY_MARGIN_LEAVES.slice(0, 1) : STUDY_MARGIN_LEAVES;

  return (
    <>
      <div
        className={`${styles.studyBackdropRoot} ${!shouldAnimate ? styles.backdropPaused : ""}`}
        aria-hidden="true"
      >
        {/* 1. Soft Morning Study Light Layer */}
        <div className={styles.studySunlightLayer}>
          <span className={styles.studySunRayPrimary} />
          {!isMobile ? <span className={styles.studySunRaySecondary} /> : null}
        </div>

        {/* 2. Distant Layered Garden Hills with Subtle Scroll Parallax */}
        <motion.div className={styles.studyHorizonLayer} style={{ y: horizonY }}>
          <svg
            className={styles.studyHorizonSvg}
            viewBox="0 0 1440 380"
            preserveAspectRatio="none"
            fill="none"
          >
            <path
              d="M0 268L155 204C202 184 258 190 306 214L435 272L610 176C658 148 720 152 764 184L935 292L1105 190C1154 160 1216 164 1262 198L1440 304V380H0V268Z"
              fill="#B8E3DE"
              fillOpacity="0.42"
            />
            <path
              d="M0 312C195 262 365 256 545 298C725 340 930 248 1145 278C1280 296 1372 320 1440 332V380H0V312Z"
              fill="#8BE5C2"
              fillOpacity="0.24"
            />
          </svg>
        </motion.div>

        {/* 3. Reused CloudLayer from Student Home at calmer density */}
        <CloudLayer depth="far" count={isMobile ? 1 : 2} />
        {!isMobile ? <CloudLayer depth="near" count={1} /> : null}

        {/* 4. Subtle Swaying Edge Foliage */}
        <svg className={styles.studyEdgeBoughLeft} viewBox="0 0 220 220" fill="none">
          <path
            d="M-8 38C40 48 86 72 132 108M34 52C58 36 86 32 114 40M56 76C68 104 88 126 114 142"
            stroke="#23A67A"
            strokeOpacity="0.4"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M114 40C98 26 80 28 68 42C86 48 102 48 114 40Z"
            fill="#8BE5C2"
            fillOpacity="0.58"
          />
          <path
            d="M132 108C150 98 168 106 176 122C156 128 140 122 132 108Z"
            fill="#23A67A"
            fillOpacity="0.42"
          />
        </svg>

        <svg className={styles.studyEdgeBoughRight} viewBox="0 0 220 220" fill="none">
          <path
            d="M228 36C180 48 134 74 88 112M184 52C160 36 132 34 106 42"
            stroke="#23A67A"
            strokeOpacity="0.38"
            strokeWidth="2"
            strokeLinecap="round"
          />
          <path
            d="M106 42C122 28 140 30 152 44C134 50 118 50 106 42Z"
            fill="#8BE5C2"
            fillOpacity="0.55"
          />
          <path
            d="M88 112C70 102 52 110 44 126C64 132 80 126 88 112Z"
            fill="#23A67A"
            fillOpacity="0.4"
          />
        </svg>

        {/* 5. Reused Warm Sunlight Particles at reduced study density */}
        <FloatingParticles reducedDensity />
      </div>

      {/* 6. Sparse, Gentle Margin Falling Leaves */}
      <div
        className={`${styles.studyMarginLeavesLayer} ${
          !shouldAnimate ? styles.backdropPaused : ""
        }`}
        aria-hidden="true"
      >
        {visibleLeaves.map((leaf, idx) => {
          const customStyle: CSSProperties & Record<string, string> = {
            left: leaf.left,
            width: `${leaf.size}px`,
            height: `${leaf.size}px`,
            "--leaf-dur": leaf.dur,
            "--leaf-del": leaf.del,
            "--leaf-sway": leaf.sway,
            "--leaf-drift": leaf.drift,
          };
          return (
            <div key={idx} className={styles.studyFallingLeafDrop} style={customStyle}>
              <div className={styles.studyFallingLeafPendulum}>
                <div className={styles.studyFallingLeafFlutter}>
                  <BotanicalLeafSvg shape={leaf.shape} primaryColor={leaf.color} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </>
  );
}
