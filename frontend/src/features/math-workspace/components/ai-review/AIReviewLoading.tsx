"use client";

import React, { useEffect, useState } from "react";
import { Sparkles, Check, ScanLine } from "lucide-react";
import type { SolutionStepRead } from "@/lib/api/contracts";
import styles from "./AIReview.module.css";

interface AIReviewLoadingProps {
  stepCount: number;
  steps?: ReadonlyArray<SolutionStepRead>;
}

const SCAN_STAGES = [
  "Quét cấu trúc các bước giải & ký hiệu Toán học",
  "Đối chiếu biến đổi với đáp án tham chiếu chuẩn",
  "Tổng hợp nhận xét sư phạm cho từng bước giải",
];

export function AIReviewLoading({
  stepCount,
  steps = [],
}: AIReviewLoadingProps) {
  const [activeStage, setActiveStage] = useState(0);
  const [tickerIdx, setTickerIdx] = useState(0);

  useEffect(() => {
    const t1 = window.setTimeout(() => setActiveStage(1), 750);
    const t2 = window.setTimeout(() => setActiveStage(2), 1500);
    return () => {
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, []);

  useEffect(() => {
    if (steps.length <= 1) return;
    const interval = window.setInterval(() => {
      setTickerIdx((prev) => (prev + 1) % steps.length);
    }, 520);
    return () => window.clearInterval(interval);
  }, [steps.length]);

  const currentTickerStep = steps[tickerIdx];
  const tickerPreview =
    currentTickerStep?.content_latex ||
    currentTickerStep?.explanation_text ||
    (currentTickerStep?.artifact?.artifact_type === "VARIATION_TABLE"
      ? "Bảng biến thiên hàm số"
      : null);

  return (
    <div
      className={styles.loadingCard}
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <div className={styles.orbitalStage} aria-hidden="true">
        <div className={styles.orbitRingOuter} />
        <div className={styles.orbitRingInner} />
        <div className={styles.orbitRipple} />
        <div className={styles.loadingOrb}>
          <Sparkles size={28} />
        </div>
        <span className={`${styles.floatingGlyph} ${styles.glyphTopLeft}`}>
          f&apos;(x)
        </span>
        <span className={`${styles.floatingGlyph} ${styles.glyphTopRight}`}>
          ∑
        </span>
        <span className={`${styles.floatingGlyph} ${styles.glyphBottom}`}>
          Δ
        </span>
      </div>

      <div>
        <h3 className={styles.loadingHeading}>
          Gemini đang quét & đối chiếu lời giải từng bước...
        </h3>
        <p className={styles.loadingSubtext}>
          Đang phân tích tuần tự{" "}
          {stepCount > 0 ? `${stepCount} bước giải` : "các bước giải"} đã xác
          nhận của bạn với đáp án chuẩn.
        </p>
      </div>

      <div className={styles.loadingShorthandBar} aria-hidden="true" />

      {currentTickerStep && tickerPreview && (
        <div className={styles.scanFormulaTicker}>
          <span className={styles.scanTickerBadge}>
            <ScanLine
              size={11}
              style={{ marginRight: 4, verticalAlign: "middle" }}
            />
            Đang quét Bước {currentTickerStep.step_index}
          </span>
          <span className={styles.scanTickerFormula}>{tickerPreview}</span>
        </div>
      )}

      <ul className={styles.loadingStepList}>
        {SCAN_STAGES.map((label, idx) => {
          const isDone = idx < activeStage;
          const isCurrent = idx === activeStage;
          return (
            <li
              key={label}
              className={`${styles.loadingStepItem} ${
                isCurrent ? styles.loadingStepItemActive : ""
              } ${isDone ? styles.loadingStepItemDone : ""}`}
            >
              <div className={styles.loadingStepLeft}>
                <span
                  className={`${styles.loadingBullet} ${
                    isCurrent ? styles.loadingBulletActive : ""
                  } ${isDone ? styles.loadingBulletDone : ""}`}
                  aria-hidden="true"
                />
                <span>{label}</span>
              </div>
              {isDone ? (
                <span className={styles.loadingStageTag}>
                  <Check
                    size={11}
                    style={{ marginRight: 3, verticalAlign: "middle" }}
                  />
                  Đã quét
                </span>
              ) : isCurrent ? (
                <span className={styles.loadingStageTag}>Đang xử lý...</span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
