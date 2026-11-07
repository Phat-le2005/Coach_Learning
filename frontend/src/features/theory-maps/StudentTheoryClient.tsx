"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { theoryApi, type TheoryMap, type TheorySummary } from "./api";
import { TheoryMapView } from "./TheoryMapView";
import { TheoryNotebookView } from "./TheoryNotebookView";
import { TheorySourceViewer } from "./TheorySourceViewer";
import styles from "./TheoryMaps.module.css";

export function StudentTheoryClient() {
  const [list, setList] = useState<TheorySummary[]>([]);
  const [document, setDocument] = useState<TheoryMap | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState("");
  const [page, setPage] = useState(1);
  const [notebookPage, setNotebookPage] = useState<number | undefined>(undefined);
  const [view, setView] = useState<"map" | "notebook" | "source">("map");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    theoryApi
      .studentList()
      .then(async (items) => {
        if (!active) return;
        setList(items);
        if (!items.length) return;
        // Check query params (?topic=... or ?node=...)
        let targetDoc = items[0];
        let targetNodeId = "";
        try {
          const urlParams = new URLSearchParams(window.location.search);
          const rawTopic = urlParams.get("topic")?.toLowerCase().trim();
          const rawNode = urlParams.get("node")?.trim();

          if (rawTopic) {
            const matchedDoc = items.find((doc) =>
              doc.title.toLowerCase().includes(rawTopic) || rawTopic.includes(doc.title.toLowerCase())
            );
            if (matchedDoc) targetDoc = matchedDoc;
          }

          const docData = await theoryApi.studentGet(targetDoc.id);
          if (rawNode) {
            const nodeMatch = docData.nodes.find((n) => n.id === rawNode);
            if (nodeMatch) targetNodeId = nodeMatch.id;
          } else if (rawTopic) {
            const nodeMatch = docData.nodes.find((n) =>
              n.title.toLowerCase().includes(rawTopic) || rawTopic.includes(n.title.toLowerCase())
            );
            if (nodeMatch) targetNodeId = nodeMatch.id;
          }

          if (active) {
            setDocument(docData);
            setPage(1);
            setSelectedNodeId(targetNodeId || (docData.nodes[0]?.id ?? ""));
            setView(docData.nodes.length > 0 && docData.status === "PUBLISHED" ? "map" : "source");
            return;
          }
        } catch {
          // fallback to first document
        }

        const first = await theoryApi.studentGet(items[0].id);
        if (active) {
          setDocument(first);
          setPage(1);
          setSelectedNodeId(first.nodes[0]?.id ?? "");
          setView(first.nodes.length > 0 && first.status === "PUBLISHED" ? "map" : "source");
        }
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Không thể tải kho lý thuyết.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  async function openDocument(id: string) {
    setError("");
    try {
      const next = await theoryApi.studentGet(id);
      setDocument(next);
      setPage(1);
      setSelectedNodeId(next.nodes[0]?.id ?? "");
      setView(next.nodes.length > 0 && next.status === "PUBLISHED" ? "map" : "source");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Không thể mở tài liệu.");
    }
  }

  // Calculate quick metrics for the student header
  const stats = useMemo(() => {
    if (!document || !document.nodes) return { topicsCount: 0, formulasCount: 0 };
    const topicsCount = document.nodes.filter(
      (n) => n.kind === "CONCEPT" || /^Dạng\s+/i.test(n.title)
    ).length;
    const formulasCount = document.nodes.filter(
      (n) => n.kind === "FORMULA" || Boolean(n.latex)
    ).length;
    return { topicsCount, formulasCount };
  }, [document]);

  const outline = document?.source_outline ?? [];

  return (
    <div className={styles.studentAppContainer}>
      {/* 1. COMPACT, BEAUTIFUL APP HEADER */}
      <header className={styles.studentTopBar}>
        {/* Left: Back Link & Document Selector */}
        <div className={styles.studentNavLeft}>
          <Link href="/student" className={styles.studentBackLink} title="Quay lại không gian học tập">
            <span>←</span>
            <span>Khu vườn học tập</span>
          </Link>

          <div className={styles.studentNavDivider} />

          {list.length > 1 ? (
            <div className={styles.studentDocSwitcher}>
              <span className={styles.studentDocIcon} aria-hidden="true">
                📚
              </span>
              <select
                value={document?.id ?? ""}
                onChange={(e) => void openDocument(e.target.value)}
                className={styles.studentDocSelect}
                aria-label="Chọn tài liệu bài học"
              >
                {list.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.title} ({item.page_count} trang)
                  </option>
                ))}
              </select>
            </div>
          ) : (
            <div className={styles.studentDocChip}>
              <span className={styles.studentDocIcon} aria-hidden="true">
                📚
              </span>
              <span className={styles.studentDocTitle}>
                {document?.title || "Kho lý thuyết Toán học"}
              </span>
              {document && (
                <span className={styles.studentDocCount}>{document.page_count} trang</span>
              )}
            </div>
          )}
        </div>

        {/* Center: Main View Tabs (Segmented control) */}
        {document && (
          <div className={styles.studentNavCenter}>
            <div className={styles.studentSegmentedTabs} role="tablist" aria-label="Chế độ học tập">
              {document.status === "PUBLISHED" && document.nodes.length > 0 && (
                <button
                  type="button"
                  className={`${styles.studentTabBtn} ${view === "map" ? styles.studentTabActive : ""}`}
                  onClick={() => setView("map")}
                  role="tab"
                  aria-selected={view === "map"}
                >
                  <span className={styles.studentTabIcon} aria-hidden="true">
                    🧠
                  </span>
                  <span>Sơ đồ tư duy</span>
                </button>
              )}
              {document.status === "PUBLISHED" && (
                <button
                  type="button"
                  className={`${styles.studentTabBtn} ${view === "notebook" ? styles.studentTabActive : ""}`}
                  onClick={() => setView("notebook")}
                  role="tab"
                  aria-selected={view === "notebook"}
                >
                  <span className={styles.studentTabIcon} aria-hidden="true">
                    📖
                  </span>
                  <span>Sổ tay bài học &amp; Dạng toán</span>
                </button>
              )}
              {document.source_available && (
                <button
                  type="button"
                  className={`${styles.studentTabBtn} ${view === "source" ? styles.studentTabActive : ""}`}
                  onClick={() => setView("source")}
                  role="tab"
                  aria-selected={view === "source"}
                >
                  <span className={styles.studentTabIcon} aria-hidden="true">
                    📄
                  </span>
                  <span>Tài liệu PDF gốc</span>
                </button>
              )}
            </div>
          </div>
        )}

        {/* Right: Topic & Formula Stats */}
        <div className={styles.studentNavRight}>
          {document && document.nodes.length > 0 && (
            <div className={styles.studentStatsPill} title="Thống kê tri thức chuyên đề">
              <span>🎯 {stats.topicsCount} dạng bài</span>
              <span>&bull;</span>
              <span>📐 {stats.formulasCount} công thức</span>
            </div>
          )}
        </div>
      </header>

      {/* 2. MAIN LEARNING CANVAS */}
      <main className={styles.studentMainStage}>
        {error && (
          <div className={styles.error} role="alert" style={{ marginBottom: "16px" }}>
            {error}{" "}
            <button
              type="button"
              className={styles.buttonSecondary}
              style={{ padding: "4px 10px", fontSize: "0.8rem", marginLeft: "8px" }}
              onClick={() => window.location.reload()}
            >
              Thử lại
            </button>
          </div>
        )}

        {loading && (
          <div className={styles.studentLoadingState} role="status">
            <div className={styles.studentSpinner} />
            <p>Đang tải sơ đồ tư duy và tri thức lớp học...</p>
          </div>
        )}

        {!loading && !error && list.length === 0 && (
          <div className={styles.studentEmptyState}>
            <div className={styles.studentEmptyIcon}>🌱</div>
            <h3>Chưa có tài liệu lý thuyết nào được chia sẻ</h3>
            <p>Thầy cô bộ môn sẽ sớm chia sẻ sơ đồ tư duy và chuyên đề bài giảng với lớp em nhé!</p>
            <Link href="/student" className={styles.studentBackLink}>
              ← Quay lại khu vườn học tập
            </Link>
          </div>
        )}

        {!loading && !error && document && (
          <>
            {/* VIEW 1: SƠ ĐỒ TƯ DUY TƯƠNG TÁC (TỎA TỪ TÂM / CÂY NGANG / 3D) */}
            {view === "map" && document.status === "PUBLISHED" && document.nodes.length > 0 && (
              <TheoryMapView
                key={document.id}
                nodes={document.nodes}
                selectedNodeId={selectedNodeId}
                onSelectNode={setSelectedNodeId}
                sourceUrl={document.source_available ? `/api/student/theory/${document.id}/source` : undefined}
                isTeacher={false}
                onOpenNotebook={(p) => {
                  setNotebookPage(p);
                  setView("notebook");
                }}
                onOpenSource={(p) => {
                  setPage(p);
                  setView("source");
                }}
              />
            )}

            {/* VIEW 2: SỔ TAY BÀI HỌC VÀ DẠNG TOÁN */}
            {view === "notebook" && (
              <TheoryNotebookView
                documentId={document.id}
                role="student"
                initialPage={notebookPage}
              />
            )}

            {/* VIEW 3: TÀI LIỆU PDF GỐC */}
            {view === "source" && document.source_available && (
              <div className={styles.studentSourceLayout}>
                {outline.length > 0 && (
                  <div className={styles.studyOutline} aria-label="Mục lục chủ đề">
                    {outline.map((node, index) => (
                      <button
                        key={`${node.source_page}:${index}`}
                        type="button"
                        onClick={() => setPage(node.source_page)}
                      >
                        {node.title}{" "}
                        <small>
                          {node.kind === "CHAPTER" ? "Chủ đề" : "Dạng bài"} · trang {node.source_page}
                        </small>
                      </button>
                    ))}
                  </div>
                )}

                <div className={styles.pageControls}>
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => setPage(page - 1)}
                  >
                    ← Trang trước
                  </button>
                  <label>
                    Đến trang{" "}
                    <input
                      type="number"
                      min={1}
                      max={document.page_count}
                      value={page}
                      onChange={(event) =>
                        setPage(
                          Math.max(
                            1,
                            Math.min(document.page_count, Number(event.target.value) || 1)
                          )
                        )
                      }
                    />
                    {" "}/ {document.page_count}
                  </label>
                  <button
                    type="button"
                    disabled={page >= document.page_count}
                    onClick={() => setPage(page + 1)}
                  >
                    Trang sau →
                  </button>
                </div>

                <TheorySourceViewer
                  key={document.id}
                  url={`/api/student/theory/${document.id}/source`}
                  title={document.title}
                  pageCount={document.page_count}
                  page={page}
                />
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
