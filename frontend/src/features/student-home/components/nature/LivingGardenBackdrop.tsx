"use client";

import { motion, useScroll, useTransform } from "motion/react";
import type { CSSProperties } from "react";

import { BotanicalLeafSvg, type LeafShape } from "./BirdsAndLeaves";
import { CloudLayer } from "./CloudLayer";
import { FloatingParticles } from "./FloatingParticles";
import { useGardenMotion } from "./GardenMotionContext";
import styles from "./LivingGardenBackdrop.module.css";

interface BackgroundLeafSpec {
  left: string;
  size: number;
  fallDuration: string;
  fallDelay: string;
  swayDuration: string;
  windDrift: string;
  shape: LeafShape;
  hue: string;
}

const BACKGROUND_FALLING_LEAVES: BackgroundLeafSpec[] = [
  {
    left: "22%",
    size: 15,
    fallDuration: "24s",
    fallDelay: "-4s",
    swayDuration: "4.3s",
    windDrift: "38px",
    shape: "bodhi",
    hue: "#23A67A",
  },
  {
    left: "44%",
    size: 14,
    fallDuration: "28s",
    fallDelay: "-15s",
    swayDuration: "4.8s",
    windDrift: "32px",
    shape: "willow",
    hue: "#8BE5C2",
  },
  {
    left: "65%",
    size: 14,
    fallDuration: "26s",
    fallDelay: "-9s",
    swayDuration: "4.5s",
    windDrift: "-34px",
    shape: "sunlit",
    hue: "#E8BF6A",
  },
  {
    left: "79%",
    size: 16,
    fallDuration: "23s",
    fallDelay: "-19s",
    swayDuration: "4.1s",
    windDrift: "-40px",
    shape: "bodhi",
    hue: "#23A67A",
  },
];

