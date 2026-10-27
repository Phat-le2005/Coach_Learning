"use client";

import type { CSSProperties } from "react";

import { useGardenMotion } from "./GardenMotionContext";
import styles from "./LivingGardenBackdrop.module.css";

export type LeafShape = "bodhi" | "willow" | "sunlit";

export interface BotanicalLeafProps {
  shape: LeafShape;
  primaryColor: string;
  veinColor?: string;
}

export function BotanicalLeafSvg({
  shape,
  primaryColor,
  veinColor = "#092D25",
}: BotanicalLeafProps) {
  if (shape === "willow") {
    return (
      <svg viewBox="0 0 28 28" width="100%" height="100%" fill="none">
        <path
          d="M24 3C15 5 7 12 3 24C15 21 22 13 24 3Z"
          fill={primaryColor}
          fillOpacity="0.88"
        />
        <path
          d="M3 24C9 17 16 10 24 3"
          stroke={veinColor}
          strokeOpacity="0.32"
          strokeWidth="1.1"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  if (shape === "sunlit") {
    return (
      <svg viewBox="0 0 28 28" width="100%" height="100%" fill="none">
        <path
          d="M22 5C14 4 6 9 5 20C7 21 9 23 9 23C18 21 23 14 22 5Z"
          fill={primaryColor}
          fillOpacity="0.9"
        />
        <path
          d="M4 23C9 18 15 11 22 5"
          stroke={veinColor}
          strokeOpacity="0.3"
          strokeWidth="1.15"
          strokeLinecap="round"
        />
      </svg>
    );
  }

  // Default: Bodhi / Garden Tree Leaf
  return (
    <svg viewBox="0 0 28 28" width="100%" height="100%" fill="none">
      <path
        d="M23 4C13 4 5 10 5 21C16 21 22 14 23 4Z"
        fill={primaryColor}
        fillOpacity="0.86"
      />
      <path
        d="M4 23C10 17 16 11 23 4M11 16L8 12M15 12L12 8.5"
        stroke={veinColor}
        strokeOpacity="0.3"
        strokeWidth="1.1"
        strokeLinecap="round"
      />
    </svg>
  );
}

interface MarginFallingLeafSpec {
  left: string;
  size: number;
  fallDuration: string;
  fallDelay: string;
  swayDuration: string;
  windDrift: string;
  shape: LeafShape;
  color: string;
}

// Positioned thoughtfully along the left & right garden margins so they never cover centered reading text
const MARGIN_FALLING_LEAVES: MarginFallingLeafSpec[] = [
  {
    left: "2.8%",
    size: 21,
    fallDuration: "17s",
    fallDelay: "-2.5s",
    swayDuration: "3.6s",
    windDrift: "46px",
    shape: "bodhi",
    color: "#23A67A",
  },
  {
    left: "8.2%",
    size: 18,
    fallDuration: "21s",
    fallDelay: "-9.5s",
    swayDuration: "4.2s",
    windDrift: "36px",
    shape: "willow",
    color: "#8BE5C2",
  },
  {
    left: "13.5%",
    size: 16,
    fallDuration: "23s",
    fallDelay: "-15.5s",
    swayDuration: "4.0s",
    windDrift: "30px",
    shape: "sunlit",
    color: "#E8BF6A",
  },
  {
    left: "86.5%",
    size: 18,
    fallDuration: "20s",
    fallDelay: "-5.5s",
    swayDuration: "4.1s",
    windDrift: "-38px",
    shape: "willow",
    color: "#8BE5C2",
  },
  {
    left: "91.8%",
    size: 21,
    fallDuration: "18s",
    fallDelay: "-12.5s",
    swayDuration: "3.7s",
    windDrift: "-46px",
    shape: "bodhi",
    color: "#23A67A",
  },
  {
    left: "95.8%",
    size: 17,
    fallDuration: "22s",
    fallDelay: "-18s",
    swayDuration: "4.5s",
    windDrift: "-32px",
    shape: "sunlit",
    color: "#E8BF6A",
  },
];

/**
 * Foreground-edge canopy falling leaves along the left & right margins of Student Home.
 * Pure pointer-events: none; creates gentle, lifelike falling leaf motion as the user explores the garden.
 */
export function CanopyMarginFallingLeaves() {
  const { shouldAnimate, isMobile } = useGardenMotion();
  const leaves = isMobile
    ? [MARGIN_FALLING_LEAVES[0], MARGIN_FALLING_LEAVES[4], MARGIN_FALLING_LEAVES[2]]
    : MARGIN_FALLING_LEAVES;

  return (
    <div
      className={`${styles.marginLeavesOverlay} ${!shouldAnimate ? styles.paused : ""}`}
      aria-hidden="true"
    >
      {leaves.map((leaf, idx) => {
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
          <div key={idx} className={styles.fallingLeafDrop} style={dropStyle}>
            <div className={styles.fallingLeafPendulum}>
              <div className={styles.fallingLeafFlutter}>
                <BotanicalLeafSvg shape={leaf.shape} primaryColor={leaf.color} />
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
