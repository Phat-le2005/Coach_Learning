"use client";

import { Box, FlaskConical, List, Search } from "lucide-react";
import { useMemo, type ReactNode } from "react";
import type { TeacherClassroom, TeacherStudent } from "../api";
import { classroomStudents } from "../classroom-adapter";
import { DEMO_CLASSROOM_STUDENTS } from "../classroom-demo";
import { classroomPage, presenceLabel } from "../classroom-model";
import type { StationPhase } from "../classroom-scene";
import { Classroom3DPanel, type ViewMode } from "./Classroom3DPanel";
import styles from "../Classroom3D.module.css";
import dashboard from "../TeacherDashboard.module.css";

interface Props {
  students: TeacherStudent[];
  selectedClass?: TeacherClassroom;
  isLoading: boolean;
  error?: string;
  preview: boolean;
  onPreview: (preview: boolean) => void;
  view: "3d" | "list";
  onView: (view: "3d" | "list") => void;
  query: string;
  onQuery: (query: string) => void;
  onViewStudentWorkspace: (studentId: string) => void;
  currentStation?: string;
  stationPhase?: StationPhase;
  onStationSelect?: (station: string) => void;
  onStationPhaseChange?: (station: string, phase: StationPhase) => void;
  viewMode?: ViewMode;
  onToggleViewMode?: (mode: ViewMode) => void;
  stationWorkspace?: ReactNode;
}

export function ClassroomExperience({
  students,
  selectedClass,
  isLoading,
  error,
  preview,
  onPreview,
  view,
  onView,
  query,
  onQuery,
  onViewStudentWorkspace,
  currentStation = "classes",
  stationPhase,
  onStationSelect,
  onStationPhaseChange,
  viewMode = "full",
  onToggleViewMode,
  stationWorkspace,
}: Props) {
  const liveStudents = useMemo(() => classroomStudents(students), [students]);
  const pupils = preview ? DEMO_CLASSROOM_STUDENTS : liveStudents;
  const matches = useMemo(() => classroomPage(pupils, query, 0).matches, [pupils, query]);

  if (view === "3d" && viewMode !== "compact") {
    return (
      <section aria-label="Không gian lớp mình" className={styles.fullBleed3DSection}>
        <Classroom3DPanel
          key={preview ? "cozy-demo" : selectedClass?.id ?? "unassigned"}
          students={pupils}
          query={query}
          onQueryChange={onQuery}
          classroomId={preview ? "cozy-demo" : selectedClass?.id ?? "unassigned"}
          classroomName={preview ? "Lớp Mình · Minh họa" : selectedClass?.name ?? "Lớp Mình"}
          isDemo={preview}
          onToggleDemo={onPreview}
          onSwitchTo2D={() => onView("list")}
          onViewStudentWorkspace={preview ? undefined : onViewStudentWorkspace}
          currentStation={currentStation}
          stationPhase={stationPhase}
          onStationSelect={onStationSelect}
          onStationPhaseChange={onStationPhaseChange}
          viewMode={viewMode}
          onToggleViewMode={onToggleViewMode}
          stationWorkspace={stationWorkspace}
        />
      </section>
    );
  }

  return (
    <section aria-label="Không gian lớp mình">
      <div className={styles.toolbar}>
        <div className={styles.viewSwitcher} role="group" aria-label="Nguồn dữ liệu lớp học">
          <button className={styles.viewButton} type="button" aria-pressed={!preview} onClick={() => onPreview(false)}>
            Lớp đang quản lý
          </button>
          <button className={styles.viewButton} type="button" aria-pressed={preview} onClick={() => onPreview(true)}>
            <FlaskConical size={15} aria-hidden="true" />
            Minh họa 10 bạn
          </button>
        </div>
        <div className={styles.viewSwitcher} role="group" aria-label="Chế độ hiển thị lớp học">
          <button type="button" className={styles.viewButton} aria-pressed={view === "3d"} onClick={() => onView("3d")}>
            <Box size={15} aria-hidden="true" />
            Lớp học 3D
          </button>
          <button
            type="button"
            className={styles.viewButton}
            aria-pressed={view === "list"}
            onClick={() => onView("list")}
          >
            <List size={15} aria-hidden="true" />
            Danh sách
          </button>
        </div>
      </div>
      {preview && (
        <p className={styles.demoNotice}>
          <span className={styles.demoBadge}>Lớp minh họa</span>
          Số liệu, online và yêu cầu hỗ trợ bên dưới là dữ liệu mẫu.
        </p>
      )}
      {preview && (
        <div className={styles.toolbar}>
          <label className={styles.search}>
            <Search size={16} aria-hidden="true" />
            <input
              className={dashboard.searchInput}
              aria-label="Tìm học sinh theo tên hoặc email"
              placeholder="Tìm tên hoặc email học sinh…"
              value={query}
              onChange={(event) => onQuery(event.target.value)}
            />
          </label>
        </div>
      )}
      {!preview && isLoading ? (
        <p role="status">Đang tải lớp học từ hệ thống…</p>
      ) : !preview && error ? (
        <p role="alert">{error}</p>
      ) : (
        preview && (
          <div className={dashboard.tableWrap}>
            <table className={dashboard.dataTable}>
              <caption>10 học sinh minh họa</caption>
              <thead>
                <tr>
                  <th scope="col">Học sinh</th>
                  <th scope="col">Email minh họa</th>
                  <th scope="col">Hiện diện mẫu</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((student) => (
                  <tr key={student.id}>
                    <td>{student.name}</td>
                    <td>{student.email}</td>
                    <td>{presenceLabel(student)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!matches.length && <p>Không tìm thấy học sinh</p>}
          </div>
        )
      )}
    </section>
  );
}
