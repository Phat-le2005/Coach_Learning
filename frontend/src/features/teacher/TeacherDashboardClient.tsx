"use client";

import React, { useState } from "react";
import Link from "next/link";
import canvasStyles from "@/features/math-canvas/MathCanvas.module.css";
import type { TeacherTab, TeacherMaterial } from "./types";
import {
  DEFAULT_CLASSROOM,
  INITIAL_STUDENTS,
  INITIAL_MATERIALS,
  STUDENT_INSPECTION_ATTEMPTS,
  COMPETENCY_METRICS,
} from "./data";
import { TeacherHeader } from "./components/TeacherHeader";
import { MaterialsTab } from "./components/MaterialsTab";
import { ClassroomTab } from "./components/ClassroomTab";
import { StudentWorkspaceTab } from "./components/StudentWorkspaceTab";
import { CompetencyTab } from "./components/CompetencyTab";
import styles from "./TeacherDashboard.module.css";

interface TeacherDashboardClientProps {
  teacherName?: string;
}

export function TeacherDashboardClient({
  teacherName = "Demo Mathematics Teacher 01",
}: TeacherDashboardClientProps) {
  const [activeTab, setActiveTab] = useState<TeacherTab>("materials");
  const [materials, setMaterials] = useState<TeacherMaterial[]>(INITIAL_MATERIALS);
  const [students] = useState(INITIAL_STUDENTS);
  const [attempts] = useState(STUDENT_INSPECTION_ATTEMPTS);
  const [selectedStudentForWorkspace, setSelectedStudentForWorkspace] = useState<string | undefined>(
    undefined
  );

  const handleAddMaterial = (newMat: TeacherMaterial) => {
    setMaterials((prev) => [newMat, ...prev]);
  };

  const handleViewStudentWorkspace = (studentId: string) => {
    setSelectedStudentForWorkspace(studentId);
    setActiveTab("student_workspace");
  };

  return (
    <div className={styles.dashboard}>
      <Link href="/teacher/math-canvas" className={canvasStyles.teacherLink}>Math Canvas · Xem bài khám phá học sinh →</Link>
      <TeacherHeader
        teacherName={teacherName}
        classroomName={DEFAULT_CLASSROOM.name}
        activeTab={activeTab}
        onTabChange={(tab) => {
          setActiveTab(tab);
          if (tab !== "student_workspace") {
            setSelectedStudentForWorkspace(undefined);
          }
        }}
        materialsCount={materials.length}
        studentsCount={students.length}
        attemptsCount={attempts.length}
      />

      <main className={styles.mainContent}>
        {activeTab === "materials" && (
          <MaterialsTab materials={materials} onAddMaterial={handleAddMaterial} />
        )}

        {activeTab === "classroom" && (
          <ClassroomTab
            classroom={DEFAULT_CLASSROOM}
            students={students}
            onViewStudentWorkspace={handleViewStudentWorkspace}
          />
        )}

        {activeTab === "student_workspace" && (
          <StudentWorkspaceTab
            attempts={attempts}
            selectedStudentId={selectedStudentForWorkspace}
          />
        )}

        {activeTab === "analytics" && (
          <CompetencyTab
            metrics={COMPETENCY_METRICS}
            students={students}
            onSelectStudentForWorkspace={handleViewStudentWorkspace}
          />
        )}
      </main>
    </div>
  );
}
