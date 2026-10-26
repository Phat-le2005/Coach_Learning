"use client";

import { Sparkles } from "lucide-react";
import { useId, useState } from "react";

import { getRegionStateCopy } from "../copy";
import type { KnowledgeRegionViewModel, StudentHomeActionType } from "../types";
import styles from "./KnowledgeCanopy.module.css";
import { useGardenMotion } from "./nature/GardenMotionContext";

export interface KnowledgeCanopyProps {
  regions: KnowledgeRegionViewModel[];
  subjectName: string;
  ghost?: boolean;
  actionType?: StudentHomeActionType;
  targetName?: string;
}

const NODE_CONFIGS = [
  { x: 300, y: 85, titleX: 300, titleY: 42, subX: 300, subY: 58 },
  { x: 426, y: 158, titleX: 430, titleY: 114, subX: 430, subY: 130 },
  { x: 426, y: 302, titleX: 430, titleY: 340, subX: 430, subY: 356 },
  { x: 300, y: 375, titleX: 300, titleY: 413, subX: 300, subY: 429 },
  { x: 174, y: 302, titleX: 170, titleY: 340, subX: 170, subY: 356 },
  { x: 174, y: 158, titleX: 170, titleY: 114, subX: 170, subY: 130 },
];

// Harmonized Living Garden Chapter Palette
const CHAPTER_THEMES = [
  { fill: "#23A67A", stroke: "#8BE5C2", halo: "rgba(35, 166, 122, 0.42)" },
  { fill: "#E8BF6A", stroke: "#F7F7EE", halo: "rgba(232, 191, 106, 0.42)" },
  { fill: "#5CA9D6", stroke: "#B8E3DE", halo: "rgba(92, 169, 214, 0.42)" },
  { fill: "#3BB9B0", stroke: "#8BE5C2", halo: "rgba(59, 185, 176, 0.42)" },
  { fill: "#7FA882", stroke: "#DCEFE5", halo: "rgba(127, 168, 130, 0.42)" },
  { fill: "#D49B54", stroke: "#F7F7EE", halo: "rgba(212, 155, 84, 0.42)" },
];

function formatLabel(label: string): string {
  if (label.length <= 20) return label;
  const truncated = label.slice(0, 19);
  const lastSpace = truncated.lastIndexOf(" ");
  return lastSpace > 10 ? `${truncated.slice(0, lastSpace)}…` : `${truncated}…`;
}

