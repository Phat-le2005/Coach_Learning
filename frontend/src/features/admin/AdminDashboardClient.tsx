"use client";

import { useEffect, useState } from "react";
import {
  ShieldCheck,
  RefreshCw,
  ChevronDown,
  BookOpen,
  Database,
  Cpu,
  GraduationCap,
  Plus,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  Sparkles,
  Layers,
  FileCheck2,
  Activity,
  Building2,
} from "lucide-react";
import { AccountMenu } from "@/components/auth/AccountMenu";
import { AppFooter } from "@/components/app-shell/AppFooter";
import styles from "@/features/teacher/TeacherDashboard.module.css";
import {
  adminApi,
  AdminApiError,
  type AdminAcquisitionRequest,
  type AdminAdmissionImportHistory,
  type AdminAdmissionRule,
  type AdminAIRequestLogPagination,
  type AdminAIUsageSummary,
  type AdminCurriculum,
  type AdminMajor,
  type AdminQuestion,
  type AdminSubject,
  type AdminSubjectTree,
  type AdminSupplyGap,
  type AdminUniversity,
  type AdminValidationBatch,
} from "./api";

export type AdminTabKey = "curriculum" | "question-supply" | "ai-governance" | "admission";

const getErrorMessage = (error: unknown) =>
  error instanceof AdminApiError ? error.message : "Không thể tải dữ liệu quản trị từ backend.";

