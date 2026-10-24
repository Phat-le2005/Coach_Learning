"use client";

import { useId, useState } from "react";
import { Sparkles } from "lucide-react";

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

// 6 node coordinates & dedicated text coordinates with zero overlapping:
// Center is (300, 230), Radius = 145px
const NODE_CONFIGS = [
  // Node 1 (Top, 12h): Text strictly ABOVE star (gap = 8px)
  {
    x: 300,
    y: 85,
    titleX: 300,
    titleY: 42,
    subX: 300,
    subY: 58,
  },
  // Node 2 (Top-Right, 2h): Text strictly ABOVE star (gap = 13px)
  {
    x: 426,
    y: 158,
    titleX: 430,
    titleY: 114,
    subX: 430,
    subY: 130,
  },
  // Node 3 (Bottom-Right, 4h): Text strictly BELOW star (gap = 18px)
  {
    x: 426,
    y: 302,
    titleX: 430,
    titleY: 340,
    subX: 430,
    subY: 356,
  },
  // Node 4 (Bottom, 6h): Text strictly BELOW star (gap = 20px)
  {
    x: 300,
    y: 375,
    titleX: 300,
    titleY: 413,
    subX: 300,
    subY: 429,
  },
  // Node 5 (Bottom-Left, 8h): Text strictly BELOW star (gap = 18px)
  {
    x: 174,
    y: 302,
    titleX: 170,
    titleY: 340,
    subX: 170,
    subY: 356,
  },
  // Node 6 (Top-Left, 10h): Text strictly ABOVE star (gap = 13px)
  {
    x: 174,
    y: 158,
    titleX: 170,
    titleY: 114,
    subX: 170,
    subY: 130,
  },
];

const CHAPTER_THEMES = [
  { fill: "#d8a143", stroke: "#fef08a", halo: "rgba(216, 161, 67, 0.45)" }, // Gold (Khảo sát hàm số)
  { fill: "#5ca9d6", stroke: "#bae6fd", halo: "rgba(92, 169, 214, 0.45)" }, // Sky (Tọa độ Oxyz)
  { fill: "#8578cf", stroke: "#ddd6fe", halo: "rgba(133, 120, 207, 0.45)" }, // Violet (Tích phân)
  { fill: "#3bb9b0", stroke: "#a7f3d0", halo: "rgba(59, 185, 176, 0.45)" }, // Mint/Aqua (Xác suất)
  { fill: "#de7d6b", stroke: "#fecdd3", halo: "rgba(222, 125, 107, 0.45)" }, // Coral (Thống kê)
  { fill: "#63c99a", stroke: "#d1fae5", halo: "rgba(99, 201, 154, 0.45)" }, // Emerald (PP số)
];

function formatLabel(label: string): string {
  if (label.length <= 20) return label;
  // Clean word break if too long
  const truncated = label.slice(0, 19);
  const lastSpace = truncated.lastIndexOf(" ");
  return lastSpace > 10 ? `${truncated.slice(0, lastSpace)}…` : `${truncated}…`;
}

