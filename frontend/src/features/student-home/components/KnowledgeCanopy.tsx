"use client";

import { motion } from "motion/react";
import { useId, useState } from "react";

import { useHydratedReducedMotion } from "@/lib/use-hydrated-reduced-motion";

import type { KnowledgeRegionViewModel } from "../types";
import styles from "../StudentHome.module.css";

export interface KnowledgeCanopyProps {
  regions: KnowledgeRegionViewModel[];
  subjectName: string;
  ghost?: boolean;
}

const positions = [
  { x: 112, y: 92 },
  { x: 258, y: 58 },
  { x: 408, y: 106 },
  { x: 98, y: 246 },
  { x: 406, y: 248 },
  { x: 258, y: 306 },
];

const branches = [
  "M260 183 C218 142 168 116 112 92",
  "M260 183 C259 132 257 96 258 58",
  "M260 183 C309 142 357 120 408 106",
  "M260 183 C207 196 153 218 98 246",
  "M260 183 C314 196 361 220 406 248",
  "M260 183 C258 224 258 267 258 306",
];

export function KnowledgeCanopy({ regions, subjectName, ghost = false }: KnowledgeCanopyProps) {
  const reducedMotion = useHydratedReducedMotion();
  const titleId = useId();
  const [activeId, setActiveId] = useState<string | null>(null);
  const visibleRegions = regions.slice(0, positions.length);

  return (
    <div className={[styles.canopyWrap, ghost ? styles.canopyGhost : ""].filter(Boolean).join(" ")}>
      <svg
        className={styles.canopy}
        viewBox="0 0 520 370"
        role="group"
        aria-labelledby={titleId}
      >
        <title id={titleId}>{`Bản đồ tri thức thu gọn của ${subjectName}`}</title>
        <defs>
          <radialGradient id="canopy-center" cx="50%" cy="45%" r="60%">
            <stop offset="0%" stopColor="var(--mint-200)" />
            <stop offset="100%" stopColor="var(--aqua-500)" />
          </radialGradient>
          <filter id="canopy-glow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="7" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        <g className={styles.canopyRoots} aria-hidden="true">
          <path d="M260 205 C245 248 209 286 174 340" />
          <path d="M260 205 C268 260 291 300 315 344" />
          <path d="M260 205 C257 264 252 302 252 357" />
        </g>

        {branches.slice(0, visibleRegions.length).map((path, index) => (
          <motion.path
            className={styles.canopyBranch}
            d={path}
            key={path}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: ghost ? 0.28 : 0.72 }}
            transition={{ duration: reducedMotion ? 0 : 0.7, delay: index * 0.06 }}
          />
        ))}

        <motion.g
          className={styles.canopyCore}
          initial={{ opacity: 0, scale: 0.88 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: reducedMotion ? 0 : 0.5 }}
          style={{ transformOrigin: "260px 183px" }}
          aria-hidden="true"
        >
          <circle cx="260" cy="183" r="48" />
          <circle className={styles.canopyCoreInner} cx="260" cy="183" r="32" />
          <path d="M244 188c17-4 26-14 31-30 7 20-1 37-22 43-6-3-9-7-9-13Z" />
        </motion.g>

        {visibleRegions.map((region, index) => {
          const position = positions[index];
          const active = activeId === region.id;
          return (
            <motion.g
              className={`${styles.canopyNode} ${styles[`canopyNode_${region.state}`]}`}
              role="button"
              tabIndex={0}
              aria-label={`${region.label}: ${region.progress === undefined ? "chưa đo lường" : `${region.progress}%`}`}
              key={region.id}
              onMouseEnter={() => setActiveId(region.id)}
              onMouseLeave={() => setActiveId(null)}
              onFocus={() => setActiveId(region.id)}
              onBlur={() => setActiveId(null)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  setActiveId(active ? null : region.id);
                }
              }}
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: ghost ? 0.44 : 1, scale: active ? 1.05 : 1 }}
              transition={{ duration: reducedMotion ? 0 : 0.36, delay: reducedMotion ? 0 : 0.2 + index * 0.07 }}
              style={{ transformOrigin: `${position.x}px ${position.y}px` }}
            >
              <circle className={styles.canopyNodeHalo} cx={position.x} cy={position.y} r="27" />
              <circle className={styles.canopyNodeBody} cx={position.x} cy={position.y} r="15" />
              <circle className={styles.canopyNodeDot} cx={position.x} cy={position.y} r="4" />
              {active ? (
                <g className={styles.canopyTooltip} aria-hidden="true">
                  <rect x={position.x - 66} y={position.y - 55} width="132" height="31" rx="12" />
                  <text x={position.x} y={position.y - 35} textAnchor="middle">
                    {region.label.length > 21 ? `${region.label.slice(0, 20)}…` : region.label}
                  </text>
                </g>
              ) : null}
            </motion.g>
          );
        })}

        {!ghost ? (
          <g className={styles.canopyParticles} aria-hidden="true">
            {[
              { cx: 167, cy: 154, duration: 9 },
              { cx: 351, cy: 168, duration: 12 },
              { cx: 334, cy: 276, duration: 14 },
            ].map((particle, index) => (
              <motion.circle
                key={`${particle.cx}-${particle.cy}`}
                cx={particle.cx}
                cy={particle.cy}
                r={index === 1 ? 3 : 2.5}
                animate={reducedMotion ? undefined : { y: [0, -8, 2, 0], opacity: [0.35, 0.85, 0.42, 0.35] }}
                transition={{ duration: particle.duration, repeat: Infinity, ease: "easeInOut" }}
              />
            ))}
          </g>
        ) : null}
      </svg>
      <div className={styles.canopyCaption}>
        <span /> Bản đồ học tập đang phát triển cùng bạn
      </div>
    </div>
  );
}
