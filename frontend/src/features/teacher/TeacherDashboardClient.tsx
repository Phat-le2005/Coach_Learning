"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import canvasStyles from "@/features/math-canvas/MathCanvas.module.css";
import { Users, BookOpen, ClipboardList, BarChart3, ArrowRight, AlertCircle, RefreshCw, Network } from "lucide-react";
import {
  teacherApi,
  TeacherApiError,
  type TeacherAnalytics,
  type TeacherAssignment,
  type TeacherClassroom,
  type TeacherMaterial,
  type TeacherRoster,
  type TeacherStudent,
  type TeacherSubject,
} from "./api";
import { TeacherHeader } from "./components/TeacherHeader";
import { TeacherCockpitBanner } from "./components/TeacherCockpitBanner";
import { ClassroomsTab } from "./components/ClassroomsTab";
import { MaterialsTab } from "./components/MaterialsTab";
import { SubmissionsTab } from "./components/SubmissionsTab";
import { AnalyticsTab } from "./components/AnalyticsTab";
import { CreateClassModal } from "./components/CreateClassModal";
import { UploadMaterialModal } from "./components/UploadMaterialModal";
import { TeacherTheoryClient } from "@/features/theory-maps/TeacherTheoryClient";
import { AppFooter } from "@/components/app-shell/AppFooter";
import styles from "./TeacherDashboard.module.css";

export type TabKey = "classes" | "materials" | "theory" | "submissions" | "analytics";

const getErrorMessage = (error: unknown) =>
  error instanceof TeacherApiError ? error.message : "Không thể tải dữ liệu từ máy chủ backend.";

