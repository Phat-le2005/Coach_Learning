"use client";

import { GraduationCap, RefreshCw, Plus, UploadCloud, ChevronDown } from "lucide-react";
import { AccountMenu } from "@/components/auth/AccountMenu";
import type { TeacherClassroom } from "../api";
import styles from "../TeacherDashboard.module.css";

export interface TeacherHeaderProps {
  teacherName: string;
  teacherEmail: string;
  classes: TeacherClassroom[];
  selectedClassId: string;
  onSelectClass: (id: string) => void;
  onReload: () => void;
  isReloading: boolean;
  onOpenCreateClass: () => void;
  onOpenUpload: () => void;
}

export function TeacherHeader({
  teacherName,
  teacherEmail,
  classes,
  selectedClassId,
  onSelectClass,
  onReload,
  isReloading,
  onOpenCreateClass,
  onOpenUpload,
}: TeacherHeaderProps) {
  const selectedClass = classes.find((c) => c.id === selectedClassId);
  const initials = teacherName
    ? teacherName
        .split(" ")
        .filter(Boolean)
        .slice(-2)
        .map((w) => w[0]?.toUpperCase())
        .join("")
    : "GV";

  return (
    <header className={styles.header}>
      <div className={styles.headerInner}>
        {/* Brand & Teacher Persona */}
        <div className={styles.headerTop}>
          <div className={styles.headerLeft}>
            <div className={styles.teacherAvatar} aria-hidden="true">
              {initials}
            </div>
            <div className={styles.teacherInfo}>
              <div className={styles.teacherNameRow}>
                <h1 className={styles.teacherName}>{teacherName}</h1>
                <span className={styles.roleBadge}>
                  <GraduationCap size={13} aria-hidden="true" />
                  Giáo viên THPT
                </span>
              </div>
              <p className={styles.teacherSubtitle}>
                Hệ thống Quản lý Giảng dạy &amp; Cố vấn Học tập EduMS
              </p>
            </div>
          </div>

          <div className={styles.headerRight}>
            {/* Quick Classroom Dropdown */}
            <div className={styles.classSelectorCard}>
              <label htmlFor="teacher-classroom-select" className={styles.classSelectorLabel}>
                Lớp phụ trách:
              </label>
              <div className={styles.classSelectWrap}>
                <select
                  id="teacher-classroom-select"
                  className={styles.classSelectControl}
                  value={selectedClassId}
                  onChange={(e) => onSelectClass(e.target.value)}
                  aria-label="Chọn lớp học quản lý"
                  disabled={classes.length === 0}
                >
                  {classes.length === 0 && <option value="">Chưa có lớp</option>}
                  {classes.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name} · Khối {item.grade_level} ({item.academic_year})
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} className={styles.selectChevron} aria-hidden="true" />
              </div>
            </div>

            {/* Actions: Refresh + Create + Upload */}
            <button
              type="button"
              className={styles.btnSecondary}
              onClick={onReload}
              disabled={isReloading}
              title="Đồng bộ dữ liệu mới nhất từ hệ thống"
            >
              <RefreshCw size={15} className={isReloading ? styles.spinIcon : ""} aria-hidden="true" />
              <span className={styles.hideMobile}>Làm mới</span>
            </button>

            <button
              type="button"
              className={styles.btnSecondary}
              onClick={onOpenCreateClass}
              title="Tạo lớp học mới"
            >
              <Plus size={15} aria-hidden="true" />
              <span className={styles.hideMobile}>Tạo lớp</span>
            </button>

            {selectedClass && (
              <button
                type="button"
                className={styles.btnPrimary}
                onClick={onOpenUpload}
                title="Tải đề thi hoặc tài liệu bài giảng lên lớp"
              >
                <UploadCloud size={15} aria-hidden="true" />
                <span className={styles.hideMobile}>Tải học liệu</span>
              </button>
            )}

            <div className={styles.accountMenuWrap}>
              <AccountMenu fullName={teacherName} email={teacherEmail} role="TEACHER" compact />
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}
