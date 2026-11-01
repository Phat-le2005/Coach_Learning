"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
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
  const [view, setView] = useState<"map" | "notebook" | "source">("map");
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    theoryApi.studentList().then(async (items) => {
      if (!active) return;
      setList(items);
      if (!items.length) return;
      const first = await theoryApi.studentGet(items[0].id);
      if (active) {
        setDocument(first);
        setPage(1);
        setSelectedNodeId(first.nodes[0]?.id ?? "");
        setView(first.nodes.length > 0 && first.status === "PUBLISHED" ? "map" : "source");
      }
    })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Không thể tải kho lý thuyết."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
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

  const outline = document?.source_outline ?? [];

  return (
    <main className={styles.page}>
      <div className={styles.shell}>
        <header className={styles.header}>
          <div>
            <span className={styles.eyebrow}>EduMS · Kho tri thức lớp học</span>
            <h1 className={styles.title}>Sơ đồ tư duy &amp; Kho tri thức Toán học</h1>
            <p className={styles.subtitle}>
              Học tập trực quan qua Sơ đồ tư duy tương tác do thầy cô chia sẻ. Tra cứu công thức KaTeX, phương pháp giải từng bước và đối chiếu tài liệu PDF gốc.
            </p>
          </div>
          <Link className={styles.link} href="/student">← Về khu vườn học tập</Link>
        </header>

        {error && <p className={styles.error} role="alert">{error} <button type="button" onClick={() => window.location.reload()}>Thử lại</button></p>}
        {loading && <p role="status">Đang tải tài liệu lớp học…</p>}
        {!loading && !error && list.length === 0 && <p className={styles.notice}>Giáo viên chưa chia sẻ tài liệu lý thuyết với lớp em.</p>}

        <div className={isSidebarCollapsed ? styles.columnsCollapsed : styles.columns}>
          {!isSidebarCollapsed && (
            <aside className={styles.panel}>
              <h2>Tài liệu đã chia sẻ</h2>
              <div className={styles.list}>
                {list.map((item) => (
                  <button
                    className={`${styles.listButton} ${document?.id === item.id ? styles.listButtonActive : ""}`}
                    type="button"
                    key={item.id}
                    onClick={() => void openDocument(item.id)}
                    aria-current={document?.id === item.id ? "true" : undefined}
                  >
                    <strong>{item.title}</strong>
                    <span className={styles.small}>
                      {item.page_count} trang · {item.status === "PUBLISHED" ? "Sơ đồ tư duy" : "Tài liệu PDF"}
                    </span>
                  </button>
                ))}
              </div>
            </aside>
          )}

          <section className={styles.panel}>
            {!document ? (
              <p>Chọn một tài liệu bên trái để bắt đầu học.</p>
            ) : (
              <>
                <div className={styles.documentHeaderBar}>
                  <div>
                    <h2>{document.title}</h2>
                    <div className={styles.badges}>
                      {document.status === "PUBLISHED" && <span className={styles.badgeSuccess}>🌿 Sơ đồ tư duy đã duyệt</span>}
                      {document.source_available && <span className={styles.badgeInfo}>📄 PDF gốc</span>}
                      <span className={styles.badgeMuted}>{document.page_count} trang</span>
                    </div>
                  </div>

                  <button
                    type="button"
                    className={styles.sidebarToggleBtn}
                    onClick={() => setIsSidebarCollapsed((prev) => !prev)}
                    title={isSidebarCollapsed ? "Hiện danh sách tài liệu bên trái" : "Thu gọn danh sách để mở rộng 100% không gian học"}
                  >
                    {isSidebarCollapsed ? "▶ Hiện danh sách tài liệu" : "◀ Thu gọn danh sách"}
                  </button>
                </div>

                <div className={styles.studyToolbar}>
                  {document.status === "PUBLISHED" && document.nodes.length > 0 && (
                    <button
                      type="button"
                      className={view === "map" ? styles.studyTabActive : styles.studyTab}
                      onClick={() => setView("map")}
                    >
                      🧠 Sơ đồ tư duy tương tác
                    </button>
                  )}
                  {document.status === "PUBLISHED" && (
                    <button
                      type="button"
                      className={view === "notebook" ? styles.studyTabActive : styles.studyTab}
                      onClick={() => setView("notebook")}
                    >
                      📖 Sổ tay bài học &amp; Dạng toán
                    </button>
                  )}
                  {document.source_available && (
                    <button
                      type="button"
                      className={view === "source" ? styles.studyTabActive : styles.studyTab}
                      onClick={() => setView("source")}
                    >
                      📄 Tài liệu PDF gốc
                    </button>
                  )}
                </div>

                {view === "map" && document.status === "PUBLISHED" && document.nodes.length > 0 && (
                  <TheoryMapView
                    key={document.id}
                    nodes={document.nodes}
                    selectedNodeId={selectedNodeId}
                    onSelectNode={setSelectedNodeId}
                    sourceUrl={document.source_available ? `/api/student/theory/${document.id}/source` : undefined}
                  />
                )}

                {view === "notebook" && (
                  <TheoryNotebookView
                    documentId={document.id}
                    role="student"
                  />
                )}

                {view === "source" && document.source_available && (
                  <>
                    {outline.length > 0 && (
                      <div className={styles.studyOutline} aria-label="Mục lục chủ đề">
                        {outline.map((node, index) => (
                          <button key={`${node.source_page}:${index}`} type="button" onClick={() => setPage(node.source_page)}>
                            {node.title} <small>{node.kind === "CHAPTER" ? "Chủ đề" : "Dạng bài"} · trang {node.source_page}</small>
                          </button>
                        ))}
                      </div>
                    )}
                    <div className={styles.pageControls}>
                      <button type="button" disabled={page <= 1} onClick={() => setPage(page - 1)}>← Trang trước</button>
                      <label>
                        Đến trang{" "}
                        <input
                          type="number"
                          min={1}
                          max={document.page_count}
                          value={page}
                          onChange={(event) => setPage(Math.max(1, Math.min(document.page_count, Number(event.target.value) || 1)))}
                        />
                      </label>
                      <button type="button" disabled={page >= document.page_count} onClick={() => setPage(page + 1)}>Trang sau →</button>
                    </div>
                    <TheorySourceViewer
                      key={document.id}
                      url={`/api/student/theory/${document.id}/source`}
                      title={document.title}
                      pageCount={document.page_count}
                      page={page}
                    />
                  </>
                )}
              </>
            )}
          </section>
        </div>
      </div>
    </main>
  );
}
