"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { UploadCloud, FileText, ChevronDown, ChevronUp, Trash2, Ellipsis, Network, NotebookPen, Check, Send, Undo2, Lock, Save, AlertTriangle, Sparkles, Leaf, Pencil, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { teacherApi, type TeacherClassroom, type TeacherSubject } from "@/features/teacher/api";
import { theoryApi, type TheoryMap, type TheoryNode, type TheorySummary, type NodeKind } from "./api";
import { TheoryFormulaField } from "./TheoryFormulaField";
import { TheoryMapView } from "./TheoryMapView";
import { TheoryNotebookView } from "./TheoryNotebookView";
import { UploadTheoryModal } from "./components/UploadTheoryModal";
import styles from "./TheoryMaps.module.css";

const newId = () => `node_${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`;
const errorText = (error: unknown) => (error instanceof Error ? error.message : "Không thể thực hiện thao tác.");

function initialNodeId(nodes: TheoryNode[]): string {
  const root = nodes.find((node) => node.parent_id === null);
  if (nodes.length > 25) {
    return nodes.find((node) => /^Dạng\s+/i.test(node.title))?.id ?? nodes.find((node) => node.parent_id === root?.id)?.id ?? root?.id ?? "";
  }
  return root?.id ?? "";
}

function getKindBadgeClass(kind: NodeKind): string {
  switch (kind) {
    case "FORMULA": return styles.kindBadgeFormula;
    case "EXAMPLE": return styles.kindBadgeExample;
    case "NOTE": return styles.kindBadgeNote;
    case "CONCEPT": return styles.kindBadgeConcept;
    case "METHOD": return styles.kindBadgeConcept;
    case "QUICK_TRICK": return styles.kindBadgeFormula;
    default: return styles.kindBadgeDefault;
  }
}

function getKindLabel(kind: NodeKind): string {
  switch (kind) {
    case "ROOT": return "Gốc chuyên đề";
    case "SECTION": return "Chủ đề / Bài";
    case "CONCEPT": return "Khái niệm / Định lý";
    case "FORMULA": return "Công thức KaTeX";
    case "EXAMPLE": return "Dạng bài & Ví dụ";
    case "NOTE": return "Lưu ý & Bẫy lỗi";
    case "METHOD": return "Dạng toán & Phương pháp";
    case "QUICK_TRICK": return "Mẹo giải nhanh";
    default: return "Mục kiến thức";
  }
}

export interface TeacherTheoryClientProps {
  initialClassId?: string;
  onSelectClass?: (classId: string) => void;
  isEmbedded?: boolean;
}

