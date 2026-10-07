import type { Transition, Variants } from "motion/react";

export const springSoft: Transition = {
  type: "spring",
  stiffness: 120,
  damping: 22,
  mass: 0.9,
};

export const springInteractive: Transition = {
  type: "spring",
  stiffness: 260,
  damping: 20,
  mass: 0.65,
};

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 18 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.52, ease: [0.22, 1, 0.36, 1] },
  },
};

export const fadeIn: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: { duration: 0.42, ease: [0.22, 1, 0.36, 1] },
  },
};

export const staggerContainer: Variants = {
  hidden: {},
  visible: {
    transition: {
      staggerChildren: 0.07,
      delayChildren: 0.04,
    },
  },
};

export const softScale: Variants = {
  hidden: { opacity: 0, scale: 0.97 },
  visible: {
    opacity: 1,
    scale: 1,
    transition: springSoft,
  },
};
