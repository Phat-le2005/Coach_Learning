"use client";

import { useEffect, useRef, useState } from "react";
import type { PaperOcrRead } from "@/lib/api/client";
import { generateUuid } from "../utils/ink-math";
import { CORRECTION_KEYS, insertCorrectionKey } from "../utils/ocr-correction";
import { buildPaperOcrStepContent, type ConfirmedPaperStepContent } from "../utils/paper-ocr-step";
import { OcrMathPreview } from "./OcrMathPreview";
import styles from "../MathWorkspace.module.css";

type Row = PaperOcrRead["suggestions"][number] & {
  actionId: string;
  status: "pending" | "saved" | "skipped";
  error: string | null;
};

const KIND_LABEL = { FORMULA: "Công thức", TEXT: "Diễn giải", TABLE: "Bảng / sơ đồ" } as const;
const EXTRA_MATH_KEYS = [
  { label: "∞", insert: String.raw`\infty `, description: "Chèn vô cực" },
  { label: "≤", insert: String.raw`\le `, description: "Chèn nhỏ hơn hoặc bằng" },
  { label: "≥", insert: String.raw`\ge `, description: "Chèn lớn hơn hoặc bằng" },
  { label: "≠", insert: String.raw`\ne `, description: "Chèn khác" },
  { label: "f′", insert: "'", description: "Chèn dấu phẩy đạo hàm" },
  { label: "LaTeX a/b", insert: String.raw`\frac{□}{□}`, description: "Chèn phân số LaTeX" },
  { label: "LaTeX √", insert: String.raw`\sqrt{□}`, description: "Chèn căn bậc hai LaTeX" },
] as const;

interface Props {
  result: PaperOcrRead;
  onConfirmStep: (content: ConfirmedPaperStepContent, actionId: string) => Promise<void>;
  onStepSaved: () => void;
  activeStepIndex?: number | null;
  onSelectStepIndex?: (index: number) => void;
}

