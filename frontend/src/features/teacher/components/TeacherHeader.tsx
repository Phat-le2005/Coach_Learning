"use client";

import { useEffect, useRef } from "react";
import { Leaf, RefreshCw, Plus, UploadCloud, ChevronDown, ChevronUp, Ellipsis } from "lucide-react";
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
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
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
  isCollapsed = false,
  onToggleCollapse,
}: TeacherHeaderProps) {
  const selectedClass = classes.find((c) => c.id === selectedClassId);
  const actions = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    const close = (event: PointerEvent) => { if (actions.current && !actions.current.contains(event.target as Node)) actions.current.open = false; };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, []);
  const closeActions = () => { if (actions.current) actions.current.open = false; };

  if (isCollapsed) {
    return (
      <div className={styles.collapsedHeaderBar}>
        <button
          type="button"
          className={styles.expandHeaderPill}
          onClick={onToggleCollapse}
          title="Mở rộng lại thanh Header quản lý lớp"
        >
          <ChevronDown size={14} aria-hidden="true" />
          <span>Mở thanh công cụ <strong>{selectedClass ? selectedClass.name : "Giảng dạy"}</strong></span>
        </button>
      </div>
    );
  }

  return (
    <header className={styles.header}>
      <div className={styles.teacherHeaderInner}>
        {/* Brand & Teacher Persona */}
        <div className={styles.teacherHeaderRow}>
          <div className={styles.teacherBrand} aria-label="EduMS · Không gian giảng dạy"><Leaf size={28} aria-hidden="true" /><span><strong>EduMS</strong><h1>Không gian giảng dạy</h1></span></div>

          <div className={styles.teacherClassPicker}>
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
                      {item.name} · {item.academic_year}
                    </option>
                  ))}
                </select>
                <ChevronDown size={14} className={styles.selectChevron} aria-hidden="true" />
              </div>
            </div>

          </div>
          <div className={styles.teacherHeaderActions}>
            {selectedClass && (
              <button
                type="button"
                className={styles.btnPrimary}
                onClick={onOpenUpload}
                title="Tải đề thi hoặc tài liệu bài giảng lên lớp"
                aria-label="Tải học liệu"
              >
                <UploadCloud size={15} aria-hidden="true" />
                <span className={styles.teacherUploadLabel}>Tải học liệu</span>
              </button>
            )}

            <details ref={actions} className={styles.teacherMore} onKeyDown={event => { if (event.key === "Escape") { closeActions(); event.currentTarget.querySelector("summary")?.focus(); } }}>
              <summary aria-label="Thao tác quản lý khác" title="Thao tác quản lý khác"><Ellipsis size={20} aria-hidden="true" /></summary>
              <div className={styles.teacherMoreMenu}>
                <button type="button" disabled={isReloading} onClick={() => { closeActions(); onReload(); }}><RefreshCw size={16} className={isReloading ? styles.spinIcon : ""} aria-hidden="true" />Làm mới dữ liệu</button>
                <button type="button" onClick={() => { closeActions(); onOpenCreateClass(); }}><Plus size={16} aria-hidden="true" />Tạo lớp mới</button>
                {onToggleCollapse && <button type="button" onClick={() => { closeActions(); onToggleCollapse(); }}><ChevronUp size={16} aria-hidden="true" />Thu gọn thanh công cụ</button>}
              </div>
            </details>

            <div className={styles.accountMenuWrap}>
              <AccountMenu
                fullName={teacherName}
                email={teacherEmail}
                role="TEACHER"
                compact
              />
            </div>

          </div>
        </div>
      </div>
    </header>
  );
}
