"use client";

import React from "react";
import {
  BookOpen,
  Users,
  PenTool,
  BarChart3,
  GraduationCap,
  Sparkles,
} from "lucide-react";
import type { TeacherTab } from "../types";
import styles from "../TeacherDashboard.module.css";

interface TeacherHeaderProps {
  teacherName: string;
  classroomName: string;
  activeTab: TeacherTab;
  onTabChange: (tab: TeacherTab) => void;
  materialsCount: number;
  studentsCount: number;
  attemptsCount: number;
}

export function TeacherHeader({
  teacherName,
  classroomName,
  activeTab,
  onTabChange,
  materialsCount,
  studentsCount,
  attemptsCount,
}: TeacherHeaderProps) {
  return (
    <header className={styles.header}>
      <div className={styles.headerInner}>
        <div className={styles.headerTop}>
          <div className={styles.headerLeft}>
            <div className={styles.teacherAvatar}>GV</div>
            <div className={styles.teacherInfo}>
              <h1 className={styles.teacherName}>
                {teacherName}
                <span className={styles.roleBadge}>Giáo viên Toán</span>
              </h1>
              <div className={styles.classroomSelector}>
                <span>Đang quản lý:</span>
                <span className={styles.classroomPill}>{classroomName}</span>
              </div>
            </div>
          </div>

          <div className={styles.headerRight}>
            <span className={styles.academicYearTag}>Năm học 2026 - 2027</span>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className={styles.tabsList} aria-label="Các phân hệ giảng dạy">
          <button
            type="button"
            className={`${styles.tabButton} ${activeTab === "materials" ? styles.tabButtonActive : ""}`}
            onClick={() => onTabChange("materials")}
          >
            <BookOpen size={16} />
            Kho tài liệu
            <span className={styles.tabCountBadge}>{materialsCount}</span>
          </button>

          <button
            type="button"
            className={`${styles.tabButton} ${activeTab === "classroom" ? styles.tabButtonActive : ""}`}
            onClick={() => onTabChange("classroom")}
          >
            <Users size={16} />
            Quản lý lớp học
            <span className={styles.tabCountBadge}>{studentsCount}</span>
          </button>

          <button
            type="button"
            className={`${styles.tabButton} ${activeTab === "student_workspace" ? styles.tabButtonActive : ""}`}
            onClick={() => onTabChange("student_workspace")}
          >
            <PenTool size={16} />
            Bài làm học sinh
            <span className={styles.tabCountBadge}>{attemptsCount}</span>
          </button>

          <button
            type="button"
            className={`${styles.tabButton} ${activeTab === "analytics" ? styles.tabButtonActive : ""}`}
            onClick={() => onTabChange("analytics")}
          >
            <BarChart3 size={16} />
            Thống kê năng lực
          </button>
        </nav>
      </div>
    </header>
  );
}
