"use client";

import { useEffect, useMemo, useState } from "react";
import { theoryApi, type TheoryNode, type TheoryNotebook } from "./api";
import { groupSourceRegions, resolveNotebookLesson } from "./notebook-selection";
import { TheorySourceViewer } from "./TheorySourceViewer";
import styles from "./TheoryMaps.module.css";

export function TheoryLessonSource({ node, sourceUrl }: {
  node: TheoryNode;
  sourceUrl: string;
}) {
  const [book, setBook] = useState<TheoryNotebook | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [failedImages, setFailedImages] = useState<string[]>([]);
  const [zoomedRegion, setZoomedRegion] = useState<string | null>(null);
  const source = sourceUrl.match(/^\/api\/(teacher|student)\/theory\/([^/]+)\/source$/);
  const role = source?.[1];
  const documentId = source?.[2];

  useEffect(() => {
    let active = true;
    setBook(null); setError(""); setFailedImages([]);
    if (!documentId || (role !== "teacher" && role !== "student")) {
      setError("Không xác định được tài liệu gốc của mục này.");
      return;
    }
    (role === "teacher" ? theoryApi.teacherNotebook(documentId) : theoryApi.studentNotebook(documentId))
      .then((next) => { if (active) setBook(next); })
      .catch((reason) => { if (active) setError(reason instanceof Error ? reason.message : "Không tải được nội dung nguồn."); });
    return () => { active = false; };
  }, [documentId, role, retry]);

  const blocks = useMemo(() => book ? resolveNotebookLesson(book, node) : [], [book, node]);
  const regions = useMemo(() => groupSourceRegions(blocks), [blocks]);

  if (error) return <div className={styles.lessonSourceNotice} role="alert">
    <p>{error}</p>
    <button type="button" className={styles.drawerSecondaryActionBtn} onClick={() => setRetry((value) => value + 1)}>Thử tải lại</button>
  </div>;
  if (!book) return <p role="status">Đang mở nội dung và công thức từ tài liệu gốc…</p>;
  if (regions.length === 0) {
    const fallbackBlock = book.sections.flatMap((s) => s.blocks).find((b) => b.page === node.source_page);
    if (fallbackBlock && role && documentId) {
      const blockUrl = `/api/${role}/theory/${documentId}/notebook/blocks/${fallbackBlock.page}/${fallbackBlock.ordinal}`;
      return (
        <section className={styles.lessonSource} aria-label="Nội dung bài học từ PDF">
          <div className={styles.lessonSourceHeading}>
            <strong>Nội dung từ tài liệu gốc (Trang {node.source_page})</strong>
            <span>Giữ nguyên công thức, bảng và hình</span>
          </div>
          <article className={styles.lessonSourceBlock}>
            <div className={styles.lessonSourceBlockHeader}>
              <span>Trang {fallbackBlock.page} · {fallbackBlock.title}</span>
            </div>
            <img
              src={blockUrl}
              alt={fallbackBlock.title}
              style={{ width: "100%", height: "auto", display: "block", borderRadius: "4px" }}
              loading="lazy"
            />
          </article>
        </section>
      );
    }
    return (
      <div className={styles.lessonSource}>
        <p>Chưa tách được riêng mục này. Trang nguồn được hiển thị bên dưới để em đọc đầy đủ.</p>
        <TheorySourceViewer url={sourceUrl} title={node.title} pageCount={book.page_count} page={node.source_page} />
      </div>
    );
  }

  return <section className={styles.lessonSource} aria-label="Nội dung bài học từ PDF">
    <div className={styles.lessonSourceHeading}>
      <strong>Nội dung từ tài liệu gốc</strong>
      <span>Giữ nguyên công thức, bảng và hình</span>
    </div>
    {regions.map((region) => {
      const first = region[0];
      return <article key={first.id} className={styles.lessonSourceBlock}>
        <div className={styles.lessonSourceBlockHeader}>
          <span>Trang {first.page} · {region.length > 1 ? "Nội dung liên tục" : first.title}</span>
          <button type="button" aria-pressed={zoomedRegion === first.id}
            onClick={() => setZoomedRegion((current) => current === first.id ? null : first.id)}>
            {zoomedRegion === first.id ? "Thu nhỏ" : "Phóng to"}
          </button>
        </div>
        <div className={styles.lessonSourceImageLink}>
          <div className={zoomedRegion === first.id ? styles.lessonSourceZoomed : styles.lessonSourceNatural}>
            {region.map((block) => {
              const imageUrl = `${sourceUrl.replace(/\/source$/, "/notebook/blocks")}/${block.page}/${block.ordinal}`;
              return <div key={block.id}>
                {failedImages.includes(block.id) ? <div className={styles.lessonSourceNotice} role="alert">
                  <p>Không tải được phần nội dung này.</p>
                  <button type="button" className={styles.drawerSecondaryActionBtn}
                    onClick={() => setFailedImages((values) => values.filter((id) => id !== block.id))}>Tải lại ảnh</button>
                </div> : <img className={styles.lessonSourceImage} src={imageUrl} alt={`${block.title}, nguyên bản trang ${block.page}`}
                  loading="eager" onError={() => setFailedImages((values) => [...values, block.id])} />}
              </div>;
            })}
          </div>
        </div>
      </article>;
    })}
  </section>;
}
