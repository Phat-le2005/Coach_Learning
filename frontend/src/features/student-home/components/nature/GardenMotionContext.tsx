"use client";

import {
  createContext,
  type ReactNode,
  type RefObject,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import { useHydratedReducedMotion } from "@/lib/use-hydrated-reduced-motion";

const AMBIENT_STORAGE_KEY = "edums_garden_ambient_enabled";

export interface GardenMotionContextValue {
  /** User-controlled toggle for ambient nature animations */
  ambientEnabled: boolean;
  toggleAmbient: () => void;
  /** OS-level prefers-reduced-motion */
  isReducedMotion: boolean;
  /** True when browser tab is backgrounded/hidden */
  isTabHidden: boolean;
  /** True on mobile viewports (<= 767px) to scale down particle density & parallax */
  isMobile: boolean;
  /** Master flag: true when user-controlled garden motion is enabled and browser tab is visible */
  shouldAnimate: boolean;
}

const GardenMotionContext = createContext<GardenMotionContextValue>({
  ambientEnabled: true,
  toggleAmbient: () => {},
  isReducedMotion: false,
  isTabHidden: false,
  isMobile: false,
  shouldAnimate: true,
});

export function GardenMotionProvider({ children }: { children: ReactNode }) {
  const isReducedMotion = useHydratedReducedMotion();
  const [ambientEnabled, setAmbientEnabled] = useState(true);
  const [isTabHidden, setIsTabHidden] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // Hydrate stored user preference for ambient nature effects
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(AMBIENT_STORAGE_KEY);
      if (saved === "false") {
        setAmbientEnabled(false);
      }
    } catch {
      // Ignore storage access errors in restricted environments
    }
  }, []);

  // Pause animations automatically when browser tab is hidden
  useEffect(() => {
    const handleVisibility = () => {
      setIsTabHidden(document.hidden);
    };
    handleVisibility();
    document.addEventListener("visibilitychange", handleVisibility);
    return () => document.removeEventListener("visibilitychange", handleVisibility);
  }, []);

  // Detect mobile viewport to reduce ambient complexity & parallax
  useEffect(() => {
    const mql = window.matchMedia("(max-width: 767px)");
    const update = () => setIsMobile(mql.matches);
    update();
    mql.addEventListener("change", update);
    return () => mql.removeEventListener("change", update);
  }, []);

  const toggleAmbient = useCallback(() => {
    setAmbientEnabled((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(AMBIENT_STORAGE_KEY, String(next));
      } catch {
        // Ignore storage errors
      }
      return next;
    });
  }, []);

  // Decouple default Living Garden motion from Windows client-area animation flags
  // (SPI_GETCLIENTAREAANIMATION=False sets prefers-reduced-motion: reduce on many laptops),
  // while giving the user an always-visible "Gió vườn / Tĩnh" toggle persisted in localStorage.
  const shouldAnimate = ambientEnabled && !isTabHidden;

  const value = useMemo<GardenMotionContextValue>(
    () => ({
      ambientEnabled,
      toggleAmbient,
      isReducedMotion,
      isTabHidden,
      isMobile,
      shouldAnimate,
    }),
    [ambientEnabled, toggleAmbient, isReducedMotion, isTabHidden, isMobile, shouldAnimate]
  );

  return <GardenMotionContext.Provider value={value}>{children}</GardenMotionContext.Provider>;
}

export function useGardenMotion(): GardenMotionContextValue {
  return useContext(GardenMotionContext);
}

/**
 * Lightweight IntersectionObserver hook to pause section-local CSS animations
 * when scrolled well outside the viewport, preventing off-screen GPU work
 * without causing any layout shift.
 */
export function useGardenSectionInView<T extends HTMLElement = HTMLElement>(
  rootMargin = "220px 0px"
): { ref: RefObject<T | null>; isInView: boolean } {
  const ref = useRef<T | null>(null);
  const [isInView, setIsInView] = useState(true);

  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver(
      (entries) => {
        const entry = entries[0];
        if (entry) {
          setIsInView(entry.isIntersecting);
        }
      },
      { rootMargin, threshold: 0 }
    );

    observer.observe(node);
    return () => observer.disconnect();
  }, [rootMargin]);

  return { ref, isInView };
}
