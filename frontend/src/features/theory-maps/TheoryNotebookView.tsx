"use client";

import { useEffect, useMemo, useState } from "react";
import { theoryApi, type TheoryNotebook, type NotebookBlock } from "./api";
import styles from "./TheoryMaps.module.css";

const kinds: Record<NotebookBlock["kind"], string> = {
  METHOD: "Cách làm",
  STEP: "Bước thực hiện",
  THEORY: "Lý thuyết · công thức",
  NOTE: "Ghi nhớ",
  EXAMPLE: "Ví dụ từ tài liệu",
  CONTINUATION: "Tiếp theo",
};

export function TheoryNotebookView({
  documentId,
  role,
  initialPage,
}: {
  documentId: string;
  role: "student" | "teacher";
  initialPage?: number;
}) {
  const [book, setBook] = useState<TheoryNotebook | null>(null);
  const [sectionIndex, setSectionIndex] = useState(0);
  const [cardIndex, setCardIndex] = useState(0);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [failedImage, setFailedImage] = useState("");
  const [contentsOpen, setContentsOpen] = useState(false);
  useEffect(() => { setContentsOpen(role === "teacher" || window.matchMedia("(min-width: 901px)").matches); }, [role]);
  useEffect(() => {
    let active = true;
    (role === "teacher" ? theoryApi.teacherNotebook(documentId) : theoryApi.studentNotebook(documentId))
      .then((next) => {
        if (active) {
          setBook(next);
          if (initialPage && next.sections.length > 0) {
            const foundSecIdx = next.sections.findIndex((s) =>
              s.blocks.some((b) => b.page === initialPage)
            );
            if (foundSecIdx !== -1) {
              setSectionIndex(foundSecIdx);
              const foundCardIdx = next.sections[foundSecIdx].blocks.findIndex(
                (b) => b.page === initialPage
              );
              setCardIndex(foundCardIdx !== -1 ? foundCardIdx : 0);
              setError("");
              return;
            }
          }
          setSectionIndex(0);
          setCardIndex(0);
          setError("");
        }
      })
      .catch((reason) => {
        if (active) setError(reason instanceof Error ? reason.message : "Không thể mở sổ học.");
      });
    return () => {
      active = false;
    };
  }, [documentId, role, retry, initialPage]);

  // Handle external initialPage change while book is already loaded
  useEffect(() => {
    if (!book || !initialPage) return;
    const foundSecIdx = book.sections.findIndex((s) =>
      s.blocks.some((b) => b.page === initialPage)
    );
    if (foundSecIdx !== -1) {
      setSectionIndex(foundSecIdx);
      const foundCardIdx = book.sections[foundSecIdx].blocks.findIndex(
        (b) => b.page === initialPage
      );
      setCardIndex(foundCardIdx !== -1 ? foundCardIdx : 0);
    }
  }, [book, initialPage]);

  const chapters = useMemo(() => {
    const result: { title: string; first: number; count: number }[] = [];
    book?.sections.forEach((section, index) => {
      const last = result[result.length - 1];
      if (last?.title === section.chapter_title) last.count += 1;
      else result.push({ title: section.chapter_title, first: index, count: 1 });
    });
    return result;
  }, [book]);

  if (error) return <div className={styles.notebookError} role="alert">{error}
    <button type="button" onClick={() => { setError(""); setRetry((value) => value + 1); }}>Thử lại</button></div>;
  if (!book) return <p role="status">Đang sắp xếp sổ học từ PDF gốc…</p>;
  const section = book.sections[sectionIndex];
  const block = section?.blocks[cardIndex];
  if (!section || !block) return <p className={styles.notice}>Tài liệu này chưa tách được thành thẻ học. Hãy xem PDF gốc.</p>;
  const base = role === "teacher" ? "/api/teacher/theory/" : "/api/student/theory/";
  const imageUrl = base + encodeURIComponent(documentId) + "/notebook/blocks/" + block.page + "/" + block.ordinal;

  function chooseSection(index: number) { setSectionIndex(index); setCardIndex(0); if (role === "student" && window.matchMedia("(max-width: 900px)").matches) setContentsOpen(false); }
  function move(delta: number) {
    const nextCard = cardIndex + delta;
    if (nextCard >= 0 && nextCard < section.blocks.length) { setCardIndex(nextCard); return; }
    const nextSection = sectionIndex + delta;
    if (nextSection >= 0 && nextSection < book!.sections.length) {
      setSectionIndex(nextSection);
      setCardIndex(delta > 0 ? 0 : book!.sections[nextSection].blocks.length - 1);
    }
  }

  return <div className={styles.notebook}>
    <details className={styles.notebookIntro} open={role === "teacher" ? true : undefined}>
      <summary>Về sổ tay bài học</summary>
      <p>Chọn chủ đề rồi xem lý thuyết, cách làm và ví dụ theo từng thẻ. Công thức và hình được giữ nguyên từ PDF; số trang giúp em đối chiếu bản gốc.</p>
    </details>
    <div className={styles.notebookLayout}>
      <details className={styles.notebookContents} open={contentsOpen} onToggle={event => setContentsOpen(event.currentTarget.open)}>
      <summary>Chọn chủ đề <span>{section.title}</span></summary>
      <nav className={styles.notebookNav} aria-label="Mục lục sổ học">
        {chapters.map((chapter) => <div key={chapter.first} className={styles.notebookChapter}>
          <button type="button" className={styles.notebookChapterButton} onClick={() => chooseSection(chapter.first)}>
            {chapter.title}
          </button>
          <div className={styles.notebookSectionList}>
            {book.sections.slice(chapter.first, chapter.first + chapter.count).map((item, offset) => {
              const index = chapter.first + offset;
              return <button key={item.id} type="button" aria-current={sectionIndex === index ? "true" : undefined}
                onClick={() => chooseSection(index)}>{item.title}</button>;
            })}
          </div>
        </div>)}
      </nav>
      </details>
      <article className={styles.notebookSheet} aria-live="polite">
        <div className={styles.notebookSheetHeader}>
          <span>{section.chapter_title}</span>
          <h3>{section.title}</h3>
          <p>{kinds[block.kind]} · Thẻ {cardIndex + 1}/{section.blocks.length} · Trang PDF {block.page}</p>
        </div>
        <nav className={styles.notebookTrail} aria-label="Các phần của mục học hiện tại">
          {section.blocks.map((item, index) => <button key={item.id} type="button"
            aria-current={index === cardIndex ? "step" : undefined} onClick={() => setCardIndex(index)}>
            <span>{kinds[item.kind]}</span>{item.kind === "STEP" ? item.title : item.kind === "EXAMPLE" ? item.title : "Trang " + item.page}
          </button>)}
        </nav>        <div className={styles.notebookCard}>
          <div className={styles.notebookCardHeader}>
            <span>{kinds[block.kind]}</span><strong>{block.title}</strong>
          </div>
          {failedImage === imageUrl ? <div className={styles.notebookError} role="alert">
            Không thể tải thẻ học này. Kiểm tra kết nối hoặc phiên đăng nhập rồi thử lại.
            <button type="button" onClick={() => setFailedImage("")}>Tải lại thẻ</button>
          </div> : <a href={imageUrl} target="_blank" rel="noopener noreferrer" aria-label={"Phóng to thẻ học trang " + block.page}>
            <img key={imageUrl} src={imageUrl} alt={"Trích nguyên bản trang " + block.page + ": " + block.title}
              loading="lazy" className={styles.notebookImage} onError={() => setFailedImage(imageUrl)} />
          </a>}
        </div>
        <div className={styles.notebookControls}>
          <button type="button" onClick={() => move(-1)} disabled={sectionIndex === 0 && cardIndex === 0}>← Trước</button>
          <span>{sectionIndex + 1}/{book.sections.length} mục · {book.total_blocks} thẻ học</span>
          <button type="button" onClick={() => move(1)}
            disabled={sectionIndex === book.sections.length - 1 && cardIndex === section.blocks.length - 1}>Tiếp →</button>
        </div>
      </article>
    </div>
  </div>;
}
