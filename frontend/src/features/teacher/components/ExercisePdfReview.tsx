"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowLeft, CheckCircle2, ExternalLink, FileCheck2, Pencil, RefreshCw, Save, Send } from "lucide-react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import type { TeacherMaterial } from "../api";
import { teacherPdfApi, type PdfReviewDecision, type TeacherPdfImport } from "../pdf-api";
import styles from "../TeacherDashboard.module.css";
import reviewStyles from "./ExercisePdfReview.module.css";
import { MATERIAL_DIFFICULTY_LABELS, MATERIAL_DIFFICULTY_LEVELS } from "../material-difficulty";
import { VisualMathEditor } from "./VisualMathEditor";

export const PDF_IMPORT_STATUS: Record<TeacherPdfImport["status"], string> = {
  QUEUED: "Đang chờ OCR", PROCESSING: "Đang xử lý OCR", NEEDS_REVIEW: "Chờ giáo viên duyệt", FAILED: "Cần thử lại", SUBMITTED: "Đã lưu vào kho",
};

function warningLabel(warning: string): string {
  if (warning === "INCOMPLETE") return "Vùng nguồn chưa được nhận dạng đầy đủ.";
  if (warning === "EMPTY_QUESTION") return "Chưa nhận dạng được nội dung câu hỏi.";
  if (/LATEX|MATH|FORMULA/.test(warning)) return "Có công thức hoặc ký hiệu toán cần đối chiếu với PDF.";
  if (/VISUAL|BOUNDARY|TABLE/.test(warning)) return "Cần kiểm tra hình, bảng hoặc ranh giới câu hỏi.";
  return "Một phần nội dung OCR chưa rõ, cần đối chiếu ảnh nguồn.";
}