export function AdminDashboardClient({
  adminName,
  adminEmail,
  initialTab = "curriculum",
}: {
  adminName: string;
  adminEmail: string;
  initialTab?: AdminTabKey;
}) {
  const [tab, setTab] = useState<AdminTabKey>(initialTab);
  const [reloadCount, setReloadCount] = useState(0);
  const [initialLoading, setInitialLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState("");
  const [actionNotice, setActionNotice] = useState("");

  // 1. Curriculum & Subjects states
  const [subjects, setSubjects] = useState<AdminSubject[]>([]);
  const [curricula, setCurricula] = useState<AdminCurriculum[]>([]);
  const [selectedSubjectId, setSelectedSubjectId] = useState<string>("");
  const [subjectTree, setSubjectTree] = useState<AdminSubjectTree | null>(null);
  const [treeLoading, setTreeLoading] = useState(false);

  // Create Subject / Chapter quick forms
  const [newSubjectCode, setNewSubjectCode] = useState("");
  const [newSubjectName, setNewSubjectName] = useState("");
  const [newSubjectGrade, setNewSubjectGrade] = useState<number>(12);
  const [newChapterCode, setNewChapterCode] = useState("");
  const [newChapterName, setNewChapterName] = useState("");
  const [formBusy, setFormBusy] = useState(false);

  // 2. Question Bank & Supply states
  const [questions, setQuestions] = useState<AdminQuestion[]>([]);
  const [questionStatusFilter, setQuestionStatusFilter] = useState<string>("");
  const [supplyGaps, setSupplyGaps] = useState<AdminSupplyGap[]>([]);
  const [acquisitionRequests, setAcquisitionRequests] = useState<AdminAcquisitionRequest[]>([]);
  const [validationBatches, setValidationBatches] = useState<AdminValidationBatch[]>([]);

  // 3. AI Observability states
  const [aiSummary, setAiSummary] = useState<AdminAIUsageSummary | null>(null);
  const [aiLogs, setAiLogs] = useState<AdminAIRequestLogPagination | null>(null);

  // 4. Admission Catalog states
  const [universities, setUniversities] = useState<AdminUniversity[]>([]);
  const [selectedUniversityId, setSelectedUniversityId] = useState<string>("");
  const [majors, setMajors] = useState<AdminMajor[]>([]);
  const [selectedMajorId, setSelectedMajorId] = useState<string>("");
  const [majorRules, setMajorRules] = useState<AdminAdmissionRule[]>([]);
  const [importHistory, setImportHistory] = useState<AdminAdmissionImportHistory[]>([]);
  const [newUniCode, setNewUniCode] = useState("");
  const [newUniName, setNewUniName] = useState("");
  const [newUniRegion, setNewUniRegion] = useState("MIEN_BAC");

  useEffect(() => {
    if (initialTab) setTab(initialTab);
  }, [initialTab]);

  const handleSelectTab = (nextTab: AdminTabKey) => {
    setTab(nextTab);
    setActionNotice("");
    if (typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.set("tab", nextTab);
      window.history.replaceState({}, "", url.toString());
    }
  };

  // Initial core load across Admin modules
  useEffect(() => {
    let active = true;
    setInitialLoading(true);
    setErrorMsg("");

    Promise.allSettled([
      adminApi.subjects(),
      adminApi.curricula(),
      adminApi.questions({ status: questionStatusFilter || undefined, limit: 50 }),
      adminApi.supplyGaps(),
      adminApi.acquisitionRequests(),
      adminApi.validationBatches(),
      adminApi.aiUsageSummary(),
      adminApi.aiUsageLogs(1, 25),
      adminApi.universities(),
      adminApi.admissionImportHistory(),
    ])
      .then((results) => {
        if (!active) return;
        const errors: string[] = [];

        if (results[0].status === "fulfilled") {
          const list = results[0].value;
          setSubjects(list);
          setSelectedSubjectId((cur) =>
            list.some((s) => s.id === cur) ? cur : list[0]?.id ?? ""
          );
        } else {
          errors.push(`Môn học: ${getErrorMessage(results[0].reason)}`);
        }

        if (results[1].status === "fulfilled") setCurricula(results[1].value);
        if (results[2].status === "fulfilled") setQuestions(results[2].value);
        if (results[3].status === "fulfilled") setSupplyGaps(results[3].value);
        if (results[4].status === "fulfilled") setAcquisitionRequests(results[4].value);
        if (results[5].status === "fulfilled") setValidationBatches(results[5].value);
        if (results[6].status === "fulfilled") setAiSummary(results[6].value);
        if (results[7].status === "fulfilled") setAiLogs(results[7].value);

        if (results[8].status === "fulfilled") {
          const unis = results[8].value;
          setUniversities(unis);
          setSelectedUniversityId((cur) =>
            unis.some((u) => u.id === cur) ? cur : unis[0]?.id ?? ""
          );
        }
        if (results[9].status === "fulfilled") setImportHistory(results[9].value);

        if (errors.length > 0) setErrorMsg(errors.join(" · "));
      })
      .finally(() => {
        if (active) setInitialLoading(false);
      });

    return () => {
      active = false;
    };
  }, [reloadCount, questionStatusFilter]);

  // Load Curriculum Tree when selectedSubjectId changes
  useEffect(() => {
    if (!selectedSubjectId) {
      setSubjectTree(null);
      return;
    }
    let active = true;
    setTreeLoading(true);
    adminApi
      .curriculumTree(selectedSubjectId)
      .then((tree) => {
        if (active) setSubjectTree(tree);
      })
      .catch(() => {
        if (active) setSubjectTree(null);
      })
      .finally(() => {
        if (active) setTreeLoading(false);
      });
    return () => {
      active = false;
    };
  }, [selectedSubjectId, reloadCount]);

  // Load Majors when selectedUniversityId changes
  useEffect(() => {
    if (!selectedUniversityId) {
      setMajors([]);
      setSelectedMajorId("");
      return;
    }
    let active = true;
    adminApi
      .majorsByUniversity(selectedUniversityId)
      .then((list) => {
        if (!active) return;
        setMajors(list);
        setSelectedMajorId((cur) => (list.some((m) => m.id === cur) ? cur : list[0]?.id ?? ""));
      })
      .catch(() => {
        if (active) setMajors([]);
      });
    return () => {
      active = false;
    };
  }, [selectedUniversityId, reloadCount]);

  // Load Admission Rules when selectedMajorId changes
  useEffect(() => {
    if (!selectedMajorId) {
      setMajorRules([]);
      return;
    }
    let active = true;
    adminApi
      .rulesByMajor(selectedMajorId)
      .then((rules) => {
        if (active) setMajorRules(rules);
      })
      .catch(() => {
        if (active) setMajorRules([]);
      });
    return () => {
      active = false;
    };
  }, [selectedMajorId, reloadCount]);

  // Handlers
  const handleCreateSubject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newSubjectCode.trim() || !newSubjectName.trim()) return;
    setFormBusy(true);
    setErrorMsg("");
    setActionNotice("");
    try {
      const created = await adminApi.createSubject({
        code: newSubjectCode.trim().toUpperCase(),
        name: newSubjectName.trim(),
        grade_level: newSubjectGrade,
      });
      setNewSubjectCode("");
      setNewSubjectName("");
      setSelectedSubjectId(created.id);
      setActionNotice(`Đã tạo môn học ${created.name} (${created.code}).`);
      setReloadCount((c) => c + 1);
    } catch (err) {
      setErrorMsg(getErrorMessage(err));
    } finally {
      setFormBusy(false);
    }
  };

  const handleCreateChapter = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedSubjectId || !newChapterCode.trim() || !newChapterName.trim()) return;
    setFormBusy(true);
    setErrorMsg("");
    setActionNotice("");
    try {
      const nextIndex = subjectTree ? subjectTree.chapters.length : 0;
      await adminApi.createChapter({
        subject_id: selectedSubjectId,
        code: newChapterCode.trim().toUpperCase(),
        name: newChapterName.trim(),
        order_index: nextIndex,
      });
      setNewChapterCode("");
      setNewChapterName("");
      setActionNotice("Đã thêm chương mới vào cây chương trình.");
      setReloadCount((c) => c + 1);
    } catch (err) {
      setErrorMsg(getErrorMessage(err));
    } finally {
      setFormBusy(false);
    }
  };

  const handleApproveQuestion = async (questionId: string) => {
    setFormBusy(true);
    setErrorMsg("");
    setActionNotice("");
    try {
      await adminApi.approveQuestion(questionId);
      setActionNotice("Đã phê duyệt câu hỏi vào ngân hàng câu hỏi chuẩn.");
      setReloadCount((c) => c + 1);
    } catch (err) {
      setErrorMsg(getErrorMessage(err));
    } finally {
      setFormBusy(false);
    }
  };

  const handleReassessGaps = async () => {
    setFormBusy(true);
    setErrorMsg("");
    setActionNotice("");
    try {
      const updated = await adminApi.reassessOpenGaps();
      setSupplyGaps(updated);
      setActionNotice(`Đã đánh giá lại ${updated.length} khoảng trống ngân hàng câu hỏi.`);
    } catch (err) {
      setErrorMsg(getErrorMessage(err));
    } finally {
      setFormBusy(false);
    }
  };

  const handlePlanAcquisition = async (gapId: string) => {
    setFormBusy(true);
    setErrorMsg("");
    setActionNotice("");
    try {
      await adminApi.planGapAcquisition(gapId);
      setActionNotice("Đã lập yêu cầu thu thập học liệu (Acquisition Request) cho khoảng trống này.");
      setReloadCount((c) => c + 1);
    } catch (err) {
      setErrorMsg(getErrorMessage(err));
    } finally {
      setFormBusy(false);
    }
  };

  const handleCreateUniversity = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newUniCode.trim() || !newUniName.trim()) return;
    setFormBusy(true);
    setErrorMsg("");
    setActionNotice("");
    try {
      const created = await adminApi.createUniversity({
        code: newUniCode.trim().toUpperCase(),
        name: newUniName.trim(),
        region: newUniRegion,
      });
      setNewUniCode("");
      setNewUniName("");
      setSelectedUniversityId(created.id);
      setActionNotice(`Đã thêm trường ${created.name} (${created.code}).`);
      setReloadCount((c) => c + 1);
    } catch (err) {
      setErrorMsg(getErrorMessage(err));
    } finally {
      setFormBusy(false);
    }
  };

  const initials = adminName
    ? adminName
        .split(" ")
        .filter(Boolean)
        .slice(-2)
        .map((w) => w[0]?.toUpperCase())
        .join("")
    : "AD";

  const selectedSubject = subjects.find((s) => s.id === selectedSubjectId);
  const openGapsCount = supplyGaps.filter((g) => g.status !== "RESOLVED").length;

  return (
    <div className={styles.dashboard}>
      {/* Sticky Header */}
      <header className={styles.header}>
        <div className={styles.headerInner}>
          <div className={styles.headerTop}>
            <div className={styles.headerLeft}>
              <div className={styles.teacherAvatar} aria-hidden="true">
                {initials}
              </div>
              <div className={styles.teacherInfo}>
                <div className={styles.teacherNameRow}>
                  <h1 className={styles.teacherName}>{adminName}</h1>
                  <span className={styles.roleBadge}>
                    <ShieldCheck size={13} aria-hidden="true" />
                    Quản trị viên Hệ thống
                  </span>
                </div>
                <p className={styles.teacherSubtitle}>
                  Trung tâm Điều hành Chương trình học, Ngân hàng Câu hỏi, Giám sát AI &amp; Tuyển sinh EduMS
                </p>
              </div>
            </div>

            <div className={styles.headerRight}>
              <div className={styles.classSelectorCard}>
                <label htmlFor="admin-subject-select" className={styles.classSelectorLabel}>
                  Môn trọng tâm:
                </label>
                <div className={styles.classSelectWrap}>
                  <select
                    id="admin-subject-select"
                    className={styles.classSelectControl}
                    value={selectedSubjectId}
                    onChange={(e) => setSelectedSubjectId(e.target.value)}
                    aria-label="Chọn môn học quản trị"
                    disabled={subjects.length === 0}
                  >
                    {subjects.length === 0 && <option value="">Chưa có môn học</option>}
                    {subjects.map((subj) => (
                      <option key={subj.id} value={subj.id}>
                        {subj.name} ({subj.code}){subj.grade_level ? ` · Khối ${subj.grade_level}` : ""}
                      </option>
                    ))}
                  </select>
                  <ChevronDown size={14} className={styles.selectChevron} aria-hidden="true" />
                </div>
              </div>

              <button
                type="button"
                className={styles.btnSecondary}
                onClick={() => setReloadCount((c) => c + 1)}
                disabled={initialLoading || formBusy}
                title="Đồng bộ dữ liệu quản trị mới nhất"
              >
                <RefreshCw
                  size={15}
                  className={initialLoading ? styles.spinIcon : ""}
                  aria-hidden="true"
                />
                <span className={styles.hideMobile}>Làm mới</span>
              </button>

              <div className={styles.accountMenuWrap}>
                <AccountMenu fullName={adminName} email={adminEmail} role="ADMIN" compact />
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className={styles.mainContent}>
        {errorMsg && (
          <div className={styles.systemAlertBar} role="alert">
            <AlertCircle size={18} aria-hidden="true" />
            <span>{errorMsg}</span>
            <button
              type="button"
              onClick={() => setReloadCount((c) => c + 1)}
              className={styles.alertActionBtn}
            >
              <RefreshCw size={14} /> Thử lại
            </button>
          </div>
        )}

        {actionNotice && (
          <div
            style={{
              padding: "12px 18px",
              borderRadius: "14px",
              background: "rgba(220, 239, 229, 0.85)",
              border: "1px solid #286955",
              color: "#102e26",
              fontSize: "0.88rem",
              fontWeight: 650,
              display: "flex",
              alignItems: "center",
              gap: "10px",
            }}
          >
            <CheckCircle2 size={18} />
            <span>{actionNotice}</span>
          </div>
        )}

        {/* Cockpit Banner & 4 System KPI Cards */}
        <div className={styles.cockpitBanner}>
          <div className={styles.cockpitWelcome}>
            <div className={styles.cockpitIntro}>
              <div className={styles.cockpitTag}>
                <Sparkles size={13} aria-hidden="true" />
                Quản trị Kiến trúc &amp; Dữ liệu Chuẩn
              </div>
              <h2 className={styles.cockpitGreeting}>Trung tâm Quản trị EduMS</h2>
              <p className={styles.cockpitClassMeta}>
                {selectedSubject ? (
                  <>
                    Đang xem cấu trúc môn <strong>{selectedSubject.name}</strong> ({selectedSubject.code}) ·{" "}
                    {curricula.length} bộ chương trình · {universities.length} trường đại học trong danh mục.
                  </>
                ) : (
                  "Quản lý tập trung cây chương trình GDPT 2018, kiểm duyệt câu hỏi, theo dõi lỗ hổng học liệu và giám sát chi phí AI."
                )}
              </p>
            </div>
          </div>

          <div className={styles.kpiGrid}>
            {/* KPI 1: Môn học & Chương trình */}
            <div
              className={`${styles.kpiCard} ${styles.kpiCardClickable}`}
              onClick={() => handleSelectTab("curriculum")}
              role="button"
              tabIndex={0}
            >
              <div className={`${styles.kpiIconWrap} ${styles.kpiIconEmerald}`}>
                <Layers size={24} aria-hidden="true" />
              </div>
              <div className={styles.kpiMeta}>
                <span className={styles.kpiLabel}>Chương trình &amp; Môn học</span>
                <div className={styles.kpiValueRow}>
                  <strong className={styles.kpiValue}>{subjects.length}</strong>
                  <span className={styles.kpiUnit}>môn học</span>
                </div>
                <span className={styles.kpiSub}>
                  {subjectTree
                    ? `${subjectTree.chapters.length} chương trong môn đang chọn`
                    : `${curricula.length} khung chương trình`}
                </span>
              </div>
            </div>

            {/* KPI 2: Ngân hàng câu hỏi & Supply Gaps */}
            <div
              className={`${styles.kpiCard} ${styles.kpiCardClickable} ${
                openGapsCount > 0 ? styles.kpiCardAlert : ""
              }`}
              onClick={() => handleSelectTab("question-supply")}
              role="button"
              tabIndex={0}
            >
              <div
                className={`${styles.kpiIconWrap} ${
                  openGapsCount > 0 ? styles.kpiIconAmber : styles.kpiIconMint
                }`}
              >
                <Database size={24} aria-hidden="true" />
              </div>
              <div className={styles.kpiMeta}>
                <span className={styles.kpiLabel}>Kho câu hỏi &amp; Lỗ hổng</span>
                <div className={styles.kpiValueRow}>
                  <strong className={styles.kpiValue}>{questions.length}</strong>
                  <span className={styles.kpiUnit}>câu hỏi hiển thị</span>
                </div>
                <span className={styles.kpiSub}>
                  {openGapsCount} khoảng trống cung ứng · {validationBatches.length} lô kiểm duyệt
                </span>
              </div>
            </div>

            {/* KPI 3: Vận hành AI */}
            <div
              className={`${styles.kpiCard} ${styles.kpiCardClickable}`}
              onClick={() => handleSelectTab("ai-governance")}
              role="button"
              tabIndex={0}
            >
              <div className={`${styles.kpiIconWrap} ${styles.kpiIconSky}`}>
                <Cpu size={24} aria-hidden="true" />
              </div>
              <div className={styles.kpiMeta}>
                <span className={styles.kpiLabel}>Lưu lượng AI Gateway</span>
                <div className={styles.kpiValueRow}>
                  <strong className={styles.kpiValue}>{aiSummary?.total_requests ?? 0}</strong>
                  <span className={styles.kpiUnit}>lượt gọi AI</span>
                </div>
                <span className={styles.kpiSub}>
                  {aiSummary
                    ? `${aiSummary.total_tokens.toLocaleString()} tokens · Tỷ lệ lỗi ${(aiSummary.failure_rate * 100).toFixed(1)}%`
                    : "Giám sát độ trễ & chi phí"}
                </span>
              </div>
            </div>

            {/* KPI 4: Danh mục Tuyển sinh Đại học */}
            <div
              className={`${styles.kpiCard} ${styles.kpiCardClickable}`}
              onClick={() => handleSelectTab("admission")}
              role="button"
              tabIndex={0}
            >
              <div className={`${styles.kpiIconWrap} ${styles.kpiIconMint}`}>
                <GraduationCap size={24} aria-hidden="true" />
              </div>
              <div className={styles.kpiMeta}>
                <span className={styles.kpiLabel}>Dữ liệu Tuyển sinh</span>
                <div className={styles.kpiValueRow}>
                  <strong className={styles.kpiValue}>{universities.length}</strong>
                  <span className={styles.kpiUnit}>trường đại học</span>
                </div>
                <span className={styles.kpiSub}>
                  {majors.length} ngành thuộc trường đang chọn · {importHistory.length} lịch sử import
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Sticky Navigation Tabs */}
        <div className={styles.tabsStickyWrap}>
          <nav className={styles.tabsBar} aria-label="Điều hướng cổng quản trị">
            <button
              type="button"
              onClick={() => handleSelectTab("curriculum")}
              className={`${styles.tabItem} ${tab === "curriculum" ? styles.tabItemActive : ""}`}
            >
              <BookOpen size={16} aria-hidden="true" />
              <span>Chương trình &amp; Cây Kiến thức</span>
              <span className={styles.tabCounterBadge}>{subjects.length}</span>
            </button>

            <button
              type="button"
              onClick={() => handleSelectTab("question-supply")}
              className={`${styles.tabItem} ${tab === "question-supply" ? styles.tabItemActive : ""}`}
            >
              <FileCheck2 size={16} aria-hidden="true" />
              <span>Ngân hàng Câu hỏi &amp; Cung ứng</span>
              {openGapsCount > 0 && <span className={styles.tabAlertBadge}>{openGapsCount}</span>}
            </button>

            <button
              type="button"
              onClick={() => handleSelectTab("ai-governance")}
              className={`${styles.tabItem} ${tab === "ai-governance" ? styles.tabItemActive : ""}`}
            >
              <Activity size={16} aria-hidden="true" />
              <span>Giám sát Vận hành AI</span>
              {aiSummary && <span className={styles.tabCounterBadge}>{aiSummary.total_requests}</span>}
            </button>

            <button
              type="button"
              onClick={() => handleSelectTab("admission")}
              className={`${styles.tabItem} ${tab === "admission" ? styles.tabItemActive : ""}`}
            >
              <Building2 size={16} aria-hidden="true" />
              <span>Quy chế &amp; Trường Đại học</span>
              <span className={styles.tabCounterBadge}>{universities.length}</span>
            </button>
          </nav>
        </div>

        {/* TAB 1: CURRICULUM & KNOWLEDGE GRAPH */}
        {tab === "curriculum" && (
          <div className={styles.tabContentWrap}>
            {/* Quick Create Subject & Chapter */}
            <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))" }}>
              <form onSubmit={(e) => void handleCreateSubject(e)} className={styles.sectionCard}>
                <div className={styles.sectionCardHeader}>
                  <div>
                    <h3 className={styles.sectionHeading}>Khởi tạo Môn học Mới</h3>
                    <p className={styles.sectionSubheading}>POST /admin/subjects</p>
                  </div>
                </div>
                <div style={{ display: "grid", gap: "10px", gridTemplateColumns: "1fr 2fr 90px" }}>
                  <input
                    type="text"
                    placeholder="Mã (VD: MATH_G12)"
                    value={newSubjectCode}
                    onChange={(e) => setNewSubjectCode(e.target.value)}
                    required
                    style={{ padding: "8px 12px", borderRadius: "10px", border: "1px solid rgba(40,105,85,0.25)" }}
                  />
                  <input
                    type="text"
                    placeholder="Tên môn học (VD: Toán 12)"
                    value={newSubjectName}
                    onChange={(e) => setNewSubjectName(e.target.value)}
                    required
                    style={{ padding: "8px 12px", borderRadius: "10px", border: "1px solid rgba(40,105,85,0.25)" }}
                  />
                  <input
                    type="number"
                    min={1}
                    max={12}
                    value={newSubjectGrade}
                    onChange={(e) => setNewSubjectGrade(Number(e.target.value))}
                    style={{ padding: "8px 10px", borderRadius: "10px", border: "1px solid rgba(40,105,85,0.25)" }}
                  />
                </div>
                <div>
                  <button type="submit" className={styles.btnPrimary} disabled={formBusy}>
                    <Plus size={15} /> Tạo môn học
                  </button>
                </div>
              </form>

              <form onSubmit={(e) => void handleCreateChapter(e)} className={styles.sectionCard}>
                <div className={styles.sectionCardHeader}>
                  <div>
                    <h3 className={styles.sectionHeading}>
                      Thêm Chương vào {selectedSubject?.name ?? "Môn đang chọn"}
                    </h3>
                    <p className={styles.sectionSubheading}>POST /admin/chapters</p>
                  </div>
                </div>
                <div style={{ display: "grid", gap: "10px", gridTemplateColumns: "1fr 2fr" }}>
                  <input
                    type="text"
                    placeholder="Mã chương (VD: CH01)"
                    value={newChapterCode}
                    onChange={(e) => setNewChapterCode(e.target.value)}
                    required
                    disabled={!selectedSubjectId}
                    style={{ padding: "8px 12px", borderRadius: "10px", border: "1px solid rgba(40,105,85,0.25)" }}
                  />
                  <input
                    type="text"
                    placeholder="Tên chương (VD: Ứng dụng đạo hàm)"
                    value={newChapterName}
                    onChange={(e) => setNewChapterName(e.target.value)}
                    required
                    disabled={!selectedSubjectId}
                    style={{ padding: "8px 12px", borderRadius: "10px", border: "1px solid rgba(40,105,85,0.25)" }}
                  />
                </div>
                <div>
                  <button
                    type="submit"
                    className={styles.btnPrimary}
                    disabled={formBusy || !selectedSubjectId}
                  >
                    <Plus size={15} /> Thêm chương
                  </button>
                </div>
              </form>
            </div>

            {/* Curriculum Tree Viewer */}
            <div className={styles.sectionCard}>
              <div className={styles.sectionCardHeader}>
                <div>
                  <div className={styles.badgeCluster}>
                    <h3 className={styles.sectionHeading}>
                      Cây Chương trình Chuẩn: {subjectTree?.name ?? selectedSubject?.name ?? "Chưa chọn môn"}
                    </h3>
                    {subjectTree && (
                      <span className={styles.studentTotalPill}>
                        {subjectTree.chapters.length} chương
                      </span>
                    )}
                  </div>
                  <p className={styles.sectionSubheading}>
                    Cấu trúc phân cấp: Môn học &rarr; Chương (Chapter) &rarr; Chủ đề (Topic) &rarr; Dạng bài toán (ProblemType) kèm liên kết Concept &amp; Chuẩn đầu ra
                  </p>
                </div>
              </div>

              {treeLoading ? (
                <div className={styles.tableLoadingState}>
                  <div className={styles.spinner} aria-hidden="true" />
                  <p>Đang tải cây chương trình từ backend...</p>
                </div>
              ) : !subjectTree || subjectTree.chapters.length === 0 ? (
                <div className={styles.emptyCard}>
                  <BookOpen size={32} className={styles.emptyIcon} />
                  <h4 className={styles.emptyTitle}>Môn học chưa có chương nào</h4>
                  <p className={styles.emptyDesc}>
                    Sử dụng biểu mẫu bên trên hoặc công cụ seed curriculum để nạp chương và dạng bài.
                  </p>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  {subjectTree.chapters.map((chap) => (
                    <div key={chap.id} className={styles.chapterCardModern}>
                      <div className={styles.chapterCardTop}>
                        <span className={styles.chapterSubjectPill}>{chap.code}</span>
                        <span className={styles.chapterProficientText}>
                          <strong>{chap.topics.length}</strong> chủ đề
                        </span>
                      </div>
                      <h4 className={styles.chapterCardTitle}>{chap.name}</h4>

                      {chap.topics.length > 0 && (
                        <div style={{ display: "grid", gap: "10px", marginTop: "10px" }}>
                          {chap.topics.map((top) => (
                            <div
                              key={top.id}
                              style={{
                                padding: "10px 14px",
                                borderRadius: "12px",
                                background: "rgba(245, 243, 233, 0.7)",
                                border: "1px solid rgba(40, 105, 85, 0.14)",
                              }}
                            >
                              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <strong style={{ fontSize: "0.9rem", color: "#173f34" }}>
                                  [{top.code}] {top.name}
                                </strong>
                                <span style={{ fontSize: "0.76rem", color: "#52675d" }}>
                                  {top.problem_types.length} dạng bài
                                </span>
                              </div>
                              {top.problem_types.length > 0 && (
                                <div style={{ display: "flex", flexWrap: "wrap", gap: "6px", marginTop: "8px" }}>
                                  {top.problem_types.map((pt) => (
                                    <span
                                      key={pt.id}
                                      style={{
                                        fontSize: "0.76rem",
                                        padding: "4px 9px",
                                        borderRadius: "8px",
                                        background: "#ffffff",
                                        border: "1px solid rgba(40,105,85,0.2)",
                                        color: "#102e26",
                                      }}
                                    >
                                      <strong>{pt.code}</strong>: {pt.name} ({pt.concept_count} khái niệm)
                                    </span>
                                  ))}
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 2: QUESTION BANK & SUPPLY PIPELINE */}
        {tab === "question-supply" && (
          <div className={styles.tabContentWrap}>
            {/* Supply Gaps Section */}
            <div className={styles.sectionCard}>
              <div className={styles.sectionCardHeader}>
                <div>
                  <div className={styles.badgeCluster}>
                    <h3 className={styles.sectionHeading}>
                      Khoảng trống Cung ứng Câu hỏi (Question Supply Gaps)
                    </h3>
                    <span className={openGapsCount > 0 ? styles.badgeAlertCount : styles.studentTotalPill}>
                      {supplyGaps.length} ghi nhận
                    </span>
                  </div>
                  <p className={styles.sectionSubheading}>
                    Phát hiện tự động khi học sinh luyện tập/kiểm tra nhưng thiếu câu hỏi đã duyệt trong dải độ khó yêu cầu.
                  </p>
                </div>
                <button
                  type="button"
                  className={styles.btnSecondary}
                  onClick={() => void handleReassessGaps()}
                  disabled={formBusy}
                >
                  <RefreshCw size={15} /> Đánh giá lại tồn kho
                </button>
              </div>

              {supplyGaps.length === 0 ? (
                <div className={styles.alertEmptyCard}>
                  <CheckCircle2 size={32} className={styles.textVerdant} />
                  <div>
                    <h4 className={styles.emptyTitle}>Ngân hàng câu hỏi hiện đáp ứng đủ nhu cầu</h4>
                    <p className={styles.emptyDesc}>
                      Chưa ghi nhận khoảng trống cung ứng (Supply Gap) nào từ các phiên học tập.
                    </p>
                  </div>
                </div>
              ) : (
                <div className={styles.weakGrid}>
                  {supplyGaps.map((gap) => (
                    <div key={gap.id} className={styles.weakCard}>
                      <div className={styles.weakCardTop}>
                        <span className={styles.weakCardBadge}>
                          {gap.severity} · {gap.status}
                        </span>
                        <span className={styles.weakStudentCount}>Nhu cầu: {gap.demand_count} lần</span>
                      </div>
                      <h4 className={styles.weakProblemTitle}>
                        {gap.use_case} ({gap.target_type})
                      </h4>
                      <div className={styles.weakScoreRow}>
                        <span>Câu hỏi đạt chuẩn trong dải [{gap.difficulty_min}–{gap.difficulty_max}]:</span>
                        <strong className={styles.weakScoreValue}>
                          {gap.approved_in_band_count}/{gap.minimum_required_count}
                        </strong>
                      </div>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "8px" }}>
                        <span style={{ fontSize: "0.78rem", color: "#647b70" }}>
                          Lý do: {gap.reason_code}
                        </span>
                        <button
                          type="button"
                          className={styles.btnPrimary}
                          onClick={() => void handlePlanAcquisition(gap.id)}
                          disabled={formBusy}
                          style={{ padding: "5px 12px", fontSize: "0.78rem" }}
                        >
                          Lập kế hoạch thu thập
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Acquisition Requests & Validation Batches */}
            <div style={{ display: "grid", gap: "1rem", gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))" }}>
              <div className={styles.sectionCard}>
                <div className={styles.sectionCardHeader}>
                  <div>
                    <h3 className={styles.sectionHeading}>
                      Yêu cầu Thu thập Học liệu ({acquisitionRequests.length})
                    </h3>
                    <p className={styles.sectionSubheading}>GET /question-acquisition/requests</p>
                  </div>
                </div>
                {acquisitionRequests.length === 0 ? (
                  <p style={{ fontSize: "0.86rem", color: "#647b70" }}>Chưa có yêu cầu thu thập nào.</p>
                ) : (
                  <div style={{ display: "grid", gap: "8px" }}>
                    {acquisitionRequests.slice(0, 8).map((req) => (
                      <div
                        key={req.id}
                        style={{
                          padding: "10px 12px",
                          borderRadius: "12px",
                          background: "#ffffff",
                          border: "1px solid rgba(40,105,85,0.16)",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <div>
                          <strong style={{ fontSize: "0.86rem", color: "#102e26" }}>
                            {req.strategy} · {req.use_case}
                          </strong>
                          <div style={{ fontSize: "0.76rem", color: "#52675d" }}>
                            Cần mới: {req.required_new_candidate_count} câu · Đã có ứng viên: {req.existing_candidate_count}
                          </div>
                        </div>
                        <span className={styles.studentTotalPill}>{req.status}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className={styles.sectionCard}>
                <div className={styles.sectionCardHeader}>
                  <div>
                    <h3 className={styles.sectionHeading}>
                      Lô Kiểm duyệt Ứng viên ({validationBatches.length})
                    </h3>
                    <p className={styles.sectionSubheading}>GET /question-validation/batches</p>
                  </div>
                </div>
                {validationBatches.length === 0 ? (
                  <p style={{ fontSize: "0.86rem", color: "#647b70" }}>Chưa có lô kiểm duyệt nào.</p>
                ) : (
                  <div style={{ display: "grid", gap: "8px" }}>
                    {validationBatches.slice(0, 8).map((batch) => (
                      <div
                        key={batch.id}
                        style={{
                          padding: "10px 12px",
                          borderRadius: "12px",
                          background: "#ffffff",
                          border: "1px solid rgba(40,105,85,0.16)",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <div>
                          <strong style={{ fontSize: "0.86rem", color: "#102e26" }}>
                            Lô #{batch.attempt_index}
                          </strong>
                          <div style={{ fontSize: "0.76rem", color: "#52675d" }}>
                            Chỉ tiêu: {batch.target_candidate_count_snapshot} ứng viên
                          </div>
                        </div>
                        <span className={styles.studentTotalPill}>{batch.status}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Question Bank List & Approval */}
            <div className={styles.sectionCard}>
              <div className={styles.sectionCardHeader}>
                <div>
                  <h3 className={styles.sectionHeading}>Ngân hàng Câu hỏi &amp; Phê duyệt</h3>
                  <p className={styles.sectionSubheading}>
                    Quản trị viên có quyền phê duyệt (POST /questions/&#123;id&#125;/approve) các câu hỏi đang ở trạng thái REVIEW hoặc DRAFT.
                  </p>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
                  <label htmlFor="q-status-filter" style={{ fontSize: "0.82rem", fontWeight: 600 }}>
                    Trạng thái:
                  </label>
                  <select
                    id="q-status-filter"
                    value={questionStatusFilter}
                    onChange={(e) => setQuestionStatusFilter(e.target.value)}
                    style={{
                      padding: "6px 10px",
                      borderRadius: "10px",
                      border: "1px solid rgba(40,105,85,0.25)",
                      fontSize: "0.85rem",
                    }}
                  >
                    <option value="">Tất cả</option>
                    <option value="APPROVED">APPROVED (Đã duyệt)</option>
                    <option value="REVIEW">REVIEW (Chờ duyệt)</option>
                    <option value="DRAFT">DRAFT (Bản nháp)</option>
                    <option value="ARCHIVED">ARCHIVED (Lưu trữ)</option>
                  </select>
                </div>
              </div>

              {questions.length === 0 ? (
                <div className={styles.emptyCard}>
                  <Database size={32} className={styles.emptyIcon} />
                  <h4 className={styles.emptyTitle}>Không có câu hỏi phù hợp bộ lọc</h4>
                </div>
              ) : (
                <div style={{ display: "grid", gap: "10px" }}>
                  {questions.slice(0, 25).map((q) => (
                    <div
                      key={q.id}
                      style={{
                        padding: "14px 16px",
                        borderRadius: "14px",
                        background: "#ffffff",
                        border: "1px solid rgba(40,105,85,0.16)",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        gap: "1rem",
                      }}
                    >
                      <div style={{ flex: 1 }}>
                        <div style={{ display: "flex", gap: "8px", alignItems: "center", marginBottom: "6px" }}>
                          <span className={styles.chapterSubjectPill}>{q.question_type}</span>
                          <span className={styles.studentTotalPill}>{q.status}</span>
                          <span style={{ fontSize: "0.78rem", color: "#52675d" }}>
                            Độ khó: {Math.round(q.difficulty * 100)}% · Nguồn: {q.source_type}
                          </span>
                        </div>
                        <p style={{ margin: 0, fontSize: "0.9rem", color: "#102e26", lineHeight: 1.45 }}>
                          {q.content.length > 220 ? `${q.content.slice(0, 220)}...` : q.content}
                        </p>
                      </div>
                      {q.status !== "APPROVED" && (
                        <button
                          type="button"
                          className={styles.btnPrimary}
                          onClick={() => void handleApproveQuestion(q.id)}
                          disabled={formBusy}
                          style={{ padding: "6px 12px", fontSize: "0.8rem" }}
                        >
                          <CheckCircle2 size={14} /> Phê duyệt
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 3: AI GOVERNANCE & OBSERVABILITY */}
        {tab === "ai-governance" && (
          <div className={styles.tabContentWrap}>
            <div className={styles.sectionCard}>
              <div className={styles.sectionCardHeader}>
                <div>
                  <h3 className={styles.sectionHeading}>Tổng hợp Lưu lượng &amp; Chi phí AI theo Tác vụ</h3>
                  <p className={styles.sectionSubheading}>
                    GET /admin/ai/usage/summary — Theo dõi tần suất gọi, độ trễ trung bình, lượng token và tỷ lệ lỗi của từng loại tác vụ sư phạm
                  </p>
                </div>
              </div>

              {!aiSummary || aiSummary.requests_per_task.length === 0 ? (
                <div className={styles.emptyCard}>
                  <Cpu size={32} className={styles.emptyIcon} />
                  <h4 className={styles.emptyTitle}>Chưa có nhật ký thực thi AI</h4>
                  <p className={styles.emptyDesc}>
                    Khi hệ thống thực hiện các tác vụ AI (Gia sư, Tổng kết phụ huynh, Chấm bước giải...), số liệu sẽ được ghi nhận tại đây.
                  </p>
                </div>
              ) : (
                <div className={styles.chaptersGridModern}>
                  {aiSummary.requests_per_task.map((metric) => (
                    <div key={metric.task} className={styles.chapterCardModern}>
                      <div className={styles.chapterCardTop}>
                        <span className={styles.chapterSubjectPill}>{metric.task}</span>
                        <span className={styles.chapterProficientText}>
                          <strong>{metric.requests}</strong> lượt gọi
                        </span>
                      </div>
                      <div style={{ display: "grid", gap: "4px", fontSize: "0.84rem", color: "#52675d", marginTop: "6px" }}>
                        <div>
                          Thành công: <strong>{metric.successful_requests}</strong> · Lỗi:{" "}
                          <strong>{metric.failed_requests}</strong> ({(metric.failure_rate * 100).toFixed(1)}%)
                        </div>
                        <div>
                          Độ trễ TB: <strong>{Math.round(metric.average_latency_ms)} ms</strong>
                        </div>
                        <div>
                          Tổng Tokens: <strong>{metric.total_tokens.toLocaleString()}</strong> · Chi phí ước tính:{" "}
                          <strong>${metric.estimated_cost.toFixed(4)}</strong>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Recent AI Execution Logs */}
            <div className={styles.sectionCard}>
              <div className={styles.sectionCardHeader}>
                <div>
                  <h3 className={styles.sectionHeading}>
                    Nhật ký Truy vết AI Gần đây ({aiLogs?.total ?? 0} bản ghi)
                  </h3>
                  <p className={styles.sectionSubheading}>GET /admin/ai/usage</p>
                </div>
              </div>

              {!aiLogs || aiLogs.items.length === 0 ? (
                <p style={{ fontSize: "0.86rem", color: "#647b70" }}>Chưa có bản ghi log AI nào.</p>
              ) : (
                <div style={{ display: "grid", gap: "8px" }}>
                  {aiLogs.items.map((log) => (
                    <div
                      key={log.id}
                      style={{
                        padding: "10px 14px",
                        borderRadius: "12px",
                        background: "#ffffff",
                        border: "1px solid rgba(40,105,85,0.16)",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        flexWrap: "wrap",
                        gap: "8px",
                      }}
                    >
                      <div>
                        <strong style={{ fontSize: "0.88rem", color: "#102e26" }}>
                          {log.task} · {log.provider}/{log.model}
                        </strong>
                        <div style={{ fontSize: "0.76rem", color: "#52675d" }}>
                          Prompt: {log.prompt_name} ({log.prompt_version}) · Độ trễ: {Math.round(log.latency_ms)} ms ·{" "}
                          {new Date(log.created_at).toLocaleString("vi-VN")}
                        </div>
                      </div>
                      <span
                        className={log.success ? styles.studentTotalPill : styles.badgeAlertCount}
                      >
                        {log.success ? "SUCCESS" : log.error_type || "FAILED"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* TAB 4: UNIVERSITY ADMISSION GOVERNANCE */}
        {tab === "admission" && (
          <div className={styles.tabContentWrap}>
            {/* Create University Form */}
            <form onSubmit={(e) => void handleCreateUniversity(e)} className={styles.sectionCard}>
              <div className={styles.sectionCardHeader}>
                <div>
                  <h3 className={styles.sectionHeading}>Thêm Trường Đại học vào Danh mục Tuyển sinh</h3>
                  <p className={styles.sectionSubheading}>POST /admission/universities</p>
                </div>
              </div>
              <div style={{ display: "grid", gap: "10px", gridTemplateColumns: "1fr 2fr 1fr auto" }}>
                <input
                  type="text"
                  placeholder="Mã trường (VD: BKHN)"
                  value={newUniCode}
                  onChange={(e) => setNewUniCode(e.target.value)}
                  required
                  style={{ padding: "8px 12px", borderRadius: "10px", border: "1px solid rgba(40,105,85,0.25)" }}
                />
                <input
                  type="text"
                  placeholder="Tên trường đại học"
                  value={newUniName}
                  onChange={(e) => setNewUniName(e.target.value)}
                  required
                  style={{ padding: "8px 12px", borderRadius: "10px", border: "1px solid rgba(40,105,85,0.25)" }}
                />
                <select
                  value={newUniRegion}
                  onChange={(e) => setNewUniRegion(e.target.value)}
                  style={{ padding: "8px 12px", borderRadius: "10px", border: "1px solid rgba(40,105,85,0.25)" }}
                >
                  <option value="MIEN_BAC">Miền Bắc</option>
                  <option value="MIEN_TRUNG">Miền Trung</option>
                  <option value="MIEN_NAM">Miền Nam</option>
                </select>
                <button type="submit" className={styles.btnPrimary} disabled={formBusy}>
                  <Plus size={15} /> Thêm trường
                </button>
              </div>
            </form>

            {/* Universities & Majors Explorer */}
            <div className={styles.sectionCard}>
              <div className={styles.sectionCardHeader}>
                <div>
                  <h3 className={styles.sectionHeading}>
                    Danh mục Trường Đại học, Ngành &amp; Quy chế Tuyển sinh
                  </h3>
                  <p className={styles.sectionSubheading}>
                    Dữ liệu tuyển sinh được phiên bản hóa theo năm và kiểm chứng nguồn chính thống
                  </p>
                </div>
              </div>

              {universities.length === 0 ? (
                <div className={styles.emptyCard}>
                  <GraduationCap size={32} className={styles.emptyIcon} />
                  <h4 className={styles.emptyTitle}>Chưa có trường đại học nào trong danh mục</h4>
                </div>
              ) : (
                <>
                  <div className={styles.classCardGrid}>
                    {universities.map((uni) => {
                      const active = uni.id === selectedUniversityId;
                      return (
                        <div
                          key={uni.id}
                          className={`${styles.classRoomCard} ${active ? styles.classRoomCardActive : ""}`}
                          onClick={() => setSelectedUniversityId(uni.id)}
                          role="button"
                          tabIndex={0}
                        >
                          <div className={styles.classRoomCardTop}>
                            <span className={styles.classGradeBadge}>{uni.code}</span>
                            <span className={styles.classYearBadge}>{uni.region ?? "Toàn quốc"}</span>
                          </div>
                          <h4 className={styles.classRoomName}>{uni.name}</h4>
                          <div className={styles.classRoomFooter}>
                            <span>{uni.majors_count} ngành đào tạo</span>
                            <span>{uni.is_active ? "Đang hoạt động" : "Tạm ẩn"}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {/* Majors & Rules of Selected University */}
                  {majors.length > 0 && (
                    <div style={{ marginTop: "1.25rem", display: "grid", gap: "1rem" }}>
                      <div style={{ display: "flex", gap: "8px", flexWrap: "wrap", alignItems: "center" }}>
                        <strong style={{ fontSize: "0.88rem" }}>Ngành đào tạo:</strong>
                        {majors.map((m) => (
                          <button
                            key={m.id}
                            type="button"
                            onClick={() => setSelectedMajorId(m.id)}
                            className={m.id === selectedMajorId ? styles.btnPrimary : styles.btnSecondary}
                            style={{ padding: "5px 12px", fontSize: "0.8rem" }}
                          >
                            [{m.code}] {m.name}
                          </button>
                        ))}
                      </div>

                      {majorRules.length > 0 && (
                        <div className={styles.chaptersGridModern}>
                          {majorRules.map((rule) => (
                            <div key={rule.id} className={styles.chapterCardModern}>
                              <div className={styles.chapterCardTop}>
                                <span className={styles.chapterSubjectPill}>Năm {rule.year}</span>
                                <span className={styles.chapterProficientText}>
                                  Tổ hợp: <strong>{rule.subject_combination}</strong>
                                </span>
                              </div>
                              <h4 className={styles.chapterCardTitle}>
                                {rule.method_name || rule.method_code}
                              </h4>
                              <div style={{ fontSize: "0.84rem", color: "#52675d", marginTop: "6px" }}>
                                Điểm chuẩn tham khảo:{" "}
                                <strong>{rule.historical_score ?? "—"}</strong> · Chỉ tiêu:{" "}
                                <strong>{rule.quota ?? "—"}</strong>
                              </div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>

            {/* Admission Import History */}
            <div className={styles.sectionCard}>
              <div className={styles.sectionCardHeader}>
                <div>
                  <h3 className={styles.sectionHeading}>
                    Lịch sử Import Dữ liệu Tuyển sinh ({importHistory.length})
                  </h3>
                  <p className={styles.sectionSubheading}>GET /admission/import/history</p>
                </div>
              </div>
              {importHistory.length === 0 ? (
                <p style={{ fontSize: "0.86rem", color: "#647b70" }}>Chưa có lịch sử import tuyển sinh.</p>
              ) : (
                <div style={{ display: "grid", gap: "8px" }}>
                  {importHistory.map((item) => (
                    <div
                      key={item.id}
                      style={{
                        padding: "10px 14px",
                        borderRadius: "12px",
                        background: "#ffffff",
                        border: "1px solid rgba(40,105,85,0.16)",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <div>
                        <strong style={{ fontSize: "0.88rem", color: "#102e26" }}>
                          {item.file_name} ({item.file_format})
                        </strong>
                        <div style={{ fontSize: "0.76rem", color: "#52675d" }}>
                          Tổng: {item.total_rows} dòng · Đã nạp: {item.imported_rows} · Cập nhật: {item.updated_rows} · Lỗi: {item.error_rows}
                        </div>
                      </div>
                      <span className={styles.studentTotalPill}>{item.status}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </main>

      <AppFooter variant="default" />
    </div>
  );
}
