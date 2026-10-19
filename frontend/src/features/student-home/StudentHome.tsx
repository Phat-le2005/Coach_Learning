"use client";

import { ArrowRight, BookOpenText, DatabaseZap, LockKeyhole, Sprout } from "lucide-react";
import { motion } from "motion/react";
import { type ReactNode, useState } from "react";

import { MotionProvider } from "@/components/motion/MotionProvider";
import { AmbientGlow } from "@/components/ui/AmbientGlow";
import { GradientButton } from "@/components/ui/GradientButton";
import { OrganicCard } from "@/components/ui/OrganicCard";
import { fadeUp, staggerContainer } from "@/lib/motion";

import type { ResolvedStudentAction } from "./action-resolver";
import type { PriorityViewModel, StudentHomeViewModel } from "./types";
import styles from "./StudentHome.module.css";
import { ActionDetailModal } from "./components/ActionDetailModal";
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
}

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
      <StudentCanvas>
        <StudentTopNav
          displayName={data.student.displayName}
          email={data.student.email}
          activeDays={data.momentum.activeDays}
          currentRoute="/student"
          subjectId={data.subject.id}
        />
        <main className={styles.main}>
          {data.learningContext.mode === "SELF_STUDY_ONBOARDING" ? (
            <OrganicCard className={styles.selfStudyOnboarding} variant="glass">
              <span className={styles.selfStudyIcon} aria-hidden="true">
                <Sprout size={22} />
              </span>
              <div className={styles.selfStudyCopy}>
                <p className={styles.selfStudyEyebrow}>Lối học cá nhân</p>
                <h2>Bắt đầu tự học {data.subject.name}</h2>
                <p>
                  Khám phá chương, chủ đề và dạng bài đã được phát hành. Bạn không cần tham gia lớp
                  hoặc đặt mục tiêu thi để bắt đầu.
                </p>
              </div>
              <GradientButton
                href={`/student/knowledge?subject_id=${encodeURIComponent(data.subject.id)}`}
              >
                Bắt đầu tự học
                <ArrowRight size={17} aria-hidden="true" />
              </GradientButton>
            </OrganicCard>
          ) : data.availableSubjects.length === 0 ? (
            <OrganicCard className={styles.realDataEmpty} variant="glass">
              <h3>Chưa có môn tự học được phát hành</h3>
              <p>
                Tài khoản chưa có hoạt động học tập và hệ thống chưa phát hành môn tự học phù hợp.
                EduMS không dùng dữ liệu staging hoặc số liệu giả để lấp trạng thái này.
              </p>
            </OrganicCard>
          ) : null}
          <FocusHero data={data} onOpenActionDetail={handleOpenActionDetail} />
          <OrganicCard className={styles.practiceEntry} variant="glass">
            <span className={styles.selfStudyIcon} aria-hidden="true"><BookOpenText size={22} /></span>
            <div className={styles.selfStudyCopy}>
              <p className={styles.selfStudyEyebrow}>Trang làm bài</p>
              <h2>Viết lời giải trên giấy số</h2>
              <p>Mở bài làm đã có hoặc bắt đầu từ câu hỏi được duyệt. Bạn luôn kiểm tra công thức OCR trước khi xác nhận.</p>
            </div>
            <GradientButton href="/student/attempts">Vào trang làm bài <ArrowRight size={17} aria-hidden="true" /></GradientButton>
          </OrganicCard>
          <LearningPulse data={data} />
          <KnowledgeGarden regions={data.knowledgeRegions} subjectId={data.subject.id} />
          <div className={styles.closingGrid}>
            <PriorityPath priorities={data.priorities} onSelectPriority={handleSelectPriority} />
            <CoachCard />
          </div>
        </main>
        <StudentBottomNav currentRoute="/student" subjectId={data.subject.id} />
        <ActionDetailModal
          isOpen={isModalOpen}
          onClose={handleCloseModal}
          action={selectedAction}
          priority={selectedPriority}
        />
      </StudentCanvas>
    </MotionProvider>
  );
}

export function StudentHomeDisconnected() {
  return (
    <MotionProvider>
      <StudentCanvas>
        <StudentTopNav displayName="Bạn" activeDays={0} />
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
              <KnowledgeCanopy regions={[]} subjectName="Không gian học tập" ghost />
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
