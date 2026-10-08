"use client";

import { motion } from "motion/react";
import type { CSSProperties } from "react";

import { useHydratedReducedMotion } from "@/lib/use-hydrated-reduced-motion";

import styles from "./ui.module.css";

export interface AmbientGlowProps {
  className?: string;
  color?: string;
  size?: number;
  opacity?: number;
  duration?: number;
  animated?: boolean;
}

type GlowStyle = CSSProperties & {
  "--glow-color": string;
  "--glow-size": string;
  "--glow-opacity": number;
};

export function AmbientGlow({
  className,
  color = "var(--mint-200)",
  size = 360,
  opacity = 0.46,
  duration = 14,
  animated = true,
}: AmbientGlowProps) {
  const reducedMotion = useHydratedReducedMotion();
  const style: GlowStyle = {
    "--glow-color": color,
    "--glow-size": `${size}px`,
    "--glow-opacity": opacity,
  };

  return (
    <motion.span
      aria-hidden="true"
      className={[styles.glow, className ?? ""].filter(Boolean).join(" ")}
      style={style}
      animate={reducedMotion || !animated ? undefined : { x: [0, 16, -5, 0], y: [0, -10, 6, 0] }}
      transition={{ duration, repeat: Infinity, ease: "easeInOut" }}
    />
  );
}
