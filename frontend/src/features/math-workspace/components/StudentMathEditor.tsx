"use client";

import { useEffect, useRef, useState } from "react";
import type { MathfieldElement } from "mathlive";
import { ArrowLeft, ArrowRight, ChevronDown, ChevronUp, CornerDownRight, Delete, Redo2, Sigma, Undo2 } from "lucide-react";
import { MathRenderer } from "@/components/ui/MathRenderer";
import { MATH_SYMBOL_GROUPS, searchMathSymbols, type MathSymbol } from "@/features/teacher/math-symbols";
import "mathlive/fonts.css";
import styles from "./StudentMathEditor.module.css";

const key = (id: string, label: string, latex: string, insert = latex): MathSymbol => ({ id, label, latex, insert });

/** Symbols students reach for most often in Grade 12 solution steps. */
const STUDENT_FAVORITES: MathSymbol[] = [
  key("fav-prime", "Đạo hàm y'", "y'", "#0'"),
  key("fav-square", "Bình phương", "x^2", "#0^{2}"),
  key("fav-power", "Lũy thừa", "x^n", "#0^{#?}"),
  key("fav-frac", "Phân số", "\\frac{a}{b}", "\\frac{#0}{#?}"),
  key("fav-sqrt", "Căn bậc hai", "\\sqrt{x}", "\\sqrt{#0}"),
  key("fav-iff", "Tương đương", "\\Leftrightarrow"),
  key("fav-implies", "Suy ra", "\\Rightarrow"),
  key("fav-cases", "Hoặc (các trường hợp)", "\\left[\\begin{matrix}a\\\\b\\end{matrix}\\right.", "\\left[\\begin{matrix}#0\\\\#?\\end{matrix}\\right."),
  key("fav-system", "Hệ phương trình", "\\begin{cases}a\\\\b\\end{cases}", "\\begin{cases}#0\\\\#?\\end{cases}"),
  key("fav-neq", "Khác", "\\ne"),
  key("fav-le", "Nhỏ hơn hoặc bằng", "\\le"),
  key("fav-ge", "Lớn hơn hoặc bằng", "\\ge"),
  key("fav-pm", "Cộng trừ", "\\pm"),
  key("fav-in", "Thuộc", "\\in"),
  key("fav-R", "Tập số thực", "\\mathbb{R}"),
  key("fav-inf", "Vô cực", "\\infty"),
  key("fav-interval", "Khoảng", "(a;b)", "\\left(#0;#?\\right)"),
  key("fav-union", "Hợp", "\\cup"),
  key("fav-lim", "Giới hạn", "\\lim_{x\\to a}", "\\lim_{x\\to #?}#0"),
  key("fav-int", "Tích phân", "\\int_a^b", "\\int_{#?}^{#?} #0\\,\\mathrm{d}x"),
  key("fav-text", "Chèn chữ", "\\text{Ta có}", "\\text{#0}"),
];
const NUMBER_KEYS = Array.from("0123456789xyzt+-=()").map(s => key(`num-${s}`, s, s));
const PALETTE_KEY = "edums.studentMathPalette.open";

