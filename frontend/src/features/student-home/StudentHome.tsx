"use client";

import { DatabaseZap, LockKeyhole } from "lucide-react";
import { motion } from "motion/react";
import type { ReactNode } from "react";

import { MotionProvider } from "@/components/motion/MotionProvider";
import { AmbientGlow } from "@/components/ui/AmbientGlow";
import { GradientButton } from "@/components/ui/GradientButton";
import { OrganicCard } from "@/components/ui/OrganicCard";
import { fadeUp, staggerContainer } from "@/lib/motion";

import type { KnowledgeRegionViewModel, StudentHomeViewModel } from "./types";
import styles from "./StudentHome.module.css";
import { CoachCard } from "./components/CoachCard";
import { ForestAtmosphere } from "./components/ForestAtmosphere";
import { FocusHero } from "./components/FocusHero";
import { GardenSkeleton, MetricSkeleton } from "./components/LoadingSkeletons";
import { KnowledgeCanopy } from "./components/KnowledgeCanopy";
import { KnowledgeGarden } from "./components/KnowledgeGarden";
import { LearningPulse } from "./components/LearningPulse";
import { PriorityPath } from "./components/PriorityPath";
import { StudentBottomNav } from "./components/StudentBottomNav";
import { StudentTopNav } from "./components/StudentTopNav";

export interface StudentHomeProps {
  data: StudentHomeViewModel;
  showPreviewBadge?: boolean;
}

const disconnectedRegions: KnowledgeRegionViewModel[] = Array.from({ length: 5 }, (_, index) => ({
  id: `disconnected-region-${index + 1}`,
  label: "Vùng tri thức chưa kết nối",
  state: "not_started" as const,
  accent: index % 2 === 0 ? "mint" as const : "sky" as const,
}));

function StudentCanvas({ children }: { children: ReactNode }) {
  return (
    <div className={styles.canvas} id="student-home">
      <ForestAtmosphere />
      <AmbientGlow className={styles.glowMint} size={440} opacity={0.33} duration={16} />
      <AmbientGlow className={styles.glowSky} color="var(--sky-200)" size={520} opacity={0.35} duration={19} animated={false} />
      <AmbientGlow className={styles.glowViolet} color="var(--violet-200)" size={410} opacity={0.28} duration={20} animated={false} />
      <span className={styles.backgroundCurveOne} aria-hidden="true" />
      <span className={styles.backgroundCurveTwo} aria-hidden="true" />
      {children}
    </div>
  );
}

export function StudentHome({ data, showPreviewBadge = false }: StudentHomeProps) {
  return (
    <MotionProvider>
      <StudentCanvas>
        <StudentTopNav
          displayName={data.student.displayName}
          avatarLabel={data.student.avatarLabel}
          activeDays={data.momentum.activeDays}
        />
        <main className={styles.main}>
          <FocusHero data={data} showPreviewBadge={showPreviewBadge} />
          <LearningPulse data={data} />
          <KnowledgeGarden regions={data.knowledgeRegions} />
          <div className={styles.closingGrid}>
            <PriorityPath priorities={data.priorities} />
            <CoachCard />
          </div>
        </main>
        <StudentBottomNav />
      </StudentCanvas>
    </MotionProvider>
  );
}

export function StudentHomeDisconnected() {
  return (
    <MotionProvider>
      <StudentCanvas>
        <StudentTopNav displayName="Bạn" avatarLabel="—" activeDays={0} />
        <main className={styles.main}>
          <motion.section
            className={`${styles.hero} ${styles.disconnectedHero}`}
            aria-labelledby="disconnected-title"
            variants={staggerContainer}
            initial="hidden"
            animate="visible"
          >
            <motion.div className={styles.heroCopy} variants={fadeUp}>
              <span className={styles.connectionPill}>
                <DatabaseZap size={15} aria-hidden="true" />
                Chưa kết nối dữ liệu
              </span>
              <p className={styles.greeting}>EduMS Learning Forest</p>
              <h1 id="disconnected-title">Không gian học tập đã sẵn sàng.</h1>
              <p className={styles.heroDescription}>
                Kết nối dữ liệu học tập để bắt đầu hành trình của bạn. Không có số liệu xem trước nào được hiển thị trong chế độ này.
              </p>
              <GradientButton disabled>
                <LockKeyhole size={17} aria-hidden="true" />
                Đang chờ dữ liệu
              </GradientButton>
            </motion.div>
            <motion.div className={styles.heroVisual} variants={fadeUp}>
              <KnowledgeCanopy regions={disconnectedRegions} subjectName="Không gian học tập" ghost />
            </motion.div>
          </motion.section>

          <section className={styles.disconnectedSection} aria-labelledby="prepared-title">
            <div className={styles.sectionHeading}>
              <div>
                <p className={styles.sectionEyebrow}>Sẵn sàng khi dữ liệu đến</p>
                <h2 id="prepared-title">Một trải nghiệm rõ ràng, không có số liệu giả</h2>
                <p>Các khu vực học tập sẽ được lấp đầy từ Student Learning State sau bước tích hợp API.</p>
              </div>
            </div>
            <div className={styles.disconnectedPreview}>
              <OrganicCard className={styles.disconnectedCard} variant="solid"><MetricSkeleton /></OrganicCard>
              <OrganicCard className={styles.disconnectedCard} variant="solid"><MetricSkeleton /></OrganicCard>
              <OrganicCard className={styles.disconnectedCard} variant="solid"><GardenSkeleton /></OrganicCard>
            </div>
          </section>
        </main>
        <StudentBottomNav />
      </StudentCanvas>
    </MotionProvider>
  );
}
