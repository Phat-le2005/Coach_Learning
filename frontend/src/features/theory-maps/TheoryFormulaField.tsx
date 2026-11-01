"use client";

import { useRef } from "react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import styles from "./TheoryMaps.module.css";

const keys = [
  { label: "x²", insert: "^2" },
  { label: "Phân số", insert: String.raw`\frac{□}{□}` },
  { label: "Căn", insert: String.raw`\sqrt{□}` },
  { label: "π", insert: String.raw`\pi` },
  { label: "∞", insert: String.raw`\infty` },
  { label: "≤", insert: String.raw`\le` },
  { label: "∫", insert: String.raw`\int` },
] as const;

export function TheoryFormulaField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const trimmed = value.trim();
  const hasPlaceholders = trimmed.includes("□");

  function insert(template: string) {
    const input = inputRef.current;
    const start = input?.selectionStart ?? value.length;
    const end = input?.selectionEnd ?? value.length;
    onChange(value.slice(0, start) + template + value.slice(end));
    window.requestAnimationFrame(() => {
      input?.focus();
      input?.setSelectionRange(start + template.length, start + template.length);
    });
  }

  return (
    <div className={styles.formulaField}>
      <label className={styles.field}>
        {label}
        <textarea
          ref={inputRef}
          className={styles.textarea}
          value={value}
          maxLength={1000}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Gõ công thức như y=x^2 hoặc nhập LaTeX"
        />
      </label>
      <div className={styles.formulaKeys} role="group" aria-label="Chèn ký hiệu toán">
        {keys.map((key) => (
          <button key={key.label} type="button" onClick={() => insert(key.insert)}>
            {key.label}
          </button>
        ))}
      </div>
      <p className={styles.formulaHelp}>
        Có thể gõ công thức quen thuộc như <code>y=x^2</code>. Với phân số hoặc căn, thay từng ô □ bằng biểu thức đúng trong PDF.
      </p>
      {trimmed && (
        <div className={styles.formulaPreview} role="status">
          <strong>Xem trước:</strong>
          {hasPlaceholders ? (
            <span style={{ color: "#854d0e", marginLeft: "6px" }}>
              Chưa hiển thị được. Hãy thay thế các ô vuông □ bằng biểu thức đúng.
            </span>
          ) : (
            <div className={styles.formulaPreviewDisplay}>
              <MathRenderer
                content={trimmed.includes("$$") || trimmed.includes("\\[") ? trimmed : `$$${trimmed}$$`}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