/**
 * WYSIWYG formula editing for students. The visible field renders mathematics;
 * the stored value remains LaTeX so grading and saving are unchanged.
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
  const [paletteOpen, setPaletteOpen] = useState(true);
  const [group, setGroup] = useState("favorites");
  const [query, setQuery] = useState("");

  useEffect(() => {
    try { const stored = window.localStorage.getItem(PALETTE_KEY); if (stored !== null) setPaletteOpen(stored === "1"); } catch { /* storage optional */ }
  }, []);

  useEffect(() => {
    let active = true;
    void import("mathlive").then(({ MathfieldElement: Field }) => {
      if (!active || !host.current) return;
      // Fonts are bundled by Next via the CSS import. No CDN or cloud service.
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
    // The field is created once; value/disabled are synchronized below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // External changes (other step selected, LaTeX edited) must not reset typing.
  useEffect(() => {
    const mf = field.current;
    if (!mf || value === emitted.current) return;
    mf.setValue(value, { silenceNotifications: true });
    emitted.current = value;
  }, [value, ready]);

  useEffect(() => { if (field.current) field.current.readOnly = disabled; }, [disabled, ready]);

  function togglePalette() {
    setPaletteOpen(open => {
      try { window.localStorage.setItem(PALETTE_KEY, open ? "0" : "1"); } catch { /* storage optional */ }
      return !open;
    });
  }
  function insert(symbol: MathSymbol) {
    const mf = field.current;
    if (!mf || disabled) return;
    mf.focus();
    mf.insert(symbol.insert, { format: "latex", selectionMode: symbol.insert.includes("#") ? "placeholder" : "after", focus: true, feedback: false });
    const latex = mf.getValue("latex");
    emitted.current = latex;
    onChange(latex);
  }
  function command(name: "moveToPreviousChar" | "moveToNextChar" | "moveToNextPlaceholder" | "deleteBackward" | "undo" | "redo") {
    const mf = field.current;
    if (!mf || disabled) return;
    mf.focus(); mf.executeCommand(name);
    const latex = mf.getValue("latex");
    emitted.current = latex;
    onChange(latex);
  }

  const symbols = query.trim() ? searchMathSymbols(query, "common")
    : group === "favorites" ? STUDENT_FAVORITES
      : MATH_SYMBOL_GROUPS.find(g => g.id === group)?.symbols ?? [];

  return <div className={styles.editor} data-disabled={disabled}>
    {loadError ? <p className={styles.notice} role="alert">Chưa tải được ô công thức trực quan. Em có thể sửa bằng mã công thức bên dưới.</p>
      : <div className={styles.fieldWrap}>
        {!ready && <p className={styles.loading} role="status">Đang mở ô công thức…</p>}
        <div ref={host} className={styles.fieldHost} />
      </div>}

    <div className={styles.toolbar} role="group" aria-label="Di chuyển và sửa công thức">
      <button type="button" aria-label="Sang trái" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("moveToPreviousChar")}><ArrowLeft size={15} aria-hidden="true" /></button>
      <button type="button" aria-label="Sang phải" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("moveToNextChar")}><ArrowRight size={15} aria-hidden="true" /></button>
      <button type="button" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("moveToNextPlaceholder")}><CornerDownRight size={14} aria-hidden="true" /> Ô tiếp</button>
      <button type="button" aria-label="Xóa ký hiệu trước" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("deleteBackward")}><Delete size={15} aria-hidden="true" /></button>
      <button type="button" aria-label="Hoàn tác" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("undo")}><Undo2 size={15} aria-hidden="true" /></button>
      <button type="button" aria-label="Làm lại" disabled={!ready || disabled} onMouseDown={e => e.preventDefault()} onClick={() => command("redo")}><Redo2 size={15} aria-hidden="true" /></button>
      <span className={styles.spacer} />
      <button type="button" className={styles.paletteToggle} aria-expanded={paletteOpen} aria-controls="student-math-palette" onClick={togglePalette}>
        <Sigma size={15} aria-hidden="true" /> Bộ công thức {paletteOpen ? <ChevronUp size={15} aria-hidden="true" /> : <ChevronDown size={15} aria-hidden="true" />}
      </button>
    </div>

    {paletteOpen && <div id="student-math-palette" className={styles.palette}>
      <div className={styles.numberKeys} role="group" aria-label="Số và biến">
        {NUMBER_KEYS.map(k => <button key={k.id} type="button" aria-label={`Nhập ${k.label}`} disabled={!ready || disabled}
          onMouseDown={e => e.preventDefault()} onClick={() => insert(k)}>{k.label}</button>)}
      </div>
      <div className={styles.paletteHead}>
        <div className={styles.groups} role="group" aria-label="Nhóm ký hiệu">
          <button type="button" aria-pressed={!query && group === "favorites"} onClick={() => { setGroup("favorites"); setQuery(""); }}>Hay dùng</button>
          {MATH_SYMBOL_GROUPS.map(g => <button key={g.id} type="button" aria-pressed={!query && group === g.id} onClick={() => { setGroup(g.id); setQuery(""); }}>{g.label}</button>)}
        </div>
        <input className={styles.search} type="search" value={query} onChange={e => setQuery(e.target.value)} placeholder="Tìm: căn, tích phân, vô cực…" aria-label="Tìm ký hiệu" />
      </div>
      <div className={styles.symbols} role="group" aria-label="Bảng ký hiệu toán">
        {symbols.map(symbol => <button key={symbol.id} type="button" title={symbol.label} aria-label={symbol.label} disabled={!ready || disabled}
          onMouseDown={e => e.preventDefault()} onClick={() => insert(symbol)}>
          <MathRenderer content={`$${symbol.latex}$`} inline /><span>{symbol.label}</span>
        </button>)}
        {!symbols.length && <p role="status">Chưa tìm thấy ký hiệu. Thử tên khác nhé.</p>}
      </div>
    </div>}

    <details className={styles.latex} open={loadError || undefined} data-testid="ocr-v2-latex-toggle">
      <summary>Mã công thức (dành cho em đã quen LaTeX)</summary>
      <textarea rows={3} spellCheck={false} data-testid={testId} aria-label="Mã LaTeX của bản chép" value={value} disabled={disabled}
        onChange={e => onChange(e.target.value)} />
    </details>
  </div>;
}
