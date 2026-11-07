"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ClipboardCheck, History, PenTool } from "lucide-react";
import { MotionConfig } from "motion/react";
import type { ReactNode } from "react";

import { AssignmentsListClient } from "@/app/student/assignments/AssignmentsListClient";
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
  const router = useRouter();
  const searchParams = useSearchParams();
  const urlTab = searchParams.get("tab");

  const classroomPendingCount = (data.classroomAssignments ?? []).filter(
    (a) => a.status === "NOT_STARTED" || a.status === "IN_PROGRESS"
  ).length;

  const initialTab: "classroom" | "practice" | "history" =
    urlTab === "practice"
      ? "practice"
      : urlTab === "history"
      ? "history"
      : urlTab === "classroom"
      ? "classroom"
      : data.initialTab ?? (classroomPendingCount > 0 ? "classroom" : "practice");

  const [activeTab, setActiveTab] = useState<"classroom" | "practice" | "history">(initialTab);

  useEffect(() => {
    const t = searchParams.get("tab");
    if (t === "classroom" || t === "practice" || t === "history") {
      setActiveTab(t);
    }
  }, [searchParams]);

  const handleTabChange = (tab: "classroom" | "practice" | "history") => {
    setActiveTab(tab);
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    router.replace(`/student/attempts?${params.toString()}`, { scroll: false });
  };

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
            pendingAssignmentsCount={classroomPendingCount}
          />

          <main className={styles.main}>
            {/* CONSOLIDATED HUB HEADER & SEGMENTED TABS */}
            <header className={styles.hubHeader}>
              <div className={styles.hubHeaderCopy}>
                <span className={styles.hubKicker}>EduMS · Trung tâm Thực hành & Bài tập</span>
                <h1 className={styles.hubTitle}>Không gian Làm bài & Luyện tập</h1>
                <p className={styles.hubSubtitle}>
                  Nơi hội tụ toàn bộ bài tập giáo viên giao cho lớp, trang giấy số tự luyện và nhật ký giải toán chi tiết của bạn.
                </p>
              </div>

              {/* SEGMENTED TAB SWITCHER */}
              <div className={styles.segmentedControl} role="tablist" aria-label="Chế độ làm bài">
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "classroom"}
                  className={`${styles.tabBtn} ${activeTab === "classroom" ? styles.tabBtnActive : ""}`}
                  onClick={() => handleTabChange("classroom")}
                >
                  <ClipboardCheck size={18} aria-hidden="true" />
                  <span>Bài tập của lớp</span>
                  {classroomPendingCount > 0 ? (
                    <span className={styles.tabBadgeActive}>{classroomPendingCount}</span>
                  ) : (
                    <span className={styles.tabBadgeMuted}>{data.classroomAssignments?.length ?? 0}</span>
                  )}
                </button>

                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "practice"}
                  className={`${styles.tabBtn} ${activeTab === "practice" ? styles.tabBtnActive : ""}`}
                  onClick={() => handleTabChange("practice")}
                >
                  <PenTool size={18} aria-hidden="true" />
                  <span>Tự luyện & Giấy số</span>
                  {data.totalActiveCount > 0 && (
                    <span className={styles.tabBadgeNotice}>{data.totalActiveCount} đang làm</span>
                  )}
                </button>

                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === "history"}
                  className={`${styles.tabBtn} ${activeTab === "history" ? styles.tabBtnActive : ""}`}
                  onClick={() => handleTabChange("history")}
                >
                  <History size={18} aria-hidden="true" />
                  <span>Lịch sử bài làm</span>
                  <span className={styles.tabBadgeMuted}>{data.pagination.total}</span>
                </button>
              </div>
            </header>

            {/* TAB 1 — CLASSROOM ASSIGNMENTS */}
            {activeTab === "classroom" && (
              <section className={styles.tabPanel} role="tabpanel" aria-label="Bài tập của lớp">
                <AssignmentsListClient
                  initialAssignments={data.classroomAssignments ?? []}
                  studentName={data.student.displayName}
                  embedded
                />
              </section>
            )}

            {/* TAB 2 — SELF-STUDY & DIGITAL PAPER */}
            {activeTab === "practice" && (
              <section className={styles.tabPanel} role="tabpanel" aria-label="Tự luyện & Giấy số">
                <StudyLaunchSection
                  subjects={data.subjects}
                  subjectsLoaded={data.subjectsLoaded}
                  defaultSubjectId={data.defaultSubjectId}
                  classroomPendingCount={classroomPendingCount}
                  onSelectClassroomTab={() => handleTabChange("classroom")}
                />
                <ContinueLearningSection
                  items={data.continueLearningItems}
                  totalActiveCount={data.totalActiveCount}
                />
              </section>
            )}

            {/* TAB 3 — ATTEMPTS HISTORY */}
            {activeTab === "history" && (
              <section className={styles.tabPanel} role="tabpanel" aria-label="Lịch sử bài làm">
                <AttemptsLibrarySection
                  items={data.libraryItems}
                  pagination={data.pagination}
                  activeStatusFilter={data.activeStatusFilter}
                  defaultSubjectId={data.defaultSubjectId}
                />
              </section>
            )}
          </main>

          {/* PAGE ENDING */}
          <StudyGardenEnding defaultSubjectId={data.defaultSubjectId} />

          <StudentBottomNav
            currentRoute="/student/attempts"
            subjectId={data.defaultSubjectId}
            pendingAssignmentsCount={classroomPendingCount}
          />
        </LivingStudyGardenShell>
      </GardenMotionProvider>
    </MotionProvider>
  );
}
