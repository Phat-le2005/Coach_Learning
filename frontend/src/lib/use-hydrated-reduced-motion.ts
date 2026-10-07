"use client";

import { useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

/**
 * Keeps the server render and the first client render identical, then applies
 * the user's motion preference after hydration.
 */
export function useHydratedReducedMotion(): boolean {
  const preference = useReducedMotion();
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    setReducedMotion(Boolean(preference));
  }, [preference]);

  return reducedMotion;
}
