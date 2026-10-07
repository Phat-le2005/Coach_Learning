"use client";

import { motion } from "motion/react";
import { useId } from "react";

import { useHydratedReducedMotion } from "@/lib/use-hydrated-reduced-motion";

import styles from "./ui.module.css";

export interface ProgressRingProps {
  value?: number;
  size?: number;
  strokeWidth?: number;
  label?: string;
}

export function ProgressRing({ value, size = 74, strokeWidth = 7, label }: ProgressRingProps) {
  const reducedMotion = useHydratedReducedMotion();
  const gradientId = useId().replaceAll(":", "");
  const normalized = value === undefined ? undefined : Math.min(100, Math.max(0, value));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = normalized === undefined ? circumference : circumference * (1 - normalized / 100);
  const text = normalized === undefined ? "—" : `${Math.round(normalized)}%`;

  return (
    <span
      className={styles.ring}
      style={{ width: size, height: size }}
      role="img"
      aria-label={label ?? (normalized === undefined ? "Chưa đo lường" : `Tiến độ ${text}`)}
    >
      <svg className={styles.ringSvg} width={size} height={size} aria-hidden="true">
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="var(--mint-500)" />
            <stop offset="100%" stopColor="var(--aqua-500)" />
          </linearGradient>
        </defs>
        <circle
          className={styles.ringTrack}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={strokeWidth}
        />
        {normalized !== undefined ? (
          <motion.circle
            className={styles.ringValue}
            cx={size / 2}
            cy={size / 2}
            r={radius}
            strokeWidth={strokeWidth}
            stroke={`url(#${gradientId})`}
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: reducedMotion ? 0 : 0.8, ease: [0.22, 1, 0.36, 1] }}
          />
        ) : null}
      </svg>
      <span className={styles.ringLabel}>{text}</span>
    </span>
  );
}
