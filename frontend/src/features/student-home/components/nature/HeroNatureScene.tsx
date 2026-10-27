"use client";

import type { CSSProperties } from "react";

import { BotanicalLeafSvg, type LeafShape } from "./BirdsAndLeaves";
import { useGardenMotion, useGardenSectionInView } from "./GardenMotionContext";
import styles from "./LivingGardenBackdrop.module.css";

interface HeroMote {
  top: string;
  left: string;
  size: number;
  dur: string;
  del: string;
}

const HERO_MOTES: HeroMote[] = [
  { top: "24%", left: "44%", size: 4.5, dur: "8.5s", del: "-1s" },
  { top: "68%", left: "48%", size: 3.5, dur: "10s", del: "-4s" },
  { top: "32%", left: "89%", size: 4, dur: "9.2s", del: "-2.5s" },
  { top: "76%", left: "16%", size: 3.5, dur: "11s", del: "-6s" },
  { top: "18%", left: "64%", size: 3, dur: "9.8s", del: "-3.5s" },
];

interface HeroFallingLeaf {
  left: string;
  size: number;
  dur: string;
  del: string;
  swayDur: string;
  drift: string;
  shape: LeafShape;
  color: string;
}

// Leaves gently detaching from the swaying Hero corner branches and fluttering downward
const HERO_FALLING_LEAVES: HeroFallingLeaf[] = [
  {
    left: "8%",
    size: 18,
    dur: "12.5s",
    del: "-2s",
    swayDur: "3.4s",
    drift: "68px",
    shape: "bodhi",
    color: "#8BE5C2",
  },
  {
    left: "17%",
    size: 15,
    dur: "14.5s",
    del: "-7.5s",
    swayDur: "3.9s",
    drift: "54px",
    shape: "sunlit",
    color: "#E8BF6A",
  },
  {
    left: "47%",
    size: 15,
    dur: "15s",
    del: "-4s",
    swayDur: "4.1s",
    drift: "44px",
    shape: "willow",
    color: "#8BE5C2",
  },
  {
    left: "69%",
    size: 14,
    dur: "16s",
    del: "-10s",
    swayDur: "3.8s",
    drift: "-42px",
    shape: "sunlit",
    color: "#E8BF6A",
  },
  {
    left: "84%",
    size: 16,
    dur: "13.5s",
    del: "-5.5s",
    swayDur: "3.6s",
    drift: "-62px",
    shape: "willow",
    color: "#8BE5C2",
  },
  {
    left: "92%",
    size: 18,
    dur: "15s",
    del: "-11.5s",
    swayDur: "4.1s",
    drift: "-50px",
    shape: "bodhi",
    color: "#23A67A",
  },
];