export function LivingGardenBackdrop() {
  const { shouldAnimate, isMobile } = useGardenMotion();
  const { scrollYProgress } = useScroll();

  // Gentle 2.5D depth parallax across the entire page scroll (disabled on mobile or when paused)
  const enableParallax = shouldAnimate && !isMobile;
  const horizonY = useTransform(
    scrollYProgress,
    [0, 1],
    enableParallax ? ["0%", "-14%"] : ["0%", "0%"]
  );
  const midgroundY = useTransform(
    scrollYProgress,
    [0, 1],
    enableParallax ? ["0%", "-8%"] : ["0%", "0%"]
  );

  const visibleBgLeaves = isMobile
    ? BACKGROUND_FALLING_LEAVES.slice(0, 2)
    : BACKGROUND_FALLING_LEAVES;

  return (
    <div
      className={`${styles.backdropRoot} ${!shouldAnimate ? styles.paused : ""}`}
      aria-hidden="true"
    >
      {/* 1. Global Natural Sunlight Shafts */}
      <div className={styles.sunlightLayer}>
        <span className={styles.sunRayOne} />
        <span className={styles.sunRayTwo} />
        {!isMobile ? <span className={styles.sunRayThree} /> : null}
      </div>

      {/* 2. Distant Multi-layered Mountain & Woodland Horizon (2.5D Parallax) */}
      <motion.div className={styles.landscapeLayer} style={{ y: horizonY }}>
        <svg
          className={styles.distantHorizonSvg}
          viewBox="0 0 1440 420"
          preserveAspectRatio="none"
          fill="none"
        >
          <path
            d="M0 290L140 215C185 190 245 198 295 224L420 288L585 178C635 145 702 148 748 184L915 312L1085 196C1135 162 1200 165 1248 202L1440 330V420H0V290Z"
            fill="#B8E3DE"
            fillOpacity="0.45"
          />
          <path
            d="M0 335C180 275 340 268 530 318C720 368 920 260 1140 292C1275 312 1370 342 1440 356V420H0V335Z"
            fill="#8BE5C2"
            fillOpacity="0.28"
          />
          <path
            d="M0 372C260 338 510 388 790 356C1060 325 1265 362 1440 384V420H0V372Z"
            fill="#23A67A"
            fillOpacity="0.12"
          />
        </svg>
      </motion.div>

      {/* 3. Multi-depth Drifting Sky Clouds */}
      <CloudLayer depth="far" count={isMobile ? 2 : 3} />
      {!isMobile ? <CloudLayer depth="near" count={2} /> : null}

      {/* 4. Midground Framing Canopy Branches & Soft Mist Ribbons */}
      <motion.div className={styles.midgroundCanopy} style={{ y: midgroundY }}>
        <span className={styles.mistRibbonOne} />
        <span className={styles.mistRibbonTwo} />

        <svg className={styles.edgeBoughLeft} viewBox="0 0 240 260" fill="none">
          <path
            d="M-10 40C45 52 95 78 148 122M38 58C64 38 96 34 126 42M76 76C102 64 134 68 162 84M62 82C74 114 96 140 126 158"
            stroke="#23A67A"
            strokeOpacity="0.45"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
          <path d="M126 42C108 26 88 28 76 44C96 52 114 52 126 42Z" fill="#8BE5C2" fillOpacity="0.65" />
          <path d="M162 84C146 66 124 68 112 84C132 94 148 94 162 84Z" fill="#23A67A" fillOpacity="0.45" />
          <path d="M148 122C168 112 188 120 196 138C174 144 156 138 148 122Z" fill="#8BE5C2" fillOpacity="0.6" />
          <path d="M126 158C142 152 162 160 168 178C148 182 132 174 126 158Z" fill="#23A67A" fillOpacity="0.4" />
        </svg>

        <svg className={styles.edgeBoughRight} viewBox="0 0 240 260" fill="none">
          <path
            d="M250 36C192 52 142 82 92 128M198 56C172 36 140 34 112 44M158 78C132 66 102 72 76 88M174 84C160 116 138 144 108 162"
            stroke="#23A67A"
            strokeOpacity="0.42"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
          <path d="M112 44C130 28 150 30 162 46C142 54 124 54 112 44Z" fill="#8BE5C2" fillOpacity="0.62" />
          <path d="M76 88C92 70 114 72 126 88C106 98 90 98 76 88Z" fill="#23A67A" fillOpacity="0.42" />
          <path d="M92 128C72 118 52 126 44 144C66 150 84 144 92 128Z" fill="#8BE5C2" fillOpacity="0.58" />
        </svg>
      </motion.div>

      {/* 6. Soft Background Pendulum Falling Leaves */}
      <div className={styles.floatingLeavesLayer}>
        {visibleBgLeaves.map((leaf, index) => {
          const dropStyle: CSSProperties & Record<string, string> = {
            left: leaf.left,
            width: `${leaf.size}px`,
            height: `${leaf.size}px`,
            "--fall-duration": leaf.fallDuration,
            "--fall-delay": leaf.fallDelay,
            "--sway-duration": leaf.swayDuration,
            "--wind-drift": leaf.windDrift,
          };
          return (
            <div key={index} className={styles.fallingLeafDrop} style={dropStyle}>
              <div className={styles.fallingLeafPendulum}>
                <div className={styles.fallingLeafFlutter}>
                  <BotanicalLeafSvg shape={leaf.shape} primaryColor={leaf.hue} />
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* 7. Ambient Sunlight & Pollen Particles */}
      <FloatingParticles reducedDensity={isMobile} />

      {/* 8. Subtle Foreground Soft-Focus Botanical Vignette */}
      <svg className={styles.foregroundCornerLeft} viewBox="0 0 180 150" fill="none">
        <path d="M-8 158C24 112 64 78 118 56C88 104 48 138 -8 158Z" fill="#23A67A" fillOpacity="0.45" />
        <path d="M12 162C52 128 96 108 148 98C114 134 68 156 12 162Z" fill="#8BE5C2" fillOpacity="0.55" />
      </svg>
      <svg className={styles.foregroundCornerRight} viewBox="0 0 180 150" fill="none">
        <path d="M188 158C156 112 116 78 62 56C92 104 132 138 188 158Z" fill="#23A67A" fillOpacity="0.45" />
        <path d="M168 162C128 128 84 108 32 98C66 134 112 156 168 162Z" fill="#8BE5C2" fillOpacity="0.55" />
      </svg>
    </div>
  );
}