export function KnowledgeCanopy({
  regions,
  subjectName,
  targetName,
}: KnowledgeCanopyProps) {
  const titleId = useId();
  const [activeRegion, setActiveRegion] = useState<KnowledgeRegionViewModel | null>(null);

  const visibleRegions = regions.slice(0, 6);
  const centerX = 300;
  const centerY = 230;

  // Interconnected constellation links between consecutive nodes
  const constellationLinks = NODE_CONFIGS.map((pt, index) => {
    const nextPt = NODE_CONFIGS[(index + 1) % NODE_CONFIGS.length];
    return `M ${pt.x} ${pt.y} L ${nextPt.x} ${nextPt.y}`;
  });

  return (
    <div className={styles.canopyWrap} data-testid="galaxy-radar-widget">
      <svg
        className={styles.canopy}
        viewBox="0 0 600 460"
        role="group"
        aria-labelledby={titleId}
      >
        <title id={titleId}>{`Vũ trụ tri thức của ${subjectName}`}</title>
        <defs>
          <filter id="radarGlow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="6" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <filter id="intenseCoreGlow" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="12" result="blur1" />
            <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="blur2" />
            <feMerge>
              <feMergeNode in="blur1" />
              <feMergeNode in="blur2" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <radialGradient id="centerNucleusGradient" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#63c99a" stopOpacity="1" />
            <stop offset="45%" stopColor="#286955" stopOpacity="0.85" />
            <stop offset="85%" stopColor="#102e26" stopOpacity="0.5" />
            <stop offset="100%" stopColor="#0a1d18" stopOpacity="0" />
          </radialGradient>
        </defs>

        {/* Multi-layered Glowing Orbit Tracks */}
        <circle cx={centerX} cy={centerY} r="205" className={styles.orbitTrackOuter} />
        <circle cx={centerX} cy={centerY} r="145" className={styles.orbitTrackMain} />
        <circle cx={centerX} cy={centerY} r="85" className={styles.orbitTrackInner} />

        {/* Pulsating energy ripple around center core */}
        <circle cx={centerX} cy={centerY} className={styles.corePulseRing} />

        {/* Constellation Connection Beams between Chapter Stars */}
        <g aria-hidden="true">
          {constellationLinks.map((path, idx) => {
            const isHighlighted =
              activeRegion &&
              (idx === visibleRegions.findIndex((r) => r.id === activeRegion.id) ||
                (idx + 1) % 6 === visibleRegions.findIndex((r) => r.id === activeRegion.id));

            return (
              <path
                key={idx}
                d={path}
                className={`${styles.constellationBeam} ${
                  isHighlighted ? styles.constellationBeamActive : ""
                }`}
                filter="url(#radarGlow)"
              />
            );
          })}

          {/* Radial Spokes connecting Center Core to Constellation Stars */}
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

        {/* Central Core: Subject Heart Nucleus */}
        <g
          className={styles.coreNode}
          role="button"
          tabIndex={0}
          aria-label={`Môn học ${subjectName}`}
        >
          {/* Outer glowing halo */}
          <circle
            cx={centerX}
            cy={centerY}
            r="52"
            fill="url(#centerNucleusGradient)"
            filter="url(#intenseCoreGlow)"
          />
          {/* Main Core Body */}
          <circle
            cx={centerX}
            cy={centerY}
            r="40"
            fill="#0f2b23"
            stroke="#63c99a"
            strokeWidth="3"
            filter="url(#radarGlow)"
          />
          {/* Subject Name - CRISP WHITE & BOLD */}
          <text
            x={centerX}
            y={centerY - 3}
            fill="#ffffff"
            fontWeight="800"
            fontSize="13px"
            textAnchor="middle"
            letterSpacing="0.03em"
            filter="drop-shadow(0 2px 4px rgba(0,0,0,0.9))"
            pointerEvents="none"
          >
            {subjectName}
          </text>
          {/* Subtitle - RADIANT MINT */}
          <text
            x={centerX}
            y={centerY + 14}
            fill="#a9e6c3"
            fontWeight="700"
            fontSize="9px"
            textAnchor="middle"
            letterSpacing="0.08em"
            pointerEvents="none"
          >
            VŨ TRỤ TRI THỨC
          </text>
        </g>

        {/* Orbiting Constellation Chapter Star Nodes */}
        {visibleRegions.map((region, index) => {
          const cfg = NODE_CONFIGS[index];
          const theme = CHAPTER_THEMES[index % CHAPTER_THEMES.length];
          const isSelected =
            activeRegion?.id === region.id ||
            (targetName && targetName.includes(region.label));

          return (
            <g
              key={region.id}
              className={styles.chapterNode}
              role="button"
              tabIndex={0}
              aria-label={`${region.label}: ${getRegionStateCopy(region.state)}`}
              onMouseEnter={() => setActiveRegion(region)}
              onMouseLeave={() => setActiveRegion(null)}
              onClick={() => setActiveRegion(region)}
            >
              {/* Invisible stable pointer hit-area (guarantees zero flicker on mouse hover) */}
              <circle
                cx={cfg.x}
                cy={cfg.y}
                r="38"
                fill="transparent"
                pointerEvents="all"
              />

              {/* Outer Glowing Halo - Expands smoothly on hover */}
              <circle
                cx={cfg.x}
                cy={cfg.y}
                r={isSelected ? 30 : 23}
                fill={theme.halo}
                stroke={theme.stroke}
                strokeWidth={isSelected ? 2.5 : 1.2}
                strokeOpacity={isSelected ? 1 : 0.6}
                className={styles.nodeHalo}
                filter="url(#radarGlow)"
                pointerEvents="none"
              />

              {/* Main Star Body - Expands smoothly in-place */}
              <circle
                cx={cfg.x}
                cy={cfg.y}
                r={isSelected ? 19 : 16}
                fill={theme.fill}
                stroke="#ffffff"
                strokeWidth="2.5"
                className={styles.nodeBody}
                filter="url(#radarGlow)"
                pointerEvents="none"
              />

              {/* Chapter Index Number in Star Center */}
              <text
                x={cfg.x}
                y={cfg.y + 4.5}
                fill="#ffffff"
                fontSize="11.5px"
                fontWeight="800"
                textAnchor="middle"
                pointerEvents="none"
              >
                {index + 1}
              </text>

              {/* Star Sparkle Deco above Node */}
              <text
                x={cfg.x + 13}
                y={cfg.y - 12}
                className={styles.starSparkle}
                fontSize="11"
              >
                ✦
              </text>

              {/* Chapter Name Label (Strictly calculated coordinates, ZERO overlap with circles!) */}
              <text
                x={cfg.titleX}
                y={cfg.titleY}
                className={styles.nodeLabel}
              >
                {formatLabel(region.label)}
              </text>

              {/* Progress / Mastery Level Sub-label (VIBRANT MINT, ZERO overlap!) */}
              <text
                x={cfg.subX}
                y={cfg.subY}
                className={styles.nodeSubLabel}
              >
                {region.progress !== undefined
                  ? `${region.progress}% vững · ${getRegionStateCopy(region.state)}`
                  : "Chưa đo điểm"}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Dynamic Glowing Status Pill below Radar */}
      <div
        className={`${styles.tooltipWrap} ${
          activeRegion ? styles.tooltipWrapActive : ""
        }`}
      >
        {activeRegion ? (
          <span className="flex items-center justify-center gap-2">
            <Sparkles size={15} className="text-amber-300 animate-pulse" />
            <strong className="text-white">{activeRegion.label}:</strong>
            <span className="text-emerald-400 font-bold">
              {getRegionStateCopy(activeRegion.state)}
            </span>
            {activeRegion.progress !== undefined ? (
              <span className="bg-emerald-950/80 px-2 py-0.5 rounded-full text-xs text-emerald-300 border border-emerald-500/30">
                {activeRegion.progress}%
              </span>
            ) : null}
          </span>
        ) : (
          <span className="flex items-center justify-center gap-1.5 opacity-90">
            <Sparkles size={14} className="text-emerald-400" />
            <span>Chạm hoặc rê chuột vào 6 chòm sao để xem độ thành thạo</span>
          </span>
        )}
      </div>
    </div>
  );
}