export function ExercisePdfReview({ jobId, onClose, onSubmitted, onOpenRevision }: {
  jobId: string; onClose: () => void; onSubmitted: (material: TeacherMaterial) => void; onOpenRevision: (jobId: string) => void;
}) {
  const [job, setJob] = useState<TeacherPdfImport | null>(null);
  const [title, setTitle] = useState("");
  const [decisions, setDecisions] = useState<Record<string, PdfReviewDecision>>({});
  const [filter, setFilter] = useState("all");
  const [difficultyFilter, setDifficultyFilter] = useState("all");
  const [editingQuestionId, setEditingQuestionId] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [dirty, setDirty] = useState(false);
  const [retryCount, setRetryCount] = useState(0);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let initialized = false;
    setJob(null); setError(""); setNotice(""); setDecisions({}); setDirty(false); setPage(0);
    async function load() {
      try {
        const next = await teacherPdfApi.get(jobId);
        if (!active) return;
        setJob(next); setError("");
        if (!initialized && ["NEEDS_REVIEW", "SUBMITTED"].includes(next.status)) {
          initialized = true;
          setTitle(next.review?.title ?? next.title);
          const saved = new Map(next.review?.decisions.map((d) => [d.question_id, d]) ?? []);
          setDecisions(Object.fromEntries(next.questions.map((q) => [q.question_id, saved.get(q.question_id) ?? {
            question_id: q.question_id, accepted: false, source_checked: false, content: q.content, answer: q.answer, explanation: q.explanation,
            difficulty_level: q.difficulty_level,
          }])));
        }
        if (["QUEUED", "PROCESSING"].includes(next.status)) timer = setTimeout(load, 3000);
        else if (next.status === "FAILED") timer = setTimeout(load, 10000);
      } catch (err) {
        if (!active) return;
        setError(err instanceof Error ? err.message : "Không tải được bản nháp OCR.");
        timer = setTimeout(load, 8000);
      }
    }
    void load();
    return () => { active = false; if (timer) clearTimeout(timer); };
  }, [jobId, retryCount]);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (e: BeforeUnloadEvent) => { e.preventDefault(); };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [dirty]);

  function edit(id: string, changes: Partial<PdfReviewDecision>) {
    setDecisions((current) => ({ ...current, [id]: { ...current[id], ...changes } }));
    setDirty(true); setNotice("");
  }
  const payload = { title: title.trim(), decisions: Object.values(decisions) };
  const selected = Object.values(decisions).filter((d) => d.accepted).length;
  const unclassifiedSelected = Object.values(decisions).filter((d) => d.accepted && !d.difficulty_level).length;

  async function perform(action: "save" | "submit" | "retry" | "close" | "revise") {
    if (busy) return;
    if (action === "close" && (!dirty || job?.status !== "NEEDS_REVIEW")) { onClose(); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      if (action === "retry") {
        await teacherPdfApi.retry(jobId);
        setRetryCount((count) => count + 1);
      } else if (action === "revise") {
        const revision = await teacherPdfApi.revise(jobId);
        onOpenRevision(revision.id);
      } else if (action === "submit") {
        const material = await teacherPdfApi.submit(jobId, payload);
        setDirty(false); onSubmitted(material);
      } else {
        await teacherPdfApi.save(jobId, payload);
        setDirty(false); setNotice("Đã lưu bản nháp duyệt.");
        if (action === "close") onClose();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thực hiện được thao tác.");
      requestAnimationFrame(() => errorRef.current?.focus());
    } finally { setBusy(false); }
  }

  const questions = job?.questions.filter((q) => (filter === "all" || (filter === "suggested" && q.suggested) ||
    (filter === "warnings" && !q.suggested) || (filter === "selected" && decisions[q.question_id]?.accepted) ||
    (filter === "held" && !decisions[q.question_id]?.accepted)) &&
    (difficultyFilter === "all" || (difficultyFilter === "unknown" ? !decisions[q.question_id]?.difficulty_level : decisions[q.question_id]?.difficulty_level === difficultyFilter))) ?? [];
  const pageCount = Math.max(1, Math.ceil(questions.length / 10));
  const currentPage = Math.min(page, pageCount - 1);
  const editable = job?.status === "NEEDS_REVIEW";
  const processing = job?.status === "QUEUED" || job?.status === "PROCESSING";
  const isImage = job?.source_kind === "IMAGE";

  return <section className={`${styles.sectionCard} ${reviewStyles.panel}`} aria-labelledby="pdf-review-title">
    <div className={reviewStyles.header}>
      <button type="button" className={styles.btnSecondary} onClick={() => void perform("close")} disabled={busy}>
        <ArrowLeft size={16} aria-hidden="true" /> {dirty ? "Lưu nháp & quay lại" : "Kho học liệu"}
      </button>
      {job && <a className={styles.btnSecondary} href={teacherPdfApi.sourceUrl(job.id)} target="_blank" rel="noreferrer">
        <ExternalLink size={16} aria-hidden="true" /> {isImage ? "Mở ảnh gốc" : "Mở PDF gốc"}
      </a>}
    </div>
    <div className={reviewStyles.intro}>
      <h3 id="pdf-review-title" className={styles.sectionHeading}>{isImage ? "Duyệt bài tập từ ảnh" : "Duyệt bài tập từ PDF"}</h3>
      <p className={styles.sectionSubheading}>{job?.original_file_name ?? "Đang tải bản nháp…"}</p>
      {job?.revision_of && <p className={reviewStyles.editHint}>Bản chỉnh sửa sẽ được lưu thành tài liệu mới. Các bài đã giao từ bản cũ được giữ nguyên.</p>}
      <ol className={reviewStyles.steps} aria-label="Các bước nhập PDF">
        <li>{isImage ? "Tải ảnh" : "Tải PDF"}</li><li aria-current={processing ? "step" : undefined}>Xử lý OCR</li><li aria-current={editable ? "step" : undefined}>Duyệt câu hỏi</li><li aria-current={job?.status === "SUBMITTED" ? "step" : undefined}>Lưu vào kho</li>
      </ol>
    </div>
    {error && <div ref={errorRef} tabIndex={-1} className={styles.formAlert} role="alert">{error}</div>}
    {notice && <p className={styles.formSuccess} role="status">{notice}</p>}
    {!job && !error && <p className={reviewStyles.state} role="status">Đang tải thông tin OCR…</p>}
    {processing && <div className={reviewStyles.state} role="status" aria-live="polite">
      <RefreshCw size={28} aria-hidden="true" />
      <h4>{job ? PDF_IMPORT_STATUS[job.status] : ""}</h4>
      <p>Đã xử lý {job?.progress.processed_pages ?? 0}/{job?.progress.selected_pages ?? "…"} {isImage ? "ảnh" : "trang"}. {!isImage && "PDF nhiều trang có thể mất nhiều thời gian."}</p>
      <p>Bạn có thể quay lại kho học liệu và mở bản nháp này sau.</p>
      <details><summary>Tiến độ không thay đổi sau khi máy chủ khởi động lại?</summary>
        <p>Thử tiếp tục từ dữ liệu đã xử lý. Nếu OCR vẫn đang chạy, hệ thống sẽ giữ nguyên tác vụ hiện tại.</p>
        <button className={styles.btnSecondary} disabled={busy} onClick={() => void perform("retry")}>Tiếp tục xử lý</button>
      </details>
    </div>}
    {job?.status === "FAILED" && <div className={reviewStyles.state}>
      <h4>Chưa hoàn tất OCR</h4><p>{job.error}</p>
      <button className={styles.btnPrimary} disabled={busy} onClick={() => void perform("retry")}><RefreshCw size={16} aria-hidden="true" /> Thử lại OCR</button>
    </div>}
    {job?.status === "SUBMITTED" && <div className={reviewStyles.state}>
      <CheckCircle2 size={32} aria-hidden="true" /><h4>Tài liệu đã được lưu vào kho học liệu</h4>
      <p>Có thể sửa đề bài, đáp án, lời giải và bổ sung mức độ trong một bản chỉnh sửa mới.</p>
      <button type="button" className={styles.btnPrimary} disabled={busy} onClick={() => void perform("revise")}><Pencil size={16} aria-hidden="true" /> Chỉnh sửa &amp; phân loại câu hỏi</button>
      <button className={styles.btnPrimary} onClick={onClose}>Về kho học liệu</button>
    </div>}
    {(editable || job?.status === "SUBMITTED") && <>
      <div className={reviewStyles.toolbar}>
        <label className={styles.formGroup} htmlFor="pdf-reviewed-title"><span className={styles.formLabel}>Tên tài liệu sau khi duyệt</span>
          <input id="pdf-reviewed-title" className={styles.formInput} value={title} maxLength={255} disabled={busy || !editable} onChange={(e) => { setTitle(e.target.value); setDirty(true); }} />
        </label>
        <p className={reviewStyles.summary}><strong>{selected}</strong> câu giữ lại · {job.questions.length - selected} câu để lại</p>
        <p className={styles.sectionSubheading}>Đối chiếu nội dung, đáp án và hình minh họa với {isImage ? "ảnh" : "PDF"} gốc, sau đó tích chọn từng câu đạt yêu cầu. Các câu chưa chọn sẽ không được đưa vào tài liệu.</p>
        {!!job.progress.failed_regions && <p role="status" className={styles.formAlert}>Có {job.progress.failed_regions} vùng OCR chưa hoàn tất. Hãy kiểm tra {isImage ? "ảnh" : "PDF"} gốc trước khi giữ lại câu liên quan.</p>}
        <label className={reviewStyles.filter}>Hiển thị
          <select className={styles.formSelect} value={filter} onChange={(e) => { setFilter(e.target.value); setPage(0); }}>
            <option value="all">Tất cả ({job.questions.length})</option>
            <option value="suggested">Không có cảnh báo OCR ({job.questions.filter((q) => q.suggested).length})</option>
            <option value="warnings">Cần kiểm tra ({job.questions.filter((q) => !q.suggested).length})</option>
            <option value="selected">Đã chọn duyệt ({selected})</option>
            <option value="held">Câu để lại ({job.questions.length - selected})</option>
          </select>
        </label>
        <label className={reviewStyles.filter}>Lọc theo mức độ
          <select className={styles.formSelect} value={difficultyFilter} onChange={(e) => { setDifficultyFilter(e.target.value); setPage(0); }}>
            <option value="all">Tất cả mức độ</option>
            <option value="unknown">Chưa phân loại</option>
            {MATERIAL_DIFFICULTY_LEVELS.map((level) => <option key={level} value={level}>{MATERIAL_DIFFICULTY_LABELS[level]}</option>)}
          </select>
        </label>
      </div>
      {!job.questions.length && <div className={reviewStyles.state}>
        <h4>Chưa tách được câu hỏi từ {isImage ? "ảnh" : "PDF"}</h4><p>{isImage ? "Kiểm tra độ rõ của ảnh hoặc thử lại OCR." : "Kiểm tra nhãn Câu/Bài trong PDF gốc hoặc thử lại OCR."} Chưa thể lưu một tài liệu trống.</p>
        <button className={styles.btnSecondary} onClick={() => void perform("retry")} disabled={busy}>Thử lại OCR</button>
      </div>}
      <div className={reviewStyles.questions}>
        {questions.slice(currentPage * 10, (currentPage + 1) * 10).map((q) => {
          const decision = decisions[q.question_id];
          if (!decision) return null;
          const inputId = `pdf-question-${q.number}`;
          const editing = editingQuestionId === q.question_id;
          const modified = decision.content !== q.content || decision.answer !== q.answer || decision.explanation !== q.explanation;
          return <article key={q.question_id} className={`${reviewStyles.question} ${decision.accepted ? reviewStyles.accepted : ""}`}>
            <div className={reviewStyles.questionTop}>
              <h4>Câu {q.source_number ?? q.number} <span className={reviewStyles.muted}>· Mục {q.number}{q.pages.length ? ` · Trang ${q.pages.join(", ")}` : ""}</span></h4>
              <div className={reviewStyles.questionActions}>
                <span className={reviewStyles.status}>{q.suggested ? "Không có cảnh báo OCR" : "Cần kiểm tra nguồn"}</span>
                {modified && <span className={reviewStyles.status}>Đã chỉnh sửa</span>}
                {editable && <button type="button" className={styles.btnSecondarySmall} disabled={busy}
                  aria-expanded={editing} aria-controls={`${inputId}-editor`}
                  onClick={() => {
                    setEditingQuestionId(editing ? null : q.question_id);
                    if (!editing) requestAnimationFrame(() => document.getElementById(inputId)?.focus());
                  }}><Pencil size={14} aria-hidden="true" /> {editing ? "Đóng chỉnh sửa" : "Chỉnh sửa câu hỏi"}</button>}
              </div>
            </div>
            {!q.suggested && <details className={reviewStyles.warnings}><summary>Cảnh báo cần đối chiếu</summary><ul>{Array.from(new Set(q.warnings.map(warningLabel))).map((w) => <li key={w}>{w}</li>)}</ul></details>}
            <div className={reviewStyles.preview}><MathRenderer content={decision.content} /></div>
            {q.visual_assets.map((index) => <img key={index} src={teacherPdfApi.assetUrl(jobId, index)} alt={`Hình minh họa câu ${q.source_number ?? q.number}`} loading="lazy" className={reviewStyles.sourceImage} />)}
            {editing && <div id={`${inputId}-editor`} className={reviewStyles.editPanel} role="region" aria-label={`Chỉnh sửa câu ${q.source_number ?? q.number}`}>
              <p className={reviewStyles.editHint}>Sửa chữ trực tiếp; bấm vào công thức để sửa hoặc chọn “Chèn công thức” để mở bảng ký hiệu toán. Hệ thống tự lưu mã công thức, giáo viên không cần biết LaTeX.</p>
              <div className={reviewStyles.editGrid}>
                <div className={reviewStyles.editor}>
                  <VisualMathEditor id={inputId} label="Đề bài" value={decision.content} disabled={busy} maxLength={200000}
                    onChange={(content) => edit(q.question_id, { content, accepted: false, source_checked: false })} />
                  <VisualMathEditor id={`${inputId}-answer`} label="Đáp án" value={decision.answer} disabled={busy} maxLength={100000}
                    onChange={(answer) => edit(q.question_id, { answer, accepted: false, source_checked: false })} />
                  <VisualMathEditor id={`${inputId}-solution`} label="Lời giải" value={decision.explanation} disabled={busy} maxLength={200000}
                    onChange={(explanation) => edit(q.question_id, { explanation, accepted: false, source_checked: false })} />
                </div>
                <div className={reviewStyles.livePreview} aria-label="Bản xem trước sau chỉnh sửa">
                  <h5>Xem trước sau chỉnh sửa</h5>
                  <strong>Đề bài</strong><MathRenderer content={decision.content || "Chưa nhập đề bài."} />
                  <strong>Đáp án</strong><MathRenderer content={decision.answer || "Chưa nhập đáp án."} />
                  <strong>Lời giải</strong><MathRenderer content={decision.explanation || "Chưa nhập lời giải."} />
                </div>
              </div>
              <p className={reviewStyles.editHint}>Sau khi sửa nội dung, hãy đối chiếu và tích duyệt lại câu này. Chọn Lưu nháp hoặc Lưu vào kho để ghi lại thay đổi.</p>
              <button type="button" className={styles.btnSecondarySmall} onClick={() => setEditingQuestionId(null)}>Xong chỉnh sửa</button>
            </div>}
            {(decision.answer || decision.explanation) && <details className={reviewStyles.editor}><summary>Xem đáp án / lời giải</summary>
              {decision.answer && <><strong>Đáp án</strong><MathRenderer content={decision.answer} /></>}
              {decision.explanation && <><strong>Lời giải</strong><MathRenderer content={decision.explanation} /></>}
            </details>}
            <fieldset className={reviewStyles.difficulty} aria-describedby={`${inputId}-difficulty-help`}>
              <legend>Mức độ câu hỏi</legend>
              <div className={reviewStyles.difficultyOptions}>
                {MATERIAL_DIFFICULTY_LEVELS.map((level) => <label key={level} className={decision.difficulty_level === level ? reviewStyles.difficultySelected : ""}>
                  <input type="radio" name={`${inputId}-difficulty`} value={level} checked={decision.difficulty_level === level} disabled={busy || !editable}
                    onChange={() => edit(q.question_id, { difficulty_level: level })} />
                  {MATERIAL_DIFFICULTY_LABELS[level]}
                </label>)}
              </div>
              <p id={`${inputId}-difficulty-help`} className={reviewStyles.editHint}>
                {decision.difficulty_level ? `Đã phân loại: ${MATERIAL_DIFFICULTY_LABELS[decision.difficulty_level]}.` : "Chưa phân loại. Chọn một trong 4 mức trước khi lưu câu được duyệt vào kho."}
              </p>
            </fieldset>
            {!!q.source_assets.length && <details className={reviewStyles.editor}><summary>Ảnh vùng OCR để đối chiếu ({q.source_assets.length})</summary>
              {q.source_assets.map((index) => <a key={index} href={teacherPdfApi.assetUrl(jobId, index)} target="_blank" rel="noreferrer"><img src={teacherPdfApi.assetUrl(jobId, index)} alt={`Vùng nguồn OCR của câu ${q.source_number ?? q.number}`} loading="lazy" className={reviewStyles.sourceImage} /></a>)}
            </details>}
            <label className={reviewStyles.approval}><input type="checkbox" checked={decision.accepted} disabled={busy || !editable || !decision.content.trim()} onChange={(e) => edit(q.question_id, { accepted: e.target.checked, source_checked: e.target.checked })} />
              Tôi đã đối chiếu {isImage ? "ảnh" : "PDF"} gốc và duyệt giữ câu này
            </label>
          </article>;
        })}
        {!!job.questions.length && !questions.length && <p className={reviewStyles.state}>Chưa có câu hỏi trong bộ lọc này.</p>}
      </div>
      {pageCount > 1 && <nav className={reviewStyles.pagination} aria-label="Trang câu hỏi">
        <button className={styles.btnSecondary} onClick={() => setPage(currentPage - 1)} disabled={currentPage === 0}>Trang trước</button>
        <span>Trang {currentPage + 1}/{pageCount}</span>
        <button className={styles.btnSecondary} onClick={() => setPage(currentPage + 1)} disabled={currentPage + 1 === pageCount}>Trang sau</button>
      </nav>}
      {editable && <div className={reviewStyles.footer}>
        <p><FileCheck2 size={18} aria-hidden="true" /> {selected}/{job.questions.length} câu đã duyệt{dirty ? " · Chưa lưu thay đổi" : ""}</p>
        {unclassifiedSelected > 0 && <p role="status">Còn {unclassifiedSelected} câu được duyệt chưa chọn mức độ.</p>}
        <div>
          <button className={styles.btnSecondary} disabled={busy || !title.trim()} onClick={() => void perform("save")}><Save size={16} aria-hidden="true" /> Lưu nháp</button>
          <button className={styles.btnPrimary} disabled={busy || !selected || !!unclassifiedSelected || !title.trim()} onClick={() => void perform("submit")}><Send size={16} aria-hidden="true" /> {busy ? "Đang lưu…" : `Lưu ${selected} câu vào kho`}</button>
        </div>
      </div>}
    </>}
  </section>;
}
