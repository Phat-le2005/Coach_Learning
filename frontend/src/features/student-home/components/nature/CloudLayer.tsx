"use client";

import type { CSSProperties } from "react";

import styles from "./LivingGardenBackdrop.module.css";

export interface CloudLayerProps {
  depth?: "far" | "near";
  count?: number;
}

interface CloudSpec {
  top: string;
  width: string;
  opacity: string;
  duration: string;
  delay: string;
}

const FAR_CLOUDS: CloudSpec[] = [
  { top: "5%", width: "260px", opacity: "0.52", duration: "92s", delay: "-14s" },
  { top: "14%", width: "200px", opacity: "0.42", duration: "108s", delay: "-54s" },
  { top: "9%", width: "230px", opacity: "0.46", duration: "98s", delay: "-76s" },
];

const NEAR_CLOUDS: CloudSpec[] = [
  { top: "19%", width: "310px", opacity: "0.58", duration: "76s", delay: "-28s" },
  { top: "27%", width: "240px", opacity: "0.44", duration: "84s", delay: "-62s" },
];

export function CloudLayer({ depth = "far", count }: CloudLayerProps) {
  const source = depth === "far" ? FAR_CLOUDS : NEAR_CLOUDS;
  const items = count !== undefined ? source.slice(0, count) : source;

  return (
    <div className={styles.skyCloudLayer} aria-hidden="true">
      {items.map((cloud, index) => {
        const customStyle: CSSProperties & Record<string, string> = {
          top: cloud.top,
          "--cloud-width": cloud.width,
          "--cloud-opacity": cloud.opacity,
          "--cloud-duration": cloud.duration,
          "--cloud-delay": cloud.delay,
        };
        return (
          <div className={styles.cloudItem} style={customStyle} key={`${depth}-${index}`}>
            <svg className={styles.cloudSvg} viewBox="0 0 260 88" fill="none">
              <path
                d="M34 68H222C237.464 68 250 56.3594 250 42C250 28.597 239.048 17.566 225.008 16.148C218.545 6.453 207.299 0 194.5 0C178.902 0 165.729 9.575 160.377 23.095C154.789 19.862 148.257 18 141.25 18C123.798 18 109.259 30.181 105.787 46.391C101.414 44.229 96.484 43 91.25 43C75.996 43 63.36 53.792 60.558 68H34Z"
                fill="#F7F7EE"
              />
              <path
                d="M52 68H218C230 68 240 60 242 50C226 57 198 60 158 60C114 60 76 57 52 68Z"
                fill="#B8E3DE"
                fillOpacity="0.35"
              />
            </svg>
          </div>
        );
      })}
    </div>
  );
}
