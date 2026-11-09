"use client";

import { useEffect, useRef, useState } from "react";
import type { MathfieldElement } from "mathlive";
import { ArrowLeft, ArrowRight, ChevronDown, ChevronUp, CornerDownRight, Delete, Redo2, Undo2, Plus } from "lucide-react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import { MATH_SYMBOL_GROUPS, searchMathSymbols, type MathSymbol } from "@/features/teacher/math-symbols";
import "mathlive/fonts.css";
import styles from "./StudentMathEditor.module.css";

const key = (id: string, label: string, latex: string, insert = latex): MathSymbol => ({ id, label, latex, insert });

/** 20 core Grade 12 math symbols students actually need, without clutter. */
const CORE_SYMBOLS: MathSymbol[] = [
  key("core-prime", "Đạo hàm y'", "y'", "#0'"),
  key("core-square", "Bình phương x²", "x^2", "#0^{2}"),
  key("core-power", "Lũy thừa xⁿ", "x^n", "#0^{#?}"),
  key("core-frac", "Phân số a/b", "\\frac{a}{b}", "\\frac{#0}{#?}"),
  key("core-sqrt", "Căn bậc hai √x", "\\sqrt{x}", "\\sqrt{#0}"),
  key("core-nthroot", "Căn bậc n", "\\sqrt[n]{x}", "\\sqrt[#?]{#0}"),
  key("core-iff", "Tương đương (⇔)", "\\Leftrightarrow"),
  key("core-implies", "Suy ra (⇒)", "\\Rightarrow"),
  key("core-cases", "Hoặc (chia trường hợp)", "\\left[\\begin{matrix}a\\\\b\\end{matrix}\\right.", "\\left[\\begin{matrix}#0\\\\#?\\end{matrix}\\right."),
  key("core-system", "Hệ phương trình", "\\begin{cases}a\\\\b\\end{cases}", "\\begin{cases}#0\\\\#?\\end{cases}"),
  key("core-neq", "Khác (≠)", "\\ne"),
  key("core-le", "Nhỏ hơn hoặc bằng (≤)", "\\le"),
  key("core-ge", "Lớn hơn hoặc bằng (≥)", "\\ge"),
  key("core-pm", "Cộng trừ (±)", "\\pm"),
  key("core-in", "Thuộc (∈)", "\\in"),
  key("core-inf", "Vô cực (∞)", "\\infty"),
  key("core-R", "Tập số thực (ℝ)", "\\mathbb{R}"),
  key("core-lim", "Giới hạn lim", "\\lim", "\\lim_{x\\to #?}#0"),
  key("core-int", "Tích phân ∫", "\\int", "\\int_{#?}^{#?} #0\\,\\mathrm{d}x"),
  key("core-pi", "Số Pi (π)", "\\pi"),
];

/**
 * Clean, distraction-free WYSIWYG formula editor for students.
 * - Pinned formula field with large, crisp mathematical display.
 * - 20 essential Grade 12 math symbols at fingertips (no redundant number row).
 * - Optional collapsible drawer for advanced symbols when needed.
 */
