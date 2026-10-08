"use client";

import { motion } from "motion/react";
import { useId, useState } from "react";

import { useHydratedReducedMotion } from "@/lib/use-hydrated-reduced-motion";

import { getRegionStateCopy } from "../copy";
import type { KnowledgeRegionViewModel, StudentHomeActionType } from "../types";
import styles from "./KnowledgeCanopy.module.css";

export interface KnowledgeCanopyProps {
  regions: KnowledgeRegionViewModel[];
  subjectName: string;
  ghost?: boolean;
  actionType?: StudentHomeActionType;
  targetName?: string;
}

const leaves = [
  { x: 118, y: 150, rotation: -28 },
  { x: 205, y: 80, rotation: -12 },
  { x: 329, y: 64, rotation: 10 },
  { x: 447, y: 137, rotation: 28 },
  { x: 397, y: 244, rotation: 20 },
  { x: 170, y: 253, rotation: -20 },
];

const branches = [
  "M278 278 C236 229 181 187 118 150",
  "M282 270 C257 188 234 124 205 80",
  "M286 260 C292 177 306 108 329 64",
  "M291 275 C341 218 392 174 447 137",
  "M289 291 C339 280 369 263 397 244",
  "M275 292 C237 287 202 270 170 253",
];

const foliage = [
  { cx: 151, cy: 124, r: 78 },
  { cx: 226, cy: 85, r: 82 },
  { cx: 319, cy: 82, r: 88 },
  { cx: 405, cy: 122, r: 82 },
  { cx: 417, cy: 202, r: 68 },
  { cx: 166, cy: 211, r: 70 },
];

function normalizedTarget(value: string) {
  return value.toLocaleLowerCase("vi").replace(/^vùng\s+/u, "").trim();
}

