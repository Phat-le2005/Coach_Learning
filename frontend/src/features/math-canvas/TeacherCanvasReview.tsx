"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { OcrInkPreview } from "@/features/math-workspace/components/OcrInkPreview";
import { canvasRequest, type CanvasSnapshot } from "./api";
import { parseMathExpression } from "./expression";
import { GraphView } from "./GraphView";
import { describeGraphView } from "./presentation";
import styles from "./MathCanvas.module.css";

export function TeacherCanvasReview() {
  const [rows, setRows] = useState<CanvasSnapshot[]>([]);
  const [selected, setSelected] = useState<CanvasSnapshot | null>(null);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let live = true; setLoading(true); setError(false); setSelected(null);
    canvasRequest<CanvasSnapshot[]>(`teacher/snapshots?offset=${offset}`).then((data) => {
      if (live) { setRows(data); setSelected(data[0] ?? null); }
    }).catch(() => { if (live) { setError(true); setRows([]); } }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [offset, retry]);
  const model = useMemo(() => { try { return selected ? parseMathExpression(selected.expression) : null; } catch { return null; } }, [selected]);
  return <main className={styles.reviewPage}>
    <div className={styles.heading}><div><h1>Math Canvas · Bài khám phá của học sinh</h1><p className={styles.muted}>Công thức, nét viết, tham số và góc nhìn được giữ tại thời điểm lưu.</p></div><Link href="/teacher">Về lớp học</Link></div>
    {loading ? <p role="status">Đang tải bài học…</p> : error ? <div role="alert" className={styles.error}>Không thể tải bài khám phá. <button type="button" onClick={() => setRetry((n) => n + 1)}>Thử lại</button></div>
      : !rows.length ? <p className={styles.card}>Chưa có bản lưu từ học sinh thuộc lớp bạn đang phụ trách.</p> : <div className={styles.reviewGrid}>
        <nav aria-label="Bản lưu Math Canvas">{rows.map((row) => <button key={row.id} type="button" className={`${styles.saved} ${selected?.id === row.id ? styles.selected : ""}`} onClick={() => setSelected(row)}>
          <strong>{row.student_name}</strong><p>{row.expression}</p><small>{new Date(row.created_at).toLocaleString("vi-VN")} · Trang {row.page_index + 1}</small></button>)}</nav>
        {selected && model ? <article className={styles.card}>
          <span className={styles.badge}>{describeGraphView(model, selected.settings)} · Bản lưu bài học</span><h2>{selected.expression}</h2>
          <GraphView key={selected.id} model={model} settings={selected.settings} initialCamera={selected.camera} />
          <p className={styles.muted}>Có thể xoay/zoom để xem. Góc nhìn của học sinh được khôi phục khi đặt lại.</p>
          <p>Tham số: {Object.entries(selected.settings.parameters).map(([k,v]) => `${k}=${v}`).join(", ") || "Không có tham số ký hiệu"}</p>
          <p>s={selected.settings.scale}; v={selected.settings.offset}; h={selected.settings.shift_x}; k={selected.settings.shift_y}; miền ±{selected.settings.domain}</p>
          {selected.source_strokes.length ? <OcrInkPreview strokes={selected.source_strokes} /> : <p className={styles.muted}>Công thức được nhập trực tiếp.</p>}
          {selected.note ? <div className={styles.section}><strong>Ghi chú của học sinh</strong><p>{selected.note}</p></div> : null}
          {selected.explanation ? <div className={styles.explanation}><strong>AI giải thích tại thời điểm lưu · {selected.explanation.provider}</strong><p>{selected.explanation.text}</p></div>
            : <p className={styles.muted}>Bản lưu này chưa kèm giải thích AI.</p>}
        </article> : <p className={styles.error}>Công thức trong bản lưu chưa được hỗ trợ.</p>}
      </div>}
    <div className={styles.row}><button className={styles.button} disabled={loading || offset === 0} onClick={() => setOffset((n) => Math.max(0, n - 20))}>Trang trước</button>
      <span>Trang {Math.floor(offset / 20) + 1}</span><button className={styles.button} disabled={loading || rows.length < 20} onClick={() => setOffset((n) => n + 20)}>Trang sau</button></div>
  </main>;
}