export function StudentMathEditor({ value, disabled = false, onChange, testId = "ocr-v2-content" }: {
  value: string; disabled?: boolean; onChange: (latex: string) => void; testId?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const field = useRef<MathfieldElement | null>(null);
  const emitted = useRef<string | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [group, setGroup] = useState(MATH_SYMBOL_GROUPS[0]?.id ?? "calculus");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let active = true;
    void import("mathlive").then(({ MathfieldElement: Field }) => {
      if (!active || !host.current) return;
      Field.fontsDirectory = null; Field.soundsDirectory = null; Field.computeEngine = null;
      const mf = new Field();
      mf.mathVirtualKeyboardPolicy = "manual";
      mf.smartFence = true;
      mf.setAttribute("aria-label", "Sửa công thức của em");
      mf.setAttribute("data-testid", "student-mathfield");
      mf.addEventListener("input", () => {
        const latex = mf.getValue("latex");
        emitted.current = latex;
        onChangeRef.current(latex);
      });
      host.current.replaceChildren(mf);
      field.current = mf;
      mf.setValue(value, { silenceNotifications: true });
      emitted.current = value;
      mf.readOnly = disabled;
      setReady(true);
    }).catch(() => { if (active) setLoadError(true); });
    return () => { active = false; field.current?.remove(); field.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const mf = field.current;
    if (!mf || value === emitted.current) return;
    mf.setValue(value, { silenceNotifications: true });
    emitted.current = value;
  }, [value, ready]);

  useEffect(() => { if (field.current) field.current.readOnly = disabled; }, [disabled, ready]);

  function insert(symbol: MathSymbol) {
    const mf = field.current;
    if (!mf || disabled) return;
    mf.focus();
    mf.insert(symbol.insert, {
      format: "latex",
      selectionMode: symbol.insert.includes("#") ? "placeholder" : "after",
      focus: true,
      feedback: false,
    });
    const latex = mf.getValue("latex");
    emitted.current = latex;
    onChange(latex);
  }

  function command(name: "moveToPreviousChar" | "moveToNextChar" | "moveToNextPlaceholder" | "deleteBackward" | "undo" | "redo") {
    const mf = field.current;
    if (!mf || disabled) return;
    mf.focus();
    mf.executeCommand(name);
    const latex = mf.getValue("latex");
    emitted.current = latex;
    onChange(latex);
  }

  const advancedSymbols = query.trim()
    ? searchMathSymbols(query, "all")
    : MATH_SYMBOL_GROUPS.find(g => g.id === group)?.symbols ?? [];

  return (
    <div className={styles.editor} data-disabled={disabled}>
      {/* 1. HERO FORMULA FIELD */}
      {loadError ? (
        <p className={styles.notice} role="alert">Chưa tải được ô công thức trực quan. Em có thể sửa bằng mã bên dưới.</p>
      ) : (
        <div className={styles.fieldWrap} onClick={() => field.current?.focus()}>
          {!ready && <p className={styles.loading} role="status">Đang mở ô công thức…</p>}
          <div ref={host} className={styles.fieldHost} />
        </div>
      )}

      {/* 2. COMPACT TOOLBAR */}
      <div className={styles.toolbar} role="group" aria-label="Thao tác nhanh">
        <div className={styles.navGroup}>
          <button type="button" title="Sang trái" aria-label="Sang trái" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("moveToPreviousChar")}>
            <ArrowLeft size={14} aria-hidden="true" />
          </button>
          <button type="button" title="Sang phải" aria-label="Sang phải" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("moveToNextChar")}>
            <ArrowRight size={14} aria-hidden="true" />
          </button>
          <button type="button" className={styles.btnNext} title="Nhảy tới ô nhập tiếp theo (mẫu số, số mũ...)" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("moveToNextPlaceholder")}>
            <CornerDownRight size={13} aria-hidden="true" /> Ô tiếp
          </button>
        </div>
        <div className={styles.editGroup}>
          <button type="button" title="Xóa ký hiệu trước con trỏ" aria-label="Xóa lùi" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("deleteBackward")}>
            <Delete size={14} aria-hidden="true" /> Xóa
          </button>
          <button type="button" title="Hoàn tác (Ctrl+Z)" aria-label="Hoàn tác" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("undo")}>
            <Undo2 size={14} aria-hidden="true" />
          </button>
          <button type="button" title="Làm lại (Ctrl+Y)" aria-label="Làm lại" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("redo")}>
            <Redo2 size={14} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* 3. CORE 20 GRADE-12 MATH SYMBOLS (CLEAN & BEAUTIFUL GRID) */}
      <div className={styles.symbolGrid} role="group" aria-label="Ký hiệu toán hay dùng">
        {CORE_SYMBOLS.map(s => (
          <button
            key={s.id}
            type="button"
            className={styles.symbolBtn}
            title={s.label}
            aria-label={s.label}
            disabled={!ready || disabled}
            onMouseDown={e => e.preventDefault()}
            onClick={() => insert(s)}
          >
            <MathRenderer content={`$${s.latex}$`} inline />
          </button>
        ))}
      </div>

      {/* 4. OPTIONAL ADVANCED SYMBOLS (COLLAPSIBLE) */}
      <div className={styles.moreWrap}>
        <button
          type="button"
          className={styles.moreToggle}
          aria-expanded={moreOpen}
          disabled={disabled}
          onClick={() => setMoreOpen(o => !o)}
        >
          {moreOpen ? <ChevronUp size={14} aria-hidden="true" /> : <Plus size={14} aria-hidden="true" />}
          {moreOpen ? "Thu gọn ký hiệu nâng cao" : "Thêm ký hiệu nâng cao (Lượng giác, Véc-tơ, Hy Lạp…)"}
        </button>

        {moreOpen && (
          <div className={styles.advancedDrawer}>
            <div className={styles.advancedHead}>
              <div className={styles.groups} role="group" aria-label="Chủ đề ký hiệu">
                {MATH_SYMBOL_GROUPS.map(g => (
                  <button key={g.id} type="button" aria-pressed={!query && group === g.id} onClick={() => { setGroup(g.id); setQuery(""); }}>
                    {g.label}
                  </button>
                ))}
              </div>
              <input
                className={styles.search}
                type="search"
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Tìm: góc, tích vô hướng…"
                aria-label="Tìm ký hiệu nâng cao"
              />
            </div>
            <div className={styles.advancedSymbols}>
              {advancedSymbols.map(s => (
                <button
                  key={s.id}
                  type="button"
                  className={styles.advancedSymbolBtn}
                  title={s.label}
                  aria-label={s.label}
                  disabled={!ready || disabled}
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => insert(s)}
                >
                  <MathRenderer content={`$${s.latex}$`} inline />
                  <span className={styles.symbolSubLabel}>{s.label}</span>
                </button>
              ))}
              {!advancedSymbols.length && <p className={styles.emptyNotice} role="status">Không tìm thấy ký hiệu phù hợp.</p>}
            </div>
          </div>
        )}
      </div>

      {/* 5. RAW LATEX ACCORDION (FOR POWER USERS & TESTS) */}
      <details className={styles.latex} open={loadError || undefined} data-testid="ocr-v2-latex-toggle">
        <summary>Mã LaTeX (dành cho em đã quen)</summary>
        <textarea
          rows={2}
          spellCheck={false}
          data-testid={testId}
          aria-label="Mã LaTeX của bản chép"
          value={value}
          disabled={disabled}
          onChange={e => onChange(e.target.value)}
        />
      </details>
    </div>
  );
}
