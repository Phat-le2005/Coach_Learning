"use client";

import { useGardenMotion, useGardenSectionInView } from "./GardenMotionContext";
import styles from "./LivingGardenBackdrop.module.css";

export type BridgeVariant =
  | "canopy-to-terrace"
  | "terrace-to-forest"
  | "forest-to-trail"
  | "trail-to-sanctuary";

export interface SectionNatureBridgeProps {
  variant: BridgeVariant;
}

export function SectionNatureBridge({ variant }: SectionNatureBridgeProps) {
  const { shouldAnimate } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLDivElement>("140px 0px");
  const active = shouldAnimate && isInView;

  return (
    <div
      ref={ref}
      className={`${styles.sectionBridge} ${!active ? styles.bridgePaused : ""}`}
      aria-hidden="true"
    >
      <svg className={styles.bridgeSvg} viewBox="0 0 960 64" fill="none">
        {variant === "canopy-to-terrace" && (
          <>
            <path
              d="M40 34C220 10 380 54 540 30C700 6 820 42 920 26"
              stroke="#23A67A"
              strokeOpacity="0.2"
              strokeWidth="1.5"
              strokeDasharray="6 6"
            />
            <g className={styles.bridgeSwayLeaf}>
              <path d="M472 31C462 18 446 18 438 29C450 37 464 36 472 31Z" fill="#8BE5C2" fillOpacity="0.7" />
              <path d="M488 31C498 18 514 18 522 29C510 37 496 36 488 31Z" fill="#23A67A" fillOpacity="0.45" />
              <circle cx="480" cy="31" r="4" fill="#E8BF6A" fillOpacity="0.85" />
            </g>
          </>
        )}

        {variant === "terrace-to-forest" && (
          <>
            <path
              d="M20 44C210 22 410 18 610 38C750 52 855 34 940 22"
              stroke="#23A67A"
              strokeOpacity="0.22"
              strokeWidth="1.6"
            />
            <g className={styles.bridgeSwayLeaf}>
              <path d="M290 28L298 10L306 28H290Z" fill="#23A67A" fillOpacity="0.28" />
              <path d="M304 30L314 6L324 30H304Z" fill="#8BE5C2" fillOpacity="0.52" />
              <path d="M648 39L658 15L668 39H648Z" fill="#23A67A" fillOpacity="0.32" />
              <circle cx="480" cy="25" r="3.5" fill="#E8BF6A" fillOpacity="0.75" />
            </g>
          </>
        )}

        {variant === "forest-to-trail" && (
          <>
            <path
              d="M120 18C310 52 650 12 840 46"
              stroke="#E8BF6A"
              strokeOpacity="0.42"
              strokeWidth="2"
              strokeDasharray="4 8"
              strokeLinecap="round"
            />
            <ellipse cx="380" cy="33" rx="9" ry="4" fill="#23A67A" fillOpacity="0.22" />
            <ellipse cx="480" cy="31" rx="12" ry="5" fill="#23A67A" fillOpacity="0.32" />
            <ellipse cx="580" cy="29" rx="9" ry="4" fill="#23A67A" fillOpacity="0.22" />
            <g className={styles.bridgeSwayLeaf}>
              <circle cx="480" cy="20" r="3.5" fill="#E8BF6A" />
              <path d="M480 31V22" stroke="#23A67A" strokeWidth="1.5" />
            </g>
          </>
        )}

        {variant === "trail-to-sanctuary" && (
          <>
            <path
              d="M60 36C280 18 680 18 900 36"
              stroke="#092D25"
              strokeOpacity="0.16"
              strokeWidth="1.5"
            />
            <g className={styles.bridgeSwayLeaf}>
              <path d="M466 24C452 12 434 14 426 26C442 34 456 32 466 24Z" fill="#23A67A" fillOpacity="0.42" />
              <path d="M494 24C508 12 526 14 534 26C518 34 504 32 494 24Z" fill="#8BE5C2" fillOpacity="0.62" />
              <circle cx="480" cy="24" r="4.5" fill="#23A67A" fillOpacity="0.55" />
            </g>
          </>
        )}
      </svg>
    </div>
  );
}