export function TeacherTheoryClient({
  initialClassId,
  onSelectClass,
  isEmbedded = false,
}: TeacherTheoryClientProps = {}) {
  const [classes, setClasses] = useState<TeacherClassroom[]>([]);
  const [subjects, setSubjects] = useState<TeacherSubject[]>([]);
  const [classId, setClassId] = useState(initialClassId ?? "");
  const [subjectId, setSubjectId] = useState("");
  const [list, setList] = useState<TheorySummary[]>([]);
  const [map, setMap] = useState<TheoryMap | null>(null);
  const [nodes, setNodes] = useState<TheoryNode[]>([]);
  const [editingNodeId, setEditingNodeId] = useState("");
  const [selectedMapNode, setSelectedMapNode] = useState<string | undefined>();
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
  const [isBranchEditorCollapsed, setIsBranchEditorCollapsed] = useState(true);
  const [docViewMode, setDocViewMode] = useState<"map" | "notebook">("map");
  const [notebookPage, setNotebookPage] = useState<number | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => { setSelectedMapNode(undefined); }, [map?.id]);

  useEffect(() => {
    let active = true;
    Promise.all([teacherApi.classes(), teacherApi.subjects()])
      .then(([classrooms, items]) => {
        if (!active) return;
        setClasses(classrooms);
        setSubjects(items);
        const resolvedClassId =
          initialClassId && classrooms.some((item) => item.id === initialClassId)
            ? initialClassId
            : classrooms[0]?.id ?? "";
        setClassId((prev) => prev || resolvedClassId);
        const currentClass = classrooms.find((item) => item.id === resolvedClassId) ?? classrooms[0];
        const matches = items.filter((item) => item.grade_level === null || item.grade_level === currentClass?.grade_level);
        if (matches.length === 1) setSubjectId(matches[0].id);
      })
      .catch((reason) => {
        if (active) setError(errorText(reason));
      });
    return () => {
      active = false;
    };
  }, [initialClassId]);

  // Synchronize when initialClassId changes from parent (e.g. TeacherHeader dropdown)
  useEffect(() => {
    if (initialClassId && initialClassId !== classId) {
      setClassId(initialClassId);
      setSubjectId("");
    }
  }, [initialClassId]);

  useEffect(() => {
    if (!classId) return;
    let active = true;
    setMap(null);
    setNodes([]);
    setList([]);
    setEditingNodeId("");
    theoryApi
      .teacherList(classId)
      .then(async (items) => {
        if (!active) return;
        setList(items);
        if (!items.length) return;
        const first = await theoryApi.teacherGet(items[0].id);
        if (active) {
          setMap(first);
          setNodes(first.nodes);
          setEditingNodeId(initialNodeId(first.nodes));
        }
      })
      .catch((reason) => {
        if (active) setError(errorText(reason));
      });
    return () => {
      active = false;
    };
  }, [classId]);

  const selectedClass = classes.find((item) => item.id === classId);
  const eligibleSubjects = subjects.filter((item) => item.grade_level === null || item.grade_level === selectedClass?.grade_level);
  const dirty = map !== null && JSON.stringify(map.nodes) !== JSON.stringify(nodes);
  const editingIndex = Math.max(0, nodes.findIndex((item) => item.id === editingNodeId));
  const editingNode = nodes[editingIndex];
  const reviewedCount = nodes.filter((n) => n.reviewed).length;
  const allReviewed = nodes.length > 0 && reviewedCount === nodes.length;

  async function run(action: () => Promise<TheoryMap>, success: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await action();
      setMap(result);
      setNodes(result.nodes);
      setEditingNodeId((current) =>
        result.id === map?.id && result.nodes.some((node) => node.id === current) ? current : initialNodeId(result.nodes)
      );
      setList((old) => [result, ...old.filter((item) => item.id !== result.id)]);
      setNotice(success);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  async function handlePublish() {
    if (!map || busy || nodes.length === 0) return;

    let targetNodes = nodes;
    if (!allReviewed) {
      const confirmReview = window.confirm(
        `Tài liệu này có ${nodes.length - reviewedCount}/${nodes.length} nhánh chưa duyệt học thuật.\n\nBạn có muốn tự động xác nhận duyệt tất cả ${nodes.length} nhánh và phát hành ngay cho học sinh không?`
      );
      if (!confirmReview) return;
      targetNodes = nodes.map((n) => ({ ...n, reviewed: true }));
      setNodes(targetNodes);
    }

    const parentIds = new Set(targetNodes.map((n) => n.parent_id).filter(Boolean));
    targetNodes = targetNodes.map((n) => {
      if (
        n.kind !== "ROOT" &&
        !parentIds.has(n.id) &&
        !n.body.trim() &&
        !(n.latex || "").trim() &&
        (!n.learning_steps || n.learning_steps.length === 0)
      ) {
        return {
          ...n,
          body: `Xem nội dung kiến thức chi tiết tại trang ${n.source_page} của tài liệu PDF gốc.`,
        };
      }
      return n;
    });

    await run(async () => {
      let currentMap = map;
      currentMap = await theoryApi.save(currentMap, targetNodes);
      return await theoryApi.publish(currentMap);
    }, "Đã duyệt học thuật và phát hành Sơ đồ tư duy thành công cho học sinh trong lớp!");
  }

  async function handleDeleteDocument(target: TheorySummary | TheoryMap) {
    const isCurrent = map?.id === target.id;
    if (
      !window.confirm(
        `Bạn có chắc chắn muốn xóa tài liệu "${target.title}" không?\nThao tác này sẽ xóa vĩnh viễn tệp PDF và toàn bộ sơ đồ tư duy liên quan.`
      )
    ) {
      return;
    }
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await theoryApi.delete(target.id);
      const remaining = list.filter((item) => item.id !== target.id);
      setList(remaining);

      if (isCurrent) {
        if (remaining.length > 0) {
          const next = await theoryApi.teacherGet(remaining[0].id);
          setMap(next);
          setNodes(next.nodes);
          setEditingNodeId(initialNodeId(next.nodes));
        } else {
          setMap(null);
          setNodes([]);
          setEditingNodeId("");
        }
      }
      setNotice(`Đã xóa tài liệu "${target.title}" thành công.`);
    } catch (reason) {
      setError(errorText(reason));
    } finally {
      setBusy(false);
    }
  }

  function edit(index: number, patch: Partial<TheoryNode>) {
    setNodes((old) =>
      old.map((node, position) => (position === index ? { ...node, ...patch, reviewed: true } : node))
    );
  }

  function addNode() {
    const id = newId();
    const parent = editingNode?.id ?? nodes[0]?.id ?? null;
    setNodes((old) => [
      ...old,
      {
        id,
        parent_id: parent,
        kind: parent ? "CONCEPT" : "ROOT",
        title: parent ? "Nhánh mới" : map?.title ?? "Chủ đề",
        body: "",
        latex: null,
        learning_steps: [],
        source_page: editingNode?.source_page ?? 1,
        source_quote: editingNode?.source_quote || map?.title || "Trích dẫn nguồn",
        reviewed: true,
      },
    ]);
    setEditingNodeId(id);
  }

  function addChildNode(parentId: string) {
    const parentNode = nodes.find((n) => n.id === parentId);
    const id = newId();
    setNodes((old) => [
      ...old,
      {
        id,
        parent_id: parentId,
        kind: parentNode?.kind === "SECTION" ? "CONCEPT" : "FORMULA",
        title: parentNode?.kind === "SECTION" ? "Dạng toán mới" : "Công thức mới",
        body: "",
        latex: null,
        learning_steps: [],
        source_page: parentNode?.source_page ?? 1,
        source_quote: parentNode?.source_quote || map?.title || "Trích dẫn nguồn",
        reviewed: true,
      },
    ]);
    setEditingNodeId(id);
    setTimeout(() => {
      const editEl = document.getElementById("theory-node-editor");
      if (editEl) editEl.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 100);
  }

  function removeNode(id: string) {
    if (nodes.length <= 1) return;
    setNodes((old) => old.filter((node) => node.id !== id));
    setEditingNodeId(nodes[0]?.id ?? "");
  }

  function addStep() {
    if (!editingNode) return;
    const nextSteps = [
      ...editingNode.learning_steps,
      {
        instruction: `Bước ${editingNode.learning_steps.length + 1}: `,
        latex: null,
        source_page: editingNode.source_page,
        source_quote: null,
      },
    ];
    edit(editingIndex, { learning_steps: nextSteps });
  }

  function updateStep(index: number, patch: Partial<TheoryNode["learning_steps"][number]>) {
    if (!editingNode) return;
    edit(editingIndex, {
      learning_steps: editingNode.learning_steps.map((step, position) => (position === index ? { ...step, ...patch } : step)),
    });
  }

  function removeStep(index: number) {
    if (!editingNode) return;
    edit(editingIndex, {
      learning_steps: editingNode.learning_steps.filter((_, position) => position !== index),
    });
  }

  function moveStep(index: number, direction: -1 | 1) {
    if (!editingNode) return;
    const next = [...editingNode.learning_steps];
    const target = index + direction;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    edit(editingIndex, { learning_steps: next });
  }

  const RootTag = isEmbedded ? "div" : "main";

  return (
    <RootTag className={isEmbedded ? styles.embeddedRoot : styles.page}>
      <div className={`${styles.teacherWorkspace} ${isEmbedded ? styles.embeddedShell : styles.shell}`}>
        {!isEmbedded && (
          <header className={styles.header}>
            <div>
              <span className={styles.eyebrow}>EduMS · Không gian giáo viên</span>
              <h1 className={styles.title}>Kho tri thức · Sơ đồ tư duy Toán học</h1>
              <p className={styles.subtitle}>
                Tải tài liệu PDF bài giảng hoặc chuyên đề. AI Gemini sẽ tự động phân tích và kiến tạo Sơ đồ tư duy (Mindmap) sư phạm trực quan, công thức KaTeX chuẩn mực và phương pháp giải mẫu.
              </p>
            </div>
            <Link className={styles.link} href="/teacher">
              ← Về trang giáo viên
            </Link>
          </header>
        )}

        {error && <p className={styles.error} role="alert">{error}</p>}
        {notice && <p className={styles.notice} role="status">{notice}</p>}

        <div className={isSidebarCollapsed ? styles.columnsCollapsed : styles.columns}>
          {!isSidebarCollapsed && (
            <aside className={`${styles.panel} ${styles.documentSidebar}`} aria-label="Danh sách tài liệu lý thuyết">
              <div className={styles.sidebarHeaderRow}>
                <div className={styles.sidebarTitleGroup}>
                  <h2 className={styles.sidebarTitle}>Tài liệu lớp</h2>
                  <span className={styles.sidebarDocCount}>
                    {list.length} tài liệu PDF
                  </span>
                </div>
                <button
                  type="button"
                  className={styles.uploadTriggerBtn}
                  onClick={() => setIsUploadModalOpen(true)}
                  disabled={!classId || busy}
                  title="Tải lên tài liệu PDF mới cho lớp"
                >
                  <UploadCloud size={16} aria-hidden="true" />
                  <span>+ Tải PDF</span>
                </button>
              </div>

              {!isEmbedded && (
                <label className={styles.field}>
                  Lớp học
                  <select
                    className={styles.select}
                    value={classId}
                    onChange={(event) => {
                      const nextId = event.target.value;
                      setClassId(nextId);
                      setSubjectId("");
                      onSelectClass?.(nextId);
                    }}
                  >
                    {classes.length === 0 && <option value="">Chưa có lớp được phân công</option>}
                    {classes.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}

              <div className={styles.list}>
                {list.length === 0 ? (
                  <div className={styles.emptySidebarNotice}>
                    <FileText size={32} className={styles.emptySidebarIcon} aria-hidden="true" />
                    <p>Chưa có tài liệu nào cho lớp này.</p>
                    <button
                      type="button"
                      className={styles.emptyUploadBtn}
                      onClick={() => setIsUploadModalOpen(true)}
                      disabled={!classId || busy}
                    >
                      + Tải lên tài liệu PDF
                    </button>
                  </div>
                ) : (
                  list.map((item) => (
                    <div
                      key={item.id}
                      className={`${styles.listItemWrapper} ${map?.id === item.id ? styles.listItemWrapperActive : ""}`}
                    >
                      <button
                        className={styles.listButtonInner}
                        type="button"
                        aria-current={map?.id === item.id ? "true" : undefined}
                        onClick={() => {
                          if (dirty && !window.confirm("Bỏ các chỉnh sửa chưa lưu?")) return;
                          setError("");
                          setNotice("");
                          theoryApi
                            .teacherGet(item.id)
                            .then((result) => {
                              setMap(result);
                              setNodes(result.nodes);
                              setEditingNodeId(initialNodeId(result.nodes));
                            })
                            .catch((reason) => setError(errorText(reason)));
                        }}
                      >
                        <div className={styles.docItemRow}>
                          <div className={styles.docItemIconWrap}>
                            <FileText size={18} className={styles.docItemFileIcon} aria-hidden="true" />
                          </div>
                          <div className={styles.docItemMeta}>
                            <strong className={styles.docItemTitle} title={item.title}>
                              {item.title}
                            </strong>
                            <div className={styles.docItemBadges}>
                              <span className={styles.docItemPageBadge}>
                                {item.page_count} trang
                              </span>
                              <span className={item.status === "PUBLISHED" ? styles.docStatusPublished : styles.docStatusDraft}>
                                {item.status === "PUBLISHED" ? <><Send size={13} aria-hidden="true" />Đã phát hành</> : <><FileText size={13} aria-hidden="true" />Bản nháp</>}
                              </span>
                            </div>
                          </div>
                        </div>
                      </button>
                      <button
                        type="button"
                        className={styles.deleteDocIconBtn}
                        title={`Xóa tài liệu "${item.title}"`}
                        aria-label={`Xóa tài liệu ${item.title}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleDeleteDocument(item);
                        }}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </aside>
          )}

          <section className={styles.panel}>
            {!map ? (
              <div className={styles.emptyStateCard}>
                <div className={styles.emptyStateIcon}><FileText size={24} aria-hidden="true" /></div>
                <h3>Chưa chọn tài liệu</h3>
                <p>
                  Vui lòng chọn một tài liệu từ danh sách bên trái để khám phá Sơ đồ tư duy, hoặc bấm nút &ldquo;+ Tải PDF&rdquo; để thêm tài liệu mới cho lớp.
                </p>
                <button
                  className={styles.button}
                  type="button"
                  onClick={() => setIsUploadModalOpen(true)}
                  disabled={!classId || busy}
                >
                  <UploadCloud size={16} aria-hidden="true" />
                  + Tải lên PDF bài học
                </button>
              </div>
            ) : (
              <>
                <div className={styles.documentHeaderBar}>
                  <div className={styles.documentHeaderInfo}>
                    <h2>{map.title}</h2>
                    <div className={styles.badges}>
                      {map.status === "PUBLISHED" ? (
                        <span className={styles.badgeSuccess}><><Send size={13} aria-hidden="true" /> Đã phát hành</> cho lớp</span>
                      ) : (
                        <span className={styles.badgeMuted}><FileText size={13} aria-hidden="true" />Bản nháp</span>
                      )}
                      {map.ai_model === "gemini" && <span className={styles.badgeAi}><><Sparkles size={13} aria-hidden="true" /> AI Gemini</></span>}
                      {map.ai_model === "local_heuristic" && <span className={styles.badgeMuted}><><Leaf size={13} aria-hidden="true" /> Dàn ý cục bộ</></span>}
                      {nodes.length > 0 && (
                        <span className={allReviewed ? styles.badgeSuccess : styles.badgeWarning}>
                          {allReviewed ? "Đã duyệt tất cả nhánh" : `Đã duyệt ${reviewedCount}/${nodes.length} nhánh`}
                        </span>
                      )}
                      <span className={styles.badgeMuted}>{nodes.length} nhánh tri thức</span>
                      <span className={styles.badgeMuted}>{map.page_count} trang PDF</span>
                      {map.extraction_warning_pages && map.extraction_warning_pages.length > 0 && (
                        <span
                          className={styles.badgeWarning}
                          title={`Các trang có font/ký hiệu toán học cần kiểm tra mắt: trang ${map.extraction_warning_pages.join(", ")}`}
                        >
                          <AlertTriangle size={13} aria-hidden="true" />{map.extraction_warning_pages.length} trang có font toán cần đối chiếu
                        </span>
                      )}
                      {map.source_available ? (
                        <span className={styles.badgeInfo}><><FileText size={13} aria-hidden="true" /> PDF đang chia sẻ</></span>
                      ) : (
                        <span className={styles.badgeMuted}><><Lock size={13} aria-hidden="true" /> PDF chưa chia sẻ</></span>
                      )}
                    </div>
                  </div>

                  <div className={styles.toolbarGroup}>
                    {/* Academic Review All Button */}
                    {map.status !== "PUBLISHED" && nodes.length > 0 && (
                      <button
                        className={styles.buttonReviewAll}
                        type="button"
                        disabled={busy}
                        onClick={() => {
                          if (allReviewed) {
                            if (window.confirm("Bỏ đánh dấu duyệt của tất cả các nhánh để kiểm tra lại?")) {
                              setNodes((current) => current.map((n) => ({ ...n, reviewed: false })));
                            }
                          } else {
                            if (
                              window.confirm(
                                `Xác nhận bạn đã kiểm tra và rà soát tính chính xác học thuật của toàn bộ ${nodes.length} nhánh trong tài liệu này?`
                              )
                            ) {
                              setNodes((current) => current.map((n) => ({ ...n, reviewed: true })));
                            }
                          }
                        }}
                        title={allReviewed ? "Nhấn để hủy duyệt học thuật toàn bộ" : "Duyệt học thuật tất cả nhánh sau khi đã rà soát"}
                      >
                        <Check size={15} aria-hidden="true" /> {allReviewed ? "Đã duyệt học thuật (100%)" : `Duyệt tất cả nhánh (${reviewedCount}/${nodes.length})`}
                      </button>
                    )}

                    {/* Primary Publish / Unpublish */}
                    {map.status !== "PUBLISHED" ? (
                      <button
                        className={styles.buttonPublish}
                        type="button"
                        disabled={busy || nodes.length === 0}
                        onClick={() => void handlePublish()}
                        title={!allReviewed ? `Cần duyệt tất cả các nhánh học thuật trước khi phát hành (${reviewedCount}/${nodes.length} đã duyệt) - Bấm để duyệt & phát hành` : "Phát hành tài liệu cho học sinh"}
                      >
                        <Send size={15} aria-hidden="true" />Phát hành cho học sinh
                      </button>
                    ) : (
                      <button
                        className={styles.buttonUnpublish}
                        type="button"
                        disabled={busy}
                        onClick={() => void run(() => theoryApi.unpublish(map), "Đã hủy phát hành sơ đồ về bản nháp.")}
                      >
                        <Undo2 size={15} aria-hidden="true" /> Hủy phát hành
                      </button>
                    )}

                    {/* Save Changes - ONLY displayed when dirty! */}
                    {dirty && (
                      <button
                        className={styles.buttonSave}
                        type="button"
                        disabled={busy}
                        onClick={() => void run(() => theoryApi.save(map, nodes), "Đã lưu các chỉnh sửa của sơ đồ.")}
                        title="Bạn có chỉnh sửa chưa lưu"
                      >
                        <Save size={15} aria-hidden="true" /> Lưu thay đổi
                      </button>
                    )}

                    <details className={styles.teacherDocumentOptions} onKeyDown={event => { if (event.key === "Escape") { event.currentTarget.open = false; event.currentTarget.querySelector("summary")?.focus(); } }}>
                      <summary><Ellipsis size={16} aria-hidden="true" />Tùy chọn tài liệu</summary><div>
                    {/* Share PDF Toggle */}
                    <button
                      className={`${styles.button} ${styles.buttonSecondary}`}
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void run(
                          () => theoryApi.setSourceVisibility(map, !map.source_available),
                          map.source_available ? "Đã khóa tệp PDF gốc với học sinh." : "Đã mở chia sẻ tệp PDF gốc cho học sinh."
                        )
                      }
                      title={map.source_available ? "Bấm để tắt chia sẻ file PDF cho học sinh" : "Bấm để học sinh có thể xem file PDF gốc"}
                    >
                      {map.source_available ? <><Lock size={15} aria-hidden="true" />Khóa PDF gốc</> : <><FileText size={15} aria-hidden="true" />Chia sẻ PDF cho lớp</>}
                    </button>

                    {/* Delete Document Button */}
                    <button
                      className={styles.buttonDanger}
                      type="button"
                      disabled={busy}
                      onClick={() => void handleDeleteDocument(map)}
                      title="Xóa tài liệu và toàn bộ sơ đồ tư duy này"
                    >
                      <Trash2 size={15} aria-hidden="true" /> Xóa tài liệu
                    </button>

                      </div>
                    </details>
                    {/* Sidebar Toggle */}
                    <button
                      type="button"
                      className={styles.sidebarToggleBtn}
                      onClick={() => setIsSidebarCollapsed((prev) => !prev)}
                      title={isSidebarCollapsed ? "Hiện danh sách tài liệu bên trái" : "Thu gọn danh sách để mở rộng 100% không gian"}
                    >
                      {isSidebarCollapsed ? <><PanelLeftOpen size={15} aria-hidden="true" />Danh sách tài liệu</> : <><PanelLeftClose size={15} aria-hidden="true" />Thu gọn danh sách</>}
                    </button>
                  </div>
                </div>

                <div className={styles.studyToolbar}>
                  <button
                    type="button"
                    className={docViewMode === "map" ? styles.studyTabActive : styles.studyTab}
                    onClick={() => setDocViewMode("map")}
                  >
                    <Network size={16} aria-hidden="true" /> Sơ đồ tư duy
                  </button>
                  <button
                    type="button"
                    className={docViewMode === "notebook" ? styles.studyTabActive : styles.studyTab}
                    onClick={() => setDocViewMode("notebook")}
                  >
                    <NotebookPen size={16} aria-hidden="true" /> Sổ tay bài học
                  </button>
                </div>

                {docViewMode === "notebook" ? (
                  <TheoryNotebookView
                    documentId={map.id}
                    role="teacher"
                    initialPage={notebookPage}
                  />
                ) : nodes.length === 0 ? (
                  <div className={styles.emptyStateCard}>
                    <div className={styles.emptyStateIcon}><Network size={28} aria-hidden="true" /></div>
                    <h3>Chưa có sơ đồ tư duy cho tài liệu này</h3>
                    <p>
                      Tạo bản nháp sơ đồ từ PDF, sau đó kiểm tra từng nhánh trước khi phát hành cho lớp.
                    </p>
                    <button
                      className={styles.buttonAi}
                      type="button"
                      disabled={busy}
                      onClick={async () => {
                        setBusy(true);
                        setError("");
                        setNotice("");
                        try {
                          const result = await theoryApi.generate(map.id);
                          setMap(result);
                          setNodes(result.nodes);
                          setEditingNodeId(initialNodeId(result.nodes));
                          setList((old) => [result, ...old.filter((item) => item.id !== result.id)]);
                          if (result.ai_model === "gemini") {
                            setNotice("AI Gemini đã phân tích tài liệu và tạo sơ đồ tư duy.");
                          } else {
                            setNotice("Đã khởi tạo cấu trúc Sơ đồ tư duy từ văn bản PDF cục bộ (AI Gemini tạm thời không phản hồi).");
                          }
                        } catch (reason) {
                          setError(errorText(reason));
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      <Sparkles size={15} aria-hidden="true" />{busy ? "Đang xử lý PDF với AI..." : "Tạo sơ đồ tư duy bằng AI"}
                    </button>
                  </div>
                ) : (
                  <>
                    <TheoryMapView
                      key={map.id}
                      nodes={nodes}
                      selectedNodeId={selectedMapNode}
                      onSelectNode={id => { setEditingNodeId(id); setSelectedMapNode(id); }}
                      sourceUrl={`/api/teacher/theory/${map.id}/source`}
                      sourceTitle={map.title}
                      sourcePageCount={map.page_count}
                      initialSourcePage={editingNode?.source_page ?? 1}
                      onEditNode={(id) => {
                        setEditingNodeId(id);
                        setIsBranchEditorCollapsed(false);
                        const editEl = document.getElementById("theory-node-editor");
                        if (editEl) editEl.scrollIntoView({ behavior: "smooth", block: "start" });
                      }}
                      onAddChildNode={(parentId) => {
                        addChildNode(parentId);
                      }}
                      onDeleteNode={(id) => {
                        removeNode(id);
                      }}
                      onOpenNotebook={(page) => {
                        setNotebookPage(page);
                        setDocViewMode("notebook");
                      }}
                      isTeacher={true}
                    />

                    {editingNode && (
                      <div
                        id="theory-node-editor"
                        className={`${styles.quickEditCard} ${isBranchEditorCollapsed ? styles.quickEditCardCollapsed : ""}`}
                      >
                        <div className={styles.quickEditHeader}>
                          <div className={styles.quickEditTitleRow}>
                            <h3>Chỉnh sửa nhánh: &ldquo;{editingNode.title}&rdquo;</h3>
                            <span className={`${styles.kindBadge} ${getKindBadgeClass(editingNode.kind)}`}>
                              {getKindLabel(editingNode.kind)}
                            </span>
                            <button
                              type="button"
                              className={editingNode.reviewed ? styles.approvedNodePill : styles.unapprovedNodePill}
                              onClick={() => edit(editingIndex, { reviewed: !editingNode.reviewed })}
                              title="Nhấn để đổi trạng thái duyệt học thuật của nhánh này"
                            >
                              {editingNode.reviewed ? <><Check size={13} aria-hidden="true" />Đã duyệt nhánh này</> : <><AlertTriangle size={13} aria-hidden="true" />Chưa duyệt (Bấm để duyệt)</>}
                            </button>
                            <span className={styles.small}>
                              Nhánh {editingIndex + 1}/{nodes.length}
                            </span>
                          </div>

                          <div className={styles.toolbarGroup}>
                            {editingNode.kind !== "ROOT" && (
                              <button
                                className={styles.deleteBranchBtn}
                                type="button"
                                onClick={() => removeNode(editingNode.id)}
                                title="Xóa nhánh này khỏi sơ đồ"
                              >
                                <Trash2 size={13} aria-hidden="true" />
                                Xóa nhánh
                              </button>
                            )}

                            <button
                              type="button"
                              className={styles.toggleBranchEditorBtn}
                              onClick={() => setIsBranchEditorCollapsed((prev) => !prev)}
                              title={isBranchEditorCollapsed ? "Mở rộng để chỉnh sửa công thức KaTeX & các bước giải" : "Thu gọn phần tinh chỉnh nhánh"}
                            >
                              {isBranchEditorCollapsed ? (
                                <>
                                  <ChevronDown size={14} aria-hidden="true" />
                                  Mở rộng tinh chỉnh
                                </>
                              ) : (
                                <>
                                  <ChevronUp size={14} aria-hidden="true" />
                                  Thu gọn
                                </>
                              )}
                            </button>
                          </div>
                        </div>

                        {isBranchEditorCollapsed ? (
                          <p className={styles.collapsedHint}>
                            Nhánh đang chọn: <strong>{editingNode.title}</strong> ({getKindLabel(editingNode.kind)}). Bấm <em>&ldquo;Mở rộng tinh chỉnh&rdquo;</em> để sửa tiêu đề, công thức LaTeX và các bước giải mẫu.
                          </p>
                        ) : (
                          <>
                            <div className={styles.editGrid}>
                              <label className={styles.field}>
                                Tiêu đề nhánh
                                <input
                                  className={styles.input}
                                  value={editingNode.title}
                                  onChange={(event) => edit(editingIndex, { title: event.target.value })}
                                  maxLength={250}
                                />
                              </label>

                              <label className={styles.field}>
                                Loại nhánh
                                <select
                                  className={styles.select}
                                  value={editingNode.kind}
                                  onChange={(event) => edit(editingIndex, { kind: event.target.value as NodeKind })}
                                >
                                  <option value="ROOT">Nút gốc (ROOT)</option>
                                  <option value="SECTION">Chủ đề lớn (SECTION)</option>
                                  <option value="CONCEPT">Khái niệm / Định lý (CONCEPT)</option>
                                  <option value="FORMULA">Công thức trọng tâm (FORMULA)</option>
                                  <option value="EXAMPLE">Dạng bài tập / Ví dụ (EXAMPLE)</option>
                                  <option value="NOTE">Lưu ý / Bẫy sai lầm (NOTE)</option>
                                </select>
                              </label>
                            </div>

                            <label className={styles.field}>
                              Nội dung tóm tắt / Điều cần hiểu
                              <textarea
                                className={styles.textarea}
                                value={editingNode.body}
                                onChange={(event) => edit(editingIndex, { body: event.target.value })}
                                placeholder="Tóm tắt ngắn gọn khái niệm, định lý hoặc bản chất toán học..."
                              />
                            </label>

                            <TheoryFormulaField
                              label="Công thức LaTeX (nếu có)"
                              value={editingNode.latex ?? ""}
                              onChange={(val) => edit(editingIndex, { latex: val.trim() ? val : null })}
                            />

                            <div className={styles.stepEditor}>
                              <div className={styles.stepHeader}>
                                <div>
                                  <h4>Các bước phương pháp giải / Ví dụ mẫu</h4>
                                  <p>Thêm các bước giải bài tập cụ thể giúp học sinh dễ nhớ và vận dụng.</p>
                                </div>
                                <button className={`${styles.button} ${styles.buttonSecondary}`} type="button" onClick={addStep}>
                                  + Thêm bước giải
                                </button>
                              </div>

                              {editingNode.learning_steps.map((step, sIdx) => (
                                <div key={sIdx} className={styles.stepCard}>
                                  <div className={styles.stepHeader}>
                                    <strong>Bước {sIdx + 1}</strong>
                                    <div className={styles.stepControls}>
                                      <button type="button" disabled={sIdx === 0} onClick={() => moveStep(sIdx, -1)}>
                                        ↑
                                      </button>
                                      <button
                                        type="button"
                                        disabled={sIdx === editingNode.learning_steps.length - 1}
                                        onClick={() => moveStep(sIdx, 1)}
                                      >
                                        ↓
                                      </button>
                                      <button type="button" onClick={() => removeStep(sIdx)}>
                                        <Trash2 size={13} aria-hidden="true" />Xóa
                                      </button>
                                    </div>
                                  </div>
                                  <label className={styles.field}>
                                    Hướng dẫn thực hiện
                                    <input
                                      className={styles.input}
                                      value={step.instruction}
                                      onChange={(event) => updateStep(sIdx, { instruction: event.target.value })}
                                      placeholder="Ví dụ: Tính đạo hàm y' và giải phương trình y' = 0"
                                    />
                                  </label>
                                  <label className={styles.field}>
                                    Công thức LaTeX ở bước này (tùy chọn)
                                    <input
                                      className={styles.input}
                                      value={step.latex ?? ""}
                                      onChange={(event) =>
                                        updateStep(sIdx, { latex: event.target.value.trim() ? event.target.value : null })
                                      }
                                      placeholder="Ví dụ: f'(x) = 3x^2 - 6x"
                                    />
                                  </label>
                                </div>
                              ))}
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </section>
            </div>
          </div>

          <UploadTheoryModal
            isOpen={isUploadModalOpen}
            onClose={() => setIsUploadModalOpen(false)}
            classNameTitle={selectedClass?.name}
            eligibleSubjects={eligibleSubjects}
            onUpload={async (subId, docTitle, docFile) => {
              await run(
                () => theoryApi.upload(classId, subId, docTitle, docFile),
                "Đã tải lên tài liệu PDF thành công. Hãy bấm Tạo sơ đồ AI để tạo bản đồ tri thức!"
              );
            }}
            isBusy={busy}
          />
        </RootTag>
      );
    }
