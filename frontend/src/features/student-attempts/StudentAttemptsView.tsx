"use client";

import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

import { MotionProvider } from "@/components/motion/MotionProvider";
import { StudentBottomNav } from "@/features/student-home/components/StudentBottomNav";
import { StudentTopNav } from "@/features/student-home/components/StudentTopNav";
import {
  GardenMotionProvider,
  useGardenMotion,
} from "@/features/student-home/components/nature/GardenMotionContext";
import { springSoft } from "@/lib/motion";

import { AttemptsLibrarySection } from "./components/AttemptsLibrarySection";
import { ContinueLearningSection } from "./components/ContinueLearningSection";
import { StudyGardenBackdrop } from "./components/StudyGardenBackdrop";
import { StudyGardenEnding } from "./components/StudyGardenEnding";
import { StudyLaunchSection } from "./components/StudyLaunchSection";
import { StudyWelcomeHero } from "./components/StudyWelcomeHero";
import styles from "./StudentAttempts.module.css";
import type { StudentAttemptsViewModel } from "./types";

export interface StudentAttemptsViewProps {
  data: StudentAttemptsViewModel;
}

function LivingStudyGardenShell({ children }: { children: ReactNode }) {
  const { ambientEnabled } = useGardenMotion();

  return (
    <MotionConfig reducedMotion={ambientEnabled ? "never" : "always"} transition={springSoft}>
      <div
        id="student-attempts-top"
        className={styles.canvas}
        data-garden-motion={ambientEnabled ? "on" : "off"}
      >
        <StudyGardenBackdrop />
        {children}
      </div>
    </MotionConfig>
  );
}

export function StudentAttemptsView({ data }: StudentAttemptsViewProps) {
  return (
    <MotionProvider>
      <GardenMotionProvider>
        <LivingStudyGardenShell>
          {/* Unified Navigation shared with Student Home & Knowledge World */}
          <StudentTopNav
            displayName={data.student.displayName}
            email={data.student.email}
            currentRoute="/student/attempts"
            subjectId={data.defaultSubjectId}
            showAmbientToggle
          />

          <main className={styles.main}>
            {/* SECTION A — STUDY WELCOME HERO */}
            <StudyWelcomeHero
              totalAttempts={data.pagination.total}
              activeAttemptsCount={data.totalActiveCount}
              defaultSubjectId={data.defaultSubjectId}
            />

            {/* SECTION B — START NEW ATTEMPT: Study Launch Panel */}
            <StudyLaunchSection
              subjects={data.subjects}
              subjectsLoaded={data.subjectsLoaded}
              defaultSubjectId={data.defaultSubjectId}
            />

            {/* SECTION C — CONTINUE LEARNING (Shown when DRAFT / IN_PROGRESS exist) */}
            <ContinueLearningSection
              items={data.continueLearningItems}
              totalActiveCount={data.totalActiveCount}
            />

            {/* SECTION D — MY ATTEMPTS LIBRARY */}
            <AttemptsLibrarySection
              items={data.libraryItems}
              pagination={data.pagination}
              activeStatusFilter={data.activeStatusFilter}
              defaultSubjectId={data.defaultSubjectId}
            />
          </main>

          {/* SECTION E — CALM PAGE ENDING */}
          <StudyGardenEnding defaultSubjectId={data.defaultSubjectId} />

          <StudentBottomNav
            currentRoute="/student/attempts"
            subjectId={data.defaultSubjectId}
          />
        </LivingStudyGardenShell>
      </GardenMotionProvider>
    </MotionProvider>
  );
}
