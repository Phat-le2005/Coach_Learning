"use client";

import type { CSSProperties } from "react";

import styles from "./LivingGardenBackdrop.module.css";

export interface FloatingParticlesProps {
  reducedDensity?: boolean;
}

interface MoteSpec {
  top: string;
  left: string;
  size: number;
  delay: string;
  duration: string;
  tone: "gold" | "mint" | "sky";
}

const MOTES: MoteSpec[] = [
  { top: "11%", left: "14%", size: 4.5, delay: "-2s", duration: "15s", tone: "gold" },
  { top: "19%", left: "78%", size: 4, delay: "-6s", duration: "18s", tone: "mint" },
  { top: "32%", left: "26%", size: 3.5, delay: "-4s", duration: "17s", tone: "sky" },
  { top: "44%", left: "86%", size: 5, delay: "-9s", duration: "20s", tone: "gold" },
  { top: "55%", left: "11%", size: 4, delay: "-3s", duration: "16s", tone: "mint" },
  { top: "66%", left: "68%", size: 3.5, delay: "-11s", duration: "19s", tone: "gold" },
  { top: "77%", left: "22%", size: 4.5, delay: "-5s", duration: "21s", tone: "sky" },
  { top: "86%", left: "82%", size: 4, delay: "-7s", duration: "17s", tone: "mint" },
  { top: "38%", left: "54%", size: 3, delay: "-12s", duration: "22s", tone: "gold" },
  { top: "91%", left: "44%", size: 3.5, delay: "-1.5s", duration: "18s", tone: "mint" },
];

export function FloatingParticles({ reducedDensity = false }: FloatingParticlesProps) {
  const visibleMotes = reducedDensity ? MOTES.slice(0, 5) : MOTES;

  return (
    <div className={styles.pollenLayer} aria-hidden="true">
      {visibleMotes.map((mote, index) => {
        const customStyle: CSSProperties & Record<string, string> = {
          "--mote-top": mote.top,
          "--mote-left": mote.left,
          "--mote-size": `${mote.size}px`,
          "--mote-delay": mote.delay,
          "--mote-duration": mote.duration,
        };
        const toneClass =
          mote.tone === "gold"
            ? styles.moteGold
            : mote.tone === "mint"
            ? styles.moteMint
            : styles.moteSky;

        return (
          <span
            key={index}
            className={`${styles.pollenMote} ${toneClass}`}
            style={customStyle}
          />
        );
      })}
    </div>
  );
}
