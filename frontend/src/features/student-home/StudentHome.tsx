"use client";

import { DatabaseZap, LockKeyhole } from "lucide-react";
import { MotionConfig, motion } from "motion/react";
import { type ReactNode, useState } from "react";
import { useRouter } from "next/navigation";

import { MotionProvider } from "@/components/motion/MotionProvider";
import { GradientButton } from "@/components/ui/GradientButton";
import { OrganicCard } from "@/components/ui/OrganicCard";
import { fadeUp, springSoft, staggerContainer } from "@/lib/motion";

import type { ResolvedStudentAction } from "./action-resolver";
import { ActionDetailModal } from "./components/ActionDetailModal";
import { FocusHero } from "./components/FocusHero";
import { HomeAppearance, useHomeAppearance } from "./components/HomeAppearance";
import { GardenHorizonEnding } from "./components/GardenHorizonEnding";
import { KnowledgeCanopy } from "./components/KnowledgeCanopy";
import { KnowledgeGarden } from "./components/KnowledgeGarden";
import { CoachCard } from "./components/CoachCard";
import { LearningPulse } from "./components/LearningPulse";
import { GardenSkeleton, MetricSkeleton } from "./components/LoadingSkeletons";
import { PriorityPath } from "./components/PriorityPath";
import { StudentBottomNav } from "./components/StudentBottomNav";
import { StudentTopNav } from "./components/StudentTopNav";
import { CanopyMarginFallingLeaves } from "./components/nature/BirdsAndLeaves";
import { GardenMotionProvider, useGardenMotion } from "./components/nature/GardenMotionContext";
import { HeroNatureScene } from "./components/nature/HeroNatureScene";
import { LivingGardenBackdrop } from "./components/nature/LivingGardenBackdrop";
import styles from "./StudentHome.module.css";
import ui from "./HomeRefresh.module.css";
import type { PriorityViewModel, StudentHomeViewModel } from "./types";

export interface StudentHomeProps {
  data: StudentHomeViewModel;
}

function LivingGardenCanvas({ children, refreshed = false }: { children: ReactNode; refreshed?: boolean }) {
  const { ambientEnabled } = useGardenMotion();
  const { theme } = useHomeAppearance();

  return (
    <MotionConfig reducedMotion={ambientEnabled ? "user" : "always"} transition={springSoft}>
      <div
        className={refreshed ? `${styles.canvas} ${ui.home}` : styles.canvas}
        id="student-home"
        data-garden-motion={ambientEnabled ? "on" : "off"}
        data-home-theme={refreshed ? theme : undefined}
      >
        <LivingGardenBackdrop refined={refreshed} />
        <CanopyMarginFallingLeaves />
        {children}
      </div>
    </MotionConfig>
  );
}

export function StudentHome({ data }: StudentHomeProps) {
  const router = useRouter();
  const [planRequest, setPlanRequest] = useState(0);
  const [planOpen, setPlanOpen] = useState(false);
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

  const pendingAssignmentsCount = data.assignments.activeCount ?? data.assignments.pendingCount;

  return (
    <HomeAppearance><MotionProvider>
      <GardenMotionProvider>
        <LivingGardenCanvas refreshed>
          <StudentTopNav
            displayName={data.student.displayName}
            email={data.student.email}
            activeDays={data.momentum.activeDays}
            currentRoute="/student"
            subjectId={data.subject.id}
            showAmbientToggle
            pendingAssignmentsCount={pendingAssignmentsCount}
            refreshed
          />

          <main className={styles.main}>
            <div className={ui.greeting}><p>Chào {data.student.displayName}. Hôm nay mình học nhé.</p>
              {data.availableSubjects.length > 1 ? <select aria-label="Chọn môn học" value={data.subject.id} onChange={event => router.push(`/student?subject_id=${encodeURIComponent(event.target.value)}`)}>{data.availableSubjects.map(subject => <option key={subject.id} value={subject.id}>{subject.name}</option>)}</select> : <span>{data.subject.name}</span>}
            </div>
            <FocusHero data={data} suspended={isModalOpen || planOpen} onOpenPlan={() => setPlanRequest(value => value + 1)} />

            {/* TIER 2 — LEARNING PULSE: Key Metrics & Today's Study Plan */}
            <LearningPulse data={data} planRequest={planRequest} onDetails={handleOpenActionDetail} onPlanOpenChange={setPlanOpen} />

            {/* TIER 3 — PRIORITY PATH: Targeted Error Remediation & Focused Tasks */}
            <PriorityPath priorities={data.priorities} mastery={data.mastery} momentum={data.momentum} onSelectPriority={handleSelectPriority} subjectId={data.subject.id} />
            <KnowledgeGarden regions={data.knowledgeRegions} subjectId={data.subject.id} />
            <CoachCard data={data} />
          </main>

          {/* SECTION 7 — PAGE ENDING: Meadow Horizon */}
          <footer className={ui.pageFooter}><strong>EduMS</strong><p>Không gian cho cách nghĩ của bạn.</p></footer>

          <StudentBottomNav
            currentRoute="/student"
            subjectId={data.subject.id}
            pendingAssignmentsCount={pendingAssignmentsCount}
            refreshed
          />

          <ActionDetailModal
            isOpen={isModalOpen}
            onClose={handleCloseModal}
            action={selectedAction}
            priority={selectedPriority}
          />
        </LivingGardenCanvas>
      </GardenMotionProvider>
    </MotionProvider></HomeAppearance>
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