export function HeroNatureScene() {
  const { shouldAnimate, isMobile } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLDivElement>("160px 0px");
  const active = shouldAnimate && isInView;
  const motes = isMobile ? HERO_MOTES.slice(0, 3) : HERO_MOTES;
  const fallingLeaves = isMobile ? HERO_FALLING_LEAVES.slice(0, 2) : HERO_FALLING_LEAVES;

  return (
    <div
      ref={ref}
      className={`${styles.heroNatureScene} ${!active ? styles.heroPaused : ""}`}
      aria-hidden="true"
    >
      {/* 1. Warm Canopy Sun Halo & Filtering Sunbeams */}
      <span className={styles.heroSunHalo} />
      <svg className={styles.heroSunbeamSvg} viewBox="0 0 800 560" preserveAspectRatio="none" fill="none">
        <defs>
          <linearGradient id="heroBeamGrad1" x1="620" y1="0" x2="260" y2="520" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#F7F7EE" stopOpacity="0.34" />
            <stop offset="45%" stopColor="#E8BF6A" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#8BE5C2" stopOpacity="0" />
          </linearGradient>
          <linearGradient id="heroBeamGrad2" x1="740" y1="0" x2="430" y2="540" gradientUnits="userSpaceOnUse">
            <stop offset="0%" stopColor="#B8E3DE" stopOpacity="0.28" />
            <stop offset="55%" stopColor="#8BE5C2" stopOpacity="0.09" />
            <stop offset="100%" stopColor="#092D25" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon points="510,0 650,0 330,560 150,560" fill="url(#heroBeamGrad1)" />
        <polygon points="680,0 790,0 540,560 395,560" fill="url(#heroBeamGrad2)" />
      </svg>

      {/* 2. Distant Drifting Clouds */}
      <svg className={styles.heroCloudFar} viewBox="0 0 220 68" fill="none">
        <path
          d="M24 54H188C201 54 211 45 211 33C211 22 201 13 189 12C183 4 174 0 163 0C149 0 138 8 133 19C128 16 122 15 116 15C101 15 89 25 86 38C82 36 77 35 72 35C59 35 48 43 46 54H24Z"
          fill="#F7F7EE"
        />
      </svg>
      <svg className={styles.heroCloudMid} viewBox="0 0 260 76" fill="none">
        <path
          d="M28 62H224C239 62 251 51 251 38C251 25 240 15 226 14C219 5 208 0 195 0C180 0 167 9 161 22C155 19 149 17 142 17C125 17 110 28 107 43C102 41 97 40 92 40C77 40 65 49 62 62H28Z"
          fill="#B8E3DE"
        />
      </svg>
      {!isMobile ? (
        <svg className={styles.heroCloudNear} viewBox="0 0 190 58" fill="none">
          <path
            d="M18 46H164C175 46 184 38 184 28C184 19 176 11 165 10C160 4 152 0 142 0C131 0 121 7 117 16C112 14 107 13 102 13C89 13 79 21 76 32C72 31 68 30 64 30C53 30 44 37 42 46H18Z"
            fill="#F7F7EE"
          />
        </svg>
      ) : null}

      {/* 3. Multi-layered Distant Mountains & Evergreen Forest Ridges */}
      <svg
        className={styles.heroMountainsSvg}
        viewBox="0 0 1440 210"
        preserveAspectRatio="none"
        fill="none"
      >
        <path
          d="M0 154L120 96C165 74 220 78 262 104L390 162L555 72C605 45 668 48 714 82L885 168L1065 68C1118 38 1184 42 1234 78L1440 158V210H0V154Z"
          fill="#8BE5C2"
          fillOpacity="0.13"
        />
        <path
          d="M0 172C160 132 325 128 495 164C675 198 855 118 1065 138C1215 152 1340 168 1440 178V210H0V172Z"
          fill="#23A67A"
          fillOpacity="0.22"
        />
        <path
          d="M0 188C190 168 380 198 610 182C840 166 1090 154 1280 178C1350 186 1402 192 1440 194V210H0V188Z"
          fill="#092D25"
          fillOpacity="0.52"
        />
        <g fill="#092D25" fillOpacity="0.38">
          <path d="M980 146L992 118L1004 146H980Z" />
          <path d="M998 148L1013 110L1028 148H998Z" />
          <path d="M1022 150L1034 124L1046 150H1022Z" />
          <path d="M210 148L222 122L234 148H210Z" />
          <path d="M228 150L242 115L256 150H228Z" />
        </g>
      </svg>

      {/* 5. Swaying Canopy Branches & Leaves at Hero Corners */}
      <svg className={styles.heroBranchTopLeft} viewBox="0 0 280 210" fill="none">
        <path
          d="M-12 -8C42 22 98 54 162 82M42 20C78 12 114 18 146 34M86 48C118 44 152 52 182 72M56 32C64 68 84 102 112 128"
          stroke="#8BE5C2"
          strokeOpacity="0.34"
          strokeWidth="2.2"
          strokeLinecap="round"
        />
        <g className={styles.heroLeafCluster}>
          <path d="M146 34C128 16 104 16 90 32C112 42 132 42 146 34Z" fill="#8BE5C2" fillOpacity="0.38" />
          <path d="M182 72C166 52 142 52 128 68C148 80 168 80 182 72Z" fill="#23A67A" fillOpacity="0.45" />
          <path d="M162 82C184 74 206 84 214 104C190 108 170 100 162 82Z" fill="#B8E3DE" fillOpacity="0.32" />
          <path d="M112 128C130 124 148 134 154 152C132 154 116 144 112 128Z" fill="#8BE5C2" fillOpacity="0.3" />
          <circle cx="152" cy="36" r="3" fill="#E8BF6A" fillOpacity="0.75" />
        </g>
      </svg>

      <svg className={styles.heroBranchTopRight} viewBox="0 0 260 195" fill="none">
        <path
          d="M272 -6C218 24 164 52 108 78M218 18C184 10 150 16 122 32M174 46C144 42 114 50 88 68"
          stroke="#8BE5C2"
          strokeOpacity="0.3"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <g className={styles.heroLeafCluster}>
          <path d="M122 32C138 14 162 14 176 30C154 40 136 40 122 32Z" fill="#8BE5C2" fillOpacity="0.34" />
          <path d="M88 68C104 50 126 50 140 66C120 76 102 76 88 68Z" fill="#23A67A" fillOpacity="0.42" />
          <path d="M108 78C86 70 66 80 58 98C80 102 100 94 108 78Z" fill="#E8BF6A" fillOpacity="0.26" />
        </g>
      </svg>

      {/* 6. Canopy Falling Leaves inside Hero (Lá khẽ lìa cành rơi nghiêng theo gió) */}
      {fallingLeaves.map((leaf, idx) => {
        const dropStyle: CSSProperties & Record<string, string> = {
          left: leaf.left,
          width: `${leaf.size}px`,
          height: `${leaf.size}px`,
          "--hero-leaf-dur": leaf.dur,
          "--hero-leaf-del": leaf.del,
          "--sway-duration": leaf.swayDur,
          "--hero-leaf-drift": leaf.drift,
        };
        return (
          <div key={`hero-leaf-${idx}`} className={styles.heroFallingLeafDrop} style={dropStyle}>
            <div className={styles.fallingLeafPendulum}>
              <div className={styles.fallingLeafFlutter}>
                <BotanicalLeafSvg
                  shape={leaf.shape}
                  primaryColor={leaf.color}
                  veinColor="#F7F7EE"
                />
              </div>
            </div>
          </div>
        );
      })}

      {/* 7. Slow-moving Warm Sunlight Motes */}
      {motes.map((m, idx) => {
        const moteStyle: CSSProperties & Record<string, string> = {
          top: m.top,
          left: m.left,
          width: `${m.size}px`,
          height: `${m.size}px`,
          "--mote-dur": m.dur,
          "--mote-del": m.del,
        };
        return <span key={idx} className={styles.heroLightMote} style={moteStyle} />;
      })}
    </div>
  );
}
