"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

import { springSoft } from "@/lib/motion";

export interface MotionProviderProps {
  children: ReactNode;
}

export function MotionProvider({ children }: MotionProviderProps) {
  return (
    <MotionConfig reducedMotion="user" transition={springSoft}>
      {children}
    </MotionConfig>
  );
}
