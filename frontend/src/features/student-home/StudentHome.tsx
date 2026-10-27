"use client";

import { DatabaseZap, LockKeyhole } from "lucide-react";
import { MotionConfig, motion } from "motion/react";
import { type ReactNode, useState } from "react";

import { MotionProvider } from "@/components/motion/MotionProvider";
import { GradientButton } from "@/components/ui/GradientButton";
import { OrganicCard } from "@/components/ui/OrganicCard";
import { fadeUp, springSoft, staggerContainer } from "@/lib/motion";

import type { ResolvedStudentAction } from "./action-resolver";
import { ActionDetailModal } from "./components/ActionDetailModal";
import { CoachCard } from "./components/CoachCard";
import { FocusHero } from "./components/FocusHero";
import { GardenHorizonEnding } from "./components/GardenHorizonEnding";
import { KnowledgeCanopy } from "./components/KnowledgeCanopy";
import { KnowledgeGarden } from "./components/KnowledgeGarden";
import { LearningPulse } from "./components/LearningPulse";
import { GardenSkeleton, MetricSkeleton } from "./components/LoadingSkeletons";
import { PriorityPath } from "./components/PriorityPath";
import { PracticePathway } from "./components/PracticePathway";
import { StudentBottomNav } from "./components/StudentBottomNav";
import { StudentTopNav } from "./components/StudentTopNav";
import { CanopyMarginFallingLeaves } from "./components/nature/BirdsAndLeaves";
import { GardenMotionProvider, useGardenMotion } from "./components/nature/GardenMotionContext";
import { HeroNatureScene } from "./components/nature/HeroNatureScene";
import { LivingGardenBackdrop } from "./components/nature/LivingGardenBackdrop";
import { SectionNatureBridge } from "./components/nature/SectionNatureBridge";
import styles from "./StudentHome.module.css";
import type { PriorityViewModel, StudentHomeViewModel } from "./types";

export interface StudentHomeProps {
  data: StudentHomeViewModel;
}

function LivingGardenCanvas({ children }: { children: ReactNode }) {
  const { ambientEnabled } = useGardenMotion();

  return (
    <MotionConfig reducedMotion={ambientEnabled ? "never" : "always"} transition={springSoft}>
      <div
        className={styles.canvas}
        id="student-home"
        data-garden-motion={ambientEnabled ? "on" : "off"}
      >
        <LivingGardenBackdrop />
        <CanopyMarginFallingLeaves />
        {children}
      </div>
    </MotionConfig>
  );
}

export function StudentHome({ data }: StudentHomeProps) {
  const [selectedAction, setSelectedAction] = useState<ResolvedStudentAction | null>(null);
  const [selectedPriority, setSelectedPriority] = useState<PriorityViewModel | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleOpenActionDetail = () => {
    setSelectedAction(data.resolvedAction);
    setSelectedPriority(null);
    setIsModalOpen(true);
  };

  const handleSelectPriority = (priority: PriorityViewModel) => {
    setSelectedAction(null);
    setSelectedPriority(priority);
    setIsModalOpen(true);
  };

  const handleCloseModal = () => {
    setIsModalOpen(false);
    setSelectedAction(null);
    setSelectedPriority(null);
  };

  return (
    <MotionProvider>
      <GardenMotionProvider>
        <LivingGardenCanvas>
          <StudentTopNav
            displayName={data.student.displayName}
            email={data.student.email}
            activeDays={data.momentum.activeDays}
            currentRoute="/student"
            subjectId={data.subject.id}
            showAmbientToggle
          />

          <main className={styles.main}>
            {/* SECTION 1 — HERO: Welcome to the Garden */}
            <FocusHero data={data} onOpenActionDetail={handleOpenActionDetail} />

            {/* SECTION 2 — PRACTICE ENTRY: Learning Path */}
            <PracticePathway data={data} />

            <SectionNatureBridge variant="canopy-to-terrace" />

            {/* SECTION 3 — LEARNING PULSE: Garden of Progress */}
            <LearningPulse data={data} />

            <SectionNatureBridge variant="terrace-to-forest" />

            {/* SECTION 4 — KNOWLEDGE GARDEN: Forest of Knowledge */}
            <KnowledgeGarden regions={data.knowledgeRegions} subjectId={data.subject.id} />

            <SectionNatureBridge variant="forest-to-trail" />

            {/* SECTION 5 — PRIORITY PATH: The Learning Journey */}
            <PriorityPath priorities={data.priorities} onSelectPriority={handleSelectPriority} />

            <SectionNatureBridge variant="trail-to-sanctuary" />

            {/* SECTION 6 — AI COACH: The Wisdom Corner */}
            <CoachCard />
          </main>

          {/* SECTION 7 — PAGE ENDING: Meadow Horizon */}
          <GardenHorizonEnding />

          <StudentBottomNav currentRoute="/student" subjectId={data.subject.id} />

          <ActionDetailModal
            isOpen={isModalOpen}
            onClose={handleCloseModal}
            action={selectedAction}
            priority={selectedPriority}
          />
        </LivingGardenCanvas>
      </GardenMotionProvider>
    </MotionProvider>
  );
}

export function StudentHomeDisconnected() {
  return (
    <MotionProvider>
      <GardenMotionProvider>
        <LivingGardenCanvas>
          <StudentTopNav displayName="Bạn" activeDays={0} showAmbientToggle />
          <main className={styles.main}>
            <motion.section
              className={`${styles.hero} ${styles.disconnectedHero}`}
              aria-labelledby="disconnected-title"
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
            >
              <HeroNatureScene />
              <motion.div className={styles.heroCopy} variants={fadeUp}>
                <span className={styles.connectionPill}>
                  <DatabaseZap size={15} aria-hidden="true" />
                  Chưa kết nối dữ liệu
                </span>
                <p className={styles.greeting}>EduMS Living Learning Garden</p>
                <h1 id="disconnected-title">Khu vườn học tập đã sẵn sàng.</h1>
                <p className={styles.heroDescription}>
                  Kết nối dữ liệu học tập để bắt đầu hành trình của bạn. Không có số liệu xem trước
                  nào được hiển thị trong chế độ này.
                </p>
                <GradientButton disabled>
                  <LockKeyhole size={17} aria-hidden="true" />
                  Đang chờ dữ liệu
                </GradientButton>
              </motion.div>
              <motion.div className={styles.heroVisual} variants={fadeUp}>
                <KnowledgeCanopy regions={[]} subjectName="Không gian học tập" ghost />
              </motion.div>
            </motion.section>

            <section className={styles.disconnectedSection} aria-labelledby="prepared-title">
              <div className={styles.sectionHeading}>
                <div>
                  <p className={styles.sectionEyebrow}>Sẵn sàng khi dữ liệu đến</p>
                  <h2 id="prepared-title">Một trải nghiệm rõ ràng, không có số liệu giả</h2>
                  <p>
                    Các khu vực học tập sẽ được lấp đầy từ Student Learning State sau bước tích hợp
                    API.
                  </p>
                </div>
              </div>
              <div className={styles.disconnectedPreview}>
                <OrganicCard className={styles.disconnectedCard} variant="solid">
                  <MetricSkeleton />
                </OrganicCard>
                <OrganicCard className={styles.disconnectedCard} variant="solid">
                  <MetricSkeleton />
                </OrganicCard>
                <OrganicCard className={styles.disconnectedCard} variant="solid">
                  <GardenSkeleton />
                </OrganicCard>
              </div>
            </section>
          </main>
          <GardenHorizonEnding />
          <StudentBottomNav />
        </LivingGardenCanvas>
      </GardenMotionProvider>
    </MotionProvider>
  );
}