export function PaperOcrReview({ result, onConfirmStep, onStepSaved, activeStepIndex, onSelectStepIndex }: Props) {
  const [rows, setRows] = useState<Row[]>(() => result.suggestions.map((suggestion) => ({
    ...suggestion, actionId: generateUuid(), status: "pending", error: null,
  })));
  const [savingIndex, setSavingIndex] = useState<number | null>(null);
  const [internalActiveIndex, setInternalActiveIndex] = useState(0);
  const activeEditorIndex = typeof activeStepIndex === "number" ? activeStepIndex : internalActiveIndex;

  useEffect(() => {
    if (typeof activeStepIndex === "number" && activeStepIndex >= 0 && rows[activeStepIndex]) {
      const el = document.getElementById(`paper-ocr-panel-${rows[activeStepIndex]?.actionId}`);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  }, [activeStepIndex, rows]);
  const [sourceOpen, setSourceOpen] = useState(false);
  const [keypadOpen, setKeypadOpen] = useState(false);
  const textareas = useRef<Record<string, HTMLTextAreaElement | null>>({});
  const savedCount = rows.filter((row) => row.status === "saved").length;

  const changeRow = (index: number, changes: Partial<Row>) => {
    setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, ...changes } : row));
  };

  const selectRow = (index: number) => {
    setInternalActiveIndex(index);
    onSelectStepIndex?.(index);
    setSourceOpen(false);
    setKeypadOpen(false);
  };

  const confirm = async (index: number) => {
    const row = rows[index];
    if (!row || savingIndex !== null || row.status !== "pending") return;
    if (rows.slice(0, index).some((earlier) => earlier.status === "pending")) return;
    const content = buildPaperOcrStepContent(row.kind, row.text);
    if (!content) {
      changeRow(index, { error: "Công thức chưa hiển thị hợp lệ. Sửa ký hiệu và xem bản xem trước rồi xác nhận." });
      return;
    }
    setSavingIndex(index);
    changeRow(index, { error: null });
    try {
      // OCR is untrusted: only this explicit student action creates a solution step.
      await onConfirmStep(content, row.actionId);
      changeRow(index, { status: "saved" });
      onStepSaved();
      if (index + 1 < rows.length) selectRow(index + 1);
    } catch {
      changeRow(index, { error: "Chưa lưu được bước này. Nội dung vẫn còn để em thử lại." });
    } finally {
      setSavingIndex(null);
    }
  };

  const insertKey = (index: number, template: string) => {
    const row = rows[index];
    if (!row) return;
    const field = textareas.current[row.actionId];
    const result = insertCorrectionKey(row.text, field?.selectionStart ?? row.text.length,
      field?.selectionEnd ?? row.text.length, template);
    changeRow(index, { text: result.value, error: null });
    window.requestAnimationFrame(() => {
      field?.focus();
      field?.setSelectionRange(result.selectionStart, result.selectionEnd);
    });
  };

  return <section className={styles.paperOcrReview} aria-labelledby="paper-ocr-review-title">
    <div className={styles.paperOcrReviewHeading}>
      <h3 id="paper-ocr-review-title">Kiểm tra bài chụp</h3>
      <span role="status">{savedCount}/{rows.length} bước đã lưu</span>
    </div>
    <p>Chọn từng bước, so với ảnh gốc rồi xác nhận. Công thức dưới đây được hiển thị như khi lưu.</p>
    {savedCount > 0 && rows.every((row) => row.status !== "pending") ?
      <p>Đã duyệt xong. Bấm “Nộp bài giải” ở khung đề bài, sau đó nhận xét từng bước.</p> : null}
    {rows.length === 0 ? <p>Chưa nhận diện được bước nào. Hãy chụp lại rõ hơn hoặc nhập bước ở ô bên dưới.</p> : null}
    {rows.map((row, index) => {
      const earlierPending = rows.slice(0, index).some((earlier) => earlier.status === "pending");
      const content = buildPaperOcrStepContent(row.kind, row.text);
      const active = activeEditorIndex === index;
      const showSource = row.status === "pending" && (row.kind !== "FORMULA" || sourceOpen || !content?.latex);
      const status = row.status === "saved" ? "Đã lưu" : row.status === "skipped" ? "Đã bỏ qua"
        : row.uncertain ? "Cần kiểm tra kỹ" : "Chờ xác nhận";
      return <div className={`${styles.paperOcrRow} ${active ? styles.paperOcrRowActive : ""}`} key={row.actionId}>
        <button type="button" className={styles.paperOcrRowToggle} onClick={() => selectRow(index)}
          aria-expanded={active} aria-controls={`paper-ocr-panel-${row.actionId}`}>
          <span className={styles.paperOcrRowTitle}>Bước {index + 1} <small>Trang {row.page_number} · {KIND_LABEL[row.kind]}</small>{row.box_2d ? <span className={styles.paperOcrBboxBadge} title="Tọa độ nhận diện trên trang">📍 Có vùng ảnh</span> : null}</span>
          <span className={styles.paperOcrRowStatus}>{status}</span>
          {!active ? <span className={styles.paperOcrRowSummary}>
            {row.kind === "FORMULA" && content?.latex ? <OcrMathPreview latex={content.latex} />
              : <span>{row.text.trim().split("\n").slice(0, 2).join(" · ").slice(0, 160) || "Chưa có nội dung"}</span>}
          </span> : null}
        </button>
        {active ? <div className={styles.paperOcrEditor} id={`paper-ocr-panel-${row.actionId}`}>
          {row.status === "pending" ? <label className={styles.paperOcrKindLabel}>
            Loại nội dung
            <select value={row.kind} disabled={savingIndex !== null}
              onChange={(event) => {
                changeRow(index, { kind: event.target.value as Row["kind"], error: null });
                setSourceOpen(false);
                setKeypadOpen(false);
              }}>
              <option value="FORMULA">Công thức toán</option>
              <option value="TEXT">Diễn giải</option>
              <option value="TABLE">Bảng / sơ đồ</option>
            </select>
          </label> : null}
          {row.kind === "FORMULA" ? <div className={styles.paperFormulaSurface} aria-live="polite">
            <span className={styles.paperFormulaCaption}>Công thức của bước này</span>
            <div className={styles.paperFormulaDisplay}>
              {content?.latex ? <OcrMathPreview latex={content.latex} />
                : <span className={styles.previewError}>{row.text.trim()
                  ? "Công thức chưa hiển thị được. Sửa ký hiệu hoặc điền ô □ còn trống."
                  : "Chưa có công thức."}</span>}
            </div>
            {row.status === "pending" && content?.latex && !sourceOpen ? <button type="button"
              className={styles.paperOcrEditTrigger} onClick={() => setSourceOpen(true)}>
              Sửa ký hiệu
            </button> : null}
          </div> : row.status !== "pending" ? <pre className={styles.paperOcrTextPreview}>{row.text}</pre> : null}
          {showSource ? <div className={styles.paperOcrSourceEditor}>
            <label htmlFor={`paper-ocr-edit-${row.actionId}`}>
              {row.kind === "FORMULA" ? "Sửa công thức (có thể gõ y=x^2+2 hoặc LaTeX)" : "Sửa nội dung"}
            </label>
            <textarea aria-label={`Sửa bước gợi ý ${index + 1}`} rows={row.kind === "TABLE" ? 5 : row.kind === "FORMULA" ? 2 : 3}
              id={`paper-ocr-edit-${row.actionId}`}
              ref={(element) => { textareas.current[row.actionId] = element; }}
              maxLength={row.kind === "FORMULA" ? 1000 : 4000} value={row.text}
              disabled={savingIndex !== null}
              onChange={(event) => changeRow(index, { text: event.target.value, error: null })} />
            {row.kind === "FORMULA" ? <>
              <div className={styles.paperOcrEditTools}>
                <button type="button" aria-expanded={keypadOpen} aria-controls={`paper-keypad-${row.actionId}`}
                  onClick={() => setKeypadOpen((current) => !current)} disabled={savingIndex !== null}>
                  {keypadOpen ? "Ẩn bàn phím toán" : "Mở bàn phím toán"}
                </button>
                <button type="button" onClick={() => {
                  changeRow(index, { text: "", error: null });
                  window.requestAnimationFrame(() => textareas.current[row.actionId]?.focus());
                }} disabled={!row.text || savingIndex !== null}>Xóa gợi ý</button>
              </div>
              {keypadOpen ? <div id={`paper-keypad-${row.actionId}`} className={styles.ocrCorrectionKeys}
                role="group" aria-label={`Bàn phím toán sửa bước ${index + 1}`}>
                {[...CORRECTION_KEYS, ...EXTRA_MATH_KEYS].map((key) => <button type="button" key={key.label}
                  className={styles.ocrCorrectionKey} title={key.description} aria-label={key.description}
                  onClick={() => insertKey(index, key.insert)} disabled={savingIndex !== null}>{key.label}</button>)}
              </div> : null}
            </> : null}
          </div> : null}
          {earlierPending && row.status === "pending" ? <p className={styles.paperOcrOrderHint}>
            Xác nhận hoặc bỏ qua các bước phía trên trước để giữ đúng thứ tự bài làm.
          </p> : null}
          {row.error ? <p role="alert" className={styles.paperError}>{row.error}</p> : null}
          {row.status !== "saved" ? <div className={styles.paperOcrActions}>
            <button type="button" onClick={() => {
              const unskip = row.status === "skipped";
              changeRow(index, { status: unskip ? "pending" : "skipped" });
              if (!unskip && index + 1 < rows.length) selectRow(index + 1);
            }} disabled={savingIndex !== null ||
              (row.status === "skipped" && rows.slice(index + 1).some((later) => later.status === "saved"))}>
              {row.status === "skipped" ? "Xem lại bước" : "Bỏ qua"}
            </button>
            {row.status === "pending" ? <button type="button" onClick={() => void confirm(index)}
              disabled={!content || earlierPending || savingIndex !== null}>
              {savingIndex === index ? "Đang lưu..." : "Xác nhận bước này"}
            </button> : null}
          </div> : null}
        </div> : null}
      </div>;
    })}
  </section>;
}
