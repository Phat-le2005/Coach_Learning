"use client";

import { ArrowRight, BookOpenCheck, Lightbulb, PenTool, Shapes, Sparkles } from "lucide-react";
import Link from "next/link";

import styles from "../StudentHome.module.css";
import { SectionHeading } from "./SectionHeading";
import { useGardenMotion, useGardenSectionInView } from "./nature/GardenMotionContext";

const coachCapabilities = [
  {
    title: "Gợi ý hướng đi tiếp",
    desc: "Bật mí nấc suy luận tiếp theo khi bạn chững lại, tuyệt đối không giải hộ.",
    icon: Lightbulb,
    badge: "Từng bước",
    accent: "#E8BF6A",
  },
  {
    title: "Khái niệm & Công thức",
    desc: "Nhắc lại đúng định lý và công thức nền tảng gắn liền với bài đang giải.",
    icon: BookOpenCheck,
    badge: "Lý thuyết",
    accent: "#B8E3DE",
  },
  {
    title: "Ví dụ mẫu tương tự",
    desc: "Đối chiếu với một bài toán cùng cấu trúc để bạn tự nhận ra quy luật.",
    icon: Shapes,
    badge: "Mẫu tư duy",
    accent: "#8BE5C2",
  },
];

export function CoachCard() {
  const { shouldAnimate } = useGardenMotion();
  const { ref, isInView } = useGardenSectionInView<HTMLElement>("180px 0px");
  const active = shouldAnimate && isInView;

  return (
    <section
      ref={ref}
      className={`${styles.section} ${styles.wisdomSection} ${
        !active ? styles.sectionAnimPaused : ""
      }`}
      id="coach"
      aria-labelledby="coach-title"
    >
      <SectionHeading
        eyebrow="Góc tĩnh tâm · Quiet Intelligence"
        title="Trợ lý AI Coach dưới tán cây tri thức"
        description="Một góc yên bình để suy ngẫm sâu hơn cùng người đồng hành AI tinh tế trên trang giấy số."
      />

      <div className={styles.wisdomSanctuaryCard}>
        {/* Backlit Soft Sunlight & Ancient Shade Tree Canopy SVG */}
        <span className={styles.wisdomBacklightGlow} aria-hidden="true" />
        <svg
          className={styles.wisdomShadeTreeSvg}
          viewBox="0 0 920 380"
          preserveAspectRatio="xMinYMin slice"
          fill="none"
          aria-hidden="true"
        >
          {/* Ancient Tree Trunk & Overarching Shade Bough */}
          <path
            d="M-20 380C8 280 18 175 12 72C48 56 128 38 248 42C340 45 430 64 510 88"
            stroke="#8BE5C2"
            strokeOpacity="0.16"
            strokeWidth="18"
            strokeLinecap="round"
          />
          <path
            d="M14 115C88 84 176 76 278 92M168 48C236 24 318 22 396 44"
            stroke="#8BE5C2"
            strokeOpacity="0.14"
            strokeWidth="7"
            strokeLinecap="round"
          />
          {/* Gently Swaying Shade Canopy Clusters */}
          <g className={styles.wisdomCanopySway}>
            <ellipse cx="130" cy="42" rx="115" ry="46" fill="#23A67A" fillOpacity="0.16" />
            <ellipse cx="275" cy="36" rx="130" ry="48" fill="#8BE5C2" fillOpacity="0.12" />
            <ellipse cx="420" cy="54" rx="105" ry="38" fill="#23A67A" fillOpacity="0.12" />
            {/* Individual delicate hanging leaves */}
            <path d="M210 92C202 108 206 122 218 128C224 114 220 100 210 92Z" fill="#8BE5C2" fillOpacity="0.32" />
            <path d="M356 82C348 96 352 110 364 115C370 102 366 88 356 82Z" fill="#E8BF6A" fillOpacity="0.26" />
            <path d="M476 96C468 108 472 120 482 125C488 114 484 102 476 96Z" fill="#8BE5C2" fillOpacity="0.28" />
          </g>
        </svg>

        {/* Left Column: Calm Jade Crystal Orb, Copy & Primary CTA */}
        <div className={styles.wisdomIntroColumn}>
          <div className={styles.coachTopRow}>
            {/* Refined Jade Knowledge Crystal / Orb */}
            <div className={styles.wisdomCrystalOrb} aria-hidden="true">
              <span className={styles.wisdomOrbRingOuter} />
              <span className={styles.wisdomOrbRingInner} />
              <div className={styles.wisdomOrbCore}>
                <Sparkles size={20} />
              </div>
            </div>

            <span className={styles.coachStatusBadge}>
              <span className={styles.wisdomStatusDot} aria-hidden="true" />
              Sẵn sàng 24/7 trên giấy số
            </span>
          </div>

          <p className={styles.coachSubtitle}>Gợi mở thông minh · Không giải hộ</p>
          <h3 id="coach-title" className={styles.wisdomHeading}>
            Một gợi ý đúng lúc giúp bạn tự mình tìm ra bước tiếp theo.
          </h3>
          <p className={styles.wisdomDesc}>
            Dưới góc vườn tĩnh lặng này, AI Coach đọc từng bước biến đổi toán học bạn viết qua OCR,
            nhận diện nhẹ nhàng điểm vướng mắc và mở lối tư duy để bạn tự làm chủ lời giải.
          </p>

          <div className={styles.wisdomCtaWrap}>
            <Link href="/student/attempts" className={styles.wisdomCtaButton}>
              <PenTool size={16} aria-hidden="true" />
              Mở Trang làm bài & Trải nghiệm AI
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
            <p className={styles.wisdomFootnote}>
              ✦ AI Coach tự động đồng hành theo từng dòng lời giải trên giấy A4
            </p>
          </div>
        </div>

        {/* Right Column: 3 Organic Capability Stones */}
        <div className={styles.wisdomCapabilitiesColumn}>
          {coachCapabilities.map((item, idx) => {
            const Icon = item.icon;
            return (
              <div key={idx} className={styles.wisdomFeatureCard}>
                <div
                  className={styles.coachFeatureIcon}
                  style={{
                    background: `${item.accent}22`,
                    color: item.accent,
                    border: `1px solid ${item.accent}38`,
                  }}
                  aria-hidden="true"
                >
                  <Icon size={17} />
                </div>
                <div className={styles.wisdomFeatureCopy}>
                  <div className={styles.coachFeatureHeader}>
                    <h4 className={styles.coachFeatureTitle}>{item.title}</h4>
                    <span className={styles.coachFeatureBadge}>{item.badge}</span>
                  </div>
                  <p className={styles.coachFeatureText}>{item.desc}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