export function KnowledgeCanopy({
  regions,
  subjectName,
  ghost = false,
  actionType,
  targetName,
}: KnowledgeCanopyProps) {
  const reducedMotion = useHydratedReducedMotion();
  const titleId = useId();
  const instanceId = useId().replaceAll(":", "");
  const [activeId, setActiveId] = useState<string | null>(null);
  const visibleRegions = regions.slice(0, leaves.length);
  const normalizedActionTarget = targetName ? normalizedTarget(targetName) : "";
  let targetIndex = normalizedActionTarget
    ? visibleRegions.findIndex((region) => {
        const regionTarget = normalizedTarget(region.label);
        return normalizedActionTarget.includes(regionTarget) || regionTarget.includes(normalizedActionTarget);
      })
    : -1;

  if (targetIndex < 0 && actionType === "CONTINUE_REPAIR") {
    targetIndex = visibleRegions.findIndex((region) => region.state === "weak");
  }
  if (targetIndex < 0 && actionType === "REVIEW_DUE") {
    targetIndex = visibleRegions.findIndex((region) => region.state === "review");
  }

  const modeClass = actionType === "CONTINUE_REPAIR"
    ? styles.canopyRepair
    : actionType === "REVIEW_DUE" ? styles.canopyReview : "";

  return (
    <div className={[styles.canopyWrap, ghost ? styles.canopyGhost : "", modeClass].filter(Boolean).join(" ")}>
      <svg className={styles.canopy} viewBox="0 0 560 420" role="group" aria-labelledby={titleId}>
        <title id={titleId}>{`Cây tri thức của ${subjectName}`}</title>
        <defs>
          <linearGradient id={`${instanceId}-trunk`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#8ec7a4" />
            <stop offset="48%" stopColor="#4f9678" />
            <stop offset="100%" stopColor="#286955" />
          </linearGradient>
          <radialGradient id={`${instanceId}-ground`} cx="50%" cy="35%" r="65%">
            <stop offset="0%" stopColor="rgba(156, 224, 188, 0.34)" />
            <stop offset="100%" stopColor="rgba(59, 185, 176, 0)" />
          </radialGradient>
          <filter id={`${instanceId}-tree-glow`} x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="6" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>

        <ellipse className={styles.treeGroundGlow} cx="282" cy="367" rx="184" ry="38" fill={`url(#${instanceId}-ground)`} />
        <g className={styles.treeFoliage} aria-hidden="true">
          {foliage.map((cloud) => <circle {...cloud} key={`${cloud.cx}-${cloud.cy}`} />)}
        </g>

        <motion.path
          className={styles.treeTrunk}
          d="M284 371 C271 332 274 300 281 267 C288 231 286 201 281 164"
          stroke={`url(#${instanceId}-trunk)`}
          initial={{ pathLength: 0, opacity: 0 }}
          animate={{ pathLength: 1, opacity: ghost ? 0.32 : 0.94 }}
          transition={{ duration: reducedMotion ? 0 : 0.9, ease: [0.22, 1, 0.36, 1] }}
        />

        <g className={styles.canopyRoots} aria-hidden="true">
          <path className={actionType === "CONTINUE_REPAIR" ? styles.rootRepair : undefined} d="M284 360 C247 361 210 375 169 398" />
          <path d="M284 360 C316 366 350 380 389 402" />
          <path d="M282 358 C279 375 280 391 281 410" />
          <path d="M275 363 C253 378 239 393 226 410" />
          {actionType === "CONTINUE_REPAIR" ? <path className={styles.rootRecovery} d="M284 360 C249 362 213 375 176 396" /> : null}
        </g>

        {branches.slice(0, visibleRegions.length).map((path, index) => (
          <motion.path
            className={`${styles.canopyBranch} ${index === targetIndex ? styles.branchTarget : ""}`}
            d={path}
            key={path}
            initial={{ pathLength: 0, opacity: 0 }}
            animate={{ pathLength: 1, opacity: ghost ? 0.2 : 0.68 }}
            transition={{ duration: reducedMotion ? 0 : 0.72, delay: reducedMotion ? 0 : 0.18 + index * 0.07 }}
          />
        ))}

        <g className={styles.treeTrunkRings} aria-hidden="true">
          <path d="M278 309 Q284 315 290 308" />
          <path d="M276 333 Q284 339 292 331" />
        </g>

        {visibleRegions.map((region, index) => {
          const leaf = leaves[index];
          const active = activeId === region.id;
          const currentTarget = index === targetIndex;
          const rotation = `rotate(${leaf.rotation} ${leaf.x} ${leaf.y})`;
          const stateLabel = getRegionStateCopy(region.state);
          const progressLabel = region.progress === undefined ? "Chưa đo lường" : `${region.progress}% hoàn thành`;

          return (
            <motion.g
              className={`${styles.canopyNode} ${styles[`canopyNode_${region.state}`]} ${currentTarget ? styles.canopyNodeTarget : ""}`}
              role="button"
              tabIndex={0}
              aria-label={`${region.label}: ${stateLabel}, ${progressLabel}`}
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
              initial={{ opacity: 0, scale: 0.82 }}
              animate={{ opacity: ghost ? 0.42 : 1, scale: active ? 1.045 : 1 }}
              transition={{ duration: reducedMotion ? 0 : 0.38, delay: reducedMotion ? 0 : 0.35 + index * 0.07 }}
              style={{ transformOrigin: `${leaf.x}px ${leaf.y}px` }}
            >
              <ellipse className={styles.canopyNodeHalo} cx={leaf.x} cy={leaf.y} rx="38" ry="27" transform={rotation} />
              <ellipse className={styles.canopyNodeBody} cx={leaf.x} cy={leaf.y} rx="29" ry="19" transform={rotation} filter={`url(#${instanceId}-tree-glow)`} />
              <path className={styles.canopyNodeVein} d={`M${leaf.x - 18} ${leaf.y + 4} Q${leaf.x} ${leaf.y} ${leaf.x + 18} ${leaf.y - 3}`} transform={rotation} />
              {region.state === "not_started" ? (
                <g className={styles.canopyNodeLock} aria-hidden="true">
                  <rect x={leaf.x - 5} y={leaf.y - 2} width="10" height="8" rx="2" />
                  <path d={`M${leaf.x - 3} ${leaf.y - 2}v-3a3 3 0 0 1 6 0v3`} />
                </g>
              ) : <circle className={styles.canopyNodeDot} cx={leaf.x + 12} cy={leaf.y - 5} r="3.5" />}
              {active ? (
                <g className={styles.canopyTooltip} aria-hidden="true">
                  <rect x={leaf.x - 78} y={leaf.y - 82} width="156" height="52" rx="14" />
                  <text x={leaf.x} y={leaf.y - 63} textAnchor="middle">
                    <tspan className={styles.tooltipTitle} x={leaf.x}>{region.label.length > 22 ? `${region.label.slice(0, 21)}…` : region.label}</tspan>
                    <tspan className={styles.tooltipMeta} x={leaf.x} dy="15">{stateLabel} · {progressLabel}</tspan>
                  </text>
                </g>
              ) : null}
            </motion.g>
          );
        })}

        {!ghost ? (
          <g className={styles.canopyParticles} aria-hidden="true">
            {[
              { cx: 102, cy: 222, duration: 12 },
              { cx: 468, cy: 210, duration: 13 },
            ].map((particle, index) => (
              <motion.circle
                key={`${particle.cx}-${particle.cy}`}
                cx={particle.cx}
                cy={particle.cy}
                r={index === 1 ? 3 : 2.4}
                animate={reducedMotion ? undefined : { y: [0, -9, 3, 0], x: [0, 4, -2, 0], opacity: [0.25, 0.82, 0.4, 0.25] }}
                transition={{ duration: particle.duration, repeat: Infinity, ease: "easeInOut" }}
              />
            ))}
          </g>
        ) : null}
      </svg>
      <div className={styles.canopyCaption}>
        <span /> {ghost ? "Đang chờ dữ liệu bản đồ tri thức" : "Cây tri thức đang lớn lên cùng bạn"} <span />
      </div>
    </div>
  );
}
