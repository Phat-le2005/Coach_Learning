"use client";

import type { InkStroke } from "@/lib/api/contracts";

import styles from "../MathWorkspace.module.css";

const PAGE_WIDTH = 794;
const PAGE_HEIGHT = 1123;

interface OcrInkPreviewProps {
  strokes: InkStroke[];
}

export function OcrInkPreview({ strokes }: OcrInkPreviewProps) {
  const pens = strokes.filter((stroke) => stroke.tool === "PEN" && stroke.points.length > 0);
  if (pens.length === 0) return null;

  let minX = PAGE_WIDTH;
  let minY = PAGE_HEIGHT;
  let maxX = 0;
  let maxY = 0;
  for (const stroke of pens) {
    for (const point of stroke.points) {
      const x = Math.min(1, Math.max(0, point.x)) * PAGE_WIDTH;
      const y = Math.min(1, Math.max(0, point.y)) * PAGE_HEIGHT;
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x);
      maxY = Math.max(maxY, y);
    }
  }
  const left = Math.max(0, minX - 24);
  const top = Math.max(0, minY - 24);
  const right = Math.min(PAGE_WIDTH, maxX + 24);
  const bottom = Math.min(PAGE_HEIGHT, maxY + 24);

  return (
    <div className={styles.inkPreview}>
      <span className={styles.formLabel}>Nét viết gốc — đối chiếu từng ký hiệu trước khi lưu:</span>
      <svg
        className={styles.inkPreviewSvg}
        viewBox={`${left} ${top} ${Math.max(1, right - left)} ${Math.max(1, bottom - top)}`}
        role="img"
        aria-label="Nét viết tay đã gửi để nhận diện"
      >
        {pens.map((stroke) => {
          const points = stroke.points.map((point) => ({
            x: Math.min(1, Math.max(0, point.x)) * PAGE_WIDTH,
            y: Math.min(1, Math.max(0, point.y)) * PAGE_HEIGHT,
          }));
          const width = Math.max(2, Math.min(12, Math.round(stroke.width * 1.5)));
          if (points.length === 1) {
            return <circle key={stroke.id} cx={points[0].x} cy={points[0].y} r={Math.max(1, width / 2)} fill="#17392d" />;
          }
          const path = points.map((point, index) => `${index === 0 ? "M" : "L"}${point.x} ${point.y}`).join(" ");
          return <path key={stroke.id} d={path} fill="none" stroke="#17392d" strokeWidth={width} strokeLinecap="round" strokeLinejoin="round" />;
        })}
      </svg>
    </div>
  );
}
