"use client";

import { TeacherTheoryClient } from "@/features/theory-maps/TeacherTheoryClient";
import { AlertCircle, BarChart3, BookOpen, ClipboardList, Network, RefreshCw, Users, Box, List } from "lucide-react";
import { useEffect, useRef, useState } from "react";
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
import { AnalyticsTab } from "./components/AnalyticsTab";
import type { ViewMode } from "./components/Classroom3DPanel";
import { ClassroomExperience } from "./components/ClassroomExperience";
import { ClassroomsTab } from "./components/ClassroomsTab";
import { CreateClassModal } from "./components/CreateClassModal";
import { MaterialsTab } from "./components/MaterialsTab";
import { SubmissionsTab } from "./components/SubmissionsTab";
import { TeacherHeader } from "./components/TeacherHeader";
import { UploadMaterialModal } from "./components/UploadMaterialModal";
import styles from "./TeacherDashboard.module.css";
import { teacherPdfApi } from "./pdf-api";

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
  const [worldViewMode, setWorldViewMode] = useState<ViewMode>("full");
  const [viewMode3D, setViewMode3D] = useState<"3d" | "list">("3d");
  const [previewDemo, setPreviewDemo] = useState(false);
  const [classroomQuery, setClassroomQuery] = useState("");
  const [isTransitioning, setIsTransitioning] = useState(false);
  const [headerCollapsed, setHeaderCollapsed] = useState(false);
  const navigation = useRef<HTMLElement>(null);
  useEffect(() => {
    const bar = navigation.current;
    const active = bar?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!bar || !active) return;
    const list = bar.getBoundingClientRect(), item = active.getBoundingClientRect();
    if (item.left < list.left || item.right > list.right) bar.scrollLeft += item.left - list.left - (list.width - item.width) / 2;
  }, [tab]);

  useEffect(() => {
    if (initialTab) {
      setTab(initialTab);
    }
  }, [initialTab]);

  const handleSelectTab = (nextTab: TabKey) => {
    if (nextTab === tab) return;
    setTab(nextTab);
    setIsTransitioning(true);
    setTimeout(() => {
      setIsTransitioning(false);
    }, 350);

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
  const [pdfImportId, setPdfImportId] = useState("");

  useEffect(() => {
    const syncImport = () => setPdfImportId(new URLSearchParams(window.location.search).get("pdfImport") ?? "");
    syncImport();
    window.addEventListener("popstate", syncImport);
    return () => window.removeEventListener("popstate", syncImport);
  }, []);

  function openPdfImport(id: string) {
    setPdfImportId(id);
    const url = new URL(window.location.href);
    if (id) { url.searchParams.set("pdfImport", id); url.searchParams.set("tab", "materials"); url.searchParams.set("classroom_id", classId); }
    else url.searchParams.delete("pdfImport");
    window.history.replaceState({}, "", url.toString());
  }

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
        setClassId((current) => {
          const desired = current || new URLSearchParams(window.location.search).get("classroom_id");
          return nextClasses.some((item) => item.id === desired) ? desired! : (nextClasses[0]?.id ?? "");
        });
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
          const loadedAssignments = results[2].value;
          setAssignments(loadedAssignments);
          if (loadedAssignments.length > 0) {
            setAssignmentId((curr) =>
              curr && loadedAssignments.some((a) => a.id === curr) ? curr : loadedAssignments[0].id
            );
          }
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
    (subject) => subject.grade_level === null || subject.grade_level === selectedClass?.grade_level,
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
    if (!classId) {
      setUploadError("Vui lòng chọn lớp học trước khi tải lên học liệu.");
      return;
    }
    setUploadBusy(true);
    setUploadError("");
    setUploadSuccess("");
    try {
      if (file.type === "application/pdf" || file.type.startsWith("image/") || /\.(pdf|png|jpe?g)$/i.test(file.name)) {
        const draft = await teacherPdfApi.upload(classId, subjectId, title, file);
        setIsUploadOpen(false);
        handleSelectTab("materials");
        openPdfImport(draft.id);
        return;
      }
      const created = await teacherApi.uploadMaterial(classId, subjectId, title, file);
      setMaterials((current) => [created, ...current]);
      setUploadSuccess(`Đã tải lên thành công: ${created.title}`);
      setTimeout(() => {
        setIsUploadOpen(false);
        setUploadSuccess("");
      }, 1200);
    } catch (error) {
      setUploadError(getErrorMessage(error));
      throw error;
    } finally {
      setUploadBusy(false);
    }
  }

  const handleReload = () => {
    setReloadCount((c) => c + 1);
  };

  function handleViewStudentWorkspace(studentId: string) {
    const student = students.find((item) => item.student_id === studentId);
    if (!student) return;
    setFocusedStudent({ id: student.student_id, name: student.full_name });
    setAssignmentId((current) => (assignments.some((item) => item.id === current) ? current : (assignments[0]?.id ?? "")));
    handleSelectTab("submissions");
  }

  const isPdfReview = tab === "materials" && Boolean(pdfImportId);
  const embedStationIn3D = !isPdfReview && viewMode3D === "3d" && worldViewMode !== "compact";

  const activeStationWorkspace =
    tab === "materials" ? (
      <MaterialsTab
        selectedClass={selectedClass}
        materials={materials}
        subjects={subjects}
        isLoading={classLoading}
        onOpenUpload={() => setIsUploadOpen(true)}
        pdfImportId={pdfImportId}
        onOpenPdfImport={openPdfImport}
        onMaterialSubmitted={(created) => {
          setMaterials((current) => [created, ...current.filter((m) => m.id !== created.id)]);
          openPdfImport("");
        }}
        onMaterialDeleted={(id) => setMaterials((current) => current.filter((material) => material.id !== id))}
        onAssignmentCreated={(newAssignment) => {
          setAssignments((current) => [newAssignment, ...current]);
          setAssignmentId(newAssignment.id);
          handleSelectTab("submissions");
        }}
      />
    ) : tab === "theory" ? (
      <TeacherTheoryClient initialClassId={classId} onSelectClass={setClassId} isEmbedded={true} />
    ) : tab === "submissions" ? (
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
            teacherApi
              .roster(assignmentId)
              .then(setRoster)
              .catch(() => {});
          }
        }}
      />
    ) : tab === "analytics" ? (
      <AnalyticsTab selectedClass={selectedClass} analytics={analytics} isLoading={classLoading} />
    ) : null;

  return (
    <div
      className={`${styles.dashboard} ${tab === "classes" ? styles.classroomDashboard : ""}`}
      data-3d-fullscreen={embedStationIn3D}
      data-header-collapsed={headerCollapsed}
    >
      <div className={styles.teacherChrome}>
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
        isCollapsed={headerCollapsed}
        onToggleCollapse={() => setHeaderCollapsed((v) => !v)}
      />
          <div className={styles.tabsStickyWrap}>
            <nav ref={navigation} className={styles.tabsBar} aria-label="Các phân hệ quản lý">
              <button
                type="button"
                className={`${styles.tabItem} ${tab === "classes" ? styles.tabItemActive : ""}`}
                aria-label="Lớp học &amp; Học sinh"
                onClick={() => handleSelectTab("classes")}
                aria-current={tab === "classes" ? "page" : undefined}
              >
                <Users size={17} aria-hidden="true" />
                <span>Lớp học</span>
                <span className={styles.tabCounterBadge}>{students.length}</span>
              </button>

              <button
                type="button"
                className={`${styles.tabItem} ${tab === "materials" ? styles.tabItemActive : ""}`}
                aria-label="Kho học liệu &amp; Đề thi"
                onClick={() => handleSelectTab("materials")}
                aria-current={tab === "materials" ? "page" : undefined}
              >
                <BookOpen size={17} aria-hidden="true" />
                <span>Học liệu</span>
                <span className={styles.tabCounterBadge}>{materials.length}</span>
              </button>

              <button
                type="button"
                className={`${styles.tabItem} ${tab === "theory" ? styles.tabItemActive : ""}`}
                aria-label="Sơ đồ tư duy &amp; Lý thuyết"
                onClick={() => handleSelectTab("theory")}
                aria-current={tab === "theory" ? "page" : undefined}
              >
                <Network size={17} aria-hidden="true" />
                <span>Lý thuyết</span>
              </button>

              <button
                type="button"
                className={`${styles.tabItem} ${tab === "submissions" ? styles.tabItemActive : ""}`}
                aria-label="Bài giao &amp; Chấm bài"
                onClick={() => handleSelectTab("submissions")}
                aria-current={tab === "submissions" ? "page" : undefined}
              >
                <ClipboardList size={17} aria-hidden="true" />
                <span>Chấm bài</span>
                <span className={styles.tabCounterBadge}>{assignments.length}</span>
              </button>

              <button
                type="button"
                className={`${styles.tabItem} ${tab === "analytics" ? styles.tabItemActive : ""}`}
                aria-label="Năng lực &amp; Báo cáo AI"
                onClick={() => handleSelectTab("analytics")}
                aria-current={tab === "analytics" ? "page" : undefined}
              >
                <BarChart3 size={17} aria-hidden="true" />
                <span>Báo cáo</span>
                {analytics && analytics.students_needing_attention.length > 0 && (
                  <span className={styles.tabAlertBadge}>{analytics.students_needing_attention.length}</span>
                )}
              </button>
            </nav>
            <div className={styles.teacherViewSwitch} role="group" aria-label="Chế độ hiển thị lớp học">
              <button type="button" aria-label="Lớp học 3D" aria-pressed={viewMode3D === "3d"} onClick={() => { setViewMode3D("3d"); setWorldViewMode("full"); }}><Box size={16} aria-hidden="true" /><span>3D</span></button>
              <button type="button" aria-label="Danh sách" aria-pressed={viewMode3D === "list"} onClick={() => setViewMode3D("list")}><List size={16} aria-hidden="true" /><span>Danh sách</span></button>
            </div>
          </div>
      </div>

      <main
        className={`${styles.mainContent} ${
          tab === "classes" ? styles.mainContentClassroom : tab === "theory" ? styles.mainContentWide : ""
        }`}
        data-3d-fullscreen={embedStationIn3D}
      >
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

        {/* 2. Persistent 3D Cozy Campus Simulation World (Kept alive across all tab switches) */}
        {!isPdfReview && (viewMode3D === "3d" || tab === "classes") && <div className={styles.persistentWorldWrap} data-view-mode={worldViewMode}>
          <ClassroomExperience
            students={students}
            selectedClass={selectedClass}
            isLoading={classLoading}
            error={studentError}
            preview={previewDemo}
            onPreview={setPreviewDemo}
            view={viewMode3D}
            showViewSwitcher={false}
            onView={setViewMode3D}
            query={classroomQuery}
            onQuery={setClassroomQuery}
            onViewStudentWorkspace={handleViewStudentWorkspace}
            currentStation={tab}
            onStationSelect={(st) => handleSelectTab(st as TabKey)}
            viewMode={worldViewMode}
            onToggleViewMode={setWorldViewMode}
            stationWorkspace={embedStationIn3D ? activeStationWorkspace : null}
          />
        </div>}

        {/* 4. Class Roster or Fallback Work View (only when 3D is compact or 2D list mode is active) */}
        {!embedStationIn3D && (
          <div
            className={`${styles.viewContainer} ${isTransitioning ? styles.viewContainerTransitioning : ""}`}
            data-transitioning={isTransitioning}
          >
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

            {activeStationWorkspace}
          </div>
        )}
      </main>

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