export function TeacherDashboardClient({
  teacherName,
  teacherEmail,
  initialTab = "classes",
}: {
  teacherName: string;
  teacherEmail: string;
  initialTab?: TabKey;
}) {
  const [tab, setTab] = useState<TabKey>(initialTab);

  useEffect(() => {
    if (initialTab) {
      setTab(initialTab);
    }
  }, [initialTab]);

  const handleSelectTab = (nextTab: TabKey) => {
    setTab(nextTab);
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", nextTab);
      window.history.replaceState({}, "", url.toString());
    }
  };

  useEffect(() => {
    const onPopState = () => {
      const params = new URLSearchParams(window.location.search);
      const urlTab = params.get("tab");
      if (
        urlTab === "theory" ||
        urlTab === "materials" ||
        urlTab === "submissions" ||
        urlTab === "analytics" ||
        urlTab === "classes"
      ) {
        setTab(urlTab as TabKey);
      }
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  // Core data states
  const [classes, setClasses] = useState<TeacherClassroom[]>([]);
  const [subjects, setSubjects] = useState<TeacherSubject[]>([]);
  const [classId, setClassId] = useState("");
  const [initialLoading, setInitialLoading] = useState(true);
  const [initialError, setInitialError] = useState("");
  const [reloadCount, setReloadCount] = useState(0);

  // Classroom-scoped data states
  const [classLoading, setClassLoading] = useState(false);
  const [classErrors, setClassErrors] = useState<string[]>([]);
  const [studentError, setStudentError] = useState("");
  const [focusedStudent, setFocusedStudent] = useState<{ id: string; name: string } | null>(null);
  const [students, setStudents] = useState<TeacherStudent[]>([]);
  const [materials, setMaterials] = useState<TeacherMaterial[]>([]);
  const [assignments, setAssignments] = useState<TeacherAssignment[]>([]);
  const [analytics, setAnalytics] = useState<TeacherAnalytics | null>(null);

  // Assignment submissions roster state
  const [assignmentId, setAssignmentId] = useState("");
  const [roster, setRoster] = useState<TeacherRoster | null>(null);
  const [rosterError, setRosterError] = useState("");

  // Modals state
  const [isCreateClassOpen, setIsCreateClassOpen] = useState(false);
  const [createClassBusy, setCreateClassBusy] = useState(false);
  const [createClassError, setCreateClassError] = useState("");

  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [uploadSuccess, setUploadSuccess] = useState("");

  // 1. Initial Load: Classes & Subjects
  useEffect(() => {
    let active = true;
    setInitialLoading(true);
    setInitialError("");

    Promise.all([teacherApi.classes(), teacherApi.subjects()])
      .then(([nextClasses, nextSubjects]) => {
        if (!active) return;
        setClasses(nextClasses);
        setSubjects(nextSubjects);
        setClassId((current) =>
          nextClasses.some((item) => item.id === current)
            ? current
            : nextClasses[0]?.id ?? ""
        );
      })
      .catch((error) => {
        if (active) setInitialError(getErrorMessage(error));
      })
      .finally(() => {
        if (active) setInitialLoading(false);
      });

    return () => {
      active = false;
    };
  }, [reloadCount]);

  // 2. Load Classroom Details when classId changes
  useEffect(() => {
    setFocusedStudent(null);
    setStudentError("");
    if (!classId) {
      setStudents([]);
      setMaterials([]);
      setAssignments([]);
      setAnalytics(null);
      setAssignmentId("");
      setRoster(null);
      return;
    }

    let active = true;
    setClassLoading(true);
    setClassErrors([]);
    setStudents([]);
    setMaterials([]);
    setAssignments([]);
    setAnalytics(null);
    setAssignmentId("");
    setRoster(null);

    Promise.allSettled([
      teacherApi.students(classId),
      teacherApi.materials(classId),
      teacherApi.assignments(classId),
      teacherApi.analytics(classId),
    ])
      .then((results) => {
        if (!active) return;
        const errors: string[] = [];
        if (results[0].status === "fulfilled") {
          setStudents(results[0].value.filter((student) => !student.is_synthetic));
        } else {
          const message = `Học sinh: ${getErrorMessage(results[0].reason)}`;
          setStudentError(message);
          errors.push(message);
        }
        if (results[1].status === "fulfilled") {
          setMaterials(results[1].value);
        } else {
          errors.push(`Tài liệu: ${getErrorMessage(results[1].reason)}`);
        }
        if (results[2].status === "fulfilled") {
          setAssignments(results[2].value);
        } else {
          errors.push(`Bài giao: ${getErrorMessage(results[2].reason)}`);
        }
        if (results[3].status === "fulfilled") {
          setAnalytics(results[3].value);
        } else {
          errors.push(`Thống kê: ${getErrorMessage(results[3].reason)}`);
        }
        setClassErrors(errors);
      })
      .finally(() => {
        if (active) setClassLoading(false);
      });

    return () => {
      active = false;
    };
  }, [classId, reloadCount]);

  // 3. Load Assignment Roster when assignmentId changes
  useEffect(() => {
    if (!assignmentId) {
      setRoster(null);
      setRosterError("");
      return;
    }

    let active = true;
    setRoster(null);
    setRosterError("");

    teacherApi
      .roster(assignmentId)
      .then((result) => {
        if (active) setRoster(result);
      })
      .catch((error) => {
        if (active) setRosterError(getErrorMessage(error));
      });

    return () => {
      active = false;
    };
  }, [assignmentId]);

  const selectedClass = classes.find((item) => item.id === classId);
  const eligibleSubjects = subjects.filter(
    (subject) => subject.grade_level === null || subject.grade_level === selectedClass?.grade_level
  );

  // Mutation Handlers
  async function handleCreateClass(name: string, academicYear: string, gradeLevel: number) {
    setCreateClassBusy(true);
    setCreateClassError("");
    try {
      const created = await teacherApi.createClass(name, academicYear, gradeLevel);
      setClasses((current) => [...current, created]);
      setClassId(created.id);
      setIsCreateClassOpen(false);
    } catch (error) {
      setCreateClassError(getErrorMessage(error));
    } finally {
      setCreateClassBusy(false);
    }
  }

  async function handleUploadMaterial(subjectId: string, title: string, file: File) {
    if (!classId) return;
    setUploadBusy(true);
    setUploadError("");
    setUploadSuccess("");
    try {
      const saved = await teacherApi.uploadMaterial(classId, subjectId, title, file);
      setMaterials((current) => [saved, ...current]);
      setUploadSuccess(`Đã lưu thành công "${saved.title}" vào lớp.`);
      setTimeout(() => {
        setIsUploadOpen(false);
        setUploadSuccess("");
      }, 1400);
    } catch (error) {
      setUploadError(getErrorMessage(error));
    } finally {
      setUploadBusy(false);
    }
  }

  const handleReload = () => {
    setReloadCount((v) => v + 1);
  };

  function handleViewStudentWorkspace(studentId: string) {
    const student = students.find((item) => item.student_id === studentId);
    if (!student) return;
    setFocusedStudent({ id: student.student_id, name: student.full_name });
    setAssignmentId((current) => assignments.some((item) => item.id === current) ? current : assignments[0]?.id ?? "");
    handleSelectTab("submissions");
  }

  return (
    <div className={`${styles.dashboard} ${tab === "classes" ? styles.classroomDashboard : ""}`}>
      <Link href="/teacher/math-canvas" className={canvasStyles.teacherLink}>Math Canvas</Link>
      {/* 1. Header */}
      <TeacherHeader
        teacherName={teacherName}
        teacherEmail={teacherEmail}
        classes={classes}
        selectedClassId={classId}
        onSelectClass={setClassId}
        onReload={handleReload}
        isReloading={initialLoading || classLoading}
        onOpenCreateClass={() => setIsCreateClassOpen(true)}
        onOpenUpload={() => setIsUploadOpen(true)}
      />

      <main className={`${styles.mainContent} ${tab === "classes" ? styles.mainContentClassroom : tab === "theory" ? styles.mainContentWide : ""}`}>
        {/* Error notification bar */}
        {initialError && (
          <div className={styles.systemAlertBar} role="alert">
            <AlertCircle size={18} aria-hidden="true" />
            <span>{initialError}</span>
            <button type="button" onClick={handleReload} className={styles.alertActionBtn}>
              <RefreshCw size={13} aria-hidden="true" /> Thử lại
            </button>
          </div>
        )}

        {classErrors.length > 0 && (
          <div className={styles.systemAlertBar} role="alert">
            <AlertCircle size={18} aria-hidden="true" />
            <span>{classErrors.join(" · ")}</span>
          </div>
        )}

        {/* 2. Keep classroom and theory workspaces focused on their main content. */}
        {tab !== "theory" && tab !== "classes" && (
          <TeacherCockpitBanner
            teacherName={teacherName}
            selectedClass={selectedClass}
            students={students}
            assignments={assignments}
            analytics={analytics}
            onOpenCreateClass={() => setIsCreateClassOpen(true)}
            onOpenUpload={() => setIsUploadOpen(true)}
            onSelectTab={handleSelectTab}
          />
        )}

        {/* 3. Navigation Tabs */}
        <div className={styles.tabsStickyWrap}>
          <nav className={styles.tabsBar} aria-label="Các phân hệ quản lý">
            <button
              type="button"
              className={`${styles.tabItem} ${tab === "classes" ? styles.tabItemActive : ""}`}
              onClick={() => handleSelectTab("classes")}
              aria-current={tab === "classes" ? "page" : undefined}
            >
              <Users size={17} aria-hidden="true" />
              <span>Lớp học &amp; Học sinh</span>
              <span className={styles.tabCounterBadge}>{students.length}</span>
            </button>

            <button
              type="button"
              className={`${styles.tabItem} ${tab === "materials" ? styles.tabItemActive : ""}`}
              onClick={() => handleSelectTab("materials")}
              aria-current={tab === "materials" ? "page" : undefined}
            >
              <BookOpen size={17} aria-hidden="true" />
              <span>Kho học liệu &amp; Đề thi</span>
              <span className={styles.tabCounterBadge}>{materials.length}</span>
            </button>

            <button
              type="button"
              className={`${styles.tabItem} ${tab === "theory" ? styles.tabItemActive : ""}`}
              onClick={() => handleSelectTab("theory")}
              aria-current={tab === "theory" ? "page" : undefined}
            >
              <Network size={17} aria-hidden="true" />
              <span>Sơ đồ tư duy &amp; Lý thuyết</span>
            </button>

            <button
              type="button"
              className={`${styles.tabItem} ${tab === "submissions" ? styles.tabItemActive : ""}`}
              onClick={() => handleSelectTab("submissions")}
              aria-current={tab === "submissions" ? "page" : undefined}
            >
              <ClipboardList size={17} aria-hidden="true" />
              <span>Bài giao &amp; Chấm bài</span>
              <span className={styles.tabCounterBadge}>{assignments.length}</span>
            </button>

            <button
              type="button"
              className={`${styles.tabItem} ${tab === "analytics" ? styles.tabItemActive : ""}`}
              onClick={() => handleSelectTab("analytics")}
              aria-current={tab === "analytics" ? "page" : undefined}
            >
              <BarChart3 size={17} aria-hidden="true" />
              <span>Năng lực &amp; Báo cáo AI</span>
              {analytics && analytics.students_needing_attention.length > 0 && (
                <span className={styles.tabAlertBadge}>
                  {analytics.students_needing_attention.length}
                </span>
              )}
            </button>
          </nav>
        </div>

        {/* 4. Tab Views */}
        <div className={styles.viewContainer}>
          {tab === "classes" && (
            <ClassroomsTab
              classes={classes}
              selectedClassId={classId}
              onSelectClass={setClassId}
              students={students}
              isLoading={initialLoading || classLoading}
              studentError={initialError || studentError}
              onViewStudentWorkspace={handleViewStudentWorkspace}
              onOpenCreateClass={() => setIsCreateClassOpen(true)}
            />
          )}

          {tab === "materials" && (
            <MaterialsTab
              selectedClass={selectedClass}
              materials={materials}
              subjects={subjects}
              isLoading={classLoading}
              onOpenUpload={() => setIsUploadOpen(true)}
              onAssignmentCreated={(newAssignment) => {
                setAssignments((current) => [newAssignment, ...current]);
                setAssignmentId(newAssignment.id);
                handleSelectTab("submissions");
              }}
            />
          )}

          {tab === "theory" && (
            <TeacherTheoryClient
              initialClassId={classId}
              onSelectClass={setClassId}
              isEmbedded={true}
            />
          )}

          {tab === "submissions" && (
            <SubmissionsTab
              selectedClass={selectedClass}
              assignments={assignments}
              assignmentId={assignmentId}
              onSelectAssignment={setAssignmentId}
              roster={roster}
              rosterError={rosterError}
              focusedStudent={focusedStudent}
              onClearStudent={() => setFocusedStudent(null)}
              isLoading={classLoading}
              onRefreshRoster={() => {
                if (assignmentId) {
                  teacherApi.roster(assignmentId).then(setRoster).catch(() => {});
                }
              }}
            />
          )}

          {tab === "analytics" && (
            <AnalyticsTab
              selectedClass={selectedClass}
              analytics={analytics}
              isLoading={classLoading}
            />
          )}
        </div>
      </main>

      <AppFooter variant="teacher" />

      {/* 5. Modals */}
      <CreateClassModal
        isOpen={isCreateClassOpen}
        onClose={() => {
          setIsCreateClassOpen(false);
          setCreateClassError("");
        }}
        onSubmit={handleCreateClass}
        isBusy={createClassBusy}
        errorMessage={createClassError}
      />

      <UploadMaterialModal
        isOpen={isUploadOpen}
        onClose={() => {
          setIsUploadOpen(false);
          setUploadError("");
          setUploadSuccess("");
        }}
        selectedClass={selectedClass}
        eligibleSubjects={eligibleSubjects}
        onSubmit={handleUploadMaterial}
        isBusy={uploadBusy}
        errorMessage={uploadError}
        successMessage={uploadSuccess}
      />
    </div>
  );
}
