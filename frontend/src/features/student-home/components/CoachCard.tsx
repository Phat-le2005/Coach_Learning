"use client";

import { ArrowRight, BookOpenCheck, Lightbulb, PenTool, Shapes, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { useHydratedReducedMotion } from "@/lib/use-hydrated-reduced-motion";

import styles from "../StudentHome.module.css";
import { SectionHeading } from "./SectionHeading";

const coachCapabilities = [
  {
    title: "Gợi ý hướng đi tiếp",
    desc: "Bật mí nấc tiếp theo khi bạn bí ý tưởng, không giải hộ.",
    icon: Lightbulb,
    badge: "Từng bước",
    color: "#f59e0b",
  },
  {
    title: "Khái niệm & Công thức",
    desc: "Tự động nhắc lại định lý và công thức then chốt liên quan.",
    icon: BookOpenCheck,
    badge: "Lý thuyết",
    color: "#38bdf8",
  },
  {
    title: "Ví dụ mẫu tương tự",
    desc: "Tham khảo dạng bài tương đương để hiểu rõ cách tư duy.",
    icon: Shapes,
    badge: "Mẫu giải",
    color: "#a855f7",
  },
];

export function CoachCard() {
  const reducedMotion = useHydratedReducedMotion();

  return (
    <section className={styles.coachSection} id="coach" aria-labelledby="coach-title">
      <SectionHeading eyebrow="Quiet intelligence" title="Trợ lý AI Coach" />

      <div className={styles.coachCardNew}>
        {/* Background Ambient Cosmic Aura */}
        <span
          style={{
            position: "absolute",
            top: "-80px",
            right: "-80px",
            width: "260px",
            height: "260px",
            borderRadius: "50%",
            background: "radial-gradient(circle, #63c99a 0%, #5ca9d6 50%, transparent 70%)",
            opacity: 0.35,
            filter: "blur(50px)",
            pointerEvents: "none",
          }}
          aria-hidden="true"
        />

        <div>
          {/* Header Visual: Rotating Quantum AI Orb */}
          <div className={styles.coachTopRow}>
            <div className={styles.coachOrbNew}>
              {/* Rotating outer orbit ring */}
              <motion.span
                style={{
                  position: "absolute",
                  inset: 0,
                  borderRadius: "50%",
                  border: "1px dashed rgba(99, 201, 154, 0.45)",
                }}
                animate={reducedMotion ? undefined : { rotate: 360 }}
                transition={{ duration: 16, repeat: Infinity, ease: "linear" }}
              >
                <i
                  style={{
                    position: "absolute",
                    top: 0,
                    left: "50%",
                    transform: "translate(-50%, -50%)",
                    width: "8px",
                    height: "8px",
                    borderRadius: "50%",
                    background: "#fde047",
                    boxShadow: "0 0 10px #fde047",
                  }}
                />
              </motion.span>

              {/* Inner pulsed ring */}
              <span
                style={{
                  position: "absolute",
                  inset: "8px",
                  borderRadius: "50%",
                  border: "1px solid rgba(56, 189, 248, 0.35)",
                }}
              />

              {/* Center Core */}
              <div className={styles.coachOrbCenter}>
                <Sparkles size={20} style={{ color: "#fef08a" }} />
              </div>
            </div>

            <span className={styles.coachStatusBadge}>
              <span
                style={{
                  width: "7px",
                  height: "7px",
                  borderRadius: "50%",
                  background: "#34d399",
                  boxShadow: "0 0 8px #34d399",
                }}
              />
              Sẵn sàng 24/7 trên giấy số
            </span>
          </div>

          {/* Title & Copy */}
          <p className={styles.coachSubtitle}>
            Gợi mở thông minh
          </p>
          <h2 id="coach-title" className={styles.coachHeading}>
            Một gợi ý đúng lúc giúp bạn tự mình tìm ra bước tiếp theo.
          </h2>
          <p className={styles.coachDesc}>
            Coach phân tích từng nét viết toán học của bạn qua AI OCR, phát hiện ngay chỗ nhầm lẫn và đưa ra gợi ý nâng bậc mà không giải hộ.
          </p>

          {/* 3 Capability Cards */}
          <div>
            {coachCapabilities.map((item, idx) => {
              const Icon = item.icon;
              return (
                <div key={idx} className={styles.coachItemRow}>
                  <div
                    className={styles.coachFeatureIcon}
                    style={{ background: `${item.color}25`, color: item.color }}
                  >
                    <Icon size={16} />
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className={styles.coachFeatureHeader}>
                      <h4 className={styles.coachFeatureTitle}>{item.title}</h4>
                      <span className={styles.coachFeatureBadge}>
                        {item.badge}
                      </span>
                    </div>
                    <p className={styles.coachFeatureText}>
                      {item.desc}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Footer CTA Button */}
        <div>
          <Link href="/student/attempts" className={styles.coachCtaButton}>
            <PenTool size={15} />
            Mở Trang làm bài & Trải nghiệm AI
            <ArrowRight size={15} />
          </Link>
          <p className={styles.coachFootnote}>
            ✦ AI được kích hoạt tự động theo từng bước giải trên giấy A4
          </p>
        </div>
      </div>
    </section>
  );
}
