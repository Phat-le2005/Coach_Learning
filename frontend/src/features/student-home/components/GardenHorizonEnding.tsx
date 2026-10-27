"use client";

import { ArrowUp, Sprout } from "lucide-react";

import styles from "../StudentHome.module.css";
import { useGardenMotion, useGardenSectionInView } from "./nature/GardenMotionContext";

export function GardenHorizonEnding() {
  const { shouldAnimate } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLElement>("150px 0px");
  const active = shouldAnimate && isInView;

  return (
    <footer
      ref={ref}
      className={`${styles.horizonEnding} ${!active ? styles.sectionAnimPaused : ""}`}
      aria-label="Chân trời khu vườn học tập"
    >
      <div className={styles.horizonCopyWrap}>
        <span className={styles.horizonSeedIcon} aria-hidden="true">
          <Sprout size={18} />
        </span>
        <p className={styles.horizonQuote}>
          Mỗi bước luyện tập chân thực hôm nay là một mầm xanh bền vững trong khu vườn tri thức của
          bạn.
        </p>
        <a href="#student-home" className={styles.horizonBackTopLink}>
          <ArrowUp size={14} aria-hidden="true" />
          Về đầu khu vườn
        </a>
      </div>

      {/* Layered Rolling Meadow, Swaying Wildflowers & Fluttering Butterflies */}
      <div className={styles.horizonMeadowScene} aria-hidden="true">
        {/* Delicate Animated Butterfly One */}
        <svg className={styles.meadowButterflyOne} viewBox="0 0 36 28" fill="none">
          <g className={styles.butterflyWings}>
            <path d="M18 16C11 6 3 7 4 14C5 19 12 20 18 16Z" fill="#E8BF6A" fillOpacity="0.85" />
            <path d="M18 16C25 6 33 7 32 14C31 19 24 20 18 16Z" fill="#F7F7EE" fillOpacity="0.9" />
          </g>
        </svg>

        {/* Delicate Animated Butterfly Two */}
        <svg className={styles.meadowButterflyTwo} viewBox="0 0 32 24" fill="none">
          <g className={styles.butterflyWings}>
            <path d="M16 14C10 5 3 6 4 12C5 16 11 17 16 14Z" fill="#8BE5C2" fillOpacity="0.85" />
            <path d="M16 14C22 5 29 6 28 12C27 16 21 17 16 14Z" fill="#B8E3DE" fillOpacity="0.9" />
          </g>
        </svg>

        <svg
          className={styles.horizonMeadowSvg}
          viewBox="0 0 1440 150"
          preserveAspectRatio="none"
          fill="none"
        >
          <defs>
            <linearGradient id="meadowHorizonGlow" x1="720" y1="0" x2="720" y2="150" gradientUnits="userSpaceOnUse">
              <stop offset="0%" stopColor="#E8BF6A" stopOpacity="0.16" />
              <stop offset="100%" stopColor="#8BE5C2" stopOpacity="0" />
            </linearGradient>
          </defs>

          <rect width="1440" height="150" fill="url(#meadowHorizonGlow)" />

          {/* Back Soft Meadow Hill */}
          <path
            d="M0 96C240 52 510 112 780 78C1050 44 1270 84 1440 68V150H0V96Z"
            fill="#8BE5C2"
            fillOpacity="0.36"
          />
          {/* Mid Verdant Lawn */}
          <path
            d="M0 112C310 82 610 126 930 96C1160 74 1330 98 1440 108V150H0V112Z"
            fill="#23A67A"
            fillOpacity="0.24"
          />
          {/* Foreground Deep Meadow Edge */}
          <path
            d="M0 128C380 108 740 138 1120 118C1265 110 1370 118 1440 124V150H0V128Z"
            fill="#092D25"
            fillOpacity="0.14"
          />

          {/* Swaying Grass Tufts & Tiny Meadow Flowers */}
          <g className={styles.meadowFlowersSway}>
            <path d="M180 132Q184 108 176 92" stroke="#23A67A" strokeOpacity="0.55" strokeWidth="1.8" strokeLinecap="round" />
            <circle cx="176" cy="90" r="4.5" fill="#F7F7EE" />
            <circle cx="176" cy="90" r="2" fill="#E8BF6A" />

            <path d="M204 135Q210 115 216 102" stroke="#23A67A" strokeOpacity="0.45" strokeWidth="1.6" strokeLinecap="round" />
            <circle cx="216" cy="100" r="3.8" fill="#E8BF6A" />

            <path d="M712 126Q706 102 716 86" stroke="#23A67A" strokeOpacity="0.5" strokeWidth="1.7" strokeLinecap="round" />
            <circle cx="716" cy="84" r="4.5" fill="#F7F7EE" />
            <circle cx="716" cy="84" r="2" fill="#E8BF6A" />

            <path d="M1220 128Q1226 104 1218 88" stroke="#23A67A" strokeOpacity="0.55" strokeWidth="1.8" strokeLinecap="round" />
            <circle cx="1218" cy="86" r="4.5" fill="#F7F7EE" />
            <circle cx="1218" cy="86" r="2.2" fill="#E8BF6A" />

            <path d="M1248 132Q1254 112 1260 98" stroke="#23A67A" strokeOpacity="0.45" strokeWidth="1.5" strokeLinecap="round" />
            <circle cx="1260" cy="96" r="3.8" fill="#8BE5C2" />
          </g>
        </svg>
      </div>
    </footer>
  );
}