export function KnowledgeCanopy({
  regions,
  subjectName,
  ghost = false,
  targetName,
}: KnowledgeCanopyProps) {
  const titleId = useId();
  const { shouldAnimate } = useGardenMotion();
  const [activeRegion, setActiveRegion] = useState<KnowledgeRegionViewModel | null>(null);

  const visibleRegions = regions.slice(0, 6);
  const centerX = 300;
  const centerY = 230;

  const constellationLinks = NODE_CONFIGS.map((pt, index) => {
    const nextPt = NODE_CONFIGS[(index + 1) % NODE_CONFIGS.length];
    return `M ${pt.x} ${pt.y} L ${nextPt.x} ${nextPt.y}`;
  });

  return (
    <div
      className={`${styles.canopyWrap} ${!shouldAnimate ? styles.canopyPaused : ""}`}
      data-testid="galaxy-radar-widget"
    >
      <svg
        className={styles.canopy}
        viewBox="0 0 600 460"
        role="group"
        aria-labelledby={titleId}
      >
        <title id={titleId}>{`Vũ trụ tri thức của ${subjectName}`}</title>
        <defs>
          <filter id="gardenCanopyGlow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="gardenCoreGlow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="11" result="blur1" />
            <feGaussianBlur in="SourceGraphic" stdDeviation="3.5" result="blur2" />
            <feMerge>
              <feMergeNode in="blur1" />
              <feMergeNode in="blur2" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <radialGradient id="gardenNucleusGrad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#8BE5C2" stopOpacity="0.95" />
            <stop offset="45%" stopColor="#23A67A" stopOpacity="0.78" />
            <stop offset="85%" stopColor="#092D25" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#092D25" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Multi-layered Botanical-Celestial Orbit Tracks */}
        <circle cx={centerX} cy={centerY} r="205" className={styles.orbitTrackOuter} />
        <circle cx={centerX} cy={centerY} r="145" className={styles.orbitTrackMain} />
        <circle cx={centerX} cy={centerY} r="85" className={styles.orbitTrackInner} />

        {/* Subtle Botanical Leaf Buds along Outer Orbit */}
        <g className={styles.orbitBotanicalRing} aria-hidden="true">
          <path d="M300 20C306 14 314 15 317 22C310 26 304 25 300 20Z" fill="#8BE5C2" fillOpacity="0.48" />
          <path d="M503 230C509 236 508 244 501 247C497 240 498 234 503 230Z" fill="#E8BF6A" fillOpacity="0.48" />
          <path d="M300 436C294 442 286 441 283 434C290 430 296 431 300 436Z" fill="#8BE5C2" fillOpacity="0.48" />
          <path d="M97 230C91 224 92 216 99 213C103 220 102 226 97 230Z" fill="#B8E3DE" fillOpacity="0.48" />
        </g>

        {/* Pulsating energy ripple around center core */}
        <circle cx={centerX} cy={centerY} className={styles.corePulseRing} />

        {/* Constellation Connection Beams between Chapter Nodes */}
        <g aria-hidden="true">
          {constellationLinks.map((path, idx) => {
            const activeIdx = activeRegion
              ? visibleRegions.findIndex((r) => r.id === activeRegion.id)
              : -1;
            const isHighlighted =
              activeIdx >= 0 && (idx === activeIdx || (idx + 1) % 6 === activeIdx);

            return (
              <path
                key={idx}
                d={path}
                className={`${styles.constellationBeam} ${
                  isHighlighted ? styles.constellationBeamActive : ""
                }`}
                filter="url(#gardenCanopyGlow)"
              />
            );
          })}

          {NODE_CONFIGS.map((pt, idx) => (
            <line
              key={`spoke-${idx}`}
              x1={centerX}
              y1={centerY}
              x2={pt.x}
              y2={pt.y}
              className={styles.spokeLine}
            />
          ))}
        </g>

        {/* Central Core: Living Subject Heart */}
        <g
          className={styles.coreNode}
          role="button"
          tabIndex={0}
          aria-label={`Môn học ${subjectName}`}
        >
          <circle
            cx={centerX}
            cy={centerY}
            r="52"
            fill="url(#gardenNucleusGrad)"
            filter="url(#gardenCoreGlow)"
          />
          <circle
            cx={centerX}
            cy={centerY}
            r="41"
            fill="#092D25"
            stroke="#8BE5C2"
            strokeWidth="2.6"
            filter="url(#gardenCanopyGlow)"
          />
          <text
            x={centerX}
            y={centerY - 3}
            fill="#F7F7EE"
            fontWeight="800"
            fontSize="13px"
            textAnchor="middle"
            letterSpacing="0.02em"
            pointerEvents="none"
          >
            {subjectName}
          </text>
          <text
            x={centerX}
            y={centerY + 14}
            fill="#8BE5C2"
            fontWeight="700"
            fontSize="8.5px"
            textAnchor="middle"
            letterSpacing="0.09em"
            pointerEvents="none"
          >
            {ghost ? "ĐANG CHỜ DỮ LIỆU" : "VƯỜN TRI THỨC"}
          </text>
        </g>

        {/* Orbiting Chapter Nodes */}
        {visibleRegions.map((region, index) => {
          const cfg = NODE_CONFIGS[index];
          const theme = CHAPTER_THEMES[index % CHAPTER_THEMES.length];
          const isSelected =
            activeRegion?.id === region.id ||
            Boolean(targetName && targetName.includes(region.label));

          return (
            <g
              key={region.id}
              className={styles.chapterNode}
              role="button"
              tabIndex={0}
              aria-label={`${region.label}: ${getRegionStateCopy(region.state)}`}
              onMouseEnter={() => setActiveRegion(region)}
              onMouseLeave={() => setActiveRegion(null)}
              onFocus={() => setActiveRegion(region)}
              onBlur={() => setActiveRegion(null)}
              onClick={() => setActiveRegion(region)}
            >
              <circle cx={cfg.x} cy={cfg.y} r="38" fill="transparent" pointerEvents="all" />

              <circle
                cx={cfg.x}
                cy={cfg.y}
                r={isSelected ? 30 : 23}
                fill={theme.halo}
                stroke={theme.stroke}
                strokeWidth={isSelected ? 2.4 : 1.2}
                strokeOpacity={isSelected ? 1 : 0.65}
                className={styles.nodeHalo}
                filter="url(#gardenCanopyGlow)"
                pointerEvents="none"
              />

              <circle
                cx={cfg.x}
                cy={cfg.y}
                r={isSelected ? 18.5 : 15.5}
                fill={theme.fill}
                stroke="#F7F7EE"
                strokeWidth="2.2"
                className={styles.nodeBody}
                filter="url(#gardenCanopyGlow)"
                pointerEvents="none"
              />

              <text
                x={cfg.x}
                y={cfg.y + 4}
                fill="#092D25"
                fontSize="11.5px"
                fontWeight="800"
                textAnchor="middle"
                pointerEvents="none"
              >
                {index + 1}
              </text>

              <text
                x={cfg.x + 13}
                y={cfg.y - 12}
                className={styles.starSparkle}
                fontSize="10.5"
              >
                ✦
              </text>

              <text x={cfg.titleX} y={cfg.titleY} className={styles.nodeLabel}>
                {formatLabel(region.label)}
              </text>

              <text x={cfg.subX} y={cfg.subY} className={styles.nodeSubLabel}>
                {region.progress !== undefined
                  ? `${region.progress}% vững · ${getRegionStateCopy(region.state)}`
                  : "Chưa đo điểm"}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Dynamic Glass Status Pill below Canopy */}
      <div
        className={`${styles.tooltipWrap} ${
          activeRegion ? styles.tooltipWrapActive : ""
        }`}
      >
        {activeRegion ? (
          <span className={styles.tooltipRow}>
            <Sparkles size={14} className={styles.tooltipIconGold} aria-hidden="true" />
            <strong className={styles.tooltipTitle}>{activeRegion.label}:</strong>
            <span className={styles.tooltipState}>
              {getRegionStateCopy(activeRegion.state)}
            </span>
            {activeRegion.progress !== undefined ? (
              <span className={styles.tooltipPercentBadge}>{activeRegion.progress}%</span>
            ) : null}
          </span>
        ) : (
          <span className={styles.tooltipRow}>
            <Sparkles size={14} className={styles.tooltipIconMint} aria-hidden="true" />
            <span>
              {ghost
                ? "Kết nối dữ liệu học tập để thắp sáng các nhánh tri thức"
                : "Chạm hoặc rê chuột vào các nhánh để xem độ thành thạo"}
            </span>
          </span>
        )}
      </div>
    </div>
  );
}
